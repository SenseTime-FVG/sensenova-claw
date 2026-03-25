"""工具系统增强单元测试：截断统一、write_file 增强、权限管理

全部使用真实组件，无 mock/patch。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from sensenova_claw.kernel.events.bus import PrivateEventBus, PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESPONSE,
)
from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.capabilities.tools.builtin import (
    BashCommandTool,
    FetchUrlTool,
    ReadFileTool,
    SerperSearchTool,
    WriteFileTool,
)
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.platform.config.config import Config


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
    async def test_write_mode_overwrites(self, tmp_path):
        """mode=write 全量覆盖"""
        f = tmp_path / "test.txt"
        f.write_text("old content", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="new content", mode="write")

        assert result["success"] is True
        assert result["mode"] == "write"
        assert f.read_text(encoding="utf-8") == "new content"

    async def test_append_mode(self, tmp_path):
        """mode=append 追加到末尾"""
        f = tmp_path / "test.txt"
        f.write_text("line1\n", encoding="utf-8")

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="line2\n", mode="append")

        assert result["success"] is True
        assert result["mode"] == "append"
        assert f.read_text(encoding="utf-8") == "line1\nline2\n"

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

    async def test_insert_mode_file_not_exists(self, tmp_path):
        """mode=insert + 文件不存在 → 等同于 write"""
        f = tmp_path / "new_file.txt"

        tool = WriteFileTool()
        result = await tool.execute(
            file_path=str(f), content="new content", mode="insert", start_line=1
        )

        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "new content"

    async def test_default_mode_is_write(self, tmp_path):
        """不传 mode 默认为 write"""
        f = tmp_path / "test.txt"

        tool = WriteFileTool()
        result = await tool.execute(file_path=str(f), content="content")

        assert result["success"] is True
        assert result["mode"] == "write"
        assert f.read_text(encoding="utf-8") == "content"


# ---------- 辅助函数：创建临时配置的 ToolSessionWorker ----------


def _make_worker(
    session_id: str = "test_session",
    tmp_path: Path | None = None,
    config_overrides: dict | None = None,
):
    """创建带有真实组件的 ToolSessionWorker

    通过临时 config.yml 控制行为，避免使用 mock。
    """
    # 创建临时配置文件
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())

    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)

    # 应用配置覆盖
    if config_overrides:
        for key, value in config_overrides.items():
            cfg.set(key, value)

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(exist_ok=True)
    cfg.set("system.workspace_dir", str(workspace_dir))

    public = PublicEventBus()
    private = PrivateEventBus(session_id=session_id, public_bus=public)
    registry = ToolRegistry()

    agent_config_dir = tmp_path / "agents"
    agent_config_dir.mkdir(exist_ok=True)
    agent_registry = AgentRegistry()
    agent_registry.load_from_config(cfg.data)

    bus_router = BusRouter(public_bus=public)
    rt = ToolRuntime(
        bus_router=bus_router,
        registry=registry,
        agent_registry=agent_registry,
    )

    worker = ToolSessionWorker(
        session_id=session_id,
        private_bus=private,
        runtime=rt,
    )

    return worker, cfg


# ---------- 结果截断统一 ----------


class TestResultTruncation:
    def test_short_result_not_truncated(self, tmp_path):
        """短结果不截断"""
        worker, cfg = _make_worker(tmp_path=tmp_path)

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            result = {"key": "value"}
            truncated = worker._truncate_result(result, "tc_12345678")
            assert truncated == result
        finally:
            tw.config = original_config

    def test_long_result_truncated(self, tmp_path):
        """超长结果应被截断"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.result_truncation.max_tokens": 8000,
            "tools.result_truncation.save_dir": "workspace",
        })

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            # 生成超过 8000*3=24000 字符的结果
            long_str = "x" * 30000
            truncated = worker._truncate_result(long_str, "tc_12345678")
            assert isinstance(truncated, str)
            assert "[内容已截断]" in truncated
            assert len(truncated) < len(long_str)
        finally:
            tw.config = original_config


# ---------- 权限管理 ----------


