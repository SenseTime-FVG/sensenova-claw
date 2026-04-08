"""
StateTracker 单元测试（TDD）
测试 ResearchState 数据类和 StateTracker 状态管理器
"""
import pytest
from sensenova_claw.capabilities.deep_research.state_tracker import (
    ResearchState,
    StateTracker,
)


# ──────────────────────────────────────────────
# 辅助工具
# ──────────────────────────────────────────────

def make_plan(dim_ids: list[str]) -> dict:
    """构建带维度列表的测试计划"""
    return {
        "title": "测试研究计划",
        "dimensions": [{"id": did, "title": f"维度{did}"} for did in dim_ids],
    }


# ──────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────

class TestCreateState:
    """test_create_state：验证新建状态的初始字段"""

    def test_create_state(self):
        tracker = StateTracker()
        state = tracker.create("r001", "AI 研究趋势")

        assert state.research_id == "r001"
        assert state.query == "AI 研究趋势"
        assert state.status == "plan"
        assert state.plan == {}
        assert state.current_wave == 0
        assert state.dimension_states == {}
        assert state.sub_reports == {}
        assert state.review_history == []
        assert state.retry_counts == {}
        assert state.final_report is None
        assert state.created_at != ""
        assert state.updated_at != ""

    def test_create_returns_research_state_instance(self):
        tracker = StateTracker()
        state = tracker.create("r002", "量子计算")
        assert isinstance(state, ResearchState)

    def test_create_multiple_states_isolated(self):
        tracker = StateTracker()
        s1 = tracker.create("r001", "查询A")
        s2 = tracker.create("r002", "查询B")
        assert s1.research_id != s2.research_id
        assert s1.query != s2.query


