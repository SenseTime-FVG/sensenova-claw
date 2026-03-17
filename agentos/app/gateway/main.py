from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentos.platform.config.config import config
from agentos.platform.logging.setup import setup_logging
from agentos.kernel.scheduler.runtime import CronRuntime
from agentos.kernel.scheduler.tool import CronTool
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.persister import EventPersister
from agentos.kernel.events.router import BusRouter
from agentos.kernel.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED, TOOL_CONFIRMATION_RESPONSE
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
from agentos.platform.security.middleware import verify_request, verify_websocket
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
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
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

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

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
    auth_service = TokenAuthService()

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


async def _verify_auth(request: Request) -> None:
    """统一的 API 认证检查（基于 token cookie/query param/header）"""
    auth_enabled = config.get("security.auth_enabled", False)
    if not auth_enabled:
        return
    services: Services = app.state.services
    if not verify_request(request, services.auth_service):
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@app.get("/api/sessions")
async def list_sessions(request: Request):
    """获取会话列表（需要认证）"""
    await _verify_auth(request)
    services: Services = app.state.services
    sessions = await services.repo.list_sessions(limit=50)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/sessions/{session_id}/turns")
async def get_session_turns(session_id: str, request: Request):
    """获取会话的所有轮次（需要认证）"""
    await _verify_auth(request)
    services: Services = app.state.services
    turns = await services.repo.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str, request: Request):
    """获取会话的所有事件（需要认证）"""
    await _verify_auth(request)
    services: Services = app.state.services
    events = await services.repo.get_session_events(session_id)
    return JSONResponse(content={"events": events})


