"""v0.9 集成测试：飞书出站增强（card/text/event_filter/outbound/MessageTool）

去除所有 mock/MagicMock/AsyncMock/patch，使用真实组件验证。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    MESSAGE_OUTBOUND_SENT,
    TOOL_CALL_STARTED,
)
from agentos.adapters.channels.base import Channel, OutboundCapable
from agentos.interfaces.ws.gateway import Gateway
from agentos.adapters.channels.feishu.card import build_markdown_card
from agentos.adapters.channels.feishu.text import chunk_text
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.capabilities.tools.message_tool import MessageTool


# ---- card.py 测试 ----


class TestBuildMarkdownCard:
    def test_basic_card(self):
        result = build_markdown_card("hello world")
        card = json.loads(result)
        assert card["config"]["wide_screen_mode"] is True
        assert len(card["elements"]) == 1
        assert card["elements"][0]["text"]["tag"] == "lark_md"
        assert card["elements"][0]["text"]["content"] == "hello world"
        assert "header" not in card

    def test_card_with_title(self):
        result = build_markdown_card("content", title="Title")
        card = json.loads(result)
        assert card["header"]["title"]["content"] == "Title"
        assert card["header"]["title"]["tag"] == "plain_text"

    def test_card_returns_valid_json(self):
        result = build_markdown_card("**bold** and `code`")
        json.loads(result)  # 不抛异常


# ---- text.py 测试 ----


class TestChunkText:
    def test_short_text_no_split(self):
        text = "hello world"
        assert chunk_text(text) == [text]

    def test_exact_limit(self):
        text = "a" * 4000
        assert chunk_text(text) == [text]

    def test_split_at_paragraph(self):
        text = "A" * 2000 + "\n\n" + "B" * 2000
        chunks = chunk_text(text, limit=3000)
        assert len(chunks) == 2
        assert chunks[0].strip() == "A" * 2000
        assert chunks[1].strip() == "B" * 2000

    def test_split_at_newline(self):
        text = "A" * 2000 + "\n" + "B" * 2000
        chunks = chunk_text(text, limit=3000)
        assert len(chunks) == 2

    def test_code_block_fence_handling(self):
        """代码块跨片时应正确闭合/重开"""
        text = "intro\n```python\n" + "x = 1\n" * 800 + "```\nend"
        chunks = chunk_text(text, limit=2000)
        assert len(chunks) >= 2
        # 第一片应以 ``` 闭合
        assert chunks[0].rstrip().endswith("```")
        # 第二片应以 ``` 开始（重开代码块）
        assert chunks[1].lstrip().startswith("```")

    def test_no_fence_for_even_count(self):
        """完整代码块不应额外添加 fence"""
        text = "```python\nprint('hi')\n```\n\n" + "A" * 5000
        chunks = chunk_text(text, limit=3000)
        # 第一片包含完整代码块，不应额外添加 ```
        fence_count = chunks[0].count("```")
        assert fence_count % 2 == 0

    def test_custom_limit(self):
        text = "A" * 100
        chunks = chunk_text(text, limit=30)
        total = sum(len(c) for c in chunks)
        assert total >= 100  # 所有内容都在


# ---- Gateway event_filter 测试 ----


class FilteredTestChannel(Channel):
    """只接收 AGENT_STEP_COMPLETED 事件的 Channel"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id
        self.received_events: list[EventEnvelope] = []

    def get_channel_id(self) -> str:
        return self._channel_id

    def event_filter(self) -> set[str] | None:
        return {AGENT_STEP_COMPLETED}

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event: EventEnvelope) -> None:
        self.received_events.append(event)


