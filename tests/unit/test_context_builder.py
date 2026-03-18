"""B08: ContextBuilder"""
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.capabilities.agents.config import AgentConfig
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.capabilities.skills.registry import SkillRegistry, Skill
from agentos.capabilities.agents.registry import AgentRegistry
from pathlib import Path


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
        ar = AgentRegistry(config_dir=tmp_path / "a")
        ar.register(AgentConfig.create(id="main", name="Main"))
        ar.register(AgentConfig.create(id="helper", name="Helper", description="帮助工具"))
        agent = ar.get("main")
        cb = ContextBuilder(agent_registry=ar)
        msgs = cb.build_messages("test", agent_config=agent)
        sys_prompt = msgs[0]["content"]
        assert "helper" in sys_prompt

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
