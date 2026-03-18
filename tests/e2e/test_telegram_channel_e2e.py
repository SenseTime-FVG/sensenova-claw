from __future__ import annotations

import asyncio
import copy
from contextlib import suppress
from pathlib import Path

import pytest

from agentos.adapters.channels.telegram.channel import TelegramChannel
from agentos.adapters.channels.telegram.config import TelegramConfig
from agentos.adapters.channels.telegram.models import TelegramInboundMessage
from agentos.adapters.llm.factory import LLMFactory
from agentos.adapters.storage.repository import Repository
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.persister import EventPersister
from agentos.kernel.events.router import BusRouter
from agentos.kernel.events.types import AGENT_STEP_COMPLETED
from agentos.kernel.runtime.agent_runtime import AgentRuntime
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.llm_runtime import LLMRuntime
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.runtime.state import SessionStateStore
from agentos.kernel.runtime.tool_runtime import ToolRuntime
from agentos.platform.config.config import config
from agentos.platform.logging.setup import setup_logging


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeTelegramRuntime:
    def __init__(self):
        self.handler = None
        self.sent_messages: list[dict] = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> dict:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
                "message_thread_id": message_thread_id,
            }
        )
        return {"success": True, "message_id": f"msg:{chat_id}"}


@pytest.mark.asyncio
async def test_telegram_channel_end_to_end_flow(tmp_path: Path) -> None:
    """覆盖 Telegram 文本入站到 Agent 回复出站的完整链路。"""
    original_config = copy.deepcopy(config.data)

    db_path = tmp_path / "agentos.db"
    workspace = tmp_path / "workspace"
    agentos_home = tmp_path / ".agentos"

    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["workspace_dir"] = str(workspace)
    config.data["system"]["agentos_home"] = str(agentos_home)
    config.data["system"]["log_level"] = "DEBUG"
    config.data["agent"]["provider"] = "mock"
    config.data["agent"]["default_model"] = "mock-agent-v1"

    setup_logging()

    repo = Repository()
    await repo.init()

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=60)
    tool_registry = ToolRegistry()
    state_store = SessionStateStore()
    context_builder = ContextBuilder(tool_registry=tool_registry)

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry)

    gateway = Gateway(publisher=publisher)
    runtime = _FakeTelegramRuntime()
    telegram_channel = TelegramChannel(
        config=TelegramConfig(enabled=True, bot_token="123:abc"),
        plugin_api=_SimplePluginApi(gateway),
        runtime=runtime,
    )
    gateway.register_channel(telegram_channel)

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await gateway.start()
    await asyncio.sleep(0.1)

    completed = asyncio.Event()
    collected: list[EventEnvelope] = []

    async def collector():
        async for event in bus.subscribe():
            if event.source == "telegram" or event.session_id.startswith("telegram_"):
                collected.append(event)
            if event.type == AGENT_STEP_COMPLETED and event.session_id.startswith("telegram_"):
                completed.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        await telegram_channel.handle_incoming_message(
            TelegramInboundMessage(
                text="你好，帮我简单自我介绍",
                chat_id="1001",
                chat_type="p2p",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
            )
        )

        await asyncio.wait_for(completed.wait(), timeout=10)
    finally:
        if not collect_task.done():
            collect_task.cancel()
        with suppress(asyncio.CancelledError):
            await collect_task
        await gateway.stop()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await bus_router.stop()
        await persister.stop()
        config.data = original_config

    assert any(event.type == AGENT_STEP_COMPLETED for event in collected)
    assert runtime.sent_messages
    assert runtime.sent_messages[-1]["chat_id"] == "1001"
    assert "这是 mock 回复" in runtime.sent_messages[-1]["text"]
    log_file = agentos_home / "logs" / "system.log"
    assert log_file.exists()
    assert "LLM call input" in log_file.read_text(encoding="utf-8")
