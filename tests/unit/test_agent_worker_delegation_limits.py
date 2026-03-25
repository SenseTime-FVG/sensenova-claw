"""测试 delegation session 的轮次限制。"""
from __future__ import annotations

from sensenova_claw.kernel.runtime.workers.agent_worker import AgentSessionWorker


class TestDelegationSessionLimits:
    def test_is_autonomous_session_with_delegation_meta(self):
        """delegation session（含 message_trace_id）应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"message_trace_id": "rec_123"}
        assert worker._is_autonomous_session() is True

    def test_is_autonomous_session_with_proactive_meta(self):
        """proactive session 仍应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"proactive_job_id": "job_1"}
        assert worker._is_autonomous_session() is True

    def test_is_autonomous_session_with_normal_session(self):
        """普通用户会话不应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"agent_id": "default"}
        assert worker._is_autonomous_session() is False

    def test_is_autonomous_session_with_none_meta(self):
        """session_meta 为 None 时不应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = None
        assert worker._is_autonomous_session() is False
