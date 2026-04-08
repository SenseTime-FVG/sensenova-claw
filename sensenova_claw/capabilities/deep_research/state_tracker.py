"""
深度研究状态追踪器

ResearchState: 记录单次深度研究会话的完整状态
StateTracker:  内存状态管理器，提供创建/读取/更新等操作，支持导出 JSON
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串"""
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────

@dataclass
class ResearchState:
    """单次深度研究会话的完整状态快照"""

    # 研究标识
    research_id: str
    query: str

    # 整体阶段：plan / researching / reviewing / reporting / done / failed
    status: str = "plan"

    # 研究计划（由 plan-agent 生成）
    plan: dict = field(default_factory=dict)

    # 当前研究波次（从 0 开始，每轮补研加 1）
    current_wave: int = 0

    # 各维度状态：dim_id → pending / in_progress / review / passed / failed
    dimension_states: dict = field(default_factory=dict)

    # 各维度子报告：dim_id → 报告文本
    sub_reports: dict = field(default_factory=dict)

    # 评审历史：每次 review-agent 评审结果的列表
    review_history: list = field(default_factory=list)

    # 各维度重试次数：dim_id → count
    retry_counts: dict = field(default_factory=dict)

    # 最终综合报告（由 report-agent 生成）
    final_report: str | None = None

    # 时间戳
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


# ──────────────────────────────────────────────
# 状态管理器
# ──────────────────────────────────────────────

class StateTracker:
    """深度研究状态管理器（内存存储）

    生命周期：
        plan → researching → reviewing → reporting → done / failed
    """

    def __init__(self) -> None:
        # research_id → ResearchState
        self._states: dict[str, ResearchState] = {}

    # ── 基础 CRUD ──────────────────────────────

    def create(self, research_id: str, query: str) -> ResearchState:
        """新建一个研究状态，初始化所有字段并存入内存"""
        ts = _now_iso()
        state = ResearchState(
            research_id=research_id,
            query=query,
            created_at=ts,
            updated_at=ts,
        )
        self._states[research_id] = state
        return state

    def get(self, research_id: str) -> ResearchState | None:
        """按 ID 获取状态，不存在返回 None"""
        return self._states.get(research_id)

    # ── 状态更新 ───────────────────────────────

    def update_status(self, research_id: str, status: str) -> None:
        """更新整体研究阶段"""
        state = self._states[research_id]
        state.status = status
        state.updated_at = _now_iso()

    def set_plan(self, research_id: str, plan: dict) -> None:
        """保存研究计划，并根据 plan['dimensions'] 初始化各维度状态为 pending"""
        state = self._states[research_id]
        state.plan = plan
        # 用计划中的维度列表重新初始化维度状态（覆盖旧值）
        dimensions: list[dict[str, Any]] = plan.get("dimensions", [])
        state.dimension_states = {dim["id"]: "pending" for dim in dimensions}
        state.updated_at = _now_iso()

    def update_dimension(self, research_id: str, dimension_id: str, status: str) -> None:
        """更新单个维度的状态"""
        state = self._states[research_id]
        state.dimension_states[dimension_id] = status
        state.updated_at = _now_iso()

    def save_sub_report(self, research_id: str, dimension_id: str, report: str) -> None:
        """保存子报告，并将对应维度状态标记为 passed"""
        state = self._states[research_id]
        state.sub_reports[dimension_id] = report
        state.dimension_states[dimension_id] = "passed"
        state.updated_at = _now_iso()

    def record_review(self, research_id: str, review: dict) -> None:
        """将评审结果追加到 review_history"""
        state = self._states[research_id]
        state.review_history.append(review)
        state.updated_at = _now_iso()

    def increment_retry(self, research_id: str, dimension_id: str) -> int:
        """递增指定维度的重试次数，返回递增后的值"""
        state = self._states[research_id]
        count = state.retry_counts.get(dimension_id, 0) + 1
        state.retry_counts[dimension_id] = count
        state.updated_at = _now_iso()
        return count

    def set_final_report(self, research_id: str, report: str) -> None:
        """保存最终综合报告"""
        state = self._states[research_id]
        state.final_report = report
        state.updated_at = _now_iso()

    # ── 导出 ───────────────────────────────────

    def export_json(self, research_id: str) -> dict | None:
        """将状态导出为 JSON 可序列化字典

        说明：
        - sub_reports 中每条报告截断至 200 字符，避免导出文件过大
        - 返回 None 表示 research_id 不存在
        """
        state = self._states.get(research_id)
        if state is None:
            return None

        # sub_reports 截断处理
        truncated_sub_reports = {
            dim_id: text[:200]
            for dim_id, text in state.sub_reports.items()
        }

        return {
            "research_id": state.research_id,
            "query": state.query,
            "status": state.status,
            "plan": state.plan,
            "current_wave": state.current_wave,
            "dimension_states": dict(state.dimension_states),
            "sub_reports": truncated_sub_reports,
            "review_history": list(state.review_history),
            "retry_counts": dict(state.retry_counts),
            "final_report": state.final_report,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }
