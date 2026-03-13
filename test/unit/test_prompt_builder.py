"""B07: PromptBuilder"""
from app.runtime.prompt_builder import (
    build_system_prompt,
    SystemPromptParams,
    ContextFile,
    RuntimeInfo,
)


class TestPromptBuilder:
    def test_none_mode(self):
        params = SystemPromptParams(prompt_mode="none")
        prompt = build_system_prompt(params)
        assert "AgentOS" in prompt
        assert len(prompt) < 200

    def test_full_mode_basic(self):
        params = SystemPromptParams(base_prompt="你是一个助手")
        prompt = build_system_prompt(params)
        assert "你是一个助手" in prompt

    def test_tools_section(self):
        params = SystemPromptParams(
            tool_names=["bash_command", "read_file"],
            tool_summaries={"bash_command": "执行命令", "read_file": "读取文件"},
        )
        prompt = build_system_prompt(params)
        assert "bash_command" in prompt
        assert "read_file" in prompt

    def test_skills_section(self):
        params = SystemPromptParams(
            skills_prompt="<available_skills>\n- pdf_to_markdown\n</available_skills>",
        )
        prompt = build_system_prompt(params)
        assert "pdf_to_markdown" in prompt

    def test_memory_section(self):
        params = SystemPromptParams(memory_context="User prefers Python")
        prompt = build_system_prompt(params)
        assert "User prefers Python" in prompt

    def test_context_files(self):
        params = SystemPromptParams(
            context_files=[ContextFile(name="AGENTS.md", content="# My Agent")],
        )
        prompt = build_system_prompt(params)
        assert "AGENTS.md" in prompt
        assert "# My Agent" in prompt

    def test_context_files_truncation(self):
        """超长文件会被截断"""
        long_content = "x" * 25000
        params = SystemPromptParams(
            context_files=[ContextFile(name="BIG.md", content=long_content)],
        )
        prompt = build_system_prompt(params)
        assert "truncated" in prompt

    def test_runtime_info(self):
        params = SystemPromptParams(
            runtime_info=RuntimeInfo(os="Linux", model="gpt-4o"),
        )
        prompt = build_system_prompt(params)
        assert "os=Linux" in prompt
        assert "model=gpt-4o" in prompt

    def test_workspace_section(self):
        params = SystemPromptParams(workspace_dir="/home/user/workspace")
        prompt = build_system_prompt(params)
        assert "/home/user/workspace" in prompt

    def test_datetime_always_present(self):
        params = SystemPromptParams()
        prompt = build_system_prompt(params)
        assert "当前时间" in prompt

    def test_extra_context(self):
        params = SystemPromptParams(extra_system_prompt="Custom instructions here")
        prompt = build_system_prompt(params)
        assert "Custom instructions here" in prompt
