from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentos.platform.config.config import config
from agentos.platform.logging.setup import setup_logging
from agentos.kernel.scheduler.runtime import CronRuntime
from agentos.kernel.scheduler.tool import CronTool
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.persister import EventPersister
from agentos.kernel.events.router import BusRouter
from agentos.adapters.channels.websocket_channel import WebSocketChannel
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.heartbeat.runtime import HeartbeatRuntime
from agentos.adapters.llm.factory import LLMFactory
from agentos.capabilities.agents.registry import AgentRegistry
from agentos.kernel.runtime.agent_runtime import AgentRuntime
from agentos.kernel.runtime.agent_message_coordinator import AgentMessageCoordinator
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.llm_runtime import LLMRuntime
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.runtime.session_maintenance import SessionMaintenance
from agentos.kernel.runtime.state import SessionStateStore
from agentos.kernel.runtime.title_runtime import TitleRuntime
from agentos.kernel.runtime.tool_runtime import ToolRuntime
from agentos.capabilities.skills.registry import SkillRegistry
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.adapters.plugins import PluginRegistry
from agentos.platform.security.path_policy import PathPolicy
from agentos.platform.config.workspace import (
    ensure_agentos_home,
    ensure_agent_workspace,
    resolve_agentos_home,
)
from agentos.interfaces.http import agents, tools, gateway, skills, workspace, config_api

# Token 认证模块（Jupyter-lab 风格）
from agentos.platform.security.auth import TokenAuthService
from agentos.platform.security.middleware import verify_request
from agentos.interfaces.http.auth import create_auth_router

logger = logging.getLogger(__name__)


