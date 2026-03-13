"""HeartbeatRuntime — 心跳巡检

周期性 Agent 巡检，结合 HEARTBEAT_OK 协议决定是否投递结果。
Phase 1: 单次执行 + HEARTBEAT_OK + 临时 session 清理。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from agentos.platform.config.config import config
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_SYSTEM_EVENT,
    HEARTBEAT_CHECK_STARTED,
    HEARTBEAT_COMPLETED,
    HEARTBEAT_WAKE_REQUESTED,
    USER_INPUT,
)
from agentos.kernel.heartbeat.protocol import strip_heartbeat_token

logger = logging.getLogger(__name__)


def _parse_every_to_seconds(every: str) -> float:
    """解析 '30m', '1h', '5s' 等时间字符串为秒数"""
    every = every.strip().lower()
    if every.endswith("m"):
        return float(every[:-1]) * 60
    elif every.endswith("h"):
        return float(every[:-1]) * 3600
    elif every.endswith("s"):
        return float(every[:-1])
    return 1800.0  # 默认 30 分钟


class HeartbeatRuntime:
    """心跳巡检运行时"""

    def __init__(self, bus: PublicEventBus, repo: Repository):
        self._bus = bus
        self._repo = repo
        self._enabled = config.get("heartbeat.enabled", False)
        self._every_s = _parse_every_to_seconds(config.get("heartbeat.every", "30m"))
        self._prompt = config.get(
            "heartbeat.prompt",
            "Read HEARTBEAT.md if it exists. Follow it strictly. If nothing needs attention, reply HEARTBEAT_OK.",
        )
        self._ack_max_chars = config.get("heartbeat.ack_max_chars", 300)
        self._timer_task: asyncio.Task | None = None
        self._event_task: asyncio.Task | None = None
        self._pending_system_events: list[str] = []
        self._busy = False

    async def start(self) -> None:
        if not self._enabled:
            logger.info("HeartbeatRuntime disabled by config")
            return
        logger.info("HeartbeatRuntime starting (every=%ss)", self._every_s)
        self._event_task = asyncio.create_task(self._event_loop())
        self._schedule_next()

    async def stop(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None
        if self._event_task:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None
        logger.info("HeartbeatRuntime stopped")

    # ---------- 定时触发 ----------

    def _schedule_next(self) -> None:
        """安排下一次定时心跳"""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._timer_loop())

    async def _timer_loop(self) -> None:
        """定时器：等待后触发心跳"""
        try:
            await asyncio.sleep(self._every_s)
            await self.run_heartbeat_once(reason="scheduled")
        except asyncio.CancelledError:
            return
        finally:
            # 无论成功/失败都重新调度
            if self._enabled:
                self._schedule_next()

    # ---------- 事件监听 ----------

    async def _event_loop(self) -> None:
        """订阅 PublicEventBus，监听 cron.system_event 和 heartbeat.wake_requested"""
        try:
            async for event in self._bus.subscribe():
                try:
                    if event.type == CRON_SYSTEM_EVENT:
                        text = event.payload.get("text", "")
                        if text:
                            self._pending_system_events.append(text)
                    elif event.type == HEARTBEAT_WAKE_REQUESTED:
                        reason = event.payload.get("reason", "external")
                        await self.run_heartbeat_once(reason=reason)
                except Exception:
                    logger.exception("HeartbeatRuntime event_loop handler error")
        except asyncio.CancelledError:
            pass

    # ---------- 单次执行 ----------

    async def run_heartbeat_once(self, reason: str = "unknown") -> None:
        """执行一次心跳巡检"""
        if self._busy:
            logger.debug("Heartbeat busy, skipping (reason=%s)", reason)
            return

        self._busy = True
        session_id = f"hb_{uuid.uuid4().hex[:12]}"
        try:
            # 发布 heartbeat.check_started
            await self._bus.publish(EventEnvelope(
                type=HEARTBEAT_CHECK_STARTED,
                session_id="system",
                source="heartbeat",
                payload={"reason": reason},
            ))

            # 构建 prompt
            prompt = self._build_prompt()

            # 创建临时 session
            await self._repo.create_session(session_id, meta={"type": "heartbeat", "reason": reason})

            # 发布 user.input 触发 Agent Turn
            turn_id = f"turn_{uuid.uuid4().hex[:12]}"
            await self._bus.publish(EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source="heartbeat",
                payload={"content": prompt},
            ))

            # 等待 agent.step_completed
            result_text = await self._wait_for_completion(session_id, timeout=120)

            # 处理结果
            strip = strip_heartbeat_token(result_text, self._ack_max_chars)

            if strip.should_skip:
                logger.info("Heartbeat OK (reason=%s), 清理 session %s", reason, session_id)
                await self._repo.delete_session_cascade(session_id)
            else:
                # 有内容需要投递（Phase 2 实现投递逻辑）
                logger.info("Heartbeat 有内容 (reason=%s): %s", reason, strip.remaining[:100])

            # 清空已消费的 pending events
            self._pending_system_events.clear()

            # 发布 heartbeat.completed
            await self._bus.publish(EventEnvelope(
                type=HEARTBEAT_COMPLETED,
                session_id=session_id,
                source="heartbeat",
                payload={
                    "reason": reason,
                    "ok": strip.should_skip,
                    "content": strip.remaining[:200] if not strip.should_skip else "",
                },
            ))

        except Exception:
            logger.exception("Heartbeat execution failed (reason=%s)", reason)
        finally:
            self._busy = False

    # ---------- 内部方法 ----------

    def _build_prompt(self) -> str:
        """构建心跳 prompt，注入 pending system events"""
        parts = [self._prompt]
        if self._pending_system_events:
            parts.append("\n\n## Pending System Events:")
            for i, text in enumerate(self._pending_system_events, 1):
                parts.append(f"{i}. {text}")
        return "\n".join(parts)

    async def _wait_for_completion(self, session_id: str, timeout: float = 120) -> str:
        """订阅 PublicEventBus 等待 AGENT_STEP_COMPLETED"""
        result_text = ""

        async def _wait() -> None:
            nonlocal result_text
            async for event in self._bus.subscribe():
                if (
                    event.type == AGENT_STEP_COMPLETED
                    and event.session_id == session_id
                ):
                    result_text = event.payload.get("result", {}).get("content", "")
                    return

        try:
            await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Heartbeat 超时 session=%s", session_id)

        return result_text
