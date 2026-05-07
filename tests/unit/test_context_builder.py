"""B08: ContextBuilder"""
from pathlib import Path

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.capabilities.skills.registry import SkillRegistry, Skill
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder


class _SendMessageTool(Tool):
    name = "send_message"
    description = "向其他 Agent 发送消息"
    parameters = {"type": "object", "properties": {}}


class _MockTool(Tool):
    name = "mock_tool"
    description = "测试工具"
    parameters = {"type": "object", "properties": {}}


class _BashTool(Tool):
    name = "bash_command"
    description = "执行命令"
    parameters = {"type": "object", "properties": {}}


class _TodoTool(Tool):
    name = "manage_todolist"
    description = "管理待办事项"
    parameters = {"type": "object", "properties": {}}


class TestContextBuilder:
    def test_build_messages_basic(self):
        cb = ContextBuilder()
        msgs = cb.build_messages("hello")
        assert len(msgs) == 2  # system + user
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "hello" in msgs[1]["content"]

    def test_build_messages_with_history(self):
        cb = ContextBuilder()
        history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "response"}]
        msgs = cb.build_messages("new", history=history)
        assert len(msgs) == 4  # system + 2 history + user
        assert msgs[1]["content"] == "old"

    def test_build_messages_with_image_attachments(self):
        cb = ContextBuilder()
        attachments = [
            {
                "kind": "image",
                "name": "diagram.png",
                "mime_type": "image/png",
                "data": "ZmFrZV9iYXNlNjQ=",
            }
        ]
        msgs = cb.build_messages("解释这张图", attachments=attachments)
        assert msgs[-1]["role"] == "user"
        assert "解释这张图" in msgs[-1]["content"]
        assert msgs[-1]["attachments"] == attachments

    def test_build_messages_with_tools(self):
        tr = ToolRegistry()
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages("hi")
        assert "bash_command" in msgs[0]["content"]

    def test_build_messages_agent_config_filters_tools(self):
        tr = ToolRegistry()
        agent = AgentConfig(id="lim", name="L", tools=["read_file"])
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages("hi", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "read_file" in sys_prompt
        # bash_command 不应出现（除非被允许）
        # 注意 send_message 等保留工具也可能被自动加入

    def test_build_messages_tools_filter_does_not_hide_mcp_tools(self):
        class _Registry:
            def as_llm_tools(self, **kwargs):
                return [
                    {"name": "bash_command", "description": "bash", "parameters": {}},
                    {"name": "read_file", "description": "read", "parameters": {}},
                    {"name": "mcp__browsermcp__browser_snapshot", "description": "snapshot", "parameters": {}},
                ]

        agent = AgentConfig(
            id="lim",
            name="L",
            tools=["bash_command"],
            mcp_servers=["browsermcp"],
            mcp_tools=["browsermcp/browser_snapshot"],
        )
        cb = ContextBuilder(tool_registry=_Registry(), sensenova_claw_home="/tmp")
        msgs = cb.build_messages("hi", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "bash_command" in sys_prompt
        assert "mcp__browsermcp__browser_snapshot" in sys_prompt
        assert "read_file" not in sys_prompt

    def test_build_messages_with_agent_system_prompt(self):
        agent = AgentConfig(id="custom", name="C", system_prompt="你是代码助手")
        cb = ContextBuilder()
        msgs = cb.build_messages("hi", agent_config=agent)
        assert "你是代码助手" in msgs[0]["content"]

    def test_append_tool_result(self):
        cb = ContextBuilder()
        msgs = [{"role": "user", "content": "hi"}]
        msgs = cb.append_tool_result(msgs, "bash_command", {"stdout": "ok"}, "tc_123")
        assert len(msgs) == 2
        assert msgs[1]["role"] == "tool"
        assert msgs[1]["tool_call_id"] == "tc_123"
        assert "ok" in msgs[1]["content"]

    def test_delegation_prompt_injected(self, tmp_path):
        ar = AgentRegistry()
        ar.register(AgentConfig.create(id="main", name="Main"))
        ar.register(AgentConfig.create(id="helper", name="Helper", description="帮助工具"))
        agent = ar.get("main")
        cb = ContextBuilder(agent_registry=ar)
        msgs = cb.build_messages("test", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "helper" in sys_prompt

    def test_build_messages_hides_send_message_when_delegation_disabled(self):
        tr = ToolRegistry()
        tr._tools = {"send_message": _SendMessageTool()}
        agent = AgentConfig(id="lim", name="L", can_delegate_to=None)
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages("hi", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "send_message" not in sys_prompt

    def test_build_messages_hides_disabled_tool_from_agent_preferences(self, tmp_path):
        tr = ToolRegistry()
        tr._tools = {"mock_tool": _MockTool()}
        (tmp_path / ".agent_preferences.json").write_text(
            '{"agent_tools": {"lim": {"mock_tool": false}}}',
            encoding="utf-8",
        )
        agent = AgentConfig(id="lim", name="L")
        cb = ContextBuilder(tool_registry=tr, sensenova_claw_home=str(tmp_path))
        msgs = cb.build_messages("hi", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "mock_tool" not in sys_prompt

    def test_delegation_prompt_hidden_when_send_message_disabled_by_preferences(self, tmp_path):
        tr = ToolRegistry()
        tr._tools = {"send_message": _SendMessageTool()}
        (tmp_path / ".agent_preferences.json").write_text(
            '{"agent_tools": {"main": {"send_message": false}}}',
            encoding="utf-8",
        )
        ar = AgentRegistry()
        ar.register(AgentConfig.create(id="main", name="Main"))
        ar.register(AgentConfig.create(id="helper", name="Helper", description="帮助工具"))
        agent = ar.get("main")
        cb = ContextBuilder(tool_registry=tr, agent_registry=ar, sensenova_claw_home=str(tmp_path))
        msgs = cb.build_messages("test", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "<available_agents>" not in sys_prompt
        assert "send_message 工具向以上 Agent" not in sys_prompt

    def test_skills_section_injected(self, tmp_path):
        sr = SkillRegistry()
        s = Skill("pdf_parse", "Parse PDF", "body", tmp_path)
        # 创建 SKILL.md 以满足 path 属性
        (tmp_path / "SKILL.md").write_text(
            "---\nname: pdf_parse\ndescription: Parse PDF\n---\nbody",
            encoding="utf-8",
        )
        sr.register(s)
        cb = ContextBuilder(skill_registry=sr)
        msgs = cb.build_messages("hi")
        assert "pdf_parse" in msgs[0]["content"]

    def test_global_agents_md_renders_tool_condition_with_tool_names(self):
        tr = ToolRegistry()
        tr._tools = {"manage_todolist": _TodoTool()}
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages(
            "hi",
            context_files=[
                type("CF", (), {
                    "name": "AGENTS.md",
                    "content": "{%- if 'manage_todolist' in tool_names %}\n使用 manage_todolist\n{% endif -%}",
                })(),
            ],
        )
        assert "使用 manage_todolist" in msgs[0]["content"]

    def test_global_agents_md_hides_tool_condition_when_tool_missing(self):
        tr = ToolRegistry()
        tr._tools = {"mock_tool": _MockTool()}
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages(
            "hi",
            context_files=[
                type("CF", (), {
                    "name": "AGENTS.md",
                    "content": "{%- if 'manage_todolist' in tool_names %}\n使用 manage_todolist\n{% endif -%}",
                })(),
            ],
        )
        assert "使用 manage_todolist" not in msgs[0]["content"]

    def test_per_agent_agents_md_keeps_jinja_text_unrendered(self):
        tr = ToolRegistry()
        tr._tools = {"manage_todolist": _TodoTool()}
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages(
            "hi",
            context_files=[
                type("CF", (), {
                    "name": "researcher/AGENTS.md",
                    "content": "{%- if 'manage_todolist' in tool_names %}\n使用 manage_todolist\n{% endif -%}",
                })(),
            ],
        )
        assert "{%- if 'manage_todolist' in tool_names %}" in msgs[0]["content"]

    def test_global_agents_md_renders_nested_tool_conditions(self):
        tr = ToolRegistry()
        tr._tools = {
            "bash_command": _BashTool(),
            "read_file": type("ReadFileTool", (Tool,), {
                "name": "read_file",
                "description": "读取文件",
                "parameters": {"type": "object", "properties": {}},
            })(),
        }
        cb = ContextBuilder(tool_registry=tr)
        msgs = cb.build_messages(
            "hi",
            context_files=[
                type("CF", (), {
                    "name": "AGENTS.md",
                    "content": (
                        "{%- if 'bash_command' in tool_names %}\n"
                        "bash enabled\n"
                        "{%- if 'read_file' in tool_names %}\n"
                        "read enabled\n"
                        "{% endif -%}\n"
                        "{% endif -%}"
                    ),
                })(),
            ],
        )
        assert "bash enabled" in msgs[0]["content"]
        assert "read enabled" in msgs[0]["content"]
        assert "{%- if 'read_file' in tool_names %}" not in msgs[0]["content"]
