from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import config
from app.core.logging import setup_logging
from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.persister import EventPersister
from app.events.router import BusRouter
from app.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED
from app.gateway.channels.websocket_channel import WebSocketChannel
from app.gateway.gateway import Gateway
from app.llm.factory import LLMFactory
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context_builder import ContextBuilder
from app.runtime.llm_runtime import LLMRuntime
from app.runtime.publisher import EventPublisher
from app.runtime.session_maintenance import SessionMaintenance
from app.runtime.state import SessionStateStore
from app.runtime.title_runtime import TitleRuntime
from app.runtime.tool_runtime import ToolRuntime
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from app.workspace.manager import ensure_workspace

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    repo = Repository()
    await repo.init()

    # 确保 workspace 目录和引导文件存在
    workspace_dir = config.get("system.workspace_dir", "./SenseAssistant/workspace")
    await ensure_workspace(workspace_dir)

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
    skill_registry = SkillRegistry(workspace_dir=skills_dir)
    skill_registry.load_skills(config.data)

    context_builder = ContextBuilder(skill_registry=skill_registry, tool_registry=tool_registry)

    # v0.6: 初始化记忆系统
    memory_manager = None
    memory_enabled = config.get("memory.enabled", False)

    if memory_enabled:
        from app.memory.config import MemoryConfig
        from app.memory.manager import MemoryManager
        from app.memory.tools import MemorySearchTool

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
        memory_manager=memory_manager,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry)
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

    # 启动顺序：persister → bus_router → runtimes → gateway
    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()
    await gateway.start()

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
    )
    logger.info("AgentOS backend started (dual-bus architecture)")

    try:
        yield
    finally:
        # 关闭顺序：runtimes → gateway → bus_router → persister
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


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "timestamp": time.time(), "version": "0.1.0"}


@app.get("/api/sessions")
async def list_sessions():
    """获取会话列表"""
    services: Services = app.state.services
    sessions = await services.repo.list_sessions(limit=50)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/sessions/{session_id}/turns")
async def get_session_turns(session_id: str):
    """获取会话的所有轮次"""
    services: Services = app.state.services
    turns = await services.repo.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str):
    """获取会话的所有事件"""
    services: Services = app.state.services
    events = await services.repo.get_session_events(session_id)
    return JSONResponse(content={"events": events})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    services: Services = app.state.services
    ws_channel = services.ws_channel
    gateway = services.gateway
    repo = services.repo
    publisher = services.publisher

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
                await repo.create_session(session_id=session_id, meta=payload.get("meta", {}))
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
