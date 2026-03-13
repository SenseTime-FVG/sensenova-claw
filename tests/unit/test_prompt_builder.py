"""prompt_builder 单元测试

测试 build_system_prompt() 纯函数及各 Section builder。
"""

from __future__ import annotations

import pytest

from agentos.kernel.runtime.prompt_builder import (
    ContextFile,
    RuntimeInfo,
    SystemPromptParams,
    build_system_prompt,
)


class TestBuildSystemPromptModes:
    """测试 prompt_mode 控制"""

    def test_none_mode_returns_fallback(self):
        params = SystemPromptParams(prompt_mode="none")
        result = build_system_prompt(params)
        assert result == "You are a personal assistant running inside AgentOS."

    def test_full_mode_includes_identity(self):
        params = SystemPromptParams(
            prompt_mode="full",
            base_prompt="你是一个有用的AI助手。",
        )
        result = build_system_prompt(params)
        assert "你是一个有用的AI助手。" in result


class TestIdentitySection:
    """测试 Section 1: Identity"""

    def test_uses_base_prompt(self):
        params = SystemPromptParams(base_prompt="Custom identity")
        result = build_system_prompt(params)
        assert "Custom identity" in result

    def test_default_identity_when_empty(self):
        params = SystemPromptParams(base_prompt="")
        result = build_system_prompt(params)
        assert "AgentOS" in result

    def test_default_identity_when_whitespace(self):
        params = SystemPromptParams(base_prompt="   ")
        result = build_system_prompt(params)
        assert "AgentOS" in result


class TestToolingSection:
    """测试 Section 2: Tooling"""

    def test_tooling_with_names_and_summaries(self):
        params = SystemPromptParams(
            base_prompt="test",
            tool_names=["bash_command", "read_file"],
            tool_summaries={"bash_command": "执行命令", "read_file": "读取文件"},
        )
        result = build_system_prompt(params)
        assert "## Available Tools" in result
        assert "bash_command" in result
        assert "执行命令" in result
        assert "read_file" in result

    def test_tooling_empty_when_no_tools(self):
        params = SystemPromptParams(base_prompt="test", tool_names=[])
        result = build_system_prompt(params)
        assert "## Available Tools" not in result

    def test_tooling_name_without_summary(self):
        params = SystemPromptParams(
            base_prompt="test",
            tool_names=["unknown_tool"],
            tool_summaries={},
        )
        result = build_system_prompt(params)
        assert "**unknown_tool**" in result


class TestSkillsSection:
    """测试 Section 3: Skills"""

    def test_skills_included_when_present(self):
        params = SystemPromptParams(
            base_prompt="test",
            skills_prompt="<available_skills>\n- pdf: Convert PDF\n</available_skills>",
        )
        result = build_system_prompt(params)
        assert "<available_skills>" in result
        assert "pdf" in result

    def test_skills_skipped_when_none(self):
        params = SystemPromptParams(base_prompt="test", skills_prompt=None)
        result = build_system_prompt(params)
        assert "<available_skills>" not in result

    def test_skills_skipped_when_empty(self):
        params = SystemPromptParams(base_prompt="test", skills_prompt="  ")
        result = build_system_prompt(params)
        assert "<available_skills>" not in result


class TestMemorySection:
    """测试 Section 4: Memory"""

    def test_memory_included_when_present(self):
        params = SystemPromptParams(
            base_prompt="test",
            memory_context="用户上次提到他喜欢 Python。",
        )
        result = build_system_prompt(params)
        assert "## Memory" in result
        assert "用户上次提到他喜欢 Python。" in result

    def test_memory_skipped_when_none(self):
        params = SystemPromptParams(base_prompt="test", memory_context=None)
        result = build_system_prompt(params)
        assert "## Memory" not in result


