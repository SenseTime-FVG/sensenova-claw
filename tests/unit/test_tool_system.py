"""工具系统增强单元测试：截断统一、write_file 增强、权限管理"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agentos.kernel.events.bus import PrivateEventBus, PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESPONSE,
)
from agentos.kernel.runtime.workers.tool_worker import ToolSessionWorker
from agentos.capabilities.tools.base import Tool, ToolRiskLevel
from agentos.capabilities.tools.builtin import (
    BashCommandTool,
    FetchUrlTool,
    ReadFileTool,
    SerperSearchTool,
    WriteFileTool,
)
from agentos.capabilities.tools.registry import ToolRegistry


# ---------- 工具风险等级 ----------


class TestToolRiskLevel:
    def test_bash_command_is_high_risk(self):
        tool = BashCommandTool()
        assert tool.risk_level == ToolRiskLevel.HIGH

    def test_write_file_is_medium_risk(self):
        tool = WriteFileTool()
        assert tool.risk_level == ToolRiskLevel.MEDIUM

    def test_read_file_is_low_risk(self):
        tool = ReadFileTool()
        assert tool.risk_level == ToolRiskLevel.LOW

    def test_serper_search_is_low_risk(self):
        tool = SerperSearchTool()
        assert tool.risk_level == ToolRiskLevel.LOW

    def test_fetch_url_is_low_risk(self):
        tool = FetchUrlTool()
        assert tool.risk_level == ToolRiskLevel.LOW


# ---------- write_file 增强 ----------


class TestWriteFileTool:
    @pytest.mark.asyncio
    async def test_write_mode_overwrites(self, tmp_path):
        """mode=write 全量覆盖"""
        f = tmp_path / "test.txt"
        f.write_text("old content", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="new content", mode="write")

        assert result["success"] is True
        assert result["mode"] == "write"
        assert f.read_text(encoding="utf-8") == "new content"

    @pytest.mark.asyncio
    async def test_append_mode(self, tmp_path):
        """mode=append 追加到末尾"""
        f = tmp_path / "test.txt"
        f.write_text("line1\n", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="line2\n", mode="append")

        assert result["success"] is True
        assert result["mode"] == "append"
        assert f.read_text(encoding="utf-8") == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_insert_mode_pure_insert(self, tmp_path):
        """mode=insert + start_line（无 end_line）：纯插入，原内容下移"""
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(
            file_path=str(f), content="inserted\n", mode="insert", start_line=2
        )

        assert result["success"] is True
        assert result["mode"] == "insert"
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert lines[0] == "line1"
        assert lines[1] == "inserted"
        assert lines[2] == "line2"
        assert lines[3] == "line3"

    @pytest.mark.asyncio
    async def test_insert_mode_replace_range(self, tmp_path):
        """mode=insert + start_line + end_line：替换指定行范围"""
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(
            file_path=str(f),
            content="replaced\n",
            mode="insert",
            start_line=2,
            end_line=4,
        )

        assert result["success"] is True
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert lines[0] == "line1"
        assert lines[1] == "replaced"
        assert lines[2] == "line5"

    @pytest.mark.asyncio
    async def test_insert_mode_file_not_exists(self, tmp_path):
        """mode=insert + 文件不存在 → 等同于 write"""
        f = tmp_path / "new_file.txt"

        tool = WriteFileTool()
        result = await tool.execute(
            file_path=str(f), content="new content", mode="insert", start_line=1
        )

        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "new content"

    @pytest.mark.asyncio
    async def test_default_mode_is_write(self, tmp_path):
        """不传 mode 默认为 write"""
        f = tmp_path / "test.txt"

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="content")

        assert result["success"] is True
        assert result["mode"] == "write"
        assert f.read_text(encoding="utf-8") == "content"


# ---------- 结果截断统一 ----------


class TestResultTruncation:
    def _make_worker(self):
        """创建一个 ToolSessionWorker 用于测试截断逻辑"""
        public = PublicEventBus()
        private = PrivateEventBus(session_id="test_session", public_bus=public)
        registry = ToolRegistry()

        class FakeToolRuntime:
            pass

        rt = FakeToolRuntime()
        rt.registry = registry

        return ToolSessionWorker(
            session_id="test_session",
            private_bus=private,
            runtime=rt,
        )

    def test_short_result_not_truncated(self):
        """短结果不截断"""
        worker = self._make_worker()
        result = {"key": "value"}
        with patch("agentos.platform.config.config.config.get") as mock_get:
            mock_get.return_value = 8000
            truncated = worker._truncate_result(result, "tc_12345678")
        assert truncated == result

    def test_long_result_truncated(self):
        """超长结果应被截断"""
        worker = self._make_worker()
        # 生成超过 8000*3=24000 字符的结果
        long_str = "x" * 30000

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("agentos.platform.config.config.config.get") as mock_get:
                def get_side_effect(key, default=None):
                    if key == "tools.result_truncation.max_tokens":
                        return 8000
                    if key == "tools.result_truncation.save_dir":
                        return "workspace"
                    if key == "system.workspace_dir":
                        return tmpdir
                    return default

                mock_get.side_effect = get_side_effect
                truncated = worker._truncate_result(long_str, "tc_12345678")

        assert isinstance(truncated, str)
        assert "[内容已截断]" in truncated
        assert len(truncated) < len(long_str)


# ---------- 权限管理 ----------


class TestPermissionManagement:
    def _make_worker(self):
        """创建 ToolSessionWorker"""
        public = PublicEventBus()
        private = PrivateEventBus(session_id="test_perm", public_bus=public)
        registry = ToolRegistry()

        class FakeToolRuntime:
            pass

        rt = FakeToolRuntime()
        rt.registry = registry

        return ToolSessionWorker(
            session_id="test_perm",
            private_bus=private,
            runtime=rt,
        )

    def test_needs_confirmation_disabled(self):
        """权限管理关闭时不需要确认"""
        worker = self._make_worker()
        tool = BashCommandTool()  # HIGH risk

        with patch("agentos.platform.config.config.config.get") as mock_get:
            mock_get.return_value = False  # permission.enabled = False
            assert worker._needs_confirmation(tool) is False

    def test_needs_confirmation_high_risk_enabled(self):
        """权限管理开启 + HIGH 风险 → 需要确认"""
        worker = self._make_worker()
        tool = BashCommandTool()  # HIGH risk

        with patch("agentos.platform.config.config.config.get") as mock_get:
            def get_side_effect(key, default=None):
                if key == "tools.permission.enabled":
                    return True
                if key == "tools.permission.auto_approve_levels":
                    return ["low"]
                return default

            mock_get.side_effect = get_side_effect
            assert worker._needs_confirmation(tool) is True

    def test_needs_confirmation_low_risk_auto_approved(self):
        """权限管理开启 + LOW 风险 → 自动批准"""
        worker = self._make_worker()
        tool = ReadFileTool()  # LOW risk

        with patch("agentos.platform.config.config.config.get") as mock_get:
            def get_side_effect(key, default=None):
                if key == "tools.permission.enabled":
                    return True
                if key == "tools.permission.auto_approve_levels":
                    return ["low"]
                return default

            mock_get.side_effect = get_side_effect
            assert worker._needs_confirmation(tool) is False

    def test_needs_confirmation_medium_risk_not_auto_approved(self):
        """权限管理开启 + MEDIUM 风险 + 仅 low 自动批准 → 需要确认"""
        worker = self._make_worker()
        tool = WriteFileTool()  # MEDIUM risk

        with patch("agentos.platform.config.config.config.get") as mock_get:
            def get_side_effect(key, default=None):
                if key == "tools.permission.enabled":
                    return True
                if key == "tools.permission.auto_approve_levels":
                    return ["low"]
                return default

            mock_get.side_effect = get_side_effect
            assert worker._needs_confirmation(tool) is True

    def test_needs_confirmation_medium_auto_approved(self):
        """auto_approve_levels 包含 medium 时，MEDIUM 风险自动批准"""
        worker = self._make_worker()
        tool = WriteFileTool()  # MEDIUM risk

        with patch("agentos.platform.config.config.config.get") as mock_get:
            def get_side_effect(key, default=None):
                if key == "tools.permission.enabled":
                    return True
                if key == "tools.permission.auto_approve_levels":
                    return ["low", "medium"]
                return default

            mock_get.side_effect = get_side_effect
            assert worker._needs_confirmation(tool) is False

    @pytest.mark.asyncio
    async def test_confirmation_response_sets_result(self):
        """确认响应应唤醒等待并设置结果"""
        worker = self._make_worker()
        tool_call_id = "tc_confirm_test"

        # 预设一个挂起的确认
        wait_event = asyncio.Event()
        worker._pending_confirmations[tool_call_id] = wait_event

        # 模拟确认响应
        event = EventEnvelope(
            type=TOOL_CONFIRMATION_RESPONSE,
            session_id="test_perm",
            source="ui",
            payload={"tool_call_id": tool_call_id, "approved": True},
        )
        await worker._handle_confirmation_response(event)

        assert worker._confirmation_results[tool_call_id] is True
        assert wait_event.is_set()

    @pytest.mark.asyncio
    async def test_confirmation_response_rejected(self):
        """确认响应拒绝"""
        worker = self._make_worker()
        tool_call_id = "tc_reject_test"

        wait_event = asyncio.Event()
        worker._pending_confirmations[tool_call_id] = wait_event

        event = EventEnvelope(
            type=TOOL_CONFIRMATION_RESPONSE,
            session_id="test_perm",
            source="ui",
            payload={"tool_call_id": tool_call_id, "approved": False},
        )
        await worker._handle_confirmation_response(event)

        assert worker._confirmation_results[tool_call_id] is False
        assert wait_event.is_set()
