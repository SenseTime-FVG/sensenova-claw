"""HeartbeatRuntime 单元测试"""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.kernel.heartbeat.runtime import HeartbeatRuntime, _parse_every_to_seconds


class TestParseEveryToSeconds:
    """时间字符串解析测试"""

    def test_seconds(self):
        assert _parse_every_to_seconds("5s") == 5.0

    def test_minutes(self):
        assert _parse_every_to_seconds("30m") == 1800.0

    def test_hours(self):
        assert _parse_every_to_seconds("1h") == 3600.0

    def test_with_whitespace(self):
        assert _parse_every_to_seconds("  10s  ") == 10.0

    def test_case_insensitive(self):
        assert _parse_every_to_seconds("2M") == 120.0
        assert _parse_every_to_seconds("1H") == 3600.0

    def test_unknown_unit_defaults_to_30m(self):
        assert _parse_every_to_seconds("abc") == 1800.0

    def test_no_unit_defaults_to_30m(self):
        assert _parse_every_to_seconds("100") == 1800.0


@pytest.fixture
def heartbeat_deps():
    """创建 HeartbeatRuntime 依赖"""
    bus = AsyncMock()
    repo = AsyncMock()
    return bus, repo


class TestHeartbeatInit:
    """初始化测试"""

    @patch("agentos.kernel.heartbeat.runtime.config")
    def test_disabled_by_default(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": False,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus, repo = AsyncMock(), AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        assert rt._enabled is False

    @patch("agentos.kernel.heartbeat.runtime.config")
    def test_enabled_with_custom_interval(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "5m",
            "heartbeat.prompt": "custom prompt",
            "heartbeat.ack_max_chars": 100,
        }.get(k, d)
        bus, repo = AsyncMock(), AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        assert rt._enabled is True
        assert rt._every_s == 300.0
        assert rt._prompt == "custom prompt"
        assert rt._ack_max_chars == 100


class TestBuildPrompt:
    """心跳 prompt 构建测试"""

    @patch("agentos.kernel.heartbeat.runtime.config")
    def test_basic_prompt(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "Check status",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        rt = HeartbeatRuntime(AsyncMock(), AsyncMock())
        prompt = rt._build_prompt()
        assert prompt == "Check status"

    @patch("agentos.kernel.heartbeat.runtime.config")
    def test_prompt_with_pending_events(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "Check",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        rt = HeartbeatRuntime(AsyncMock(), AsyncMock())
        rt._pending_system_events = ["任务A完成", "任务B超时"]
        prompt = rt._build_prompt()
        assert "Pending System Events" in prompt
        assert "1. 任务A完成" in prompt
        assert "2. 任务B超时" in prompt


class TestRunHeartbeatOnce:
    """单次心跳执行测试"""

    @patch("agentos.kernel.heartbeat.runtime.config")
    @patch("agentos.kernel.heartbeat.runtime.strip_heartbeat_token")
    async def test_heartbeat_ok_deletes_session(self, mock_strip, mock_config):
        """HEARTBEAT_OK 回复时删除临时 session"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        mock_strip.return_value = MagicMock(should_skip=True, remaining="")

        bus = AsyncMock()
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        # mock _wait_for_completion 返回 HEARTBEAT_OK
        rt._wait_for_completion = AsyncMock(return_value="HEARTBEAT_OK")

        await rt.run_heartbeat_once(reason="test")

        repo.delete_session_cascade.assert_called_once()
        assert rt._busy is False  # 执行完后重置

    @patch("agentos.kernel.heartbeat.runtime.config")
    @patch("agentos.kernel.heartbeat.runtime.strip_heartbeat_token")
    async def test_heartbeat_with_content_keeps_session(self, mock_strip, mock_config):
        """有实际内容时不删除 session"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        mock_strip.return_value = MagicMock(should_skip=False, remaining="需要处理的内容")

        bus = AsyncMock()
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        rt._wait_for_completion = AsyncMock(return_value="需要处理的内容")

        await rt.run_heartbeat_once(reason="test")

        repo.delete_session_cascade.assert_not_called()

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_skip_when_busy(self, mock_config):
        """忙碌时跳过"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        rt._busy = True

        await rt.run_heartbeat_once(reason="test")

        # 忙碌时不发布任何事件
        bus.publish.assert_not_called()

    @patch("agentos.kernel.heartbeat.runtime.config")
    @patch("agentos.kernel.heartbeat.runtime.strip_heartbeat_token")
    async def test_clears_pending_events_after_run(self, mock_strip, mock_config):
        """执行后清空 pending events"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        mock_strip.return_value = MagicMock(should_skip=True, remaining="")

        bus = AsyncMock()
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        rt._wait_for_completion = AsyncMock(return_value="HEARTBEAT_OK")
        rt._pending_system_events = ["event1", "event2"]

        await rt.run_heartbeat_once(reason="test")

        assert rt._pending_system_events == []

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_exception_resets_busy(self, mock_config):
        """异常时也重置 _busy 标志"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        bus.publish.side_effect = RuntimeError("publish 失败")
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)

        await rt.run_heartbeat_once(reason="test")
        assert rt._busy is False


class TestStartStop:
    """启动/停止测试"""

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_start_disabled_does_nothing(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": False,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        # subscribe 需要返回一个异步迭代器
        async def empty_iter():
            return
            yield
        bus.subscribe = empty_iter
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        await rt.start()
        assert rt._event_task is None

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_stop_cleans_up(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        async def blocking_iter():
            await asyncio.Event().wait()
            return
            yield
        bus.subscribe = blocking_iter
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        await rt.start()
        assert rt._event_task is not None
        await rt.stop()
        assert rt._event_task is None


# ---------------------------------------------------------------------------
# 新增：_event_loop 路由逻辑测试
# ---------------------------------------------------------------------------

class TestEventLoop:
    """_event_loop 内部路由逻辑测试"""

    def _make_rt(self, mock_config):
        """构造启用状态的 HeartbeatRuntime"""
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        repo = AsyncMock()
        rt = HeartbeatRuntime(bus, repo)
        return rt, bus

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_cron_system_event_appends_pending(self, mock_config):
        """收到 CRON_SYSTEM_EVENT 时将 text 追加到 _pending_system_events"""
        from agentos.kernel.events.types import CRON_SYSTEM_EVENT
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)

        # 构造一个 CRON_SYSTEM_EVENT 事件，然后用 StopAsyncIteration 结束循环
        event = EventEnvelope(
            type=CRON_SYSTEM_EVENT,
            session_id="system",
            source="cron",
            payload={"text": "任务A已完成"},
        )

        # 模拟 bus.subscribe() 依次产出该事件后结束
        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        await rt._event_loop()

        assert "任务A已完成" in rt._pending_system_events

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_cron_system_event_empty_text_not_appended(self, mock_config):
        """CRON_SYSTEM_EVENT 的 text 为空时不追加"""
        from agentos.kernel.events.types import CRON_SYSTEM_EVENT
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)

        event = EventEnvelope(
            type=CRON_SYSTEM_EVENT,
            session_id="system",
            source="cron",
            payload={"text": ""},  # 空字符串，不应追加
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        await rt._event_loop()

        assert rt._pending_system_events == []

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_heartbeat_wake_requested_triggers_run(self, mock_config):
        """收到 HEARTBEAT_WAKE_REQUESTED 时调用 run_heartbeat_once 并传入 reason"""
        from agentos.kernel.events.types import HEARTBEAT_WAKE_REQUESTED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        rt.run_heartbeat_once = AsyncMock()

        event = EventEnvelope(
            type=HEARTBEAT_WAKE_REQUESTED,
            session_id="system",
            source="external",
            payload={"reason": "manual_trigger"},
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        await rt._event_loop()

        rt.run_heartbeat_once.assert_called_once_with(reason="manual_trigger")

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_heartbeat_wake_requested_default_reason(self, mock_config):
        """HEARTBEAT_WAKE_REQUESTED 不含 reason 时使用默认值 'external'"""
        from agentos.kernel.events.types import HEARTBEAT_WAKE_REQUESTED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        rt.run_heartbeat_once = AsyncMock()

        event = EventEnvelope(
            type=HEARTBEAT_WAKE_REQUESTED,
            session_id="system",
            source="external",
            payload={},  # 无 reason 字段
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        await rt._event_loop()

        rt.run_heartbeat_once.assert_called_once_with(reason="external")

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_unrelated_event_type_is_ignored(self, mock_config):
        """无关事件类型不触发任何行为"""
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        rt.run_heartbeat_once = AsyncMock()

        event = EventEnvelope(
            type="some.unrelated.event",
            session_id="system",
            source="other",
            payload={"text": "should be ignored"},
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        await rt._event_loop()

        rt.run_heartbeat_once.assert_not_called()
        assert rt._pending_system_events == []

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_event_loop_handler_exception_does_not_crash(self, mock_config):
        """单个事件处理抛异常时，循环继续而不崩溃"""
        from agentos.kernel.events.types import HEARTBEAT_WAKE_REQUESTED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        # 让 run_heartbeat_once 抛出异常
        rt.run_heartbeat_once = AsyncMock(side_effect=RuntimeError("boom"))

        event = EventEnvelope(
            type=HEARTBEAT_WAKE_REQUESTED,
            session_id="system",
            source="external",
            payload={"reason": "test"},
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        # _event_loop 应该正常返回，而不是把异常抛出
        await rt._event_loop()  # 不应抛出异常

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_event_loop_cancelled_gracefully(self, mock_config):
        """_event_loop 被取消时安静退出（不抛 CancelledError）"""
        rt, bus = self._make_rt(mock_config)

        # 阻塞的异步迭代器——task 被取消后会触发 CancelledError
        async def blocking_subscribe():
            await asyncio.Event().wait()
            return
            yield  # 使其成为异步生成器

        bus.subscribe = blocking_subscribe

        task = asyncio.create_task(rt._event_loop())
        await asyncio.sleep(0)  # 让 task 开始运行
        task.cancel()
        # 取消后不应向外抛出 CancelledError
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# 新增：_wait_for_completion 超时处理测试
# ---------------------------------------------------------------------------

class TestWaitForCompletion:
    """_wait_for_completion 超时逻辑测试"""

    def _make_rt(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "heartbeat.enabled": True,
            "heartbeat.every": "30m",
            "heartbeat.prompt": "test",
            "heartbeat.ack_max_chars": 300,
        }.get(k, d)
        bus = AsyncMock()
        repo = AsyncMock()
        return HeartbeatRuntime(bus, repo), bus

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_returns_result_on_matching_event(self, mock_config):
        """收到匹配的 AGENT_STEP_COMPLETED 事件时返回 content"""
        from agentos.kernel.events.types import AGENT_STEP_COMPLETED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        session_id = "hb_test_session"

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=session_id,
            source="agent",
            payload={"result": {"content": "巡检完毕，一切正常"}},
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        result = await rt._wait_for_completion(session_id, timeout=5)

        assert result == "巡检完毕，一切正常"

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_ignores_event_with_different_session(self, mock_config):
        """session_id 不匹配的 AGENT_STEP_COMPLETED 不会提前返回，最终超时返回空串"""
        from agentos.kernel.events.types import AGENT_STEP_COMPLETED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        session_id = "hb_correct_session"

        # 发出 session_id 不匹配的事件，然后永远阻塞
        event_wrong = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="hb_wrong_session",  # 不匹配
            source="agent",
            payload={"result": {"content": "不该被采纳的内容"}},
        )

        async def fake_subscribe():
            yield event_wrong
            # 之后永远阻塞，触发超时
            await asyncio.Event().wait()
            return
            yield

        bus.subscribe = fake_subscribe

        # 使用极短超时，让测试快速完成
        result = await rt._wait_for_completion(session_id, timeout=0.05)

        assert result == ""

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_timeout_returns_empty_string(self, mock_config):
        """等待超时时返回空字符串"""
        rt, bus = self._make_rt(mock_config)

        # 永远阻塞的订阅
        async def blocking_subscribe():
            await asyncio.Event().wait()
            return
            yield

        bus.subscribe = blocking_subscribe

        result = await rt._wait_for_completion("hb_timeout_session", timeout=0.05)

        assert result == ""

    @patch("agentos.kernel.heartbeat.runtime.config")
    async def test_missing_content_field_returns_empty(self, mock_config):
        """AGENT_STEP_COMPLETED payload 中缺少 content 字段时返回空字符串"""
        from agentos.kernel.events.types import AGENT_STEP_COMPLETED
        from agentos.kernel.events.envelope import EventEnvelope

        rt, bus = self._make_rt(mock_config)
        session_id = "hb_no_content"

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=session_id,
            source="agent",
            payload={"result": {}},  # 没有 content 字段
        )

        async def fake_subscribe():
            yield event

        bus.subscribe = fake_subscribe

        result = await rt._wait_for_completion(session_id, timeout=5)

        assert result == ""
