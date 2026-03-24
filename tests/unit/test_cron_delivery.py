"""测试 CronRuntime 的直接投递能力

验证 cron 任务触发后，文本通过 Gateway.deliver_to_channel() 到达各 Channel。
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import CRON_DELIVERY_REQUESTED
from sensenova_claw.adapters.channels.base import Channel
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.runtime.publisher import EventPublisher


@pytest_asyncio.fixture
async def repo(tmp_path):
    # 创建临时数据库并初始化，测试结束后临时目录自动清理
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
    from sensenova_claw.kernel.scheduler.models import CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

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
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

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
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

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
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

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
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

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
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    delivery = runtime.resolve_delivery_for_session("unknown_sess")
    assert delivery is None


@pytest.mark.asyncio
async def test_cron_tool_add_auto_populates_delivery(repo):
    """CronTool._add 自动从 session_id 填充 delivery"""
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime
    from sensenova_claw.kernel.scheduler.tool import CronTool

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


class OutboundCollectorChannel(Channel):
    """支持 send_outbound 的 Mock Channel，记录所有出站调用"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id
        self.outbound_calls: list[dict] = []
        self.received_events: list[EventEnvelope] = []

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event: EventEnvelope) -> None:
        self.received_events.append(event)

    async def send_outbound(self, target: str, text: str, msg_type: str = "card") -> dict:
        self.outbound_calls.append({"target": target, "text": text})
        return {"success": True, "message_id": "mock_001"}


class SpyNotificationService:
    """记录通知发送请求的简易替身。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def send(self, notification, channels=None):
        self.calls.append({
            "notification": notification,
            "channels": list(channels or []),
        })
        return {channel: True for channel in channels or []}


@pytest.mark.asyncio
async def test_deliver_text_uses_outbound_when_to_is_set(repo):
    """当 delivery.to 有值时，优先走 send_outbound 而非 deliver_to_channel"""
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch = OutboundCollectorChannel("feishu")
    gateway.register_channel(ch)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    job = CronJob(
        id="test_outbound",
        name="飞书直发",
        session_target="main",
        payload=SystemEventPayload(text="直接发到飞书"),
        delivery=CronDelivery(mode="announce", channel_id="feishu", to="oc_chat_123"),
    )

    await runtime._deliver_text(job, "直接发到飞书")

    # send_outbound 应被调用
    assert len(ch.outbound_calls) == 1
    assert ch.outbound_calls[0]["target"] == "oc_chat_123"
    assert ch.outbound_calls[0]["text"] == "直接发到飞书"
    # 不应走 deliver_to_channel（send_event 不应被调用）
    assert len(ch.received_events) == 0


@pytest.mark.asyncio
async def test_deliver_text_falls_back_to_event_when_no_to(repo):
    """当 delivery.to 为空时，走 deliver_to_channel 事件路径"""
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch = OutboundCollectorChannel("feishu")
    gateway.register_channel(ch)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)

    job = CronJob(
        id="test_fallback",
        session_target="main",
        payload=SystemEventPayload(text="回退投递"),
        delivery=CronDelivery(mode="announce", channel_id="feishu"),
    )

    await runtime._deliver_text(job, "回退投递")

    # 无 to → 不走 send_outbound
    assert len(ch.outbound_calls) == 0
    # 应走 deliver_to_channel
    assert len(ch.received_events) == 1
    assert ch.received_events[0].type == CRON_DELIVERY_REQUESTED


@pytest.mark.asyncio
async def test_deliver_text_routes_websocket_session_to_session_notification(repo):
    """WebSocket 会话提醒应转成会话内通知，而不是直接走 Channel 事件。"""
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    ch_ws = CollectorChannel("websocket")
    gateway.register_channel(ch_ws)
    gateway.bind_session("sess_cron_chat", "websocket")

    notification_service = SpyNotificationService()
    runtime = CronRuntime(
        bus=bus,
        repo=repo,
        gateway=gateway,
        notification_service=notification_service,
    )

    job = CronJob(
        id="test_ws_session_delivery",
        name="聊天提醒",
        session_target="main",
        payload=SystemEventPayload(text="在聊天里提醒我"),
        delivery=CronDelivery(mode="announce", channel_id="websocket", session_id="sess_cron_chat"),
    )

    await runtime._deliver_text(job, "在聊天里提醒我")

    assert ch_ws.received == []
    assert len(notification_service.calls) == 1
    assert notification_service.calls[0]["channels"] == ["session"]
    notification = notification_service.calls[0]["notification"]
    assert notification.session_id == "sess_cron_chat"
    assert notification.metadata["append_to_chat"] is True


@pytest.mark.asyncio
async def test_send_delivery_notifications_filters_supported_channels(repo):
    """Cron 文本通知只向 browser/native 渠道发送。"""
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    notification_service = SpyNotificationService()
    runtime = CronRuntime(
        bus=bus,
        repo=repo,
        gateway=None,
        notification_service=notification_service,
    )

    job = CronJob(
        id="test_notification_channels",
        name="提醒",
        session_target="main",
        payload=SystemEventPayload(text="通知文本"),
        delivery=CronDelivery(
            mode="none",
            session_id="sess_browser_only",
            notification_channels=["browser", "native", "session"],
        ),
    )

    await runtime._send_delivery_notifications(job, "通知文本")

    assert len(notification_service.calls) == 1
    assert notification_service.calls[0]["channels"] == ["browser", "native"]
    notification = notification_service.calls[0]["notification"]
    assert notification.session_id == "sess_browser_only"


@pytest.mark.asyncio
async def test_notify_job_failure_does_not_append_to_chat_when_only_browser_delivery(repo):
    """仅配置 browser/native 时，失败通知不应额外写回聊天会话。"""
    from sensenova_claw.kernel.scheduler.models import CronDelivery, CronJob, SystemEventPayload
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime

    bus = PublicEventBus()
    notification_service = SpyNotificationService()
    runtime = CronRuntime(
        bus=bus,
        repo=repo,
        gateway=None,
        notification_service=notification_service,
    )

    job = CronJob(
        id="test_failure_notification_scope",
        name="失败提醒",
        session_target="main",
        payload=SystemEventPayload(text="失败"),
        delivery=CronDelivery(
            mode="none",
            session_id="sess_browser_only",
            notification_channels=["browser"],
        ),
    )

    await runtime._notify_job_result(
        job=job,
        run_id=7,
        success=False,
        duration_ms=123,
        error="boom",
    )

    assert len(notification_service.calls) == 1
    assert notification_service.calls[0]["channels"] == ["browser"]
    notification = notification_service.calls[0]["notification"]
    assert notification.session_id == "sess_browser_only"


@pytest.mark.asyncio
async def test_cron_tool_add_with_notification_channels_keeps_session_scope(repo):
    """仅开启浏览器/原生通知时，仍保留当前 session 作为通知路由范围。"""
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime
    from sensenova_claw.kernel.scheduler.tool import CronTool

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway)
    tool = CronTool(runtime)

    result = await tool.execute(
        action="add",
        schedule_type="every",
        schedule_value="60000",
        text="浏览器提醒",
        name="浏览器提醒任务",
        send_to_current_session=False,
        notification_channels=["browser"],
        _session_id="sess_browser_scope",
    )

    assert result["success"] is True
    assert result["delivery_session_id"] == "sess_browser_scope"
    assert result["delivery_channel"] is None
    assert result["notification_channels"] == ["browser"]

    jobs = await runtime.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].delivery is not None
    assert jobs[0].delivery.mode == "none"
    assert jobs[0].delivery.session_id == "sess_browser_scope"