class OutboundTestChannel(Channel):
    """支持 OutboundCapable 的真实 Channel 实现"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id
        self.outbound_calls: list[dict] = []

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event: EventEnvelope) -> None:
        pass

    async def send_outbound(self, target: str, text: str, msg_type: str = "card") -> dict:
        self.outbound_calls.append({"target": target, "text": text, "msg_type": msg_type})
        return {"success": True, "message_id": "test_msg_001"}


async def test_gateway_event_filter():
    """测试 Channel event_filter 过滤事件"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = FilteredTestChannel("filtered")
    gateway.register_channel(channel)
    gateway.bind_session("sess_1", "filtered")

    await gateway.start()
    await asyncio.sleep(0.1)

    # 发送 AGENT_STEP_COMPLETED（应通过过滤）
    await publisher.publish(EventEnvelope(
        type=AGENT_STEP_COMPLETED,
        session_id="sess_1",
        source="test",
        payload={"result": {"content": "ok"}},
    ))
    await asyncio.sleep(0.1)

    # 发送 ERROR_RAISED（应被过滤）
    await publisher.publish(EventEnvelope(
        type=ERROR_RAISED,
        session_id="sess_1",
        source="test",
        payload={"error_message": "fail"},
    ))
    await asyncio.sleep(0.1)

    # 发送 TOOL_CALL_STARTED（应被过滤）
    await publisher.publish(EventEnvelope(
        type=TOOL_CALL_STARTED,
        session_id="sess_1",
        source="test",
        payload={"tool_name": "bash"},
    ))
    await asyncio.sleep(0.1)

    await gateway.stop()

    # 只有 AGENT_STEP_COMPLETED 应到达
    assert len(channel.received_events) == 1
    assert channel.received_events[0].type == AGENT_STEP_COMPLETED


async def test_gateway_send_outbound():
    """测试 Gateway.send_outbound"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = OutboundTestChannel("feishu")
    gateway.register_channel(channel)

    result = await gateway.send_outbound("feishu", "chat_123", "Hello!")
    assert result["success"] is True
    assert result["message_id"] == "test_msg_001"
    assert len(channel.outbound_calls) == 1
    assert channel.outbound_calls[0]["target"] == "chat_123"


async def test_gateway_send_outbound_not_found():
    """测试 send_outbound 到不存在的 channel"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    result = await gateway.send_outbound("nonexistent", "target", "text")
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_gateway_send_outbound_not_capable():
    """测试 send_outbound 到不支持 outbound 的 channel"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = FilteredTestChannel("ws")  # 不支持 OutboundCapable
    gateway.register_channel(channel)

    result = await gateway.send_outbound("ws", "target", "text")
    assert result["success"] is False
    assert "does not support outbound" in result["error"]


# ---- MessageTool 测试 ----


async def test_message_tool_success():
    """测试 MessageTool 成功发送"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = OutboundTestChannel("feishu")
    gateway.register_channel(channel)

    tool = MessageTool(gateway=gateway, publisher=publisher)

    # 收集审计事件
    collected: list[EventEnvelope] = []

    async def collector():
        async for event in bus.subscribe():
            if event.type == MESSAGE_OUTBOUND_SENT:
                collected.append(event)
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    result = await tool.execute(
        target="chat_test", message="Hello from tool", _session_id="sess_1",
    )
    assert result["success"] is True
    assert result["message_id"] == "test_msg_001"

    await asyncio.wait_for(collect_task, timeout=2)
    assert len(collected) == 1
    assert collected[0].payload["channel"] == "feishu"
    assert collected[0].payload["target"] == "chat_test"
    assert collected[0].session_id == "sess_1"


async def test_message_tool_missing_target():
    """测试 MessageTool 缺少 target"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    tool = MessageTool(gateway=gateway, publisher=publisher)
    result = await tool.execute(message="Hello")
    assert result["success"] is False
    assert "target is required" in result["error"]


# ---- OutboundCapable Protocol 检查 ----


def test_outbound_capable_protocol():
    """OutboundTestChannel 应满足 OutboundCapable 协议"""
    channel = OutboundTestChannel("test")
    assert isinstance(channel, OutboundCapable)


def test_filtered_channel_not_outbound_capable():
    """FilteredTestChannel 不应满足 OutboundCapable 协议"""
    channel = FilteredTestChannel("test")
    assert not isinstance(channel, OutboundCapable)
