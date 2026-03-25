from __future__ import annotations

import asyncio
import copy
from contextlib import suppress
from pathlib import Path

import pytest

from sensenova_claw.adapters.plugins.wecom.channel import WecomChannel
from sensenova_claw.adapters.plugins.wecom.config import WecomConfig
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.persister import EventPersister
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import AGENT_STEP_COMPLETED
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.platform.config.config import config
from sensenova_claw.platform.logging.setup import setup_logging


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeWecomClient:
    def __init__(self):
        self.sent_messages: list[dict] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_text(self, target: str, text: str) -> dict:
        self.sent_messages.append({"target": target, "text": text})
        return {"success": True, "message_id": f"msg:{target}"}


@pytest.mark.asyncio
async def test_wecom_channel_end_to_end_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """覆盖企微文本入站到 Agent 回复出站的完整链路。"""
    original_config = copy.deepcopy(config.data)

    db_path = tmp_path / "sensenova-claw.db"
    workspace = tmp_path / "workspace"

    monkeypatch.setenv("SENSENOVA_CLAW_HOME", str(tmp_path))
    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["workspace_dir"] = str(workspace)
    config.data["system"]["log_level"] = "DEBUG"
    config.data["llm"]["default_model"] = "mock"
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

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
    wecom_client = _FakeWecomClient()
    wecom_channel = WecomChannel(
        config=WecomConfig(enabled=True, bot_id="bot", secret="secret"),
        plugin_api=_SimplePluginApi(gateway),
        client=wecom_client,
    )
    gateway.register_channel(wecom_channel)

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
            if event.source == "wecom" or event.session_id.startswith("wecom_"):
                collected.append(event)
            if event.type == AGENT_STEP_COMPLETED and event.session_id.startswith("wecom_"):
                completed.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        await wecom_channel.handle_incoming_text(
            text="你好，帮我简单自我介绍",
            chat_id="chat-1",
            chat_type="p2p",
            sender_id="user-1",
            message_id="msg-1",
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
    assert wecom_client.sent_messages
    assert wecom_client.sent_messages[-1]["target"] == "chat-1"
    assert "当前没有可用的 LLM" in wecom_client.sent_messages[-1]["text"]
    log_file = tmp_path / "logs" / "system.log"
    assert log_file.exists()
    assert "LLM call input" in log_file.read_text(encoding="utf-8")