class TestPermissionManagement:
    def test_needs_confirmation_disabled(self, tmp_path):
        """权限管理关闭时不需要确认"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": False,
        })
        tool = BashCommandTool()  # HIGH risk

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            assert worker._needs_confirmation(tool) is False
        finally:
            tw.config = original_config

    def test_needs_confirmation_high_risk_enabled(self, tmp_path):
        """权限管理开启 + HIGH 风险 → 需要确认"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": ["low"],
        })
        tool = BashCommandTool()  # HIGH risk

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            assert worker._needs_confirmation(tool) is True
        finally:
            tw.config = original_config

    def test_needs_confirmation_low_risk_auto_approved(self, tmp_path):
        """权限管理开启 + LOW 风险 → 自动批准"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": ["low"],
        })
        tool = ReadFileTool()  # LOW risk

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            assert worker._needs_confirmation(tool) is False
        finally:
            tw.config = original_config

    def test_needs_confirmation_medium_risk_not_auto_approved(self, tmp_path):
        """权限管理开启 + MEDIUM 风险 + 仅 low 自动批准 → 需要确认"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": ["low"],
        })
        tool = WriteFileTool()  # MEDIUM risk

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            assert worker._needs_confirmation(tool) is True
        finally:
            tw.config = original_config

    def test_needs_confirmation_medium_auto_approved(self, tmp_path):
        """auto_approve_levels 包含 medium 时，MEDIUM 风险自动批准"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": ["low", "medium"],
        })
        tool = WriteFileTool()  # MEDIUM risk

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            assert worker._needs_confirmation(tool) is False
        finally:
            tw.config = original_config

    async def test_confirmation_response_sets_result(self, tmp_path):
        """确认响应应唤醒等待并设置结果"""
        worker, _ = _make_worker(session_id="test_perm", tmp_path=tmp_path)
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

    async def test_confirmation_response_rejected(self, tmp_path):
        """确认响应拒绝"""
        worker, _ = _make_worker(session_id="test_perm", tmp_path=tmp_path)
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


# ---------- 超时策略 (timeout_action) ----------


class TestTimeoutAction:
    """验证 tools.permission.timeout_action 三种策略"""

    async def test_timeout_action_reject_default(self, tmp_path):
        """默认 reject 策略：超时返回 False"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": [],
            "tools.permission.confirmation_timeout": 0.1,
            # timeout_action 默认为 reject
        })

        tool = BashCommandTool()
        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_session",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": "tc_timeout_reject",
                "tool_name": "bash_command",
                "arguments": {"command": "echo hi"},
            },
        )

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            result = await worker._request_confirmation(event, tool)
            assert result is False
        finally:
            tw.config = original_config

    async def test_timeout_action_approve(self, tmp_path):
        """approve 策略：超时返回 True"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": [],
            "tools.permission.confirmation_timeout": 0.1,
            "tools.permission.timeout_action": "approve",
        })

        tool = BashCommandTool()
        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_session",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": "tc_timeout_approve",
                "tool_name": "bash_command",
                "arguments": {"command": "echo hi"},
            },
        )

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            result = await worker._request_confirmation(event, tool)
            assert result is True
        finally:
            tw.config = original_config

    async def test_timeout_action_block(self, tmp_path):
        """block 策略：无限等待，手动唤醒后返回用户选择"""
        worker, cfg = _make_worker(tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": True,
            "tools.permission.auto_approve_levels": [],
            "tools.permission.timeout_action": "block",
        })

        tool = BashCommandTool()
        tool_call_id = "tc_timeout_block"
        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_session",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": "bash_command",
                "arguments": {"command": "echo hi"},
            },
        )

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg

            # 在后台启动 _request_confirmation，它会无限等待
            async def simulate_user_approve():
                # 等待 pending confirmation 出现
                for _ in range(50):
                    if tool_call_id in worker._pending_confirmations:
                        break
                    await asyncio.sleep(0.01)
                # 模拟用户批准
                worker._confirmation_results[tool_call_id] = True
                worker._pending_confirmations[tool_call_id].set()

            approve_task = asyncio.create_task(simulate_user_approve())
            result = await worker._request_confirmation(event, tool)
            await approve_task

            assert result is True
        finally:
            tw.config = original_config


# ---------- AgentRegistry 注入不污染 arguments ----------


class TestContextInjectionIsolation:
    """验证 _agent_registry 注入不会污染原始 arguments，
    防止 JSON 序列化失败。

    使用真实 ToolRuntime + AgentRegistry，无 mock。
    """

    async def test_arguments_not_polluted_on_success(self, tmp_path):
        """工具执行成功后，原始 arguments 不应包含 _agent_registry"""
        worker, cfg = _make_worker(session_id="test_inject", tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": False,
        })

        # 注册一个简单的真实工具（read_file 是 LOW risk，不需要确认）
        # 用 read_file 读取一个真实文件
        test_file = tmp_path / "test_input.txt"
        test_file.write_text("hello", encoding="utf-8")

        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_inject",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": "tc_success",
                "tool_name": "read_file",
                "arguments": {"file_path": str(test_file)},
            },
        )

        # 收集发布的事件
        published = []
        original_publish = worker.bus.publish

        async def capture_publish(e):
            published.append(e)
            await original_publish(e)

        worker.bus.publish = capture_publish

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            await worker._handle_tool_requested(event)
        finally:
            tw.config = original_config

        # 原始 event payload 中的 arguments 不应被污染
        original_args = event.payload["arguments"]
        assert "_agent_registry" not in original_args

    async def test_arguments_not_polluted_on_failure(self, tmp_path):
        """工具执行失败时，错误事件中的 arguments 必须可 JSON 序列化"""
        worker, cfg = _make_worker(session_id="test_inject", tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": False,
        })

        # 使用 read_file 读取一个不存在的文件，触发工具内部错误
        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_inject",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": "tc_fail",
                "tool_name": "bash_command",
                "arguments": {"command": "exit 1"},
            },
        )

        # 收集发布的事件
        published = []
        original_publish = worker.bus.publish

        async def capture_publish(e):
            published.append(e)
            await original_publish(e)

        worker.bus.publish = capture_publish

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            await worker._handle_tool_requested(event)
        finally:
            tw.config = original_config

        # 所有发布的事件 payload 都必须可 JSON 序列化
        for evt in published:
            try:
                json.dumps(evt.payload, ensure_ascii=False)
            except TypeError as e:
                pytest.fail(f"事件 {evt.type} 的 payload 不可 JSON 序列化: {e}")

        # 原始 arguments 不应包含不可序列化的内部对象
        original_args = event.payload["arguments"]
        assert "_agent_registry" not in original_args

    async def test_event_payload_serializable_for_persistence(self, tmp_path):
        """所有工具执行产生的事件 payload 都必须可 JSON 序列化（用于 SQLite 持久化）"""
        worker, cfg = _make_worker(session_id="test_inject", tmp_path=tmp_path, config_overrides={
            "tools.permission.enabled": False,
        })

        # 使用真实的 read_file 工具读取一个真实文件
        test_file = tmp_path / "serial_test.txt"
        test_file.write_text("serial content", encoding="utf-8")

        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED,
            session_id="test_inject",
            turn_id="turn_1",
            source="agent",
            payload={
                "tool_call_id": "tc_serial",
                "tool_name": "read_file",
                "arguments": {"file_path": str(test_file)},
            },
        )

        published = []
        original_publish = worker.bus.publish

        async def capture_publish(e):
            published.append(e)
            await original_publish(e)

        worker.bus.publish = capture_publish

        import sensenova_claw.kernel.runtime.workers.tool_worker as tw
        original_config = tw.config
        try:
            tw.config = cfg
            await worker._handle_tool_requested(event)
        finally:
            tw.config = original_config

        # 所有发布的事件 payload 都必须可 JSON 序列化
        assert len(published) > 0, "应至少发布一个事件"
        for evt in published:
            try:
                json.dumps(evt.payload, ensure_ascii=False)
            except TypeError as e:
                pytest.fail(f"事件 {evt.type} 的 payload 不可 JSON 序列化: {e}")
