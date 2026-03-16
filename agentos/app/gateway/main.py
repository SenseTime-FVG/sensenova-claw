from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
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
from agentos.platform.config.workspace import ensure_workspace
from agentos.interfaces.http import agents, tools, gateway, skills, workspace, config_api

# Token 认证模块
from agentos.platform.security.auth import AuthService
from agentos.platform.security.middleware import AuthMiddleware
from agentos.adapters.storage.user_repository import UserRepository
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
    title_runtime: TitleRuntime
    gateway: Gateway
    ws_channel: WebSocketChannel
    cron_runtime: CronRuntime
    heartbeat_runtime: HeartbeatRuntime
    # Token 认证服务
    auth_service: AuthService
    user_repo: UserRepository
    auth_middleware: AuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    repo = Repository()
    await repo.init()

    # 确保 workspace 目录和引导文件存在
    workspace_dir = config.get("system.workspace_dir", "./workspace")
    await ensure_workspace(workspace_dir)

    # v1.2: 初始化路径安全策略
    workspace_path = Path(workspace_dir).expanduser().resolve()
    granted_paths = config.get("system.granted_paths", [])
    path_policy = PathPolicy(workspace=workspace_path, granted_paths=granted_paths)
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
    skills_dir = Path(config.get("system.workspace_dir", ".")) / "skills"
    state_file = Path(config.get("system.workspace_dir", ".")) / "skills_state.json"
    from agentos.platform.config.config import PROJECT_ROOT
    builtin_skills_dir = PROJECT_ROOT / "workspace" / "skills"
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
        workspace_dir=str(workspace_path),
    )

    # v1.0: 初始化 AgentRegistry
    agent_config_dir = Path(config.get("system.workspace_dir", ".")) / "agents"
    agent_registry = AgentRegistry(config_dir=agent_config_dir)
    agent_registry.load_from_config(config.data)
    agent_registry.load_from_dir()

    # 将 agent_registry 注入 ContextBuilder（供委托 prompt 使用）
    context_builder.agent_registry = agent_registry

    # v0.6: 初始化记忆系统
    memory_manager = None
    memory_enabled = config.get("memory.enabled", False)

    if memory_enabled:
        from agentos.capabilities.memory.config import MemoryConfig
        from agentos.capabilities.memory.manager import MemoryManager
        from agentos.capabilities.memory.tools import MemorySearchTool

        mem_config = MemoryConfig.from_dict(config.data)
        db_path = repo.db_path.parent / "memory_index.db"
        memory_manager = MemoryManager(
            workspace_dir=str(workspace_dir),
            config=mem_config,
            db_path=db_path,
        )
        await memory_manager.sync_index()

        # 为已有的 chunks 生成嵌入向量
        await memory_manager.embed_pending_chunks()

        if mem_config.search.enabled:
            tool_registry.register(MemorySearchTool(memory_manager))

        logger.info("Memory system enabled (workspace=%s)", workspace_dir)

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
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

    # v1.0: 注册委托工具
    if config.get("delegation.enabled", True):
        from agentos.capabilities.tools.delegate_tool import DelegateTool
        delegate_tool = DelegateTool(
            agent_registry=agent_registry,
            bus_router=bus_router,
            repo=repo,
            timeout=float(config.get("delegation.default_timeout", 300)),
        )
        tool_registry.register(delegate_tool)

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
    await title_runtime.start()
    await gateway.start()

    # v0.8: Cron 定时任务 + Heartbeat 心跳巡检
    cron_runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)
    heartbeat_runtime = HeartbeatRuntime(bus=bus, repo=repo)
    if config.get("cron.enabled", True):
        tool_registry.register(CronTool(cron_runtime))
    await cron_runtime.start()
    await heartbeat_runtime.start()

    # v0.6: 初始化 Token 认证服务
    jwt_secret = config.get("security.jwt.secret_key", "")
    if not jwt_secret or len(jwt_secret) < 32:
        logger.warning("JWT_SECRET_KEY not configured or too short, using insecure default for development")
        jwt_secret = "insecure-dev-secret-change-in-production-min-32-chars-long-1234567890"

    auth_service = AuthService(
        secret_key=jwt_secret,
        algorithm=config.get("security.jwt.algorithm", "HS256"),
        access_token_expire_minutes=int(config.get("security.jwt.access_token_expire_minutes", 60)),
        refresh_token_expire_days=int(config.get("security.jwt.refresh_token_expire_days", 30)),
    )

    # 初始化用户仓储
    user_repo = UserRepository(db_path=str(repo.db_path))

    # 初始化认证中间件
    auth_middleware = AuthMiddleware(auth_service, user_repo)

    app.state.services = Services(
        repo=repo,
        bus=bus,
        publisher=publisher,
        bus_router=bus_router,
        persister=persister,
        agent_runtime=agent_runtime,
        llm_runtime=llm_runtime,
        tool_runtime=tool_runtime,
        title_runtime=title_runtime,
        gateway=gateway,
        ws_channel=ws_channel,
        cron_runtime=cron_runtime,
        heartbeat_runtime=heartbeat_runtime,
        auth_service=auth_service,
        user_repo=user_repo,
        auth_middleware=auth_middleware,
    )
    # 挂载 registries 供 API 路由使用
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.agent_registry = agent_registry
    app.state.config = config
    app.state.market_service = market_service

    # 注册认证路由
    auth_router = create_auth_router(
        auth_service=auth_service,
        user_repo=user_repo,
        auth_middleware=auth_middleware,
        enable_registration=config.get("security.public_registration", False),
    )
    app.include_router(auth_router)

    logger.info("AgentOS backend started (dual-bus architecture, multi-agent enabled, auth enabled)")

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


