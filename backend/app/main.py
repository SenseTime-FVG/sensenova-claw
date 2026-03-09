from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import config
from app.core.logging import setup_logging
from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.types import UI_TURN_CANCEL_REQUESTED, UI_USER_INPUT
from app.gateway.channels.websocket_channel import WebSocketChannel
from app.gateway.gateway import Gateway
from app.llm.factory import LLMFactory
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context_builder import ContextBuilder
from app.runtime.llm_runtime import LLMRuntime
from app.runtime.publisher import EventPublisher
from app.runtime.state import SessionStateStore
from app.runtime.title_runtime import TitleRuntime
from app.runtime.tool_runtime import ToolRuntime
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class Services:
    repo: Repository
    bus: PublicEventBus
    publisher: EventPublisher
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

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus, repo=repo)

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()
    context_builder = ContextBuilder()

    agent_runtime = AgentRuntime(
        publisher=publisher,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
    )
    llm_runtime = LLMRuntime(publisher=publisher, factory=LLMFactory())
    tool_runtime = ToolRuntime(publisher=publisher, registry=tool_registry)
    title_runtime = TitleRuntime(publisher=publisher, repo=repo)

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()
    await gateway.start()

    app.state.services = Services(
        repo=repo,
        bus=bus,
        publisher=publisher,
        agent_runtime=agent_runtime,
        llm_runtime=llm_runtime,
        tool_runtime=tool_runtime,
        title_runtime=title_runtime,
        gateway=gateway,
        ws_channel=ws_channel,
    )
    logger.info("AgentOS backend started")

    try:
        yield
    finally:
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await title_runtime.stop()
        await gateway.stop()
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
                            type=UI_TURN_CANCEL_REQUESTED,
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
                        type=UI_USER_INPUT,
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
