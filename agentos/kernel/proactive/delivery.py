"""Proactive 结果投递。"""
from __future__ import annotations
import logging
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import PROACTIVE_RESULT
from agentos.kernel.notification.models import Notification
from agentos.kernel.proactive.models import ProactiveJob

logger = logging.getLogger(__name__)


class ProactiveDelivery:
    def __init__(self, bus, notification_service):
        self._bus = bus
        self._notification_service = notification_service

    async def deliver(self, job: ProactiveJob, session_id: str, result: str):
        """投递 proactive 执行结果：发布事件 + 发送通知。"""
        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_RESULT,
            session_id=session_id,
            agent_id=job.agent_id,
            payload={
                "job_id": job.id,
                "job_name": job.name,
                "result": result,
                "session_id": session_id,
            },
            source="proactive",
        ))

        notification = Notification(
            title=f"[Proactive] {job.name}",
            body=result[:500],
            level="info",
            source="system",
            session_id=session_id,
            metadata={"job_id": job.id},
        )
        try:
            await self._notification_service.send(notification, channels=job.delivery.channels)
        except Exception as e:
            logger.warning("投递通知失败: %s", e)
