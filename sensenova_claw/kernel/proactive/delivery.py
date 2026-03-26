"""Proactive 结果投递。"""
from __future__ import annotations
import asyncio
import logging
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import PROACTIVE_RESULT
from sensenova_claw.kernel.notification.models import Notification
from sensenova_claw.kernel.proactive.models import ProactiveJob

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_INTERVAL_S = 3


class ProactiveDelivery:
    def __init__(self, bus, notification_service):
        self._bus = bus
        self._notification_service = notification_service

    async def deliver(
        self, job: ProactiveJob, session_id: str, result: str,
        *,
        source_session_id: str | None = None,
        items: list[dict] | None = None,
    ):
        """投递 proactive 执行结果：发布事件 + 发送通知。"""
        payload = {
            "job_id": job.id,
            "job_name": job.name,
            "result": result,
            "session_id": session_id,
        }
        if source_session_id:
            payload["source_session_id"] = source_session_id
        if job.delivery.recommendation_type:
            payload["recommendation_type"] = job.delivery.recommendation_type
        if items:
            payload["items"] = items

        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_RESULT,
            session_id=session_id,
            agent_id=job.agent_id,
            payload=payload,
            source="proactive",
        ))

        body = await self._build_body(job, result)

        notification = Notification(
            title=f"[Proactive] {job.name}",
            body=body,
            level="info",
            source="system",
            session_id=session_id,
            metadata={"job_id": job.id},
        )
        await self._send_with_retry(notification, job)

    async def _build_body(self, job: ProactiveJob, result: str) -> str:
        """根据 summary_prompt 决定通知正文：有则调用 LLM 摘要，无则截断原文。"""
        summary_prompt = job.delivery.summary_prompt
        if not summary_prompt:
            return result[:500]

        try:
            from sensenova_claw.platform.config.config import config as _cfg
            provider = LLMFactory().get_provider()
            _, model = _cfg.resolve_model()
            messages = [
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": result},
            ]
            resp = await provider.call(model=model, messages=messages, temperature=1.0)
            return resp.get("content", result)[:500]
        except Exception as e:
            logger.warning("LLM 摘要失败，回退到原始结果: %s", e)
            return result[:500]

    async def _send_with_retry(self, notification: Notification, job: ProactiveJob) -> None:
        """发送通知，失败时最多重试 _MAX_RETRIES 次。"""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                await self._notification_service.send(notification, channels=job.delivery.channels)
                return
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    logger.warning("投递通知失败（第 %d 次），%d 秒后重试: %s", attempt, _RETRY_INTERVAL_S, e)
                    await asyncio.sleep(_RETRY_INTERVAL_S)
                else:
                    logger.error("投递通知失败，已达最大重试次数 %d: %s", _MAX_RETRIES, e)