class TestContextFilesSection:
    """测试 Section 5: Context Files"""

    def test_context_files_included(self):
        files = [
            ContextFile(name="AGENTS.md", content="Agent rules here"),
            ContextFile(name="USER.md", content="User prefs here"),
        ]
        params = SystemPromptParams(base_prompt="test", context_files=files)
        result = build_system_prompt(params)
        assert "## Project Context" in result
        assert "### AGENTS.md" in result
        assert "Agent rules here" in result
        assert "### USER.md" in result
        assert "User prefs here" in result

    def test_context_files_skipped_when_empty(self):
        params = SystemPromptParams(base_prompt="test", context_files=[])
        result = build_system_prompt(params)
        assert "## Project Context" not in result

    def test_single_file_truncation(self):
        """单文件 > 20000 字符截断"""
        long_content = "x" * 25000
        files = [ContextFile(name="AGENTS.md", content=long_content)]
        params = SystemPromptParams(base_prompt="test", context_files=files)
        result = build_system_prompt(params)
        assert "...[truncated]" in result
        # 确保截断后不包含完整的 25000 个字符
        assert long_content not in result

    def test_total_truncation_preserves_priority(self):
        """总计 > 50000 字符按优先级裁剪（AGENTS.md > USER.md）"""
        agents_content = "A" * 30000
        user_content = "U" * 30000
        files = [
            ContextFile(name="AGENTS.md", content=agents_content),
            ContextFile(name="USER.md", content=user_content),
        ]
        params = SystemPromptParams(base_prompt="test", context_files=files)
        result = build_system_prompt(params)
        # AGENTS.md 被截断到 20000（单文件限制），但应完整保留
        # USER.md 可能被进一步裁剪
        assert "### AGENTS.md" in result


class TestDateTimeSection:
    """测试 Section 6: Date & Time"""

    def test_datetime_always_present(self):
        params = SystemPromptParams(base_prompt="test")
        result = build_system_prompt(params)
        assert "当前时间:" in result
        assert "系统:" in result


class TestExtraSection:
    """测试 Section 7: Extra Context"""

    def test_extra_included_when_present(self):
        params = SystemPromptParams(
            base_prompt="test",
            extra_system_prompt="请始终用英文回答。",
        )
        result = build_system_prompt(params)
        assert "## Extra Context" in result
        assert "请始终用英文回答。" in result

    def test_extra_skipped_when_none(self):
        params = SystemPromptParams(base_prompt="test", extra_system_prompt=None)
        result = build_system_prompt(params)
        assert "## Extra Context" not in result


class TestRuntimeSection:
    """测试 Section 8: Runtime"""

    def test_runtime_info_formatted(self):
        info = RuntimeInfo(
            os="Windows (x86_64)",
            python="3.12",
            model="gpt-4o-mini",
            channel="websocket",
        )
        params = SystemPromptParams(base_prompt="test", runtime_info=info)
        result = build_system_prompt(params)
        assert "Runtime:" in result
        assert "os=Windows (x86_64)" in result
        assert "python=3.12" in result
        assert "model=gpt-4o-mini" in result
        assert "channel=websocket" in result

    def test_runtime_skipped_when_none(self):
        params = SystemPromptParams(base_prompt="test", runtime_info=None)
        result = build_system_prompt(params)
        assert "Runtime:" not in result

    def test_runtime_partial_info(self):
        info = RuntimeInfo(os="Linux", model="gpt-4o")
        params = SystemPromptParams(base_prompt="test", runtime_info=info)
        result = build_system_prompt(params)
        assert "os=Linux" in result
        assert "model=gpt-4o" in result
        assert "python=" not in result


class TestFullPromptAssembly:
    """测试完整 prompt 组装"""

    def test_all_sections_present(self):
        params = SystemPromptParams(
            prompt_mode="full",
            base_prompt="你是AI助手",
            tool_names=["bash_command"],
            tool_summaries={"bash_command": "执行命令"},
            skills_prompt="<available_skills>\n- pdf: PDF处理\n</available_skills>",
            memory_context="用户喜欢Python",
            context_files=[ContextFile(name="AGENTS.md", content="Agent rules")],
            extra_system_prompt="额外指令",
            runtime_info=RuntimeInfo(os="Windows", python="3.12", model="gpt-4o"),
        )
        result = build_system_prompt(params)
        assert "你是AI助手" in result
        assert "## Available Tools" in result
        assert "<available_skills>" in result
        assert "## Memory" in result
        assert "## Project Context" in result
        assert "当前时间:" in result
        assert "## Extra Context" in result
        assert "Runtime:" in result
