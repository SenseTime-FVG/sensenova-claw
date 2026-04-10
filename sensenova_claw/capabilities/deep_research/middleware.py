"""DeepResearchMiddleware — 透明中间件

在 AgentMessageCoordinator 的子 agent 完成回调中运行，
根据 meta.from_agent 路由处理 research / report 完成事件。
对不包含 research_id 的普通消息完全透明（直接跳过）。
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from sensenova_claw.capabilities.deep_research.citation_manager import CitationManager
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import RESEARCH_DIMENSION_COMPLETED

if TYPE_CHECKING:
    from sensenova_claw.kernel.events.bus import PublicEventBus

logger = logging.getLogger(__name__)


def _extract_content(payload: dict) -> str:
    """从事件 payload 中提取内容文本，兼容 dict 和 str 两种 result 格式。"""
    result = payload.get("result", "")
    if isinstance(result, dict):
        return str(result.get("content", ""))
    if result is not None:
        return str(result)
    return ""


class DeepResearchMiddleware:
    """深度研究透明中间件。

    挂载到 AgentMessageCoordinator 的 on_child_completed hook，
    根据 event.payload.meta.from_agent 将完成事件路由到对应处理方法。
    """

    def __init__(
        self,
        citation_manager: CitationManager,
        bus: "PublicEventBus",
    ) -> None:
        self._citation_manager = citation_manager
        self._bus = bus

    # ── 主入口 ────────────────────────────────────────────────────────────

    async def on_child_completed(self, event: EventEnvelope) -> None:
        """主 hook，由 coordinator 在子 agent 完成时调用。

        根据 meta.from_agent 路由到具体处理方法；
        若 meta 中无 research_id，则直接跳过。
        """
        meta = event.payload.get("meta", {})
        research_id = meta.get("research_id", "")
        if not research_id:
            return

        from_agent = meta.get("from_agent", "")
        dimension_id = meta.get("dimension_id", "")

        if from_agent.startswith("research-agent"):
            await self._handle_research_completed(event, research_id, dimension_id)
        else:
            logger.debug(
                "deep_research middleware: from_agent=%s，跳过 research_id=%s",
                from_agent,
                research_id,
            )

    # ── 内部处理方法 ──────────────────────────────────────────────────────

    async def _handle_research_completed(
        self,
        event: EventEnvelope,
        research_id: str,
        dimension_id: str,
    ) -> None:
        """处理 research-agent 子报告完成：提取引用并发布完成事件。"""
        content = _extract_content(event.payload)

        # 提取引用并注册到全局引用池
        self._citation_manager.extract_and_register(content, dimension_id)

        # 发布维度完成事件
        dim_event = EventEnvelope(
            type=RESEARCH_DIMENSION_COMPLETED,
            session_id=event.session_id,
            payload={
                "research_id": research_id,
                "dimension_id": dimension_id,
            },
            source="deep_research",
        )
        await self._bus.publish(dim_event)

        logger.info(
            "research-agent 完成: research_id=%s dimension=%s",
            research_id,
            dimension_id,
        )

    # ── 辅助文件输出 ──────────────────────────────────────────────────────

    async def write_citations_file(self, report_dir: str) -> None:
        """将 citations.json 写入报告目录。"""
        os.makedirs(report_dir, exist_ok=True)

        citations_path = os.path.join(report_dir, "citations.json")
        citations_data = self._citation_manager.export_json()
        with open(citations_path, "w", encoding="utf-8") as f:
            json.dump(citations_data, f, ensure_ascii=False, indent=2)

        logger.info("citations.json 已写入: %s", report_dir)
