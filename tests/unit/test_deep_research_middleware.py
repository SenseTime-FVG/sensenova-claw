"""DeepResearchMiddleware 单元测试

测试内容：
- research-agent 子报告完成后触发引用提取
- 非研究 agent 的消息被忽略
- 缺少 research_id 的消息被忽略
- 维度完成事件在 research agent 完成后正确发布
- review-agent / report-agent 完成后正确记录状态
- write_companion_files 正确写出 JSON 文件
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from sensenova_claw.capabilities.deep_research.citation_manager import CitationManager
from sensenova_claw.capabilities.deep_research.middleware import DeepResearchMiddleware
from sensenova_claw.capabilities.deep_research.state_tracker import StateTracker
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import RESEARCH_DIMENSION_COMPLETED


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _make_event(
    session_id: str,
    from_agent: str,
    content: str,
    dimension_id: str,
    research_id: str,
) -> EventEnvelope:
    """构造一个模拟子 agent 完成的事件。"""
    return EventEnvelope(
        type="agent.step_completed",
        session_id=session_id,
        payload={
            "result": {"content": content},
            "meta": {
                "from_agent": from_agent,
                "dimension_id": dimension_id,
                "research_id": research_id,
            },
        },
    )


def _make_bus() -> MagicMock:
    """创建一个 mock EventBus，publish 为 AsyncMock。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


def _setup_state(tracker: StateTracker, research_id: str, dimensions: list[str]) -> None:
    """在 StateTracker 中初始化研究状态。"""
    tracker.create(research_id, "test query")
    tracker.set_plan(research_id, {"dimensions": [{"id": d} for d in dimensions]})
    tracker.update_status(research_id, "researching")


# ── 测试 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDeepResearchMiddleware:
    """DeepResearchMiddleware 核心行为测试。"""

    def setup_method(self) -> None:
        self.citation_mgr = CitationManager()
        self.state_tracker = StateTracker()
        self.bus = _make_bus()
        self.mw = DeepResearchMiddleware(self.citation_mgr, self.state_tracker, self.bus)

    # ── 跳过逻辑 ──────────────────────────────────────────────────────────

    async def test_skip_when_no_research_id(self) -> None:
        """缺少 research_id 的事件应被跳过，不调用 bus.publish。"""
        event = _make_event("s1", "research-agent", "content", "dim1", "")
        await self.mw.on_child_completed(event)
        self.bus.publish.assert_not_called()

    async def test_skip_unknown_agent(self) -> None:
        """未知 agent 类型的事件应被跳过。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        event = _make_event("s1", "some-other-agent", "content", "dim1", "r1")
        await self.mw.on_child_completed(event)
        self.bus.publish.assert_not_called()

    # ── research-agent 完成 ───────────────────────────────────────────────

    async def test_research_agent_triggers_citation_extraction(self) -> None:
        """research-agent 完成后应提取引用并更新维度状态。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        content = (
            "Some findings.\n\n## Sources\n\n"
            "1. [Example](https://example.com)\n"
            "2. [Test](https://test.org)\n"
        )
        event = _make_event("s1", "research-agent", content, "dim1", "r1")
        await self.mw.on_child_completed(event)

        # 引用应已提取到全局池
        assert len(self.citation_mgr.pool) == 2

    async def test_research_agent_updates_dimension_state(self) -> None:
        """research-agent 完成后应将维度状态更新为 review。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        event = _make_event("s1", "research-agent", "report text", "dim1", "r1")
        await self.mw.on_child_completed(event)

        state = self.state_tracker.get("r1")
        assert state is not None
        assert state.dimension_states["dim1"] == "review"

    async def test_research_agent_publishes_dimension_completed(self) -> None:
        """research-agent 完成后应发布 RESEARCH_DIMENSION_COMPLETED 事件。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        event = _make_event("s1", "research-agent", "report", "dim1", "r1")
        await self.mw.on_child_completed(event)

        self.bus.publish.assert_called_once()
        published = self.bus.publish.call_args[0][0]
        assert published.type == RESEARCH_DIMENSION_COMPLETED
        assert published.payload["research_id"] == "r1"
        assert published.payload["dimension_id"] == "dim1"

    # ── review-agent 完成 ─────────────────────────────────────────────────

    async def test_review_agent_records_review(self) -> None:
        """review-agent 完成后应将评审结果记录到 state_tracker。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        review_content = "Review: all good"
        event = _make_event("s1", "review-agent", review_content, "dim1", "r1")
        await self.mw.on_child_completed(event)

        state = self.state_tracker.get("r1")
        assert state is not None
        assert len(state.review_history) == 1
        assert state.review_history[0]["content"] == review_content

    # ── report-agent 完成 ─────────────────────────────────────────────────

    async def test_report_agent_saves_final_report(self) -> None:
        """report-agent 完成后应保存最终报告。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        report_text = "# Final Report\n\nConclusion."
        event = _make_event("s1", "report-agent", report_text, "", "r1")
        await self.mw.on_child_completed(event)

        state = self.state_tracker.get("r1")
        assert state is not None
        assert state.final_report == report_text

    # ── write_companion_files ─────────────────────────────────────────────

    async def test_write_companion_files(self) -> None:
        """write_companion_files 应正确输出 citations.json 和 research_state.json。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        self.state_tracker.set_final_report("r1", "done")

        with tempfile.TemporaryDirectory() as tmpdir:
            await self.mw.write_companion_files("r1", tmpdir)

            citations_path = os.path.join(tmpdir, "citations.json")
            state_path = os.path.join(tmpdir, "research_state.json")

            assert os.path.exists(citations_path)
            assert os.path.exists(state_path)

            with open(citations_path, encoding="utf-8") as f:
                citations_data = json.load(f)
            assert "total_citations" in citations_data

            with open(state_path, encoding="utf-8") as f:
                state_data = json.load(f)
            assert state_data["research_id"] == "r1"

    # ── 内容提取兼容性 ────────────────────────────────────────────────────

    async def test_result_as_string(self) -> None:
        """当 payload['result'] 是字符串时应正确提取内容。"""
        _setup_state(self.state_tracker, "r1", ["dim1"])
        event = EventEnvelope(
            type="agent.step_completed",
            session_id="s1",
            payload={
                "result": "plain string report",
                "meta": {
                    "from_agent": "report-agent",
                    "dimension_id": "",
                    "research_id": "r1",
                },
            },
        )
        await self.mw.on_child_completed(event)

        state = self.state_tracker.get("r1")
        assert state is not None
        assert state.final_report == "plain string report"
