from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sensenova_claw.platform.config.config import config
from sensenova_claw.platform.logging.setup import setup_logging
from sensenova_claw.capabilities.miniapps.service import MiniAppService
from sensenova_claw.kernel.scheduler.runtime import CronRuntime
from sensenova_claw.kernel.scheduler.tool import CronTool
from sensenova_claw.kernel.proactive.runtime import ProactiveRuntime
from sensenova_claw.capabilities.tools.proactive_tools import (
    CreateProactiveJobTool, ListProactiveJobsTool, ManageProactiveJobTool,
)
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.persister import EventPersister
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.adapters.channels.websocket_channel import WebSocketChannel
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.heartbeat.runtime import HeartbeatRuntime
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.agent_message_coordinator import AgentMessageCoordinator
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.kernel.runtime.session_maintenance import SessionMaintenance
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.title_runtime import TitleRuntime
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.adapters.plugins import PluginRegistry
from sensenova_claw.kernel.notification.service import NotificationService
from sensenova_claw.platform.config.workspace import (
    ensure_sensenova_claw_home,
    ensure_agent_workspace,
    resolve_sensenova_claw_home,
)
from sensenova_claw.platform.secrets.store import build_default_secret_store, describe_secret_store_status
from sensenova_claw.interfaces.http import agents, tools, gateway, skills, workspace, config_api, sessions
from sensenova_claw.interfaces.http import cron_api, notification_api, proactive_api