@app.get("/api/sessions")
async def list_sessions(authorization: str = Header(None)):
    """获取会话列表（需要认证）"""
    services: Services = app.state.services

    # v0.6: 认证保护
    if config.get("security.auth_enabled", False):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

        token = authorization[7:]  # 移除 "Bearer " 前缀
        try:
            payload = services.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]
            user = await services.user_repo.get_user_by_id(user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="Invalid or inactive user")
        except Exception as e:
            logger.warning(f"API authentication failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    sessions = await services.repo.list_sessions(limit=50)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/sessions/{session_id}/turns")
async def get_session_turns(session_id: str, authorization: str = Header(None)):
    """获取会话的所有轮次（需要认证）"""
    services: Services = app.state.services

    # v0.6: 认证保护
    if config.get("security.auth_enabled", False):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        token = authorization[7:]
        try:
            payload = services.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]
            user = await services.user_repo.get_user_by_id(user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="Invalid or inactive user")
        except Exception as e:
            logger.warning(f"API authentication failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    turns = await services.repo.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str, authorization: str = Header(None)):
    """获取会话的所有事件（需要认证）"""
    services: Services = app.state.services

    # v0.6: 认证保护
    if config.get("security.auth_enabled", False):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        token = authorization[7:]
        try:
            payload = services.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]
            user = await services.user_repo.get_user_by_id(user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="Invalid or inactive user")
        except Exception as e:
            logger.warning(f"API authentication failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    events = await services.repo.get_session_events(session_id)
    return JSONResponse(content={"events": events})


@app.get("/api/sessions/{session_id}/messages")
async def list_session_messages(session_id: str, authorization: str = Header(None)):
    """获取会话的所有消息（需要认证）"""
    services: Services = app.state.services

    # v0.6: 认证保护
    if config.get("security.auth_enabled", False):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        token = authorization[7:]
        try:
            payload = services.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]
            user = await services.user_repo.get_user_by_id(user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="Invalid or inactive user")
        except Exception as e:
            logger.warning(f"API authentication failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    messages = await services.repo.get_session_messages(session_id)
    return JSONResponse(content={"messages": messages})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    services: Services = app.state.services
    ws_channel = services.ws_channel
    gateway = services.gateway
    repo = services.repo
    publisher = services.publisher
    auth_service = services.auth_service
    user_repo = services.user_repo

    # v0.6: Token 认证（从查询参数获取）
    auth_enabled = config.get("security.auth_enabled", False)
    if auth_enabled:
        token = websocket.query_params.get("token")
        if not token:
            logger.warning("WebSocket connection rejected: missing token")
            await websocket.close(code=1008, reason="Missing authentication token")
            return

        try:
            payload = auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]
            user = await user_repo.get_user_by_id(user_id)
            if not user or not user.is_active:
                logger.warning(f"WebSocket connection rejected: invalid user (user_id={user_id})")
                await websocket.close(code=1008, reason="Invalid or inactive user")
                return
            logger.info(f"WebSocket authenticated: {user.username} (user_id={user_id})")
        except Exception as e:
            logger.warning(f"WebSocket connection rejected: {e}")
            await websocket.close(code=1008, reason="Invalid token")
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
