"""Telegram 真实 API 回归脚本。

运行前准备：
1. 导出 `TELEGRAM_BOT_TOKEN`
2. 可选导出 `TELEGRAM_TEST_CHAT_ID`，脚本会先主动发一条提示消息
3. 运行脚本后，用真实 Telegram 账号给 bot 发送一条私聊文本消息
"""

from __future__ import annotations

import asyncio
import copy
import os
from contextlib import suppress
from pathlib import Path

from sensenova_claw.adapters.plugins.telegram.channel import TelegramChannel
from sensenova_claw.adapters.plugins.telegram.config import TelegramConfig
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


async def main() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    test_chat_id = os.environ.get("TELEGRAM_TEST_CHAT_ID", "").strip()
    if not bot_token:
        raise SystemExit("缺少环境变量 TELEGRAM_BOT_TOKEN")

    original_config = copy.deepcopy(config.data)
    tmp_root = Path("/tmp/sensenova_claw_telegram_real_e2e")
    tmp_root.mkdir(parents=True, exist_ok=True)

    config.data["system"]["database_path"] = str(tmp_root / "sensenova-claw.db")
    config.data["system"]["workspace_dir"] = str(tmp_root / "workspace")
    config.data["system"]["sensenova_claw_home"] = str(tmp_root / ".sensenova-claw")
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
    telegram_channel = TelegramChannel(
        config=TelegramConfig(
            enabled=True,
            bot_token=bot_token,
            mode="polling",
            dm_policy="open",
            group_policy="disabled",
        ),
        plugin_api=_SimplePluginApi(gateway),
    )
    gateway.register_channel(telegram_channel)

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await gateway.start()

    if test_chat_id:
        await telegram_channel.send_outbound(
            target=test_chat_id,
            text="Sensenova-Claw Telegram 真实回归已启动，请直接回复这条消息进行测试。",
        )

    print("等待 Telegram 私聊文本消息。请现在给 bot 发送一条消息。")

    completed = asyncio.Event()

    async def collector() -> None:
        async for event in bus.subscribe():
            if event.type == AGENT_STEP_COMPLETED and event.session_id.startswith("telegram_"):
                print("收到 agent.step_completed:")
                print(event.payload)
                completed.set()
                break

    collect_task = asyncio.create_task(collector())

    try:
        await asyncio.wait_for(completed.wait(), timeout=180)
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

    log_file = tmp_root / ".sensenova-claw" / "logs" / "system.log"
    print(f"日志文件: {log_file}")
    if log_file.exists():
        print("已写入 DEBUG 日志，可检查其中的 `LLM call input`。")


if __name__ == "__main__":
    asyncio.run(main())