@app.get("/api/sessions/{session_id}/messages")
async def list_session_messages(session_id: str, request: Request):
    """获取会话的所有消息（需要认证）"""
    await _verify_auth(request)
    services: Services = app.state.services
    messages = await services.repo.get_session_messages(session_id)
    return JSONResponse(content={"messages": messages})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    services: Services = app.state.services
    ws_channel = services.ws_channel
    gateway = services.gateway
    repo = services.repo
    publisher = services.publisher

    # Token 认证（cookie 或 query param）
    auth_enabled = config.get("security.auth_enabled", False)
    if auth_enabled:
        if not verify_websocket(websocket, services.auth_service):
            logger.warning("WebSocket connection rejected: invalid or missing token")
            await websocket.close(code=1008, reason="Invalid or missing token")
            return

    await ws_channel.connect(websocket)
    logger.info("WebSocket client connected")

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            logger.info(f"Received message type: {msg_type}")
            payload = message.get("payload", {})
            session_id = message.get("session_id")

            if msg_type == "create_session":
                session_id = f"sess_{uuid.uuid4().hex[:12]}"
                agent_id = payload.get("agent_id", "default")
                meta = payload.get("meta", {})
                meta["agent_id"] = agent_id
                await repo.create_session(session_id=session_id, meta=meta)
                ws_channel.bind_session(session_id, websocket)
                gateway.bind_session(session_id, "websocket")
                await ws_channel.send_json(
                    websocket,
                    {
                        "type": "session_created",
                        "session_id": session_id,
                        "payload": {"created_at": time.time()},
                        "timestamp": time.time(),
                    },
                )
                logger.info(f"Session created: {session_id}")
                continue

            if msg_type == "list_sessions":
                sessions = await repo.list_sessions(limit=int(payload.get("limit", 50)))
                await ws_channel.send_json(
                    websocket,
                    {
                        "type": "sessions_list",
                        "payload": {"sessions": sessions},
                        "timestamp": time.time(),
                    },
                )
                continue

            if msg_type == "load_session":
                sid = payload.get("session_id")
                if sid:
                    ws_channel.bind_session(sid, websocket)
                    gateway.bind_session(sid, "websocket")
                    events = await repo.get_session_events(sid)
                    await ws_channel.send_json(
                        websocket,
                        {
                            "type": "session_loaded",
                            "session_id": sid,
                            "payload": {"events": events},
                            "timestamp": time.time(),
                        },
                    )
                continue

            if msg_type == "cancel_turn":
                if session_id:
                    await gateway.publish_from_channel(
                        EventEnvelope(
                            type=USER_TURN_CANCEL_REQUESTED,
                            session_id=session_id,
                            source="websocket",
                            payload={"reason": payload.get("reason", "user_cancel")},
                        )
                    )
                continue

            if msg_type == "user_input":
                if not session_id:
                    session_id = f"sess_{uuid.uuid4().hex[:12]}"
                    await repo.create_session(session_id=session_id, meta={"title": "自动创建会话"})
                    ws_channel.bind_session(session_id, websocket)
                    gateway.bind_session(session_id, "websocket")
                    await ws_channel.send_json(
                        websocket,
                        {
                            "type": "session_created",
                            "session_id": session_id,
                            "payload": {"created_at": time.time()},
                            "timestamp": time.time(),
                        },
                    )

                turn_id = f"turn_{uuid.uuid4().hex[:12]}"
                await gateway.publish_from_channel(
                    EventEnvelope(
                        type=USER_INPUT,
                        session_id=session_id,
                        turn_id=turn_id,
                        source="websocket",
                        payload={
                            "content": payload.get("content", ""),
                            "attachments": payload.get("attachments", []),
                            "context_files": payload.get("context_files", []),
                        },
                    )
                )
                continue


            # v1.5: 删除会话
            if msg_type == "delete_session":
                sid = payload.get("session_id")
                if sid:
                    try:
                        await repo.delete_session_cascade(sid)
                        ws_channel._session_bindings.pop(sid, None)
                        await ws_channel.send_json(websocket, {
                            "type": "session_deleted",
                            "payload": {"session_id": sid},
                            "timestamp": time.time(),
                        })
                        logger.info(f"Session deleted: {sid}")
                    except Exception as e:
                        await ws_channel.send_json(websocket, {
                            "type": "error",
                            "payload": {"message": f"删除会话失败: {e}"},
                            "timestamp": time.time(),
                        })
                continue

            # v1.5: 重命名会话
            if msg_type == "rename_session":
                sid = payload.get("session_id") or session_id
                title = payload.get("title", "")
                if sid and title:
                    try:
                        await repo.update_session_title(sid, title)
                        await ws_channel.send_json(websocket, {
                            "type": "session_renamed",
                            "payload": {"session_id": sid, "title": title},
                            "timestamp": time.time(),
                        })
                        logger.info(f"Session renamed: {sid} -> {title}")
                    except Exception as e:
                        await ws_channel.send_json(websocket, {
                            "type": "error",
                            "payload": {"message": f"重命名会话失败: {e}"},
                            "timestamp": time.time(),
                        })
                else:
                    await ws_channel.send_json(websocket, {
                        "type": "error",
                        "payload": {"message": "需要 session_id 和 title"},
                        "timestamp": time.time(),
                    })
                continue

            # v1.4: 列出可用 Agent
            if msg_type == "list_agents":
                agent_registry = app.state.agent_registry
                agents_data = [
                    {"id": a.id, "name": a.name, "description": a.description,
                     "model": a.model, "provider": a.provider}
                    for a in agent_registry.list_all()
                ]
                await ws_channel.send_json(websocket, {
                    "type": "agents_list",
                    "payload": {"agents": agents_data},
                    "timestamp": time.time(),
                })
                continue

            # v1.4: 工具确认响应
            if msg_type == "tool_confirmation_response":
                await gateway.publish_from_channel(
                    EventEnvelope(
                        type=TOOL_CONFIRMATION_RESPONSE,
                        session_id=session_id,
                        source="websocket",
                        payload={
                            "tool_call_id": payload.get("tool_call_id"),
                            "approved": payload.get("approved", False),
                        },
                    )
                )
                continue

            # v1.4: 获取会话消息历史
            if msg_type == "get_messages":
                sid = payload.get("session_id") or session_id
                messages = await repo.get_session_messages(sid) if sid else []
                await ws_channel.send_json(websocket, {
                    "type": "messages_list",
                    "payload": {"messages": messages},
                    "timestamp": time.time(),
                })
                continue

            await ws_channel.send_json(
                websocket,
                {
                    "type": "error",
                    "payload": {
                        "error_type": "InvalidMessage",
                        "message": f"unsupported message type: {msg_type}",
                        "details": {"message": message},
                    },
                    "timestamp": time.time(),
                },
            )

    except WebSocketDisconnect:
        ws_channel.disconnect(websocket)
    except Exception as exc:  # noqa: BLE001
        logger.exception("websocket endpoint error")
        ws_channel.disconnect(websocket)
        try:
            await ws_channel.send_json(
                websocket,
                {
                    "type": "error",
                    "payload": {
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "details": {},
                    },
                    "timestamp": time.time(),
                },
            )
        except Exception:  # noqa: BLE001
            pass
