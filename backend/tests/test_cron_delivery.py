"""测试 CronRuntime 的直接投递能力

验证 cron 任务触发后，文本通过 Gateway.deliver_to_channel() 到达各 Channel。
"""

from __future__ import annotations

import asyncio

import pytest

from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.types import CRON_DELIVERY_REQUESTED
from app.gateway.base import Channel
from app.gateway.gateway import Gateway
from app.runtime.publisher import EventPublisher


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    r = Repository(db_path=db_path)
    await r.init()
    return r


class CollectorChannel(Channel):
    """收集所有 send_event 调用的 Mock Channel"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id
        self.received: list[EventEnvelope] = []

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event: EventEnvelope) -> None:
        self.received.append(event)


@pytest.mark.asyncio
async def test_deliver_to_channel_routes_cron_event():
    """Gateway.deliver_to_channel 直接投递 CRON_DELIVERY_REQUESTED 到指定 Channel"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_feishu = CollectorChannel("feishu")
    ch_ws = CollectorChannel("websocket")
    gateway.register_channel(ch_feishu)
    gateway.register_channel(ch_ws)

    event = EventEnvelope(
        type=CRON_DELIVERY_REQUESTED,
        session_id="system",
        source="cron",
        payload={"job_id": "job_001", "text": "提醒文本", "to": None},
    )

    ok = await gateway.deliver_to_channel(event, "feishu")
    assert ok is True
    assert len(ch_feishu.received) == 1
    assert ch_feishu.received[0].payload["text"] == "提醒文本"
    assert len(ch_ws.received) == 0


@pytest.mark.asyncio
async def test_deliver_to_channel_not_found():
    """投递到不存在的 Channel 返回 False"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    event = EventEnvelope(
        type=CRON_DELIVERY_REQUESTED,
        session_id="system",
        source="cron",
        payload={"text": "nope"},
    )

    ok = await gateway.deliver_to_channel(event, "nonexistent")
    assert ok is False


@pytest.mark.asyncio
async def test_cron_runtime_deliver_text_broadcasts(repo):
    """CronRuntime._deliver_text 广播到所有注册的 channels"""
    from app.cron.models import CronJob, SystemEventPayload
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_a = CollectorChannel("channel_a")
    ch_b = CollectorChannel("channel_b")
    gateway.register_channel(ch_a)
    gateway.register_channel(ch_b)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    job = CronJob(
        id="test_job",
        name="测试提醒",
        session_target="main",
        payload=SystemEventPayload(text="你好，这是一条提醒"),
    )

    await runtime._deliver_text(job, "你好，这是一条提醒")

    assert len(ch_a.received) == 1
    assert ch_a.received[0].type == CRON_DELIVERY_REQUESTED
    assert ch_a.received[0].payload["text"] == "你好，这是一条提醒"
    assert ch_a.received[0].payload["job_name"] == "测试提醒"

    assert len(ch_b.received) == 1
    assert ch_b.received[0].payload["text"] == "你好，这是一条提醒"


@pytest.mark.asyncio
async def test_cron_runtime_deliver_text_respects_delivery_channel(repo):
    """CronRuntime._deliver_text 如果配置了 delivery.channel_id 则只投递到该 channel"""
    from app.cron.models import CronDelivery, CronJob, SystemEventPayload
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_feishu = CollectorChannel("feishu")
    ch_ws = CollectorChannel("websocket")
    gateway.register_channel(ch_feishu)
    gateway.register_channel(ch_ws)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    job = CronJob(
        id="test_job_2",
        name="飞书提醒",
        session_target="main",
        payload=SystemEventPayload(text="只发飞书"),
        delivery=CronDelivery(mode="announce", channel_id="feishu"),
    )

    await runtime._deliver_text(job, "只发飞书")

    assert len(ch_feishu.received) == 1
    assert len(ch_ws.received) == 0


@pytest.mark.asyncio
async def test_cron_runtime_deliver_text_skips_on_none_mode(repo):
    """delivery.mode='none' 时不投递"""
    from app.cron.models import CronDelivery, CronJob, SystemEventPayload
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch = CollectorChannel("ch")
    gateway.register_channel(ch)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    job = CronJob(
        id="test_job_3",
        session_target="main",
        payload=SystemEventPayload(text="不发"),
        delivery=CronDelivery(mode="none"),
    )

    await runtime._deliver_text(job, "不发")

    assert len(ch.received) == 0


@pytest.mark.asyncio
async def test_resolve_delivery_for_session_websocket(repo):
    """resolve_delivery_for_session 正确解析 WebSocket session 的 channel"""
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_ws = CollectorChannel("websocket")
    gateway.register_channel(ch_ws)
    gateway.bind_session("sess_abc", "websocket")

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    delivery = runtime.resolve_delivery_for_session("sess_abc")
    assert delivery is not None
    assert delivery.channel_id == "websocket"
    assert delivery.mode == "announce"
    assert delivery.to is None


@pytest.mark.asyncio
async def test_resolve_delivery_for_session_feishu_with_meta(repo):
    """resolve_delivery_for_session 从飞书 session_meta 取出 chat_id"""
    import threading
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_feishu = CollectorChannel("feishu")

    class _FakeMeta:
        chat_id = "oc_fake_chat_123"

    ch_feishu._session_meta = {"feishu_sess_1": _FakeMeta()}
    ch_feishu._lock = threading.Lock()
    gateway.register_channel(ch_feishu)
    gateway.bind_session("feishu_sess_1", "feishu")

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    delivery = runtime.resolve_delivery_for_session("feishu_sess_1")
    assert delivery is not None
    assert delivery.channel_id == "feishu"
    assert delivery.to == "oc_fake_chat_123"


@pytest.mark.asyncio
async def test_resolve_delivery_for_session_unknown(repo):
    """未绑定的 session 返回 None"""
    from app.cron.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    delivery = runtime.resolve_delivery_for_session("unknown_sess")
    assert delivery is None


@pytest.mark.asyncio
async def test_cron_tool_add_auto_populates_delivery(repo):
    """CronTool._add 自动从 session_id 填充 delivery"""
    from app.cron.runtime import CronRuntime
    from app.cron.tool import CronTool

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_feishu = CollectorChannel("feishu")
    gateway.register_channel(ch_feishu)
    gateway.bind_session("sess_tool_test", "feishu")

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)
    tool = CronTool(runtime)

    result = await tool.execute(
        action="add",
        schedule_type="every",
        schedule_value="60000",
        text="定时提醒测试",
        name="工具创建的提醒",
        _session_id="sess_tool_test",
    )

    assert result["success"] is True
    assert result["delivery_channel"] == "feishu"

    jobs = await runtime.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].delivery is not None
    assert jobs[0].delivery.channel_id == "feishu"