# Token 认证模块（Jupyter-lab 风格）
from sensenova_claw.platform.security.auth import TokenAuthService
from sensenova_claw.platform.security.middleware import verify_request
from sensenova_claw.interfaces.http.auth import create_auth_router

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
    proactive_runtime: ProactiveRuntime
    notification_service: NotificationService
    # Token 认证服务（Jupyter-lab 风格）
    auth_service: TokenAuthService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    secret_store = getattr(config, "_secret_store", None) or build_default_secret_store()
    config._secret_store = secret_store
    keyring_available, secret_store_message = describe_secret_store_status(secret_store)
    if keyring_available:
        logger.info(secret_store_message)
    else:
        logger.warning(secret_store_message)

    # 解析 SENSENOVA_CLAW_HOME（默认 ~/.sensenova-claw）
    from sensenova_claw.platform.config.config import PROJECT_ROOT
    sensenova_claw_home = resolve_sensenova_claw_home(config)
    await ensure_sensenova_claw_home(sensenova_claw_home, project_root=PROJECT_ROOT)
    sensenova_claw_home_str = str(sensenova_claw_home)

    # 数据库路径：优先配置，否则 {sensenova_claw_home}/data/sensenova-claw.db
    db_path = config.get("system.database_path", "")
    if not db_path:
        db_path = str(sensenova_claw_home / "data" / "sensenova-claw.db")

    repo = Repository(db_path=db_path)
    await repo.init()

    # 会话维护：清理过期会话
    maintenance = SessionMaintenance(repo=repo)
    await maintenance.run_maintenance()

    bus = PublicEventBus()
    from sensenova_claw.platform.config.config_manager import ConfigManager
    config_manager = ConfigManager(config=config, event_bus=bus, secret_store=secret_store)
    config_manager.start_file_watcher()
    publisher = EventPublisher(bus=bus)
    notification_service = NotificationService(bus=bus)

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
    skills_dir = sensenova_claw_home / "skills"
    state_file = sensenova_claw_home / "skills_state.json"
    builtin_skills_dir = PROJECT_ROOT / ".sensenova-claw" / "skills"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=builtin_skills_dir,
    )
    skill_registry.load_skills(config.data)

    # 初始化 SkillMarketService
    from sensenova_claw.capabilities.skills.market_service import SkillMarketService
    market_service = SkillMarketService(
        skills_dir=skills_dir,
        skill_registry=skill_registry,
        config=config.data,
    )

    context_builder = ContextBuilder(
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        sensenova_claw_home=sensenova_claw_home_str,
    )
    llm_factory = LLMFactory()

    # v1.0: 初始化 AgentRegistry（config.yml + SYSTEM_PROMPT.md 文件）
    agent_registry = AgentRegistry(sensenova_claw_home=sensenova_claw_home)
    agent_registry.load_from_config(config.data)

    custom_page_service = MiniAppService(
        sensenova_claw_home=sensenova_claw_home_str,
        config=config,
        agent_registry=agent_registry,
    )
    await custom_page_service.restore_dedicated_agents()

    # 为所有已注册 agent 初始化 per-agent workspace 和 workdir
    for agent_cfg in agent_registry.list_all():
        await ensure_agent_workspace(sensenova_claw_home_str, agent_cfg.id)

    # 将 agent_registry 注入 ContextBuilder（供多 Agent prompt 使用）
    context_builder.agent_registry = agent_registry

    # v0.6: 初始化记忆系统
    memory_manager = None
    memory_enabled = config.get("memory.enabled", False)

    if memory_enabled:
        from sensenova_claw.capabilities.memory.config import MemoryConfig
        from sensenova_claw.capabilities.memory.manager import MemoryManager
        from sensenova_claw.capabilities.memory.tools import MemorySearchTool

        mem_config = MemoryConfig.from_dict(config.data)
        mem_db_path = repo.db_path.parent / "memory_index.db"
        memory_manager = MemoryManager(
            workspace_dir=sensenova_claw_home_str,
            config=mem_config,
            db_path=mem_db_path,
            llm_factory=llm_factory,
        )
        await memory_manager.sync_index()

        # 为已有的 chunks 生成嵌入向量
        await memory_manager.embed_pending_chunks()

        if mem_config.search.enabled:
            tool_registry.register(MemorySearchTool(memory_manager))

        logger.info("Memory system enabled (home=%s)", sensenova_claw_home_str)

    # Session JSONL 写入器：按 agent 分目录存储会话到 {sensenova_claw_home}/agents/{agent_id}/sessions/
    from sensenova_claw.adapters.storage.session_jsonl import SessionJsonlWriter
    jsonl_writer = SessionJsonlWriter(base_dir=sensenova_claw_home / "agents")

    # 上下文压缩器
    from sensenova_claw.kernel.runtime.context_compressor import ContextCompressor
    default_provider, default_model = config.resolve_model()
    context_compressor = ContextCompressor(
        config=config,
        llm_factory=llm_factory,
        provider_name=default_provider,
        model=default_model,
        sensenova_claw_home=sensenova_claw_home_str,
    )

    # Runtime 使用 BusRouter（管理者模式）
    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
        agent_registry=agent_registry,
        memory_manager=memory_manager,
        jsonl_writer=jsonl_writer,
        context_compressor=context_compressor,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=llm_factory)
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry,
                               agent_registry=agent_registry)
    agent_message_coordinator = AgentMessageCoordinator(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        retry_backoff_seconds=list(config.get("delegation.retry.backoff_seconds", [0, 1, 3])),
    )
    title_runtime = TitleRuntime(bus=bus, repo=repo, agent_registry=agent_registry)

    gateway = Gateway(publisher=publisher, repo=repo, agent_registry=agent_registry)
    custom_page_service.gateway = gateway

    # v1.1: 初始化 ProactiveRuntime（主动任务）
    proactive_runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
        gateway=gateway,
        memory_manager=memory_manager,
    )
    if config.get("proactive.enabled", False):
        tool_registry.register(CreateProactiveJobTool(proactive_runtime))
        tool_registry.register(ListProactiveJobsTool(proactive_runtime))
        tool_registry.register(ManageProactiveJobTool(proactive_runtime))

    # v1.0: 注册 Agent-to-Agent 消息工具
    if config.get("delegation.enabled", True):
        from sensenova_claw.capabilities.tools.send_message_tool import SendMessageTool
        send_message_tool = SendMessageTool(
            agent_registry=agent_registry,
            bus=bus,
            repo=repo,
            coordinator=agent_message_coordinator,
            timeout=float(config.get("delegation.default_timeout", 300)),
            default_max_retries=int(config.get("delegation.retry.max_retries", 0)),
            max_tool_calls=int(config.get("delegation.max_tool_calls", 30)),
            max_llm_calls=int(config.get("delegation.max_llm_calls", 15)),
        )
        tool_registry.register(send_message_tool)

    # v0.9: 加载插件（飞书 Channel、MessageTool 与各类渠道/专用工具）
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
    await proactive_runtime.start()
    await gateway.start()

    # v0.8: Cron 定时任务 + Heartbeat 心跳巡检
    cron_runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway, notification_service=notification_service, agent_runtime=agent_runtime)
    heartbeat_runtime = HeartbeatRuntime(bus=bus, repo=repo, notification_service=notification_service)
    if config.get("cron.enabled", True):
        tool_registry.register(CronTool(cron_runtime))
    await cron_runtime.start()
    await heartbeat_runtime.start()

    # 配置变更监听
    import asyncio
    asyncio.create_task(llm_factory.start_config_listener(bus))
    asyncio.create_task(agent_registry.start_config_listener(bus, config))
    if memory_manager:
        asyncio.create_task(memory_manager.start_config_listener(bus, lambda: config.data))

    # Token 认证服务（首次生成，后续复用持久化 token）
    auth_service = TokenAuthService(sensenova_claw_home=sensenova_claw_home)

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
        proactive_runtime=proactive_runtime,
        notification_service=notification_service,
        auth_service=auth_service,
    )
    # 挂载 registries 供 API 路由使用
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.agent_registry = agent_registry
    app.state.plugin_registry = plugin_registry
    app.state.config = config
    app.state.secret_store = secret_store
    app.state.sensenova_claw_home = sensenova_claw_home_str
    app.state.market_service = market_service
    app.state.config_manager = config_manager
    app.state.custom_page_service = custom_page_service

    # 注册认证路由
    auth_router = create_auth_router(auth_service=auth_service)
    app.include_router(auth_router)

    # 打印 token 访问 URL
    server_port = config.get("server.port", 8000)
    frontend_port = 3000  # 默认前端端口
    print()
    print("=" * 60)
    print("  Sensenova-Claw Token Authentication")
    print(f"  访问地址: http://localhost:{frontend_port}/?token={auth_service.token}")
    print(f"  API 地址: http://localhost:{server_port}")
    print("  (token 已持久化，重启后自动复用)")
    print("=" * 60)
    print()

    logger.info("Sensenova-Claw backend started (dual-bus architecture, multi-agent enabled, token auth enabled)")

    try:
        yield
    finally:
        # 关闭顺序：config_manager → market_service → cron/heartbeat → runtimes → gateway → bus_router → persister
        config_manager.stop_file_watcher()
        await market_service.shutdown()
        await proactive_runtime.stop()
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
        logger.info("Sensenova-Claw backend stopped")


app = FastAPI(title="Sensenova-Claw Backend", version="0.1.0", lifespan=lifespan)
# CORS 配置：开发环境允许所有 Origin（Cursor 端口转发兼容）
cors_origins = config.get("server.cors_origins", [])
if not cors_origins:
    cors_origins = ["*"]  # 未配置时允许所有 Origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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
from sensenova_claw.interfaces.http.skills import invoke_router
app.include_router(invoke_router)
app.include_router(workspace.router)
from sensenova_claw.interfaces.http import files
app.include_router(files.router)
app.include_router(config_api.router)
app.include_router(cron_api.router)
app.include_router(notification_api.router)
from sensenova_claw.interfaces.http import todolist_api
app.include_router(todolist_api.router)
app.include_router(sessions.router)
from sensenova_claw.interfaces.http import custom_pages
app.include_router(custom_pages.router)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "timestamp": time.time(), "version": "0.1.0"}


@app.get("/api/sessions")
async def list_sessions():
    """获取会话列表"""
    sessions = await app.state.services.gateway.list_sessions()
    return JSONResponse(content={"sessions": sessions})


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话及关联数据"""
    try:
        await app.state.services.gateway.delete_session(session_id)
        return JSONResponse(content={"ok": True, "session_id": session_id})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


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