@dataclass
class Services:
    repo: Repository
    bus: PublicEventBus
    publisher: EventPublisher
    bus_router: BusRouter
    persister: EventPersister
    agent_runtime: AgentRuntime
    llm_runtime: LLMRuntime
    tool_runtime: ToolRuntime
    agent_message_coordinator: AgentMessageCoordinator
    title_runtime: TitleRuntime
    gateway: Gateway
    ws_channel: WebSocketChannel
    cron_runtime: CronRuntime
    heartbeat_runtime: HeartbeatRuntime
    # Token 认证服务（Jupyter-lab 风格）
    auth_service: TokenAuthService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # 解析 AGENTOS_HOME（默认 ~/.agentos）
    from agentos.platform.config.config import PROJECT_ROOT
    agentos_home = resolve_agentos_home(config)
    await ensure_agentos_home(agentos_home, project_root=PROJECT_ROOT)
    agentos_home_str = str(agentos_home)

    # 数据库路径：优先配置，否则 {agentos_home}/data/agentos.db
    db_path = config.get("system.database_path", "")
    if not db_path:
        db_path = str(agentos_home / "data" / "agentos.db")

    repo = Repository(db_path=db_path)
    await repo.init()

    # 路径安全策略：AGENTOS_HOME 为 GREEN zone
    granted_paths = config.get("system.granted_paths", [])
    path_policy = PathPolicy(workspace=agentos_home, granted_paths=granted_paths)
    app.state.path_policy = path_policy

    # 会话维护：清理过期会话
    maintenance = SessionMaintenance(repo=repo)
    await maintenance.run_maintenance()

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)

    # 事件持久化：独立订阅 PublicEventBus
    persister = EventPersister(bus=bus, repo=repo)

    # 双总线路由器
    bus_router = BusRouter(
        public_bus=bus,
        ttl_seconds=int(config.get("bus.private_bus_ttl", 3600)),
        gc_interval=int(config.get("bus.gc_interval", 60)),
    )

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()

    # 初始化 SkillRegistry
    skills_dir = agentos_home / "skills"
    state_file = agentos_home / "skills_state.json"
    builtin_skills_dir = PROJECT_ROOT / ".agentos" / "skills"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=builtin_skills_dir,
    )
    skill_registry.load_skills(config.data)

    # 初始化 SkillMarketService
    from agentos.capabilities.skills.market_service import SkillMarketService
    market_service = SkillMarketService(
        skills_dir=skills_dir,
        skill_registry=skill_registry,
        config=config.data,
    )

    context_builder = ContextBuilder(
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        agentos_home=agentos_home_str,
    )
    llm_factory = LLMFactory()

    # v1.0: 初始化 AgentRegistry
    agent_config_dir = agentos_home / "agents"
    agent_registry = AgentRegistry(config_dir=agent_config_dir)
    agent_registry.load_from_config(config.data)
    agent_registry.load_from_dir()

    # 为所有已注册 agent 初始化 per-agent workspace 和 workdir
    for agent_cfg in agent_registry.list_all():
        await ensure_agent_workspace(agentos_home_str, agent_cfg.id)

    # 将 agent_registry 注入 ContextBuilder（供多 Agent prompt 使用）
    context_builder.agent_registry = agent_registry

    # v0.6: 初始化记忆系统
    memory_manager = None
    memory_enabled = config.get("memory.enabled", False)

    if memory_enabled:
        from agentos.capabilities.memory.config import MemoryConfig
        from agentos.capabilities.memory.manager import MemoryManager
        from agentos.capabilities.memory.tools import MemorySearchTool

        mem_config = MemoryConfig.from_dict(config.data)
        mem_db_path = repo.db_path.parent / "memory_index.db"
        memory_manager = MemoryManager(
            workspace_dir=agentos_home_str,
            config=mem_config,
            db_path=mem_db_path,
            llm_factory=llm_factory,
        )
        await memory_manager.sync_index()

        # 为已有的 chunks 生成嵌入向量
        await memory_manager.embed_pending_chunks()

        if mem_config.search.enabled:
            tool_registry.register(MemorySearchTool(memory_manager))

        logger.info("Memory system enabled (home=%s)", agentos_home_str)

    # Runtime 使用 BusRouter（管理者模式）
    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
        agent_registry=agent_registry,
        memory_manager=memory_manager,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=llm_factory)
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry,
                               path_policy=path_policy,
                               agent_registry=agent_registry)
    agent_message_coordinator = AgentMessageCoordinator(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        retry_backoff_seconds=list(config.get("delegation.retry.backoff_seconds", [0, 1, 3])),
    )
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    gateway = Gateway(publisher=publisher, repo=repo, agent_registry=agent_registry)

    # v1.0: 注册 Agent-to-Agent 消息工具
    if config.get("delegation.enabled", True):
        from agentos.capabilities.tools.send_message_tool import SendMessageTool
        send_message_tool = SendMessageTool(
            agent_registry=agent_registry,
            bus=bus,
            repo=repo,
            coordinator=agent_message_coordinator,
            timeout=float(config.get("delegation.default_timeout", 300)),
            default_max_retries=int(config.get("delegation.retry.max_retries", 0)),
        )
        tool_registry.register(send_message_tool)

    # v0.9: 加载插件（飞书 Channel + MessageTool + FeishuApiTool 等）
    plugin_registry = PluginRegistry()
    await plugin_registry.load_plugins(
        config.data, gateway=gateway, publisher=publisher,
    )
    await plugin_registry.apply(
        gateway=gateway, tool_registry=tool_registry, publisher=publisher,
    )

    # 启动顺序：persister → bus_router → runtimes → gateway
    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await agent_message_coordinator.start()
    await title_runtime.start()
    await gateway.start()

    # v0.8: Cron 定时任务 + Heartbeat 心跳巡检
    cron_runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)
    heartbeat_runtime = HeartbeatRuntime(bus=bus, repo=repo)
    if config.get("cron.enabled", True):
        tool_registry.register(CronTool(cron_runtime))
    await cron_runtime.start()
    await heartbeat_runtime.start()

    # Token 认证服务（Jupyter-lab 风格，每次启动生成新 token）
    auth_service = TokenAuthService(agentos_home=agentos_home)

    # WebSocketChannel（注入 auth_service 用于连接认证）
    ws_channel = WebSocketChannel("websocket", auth_service=auth_service)
    gateway.register_channel(ws_channel)

    app.state.services = Services(
        repo=repo,
        bus=bus,
        publisher=publisher,
        bus_router=bus_router,
        persister=persister,
        agent_runtime=agent_runtime,
        llm_runtime=llm_runtime,
        tool_runtime=tool_runtime,
        agent_message_coordinator=agent_message_coordinator,
        title_runtime=title_runtime,
        gateway=gateway,
        ws_channel=ws_channel,
        cron_runtime=cron_runtime,
        heartbeat_runtime=heartbeat_runtime,
        auth_service=auth_service,
    )
    # 挂载 registries 供 API 路由使用
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.agent_registry = agent_registry
    app.state.config = config
    app.state.agentos_home = agentos_home_str
    app.state.market_service = market_service

    # 注册认证路由
    auth_router = create_auth_router(auth_service=auth_service)
    app.include_router(auth_router)

    # 打印 token 访问 URL
    server_port = config.get("server.port", 8000)
    frontend_port = 3000  # 默认前端端口
    print()
    print("=" * 60)
    print("  AgentOS Token Authentication")
    print(f"  访问地址: http://localhost:{frontend_port}/?token={auth_service.token}")
    print(f"  API 地址: http://localhost:{server_port}")
    print("  (token 每次启动重新生成)")
    print("=" * 60)
    print()

    logger.info("AgentOS backend started (dual-bus architecture, multi-agent enabled, token auth enabled)")

    try:
        yield
    finally:
        # 关闭顺序：market_service → cron/heartbeat → runtimes → gateway → bus_router → persister
        await market_service.shutdown()
        await cron_runtime.stop()
        await heartbeat_runtime.stop()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await agent_message_coordinator.stop()
        await title_runtime.stop()
        await gateway.stop()
        await bus_router.stop()
        await persister.stop()
        logger.info("AgentOS backend stopped")


app = FastAPI(title="AgentOS Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get("server.cors_origins", []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 不需要 token 认证的路径白名单
AUTH_WHITELIST = {
    "/health",
    "/api/auth/verify-token",
    "/api/auth/status",
    "/api/auth/logout",
}


@app.middleware("http")
async def token_auth_middleware(request: Request, call_next):
    """全局 token 认证中间件（白名单路径放行，其余需要 token）"""
    auth_enabled = config.get("security.auth_enabled", False)
    if not auth_enabled:
        return await call_next(request)

    # 白名单放行
    if request.url.path in AUTH_WHITELIST:
        return await call_next(request)

    # CORS 预检请求放行（OPTIONS 由 CORSMiddleware 处理）
    if request.method == "OPTIONS":
        return await call_next(request)

    # 验证 token
    if not hasattr(app.state, "services") or not verify_request(request, app.state.services.auth_service):
        # 401 响应需要带 CORS 头，否则浏览器会拦截
        origin = request.headers.get("origin", "")
        headers = {}
        allowed_origins = config.get("server.cors_origins", [])
        if origin in allowed_origins:
            headers["access-control-allow-origin"] = origin
            headers["access-control-allow-credentials"] = "true"
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing token"}, headers=headers)

    return await call_next(request)

# 注册 API 路由
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(gateway.router)
app.include_router(skills.router)
from agentos.interfaces.http.skills import invoke_router
app.include_router(invoke_router)
app.include_router(workspace.router)
app.include_router(config_api.router)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "timestamp": time.time(), "version": "0.1.0"}


@app.get("/api/sessions")
async def list_sessions():
    """获取会话列表"""
    sessions = await app.state.services.gateway.list_sessions()
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/sessions/{session_id}/turns")
async def get_session_turns(session_id: str):
    """获取会话的所有轮次"""
    turns = await app.state.services.gateway.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str):
    """获取会话的所有事件"""
    events = await app.state.services.gateway.get_session_events(session_id)
    return JSONResponse(content={"events": events})


@app.get("/api/sessions/{session_id}/messages")
async def list_session_messages(session_id: str):
    """获取会话的所有消息"""
    messages = await app.state.services.gateway.get_messages(session_id)
    return JSONResponse(content={"messages": messages})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 — 委托给 WebSocketChannel 处理"""
    await app.state.services.ws_channel.handle_connection(websocket)