class TestGetState:
    """test_get_nonexistent：get 不存在的 ID 应返回 None"""

    def test_get_existing(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        state = tracker.get("r001")
        assert state is not None
        assert state.research_id == "r001"

    def test_get_nonexistent(self):
        tracker = StateTracker()
        result = tracker.get("nonexistent_id")
        assert result is None


class TestUpdateStatus:
    """test_update_status：更新整体研究状态"""

    def test_update_status(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.update_status("r001", "researching")
        state = tracker.get("r001")
        assert state.status == "researching"

    def test_update_status_all_valid_values(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        for status in ("plan", "researching", "reviewing", "reporting", "done", "failed"):
            tracker.update_status("r001", status)
            assert tracker.get("r001").status == status

    def test_update_status_updates_timestamp(self):
        import time
        tracker = StateTracker()
        tracker.create("r001", "查询")
        old_ts = tracker.get("r001").updated_at
        time.sleep(0.01)
        tracker.update_status("r001", "researching")
        new_ts = tracker.get("r001").updated_at
        assert new_ts >= old_ts  # updated_at 应更新或相等


class TestSetPlan:
    """test_set_plan：保存计划并从维度列表初始化 dimension_states"""

    def test_set_plan(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        plan = make_plan(["dim1", "dim2", "dim3"])
        tracker.set_plan("r001", plan)

        state = tracker.get("r001")
        assert state.plan == plan
        # 所有维度应初始化为 pending
        assert state.dimension_states == {
            "dim1": "pending",
            "dim2": "pending",
            "dim3": "pending",
        }

    def test_set_plan_empty_dimensions(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        plan = {"title": "空计划", "dimensions": []}
        tracker.set_plan("r001", plan)
        assert tracker.get("r001").dimension_states == {}

    def test_set_plan_overwrites_previous(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_plan("r001", make_plan(["dim1"]))
        tracker.set_plan("r001", make_plan(["dim2", "dim3"]))
        state = tracker.get("r001")
        assert "dim1" not in state.dimension_states
        assert "dim2" in state.dimension_states


class TestUpdateDimension:
    """test_mark_dimension_in_progress：更新单个维度状态"""

    def test_mark_dimension_in_progress(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_plan("r001", make_plan(["dim1", "dim2"]))
        tracker.update_dimension("r001", "dim1", "in_progress")

        state = tracker.get("r001")
        assert state.dimension_states["dim1"] == "in_progress"
        assert state.dimension_states["dim2"] == "pending"

    def test_update_dimension_various_statuses(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_plan("r001", make_plan(["dim1"]))
        for status in ("pending", "in_progress", "review", "passed", "failed"):
            tracker.update_dimension("r001", "dim1", status)
            assert tracker.get("r001").dimension_states["dim1"] == status


class TestSaveSubReport:
    """test_save_sub_report：保存子报告并将维度标记为 passed"""

    def test_save_sub_report(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_plan("r001", make_plan(["dim1"]))
        tracker.save_sub_report("r001", "dim1", "这是 dim1 的子报告内容")

        state = tracker.get("r001")
        assert state.sub_reports["dim1"] == "这是 dim1 的子报告内容"
        assert state.dimension_states["dim1"] == "passed"

    def test_save_sub_report_multiple_dimensions(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_plan("r001", make_plan(["dim1", "dim2"]))
        tracker.save_sub_report("r001", "dim1", "报告A")
        tracker.save_sub_report("r001", "dim2", "报告B")

        state = tracker.get("r001")
        assert state.sub_reports["dim1"] == "报告A"
        assert state.sub_reports["dim2"] == "报告B"
        assert state.dimension_states["dim1"] == "passed"
        assert state.dimension_states["dim2"] == "passed"


class TestRecordReview:
    """test_record_review：追加到 review_history"""

    def test_record_review(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        review = {"wave": 1, "passed": ["dim1"], "failed": ["dim2"], "comment": "需补充"}
        tracker.record_review("r001", review)

        state = tracker.get("r001")
        assert len(state.review_history) == 1
        assert state.review_history[0] == review

    def test_record_multiple_reviews(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.record_review("r001", {"wave": 1, "comment": "第一次"})
        tracker.record_review("r001", {"wave": 2, "comment": "第二次"})

        state = tracker.get("r001")
        assert len(state.review_history) == 2
        assert state.review_history[1]["comment"] == "第二次"


class TestIncrementRetry:
    """test_increment_retry：递增并返回重试次数"""

    def test_increment_retry(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")

        count1 = tracker.increment_retry("r001", "dim1")
        assert count1 == 1

        count2 = tracker.increment_retry("r001", "dim1")
        assert count2 == 2

    def test_increment_retry_independent_dimensions(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.increment_retry("r001", "dim1")
        tracker.increment_retry("r001", "dim1")
        count_dim2 = tracker.increment_retry("r001", "dim2")
        assert count_dim2 == 1
        assert tracker.get("r001").retry_counts["dim1"] == 2


class TestSetFinalReport:
    """设置最终报告"""

    def test_set_final_report(self):
        tracker = StateTracker()
        tracker.create("r001", "查询")
        tracker.set_final_report("r001", "这是完整的最终报告")

        state = tracker.get("r001")
        assert state.final_report == "这是完整的最终报告"


class TestExportJson:
    """test_export_json：导出 JSON 可序列化字典，sub_reports 截断至 200 字符"""

    def test_export_json(self):
        tracker = StateTracker()
        tracker.create("r001", "量子计算研究")
        plan = make_plan(["dim1", "dim2"])
        tracker.set_plan("r001", plan)
        tracker.save_sub_report("r001", "dim1", "A" * 300)  # 超过 200 字符
        tracker.save_sub_report("r001", "dim2", "短报告")
        tracker.set_final_report("r001", "最终报告内容")
        tracker.record_review("r001", {"wave": 1, "passed": ["dim1"]})

        export = tracker.export_json("r001")

        # 基础字段
        assert export["research_id"] == "r001"
        assert export["query"] == "量子计算研究"
        assert export["status"] == "plan"
        assert export["final_report"] == "最终报告内容"
        assert len(export["review_history"]) == 1

        # sub_reports 截断到 200 字符
        assert len(export["sub_reports"]["dim1"]) == 200
        assert export["sub_reports"]["dim2"] == "短报告"

    def test_export_json_is_json_serializable(self):
        import json
        tracker = StateTracker()
        tracker.create("r001", "查询")
        export = tracker.export_json("r001")
        # 如果不能序列化会抛出异常
        json_str = json.dumps(export, ensure_ascii=False)
        assert "r001" in json_str

    def test_export_json_nonexistent_returns_none(self):
        tracker = StateTracker()
        result = tracker.export_json("nonexistent")
        assert result is None
