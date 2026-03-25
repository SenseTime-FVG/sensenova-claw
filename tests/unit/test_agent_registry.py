"""AgentRegistry CRUD + config 加载 + Agent 发现"""
from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.platform.config.config import Config


class TestAgentRegistry:
    def test_register_get(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="x", name="X"))
        assert r.get("x").name == "X"

    def test_list_all_filters_disabled(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="a", name="A", enabled=True))
        r.register(AgentConfig.create(id="b", name="B", enabled=False))
        assert len(r.list_all()) == 1

    def test_delete_default_forbidden(self):
        r = AgentRegistry()
        r.register(AgentConfig(id="default", name="D"))
        assert r.delete("default") is False

    def test_delete_nonexist(self):
        r = AgentRegistry()
        assert r.delete("nonexist") is False

    def test_delete_existing(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="p", name="P"))
        assert r.delete("p") is True
        assert r.get("p") is None

    def test_load_from_config(self):
        r = AgentRegistry()
        r.load_from_config({
            "agent": {"provider": "openai"},
            "agents": {"res": {"name": "Res"}},
        })
        assert r.get("default") is not None
        assert r.get("res") is not None

    def test_get_delegatable_all(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=[]))
        r.register(AgentConfig.create(id="h", name="H"))
        assert any(a.id == "h" for a in r.get_delegatable("main"))

    def test_get_delegatable_filtered(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        assert [x.id for x in r.get_delegatable("main")] == ["a"]

    def test_get_delegatable_nonexist(self):
        r = AgentRegistry()
        assert r.get_delegatable("nope") == []

    def test_get_sendable_filtered(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="main", name="M", can_send_message_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        assert [x.id for x in r.get_sendable("main")] == ["a"]

    def test_load_from_config_supports_send_message_keys(self):
        r = AgentRegistry()
        r.load_from_config(
            {
                "agent": {"provider": "openai"},
                "agents": {
                    "helper": {
                        "name": "Helper",
                        "can_send_message_to": ["writer"],
                        "max_send_depth": 6,
                        "max_pingpong_turns": 9,
                    }
                },
            }
        )
        helper = r.get("helper")
        assert helper is not None
        assert helper.can_send_message_to == ["writer"]
        assert helper.max_send_depth == 6
        assert helper.max_pingpong_turns == 9

    def test_default_agent_inherits_global_default_model_when_model_omitted(self, tmp_path):
        """default agent 未显式配置 model 时，应继承 llm.default_model。"""
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            "llm:\n"
            "  default_model: gpt-5.4\n"
            "agents:\n"
            "  default:\n"
            "    name: Default Agent\n"
            "    temperature: 0.6\n",
            encoding="utf-8",
        )

        cfg = Config(config_path=config_path)
        r = AgentRegistry()
        r.load_from_config(cfg.data)

        default_agent = r.get("default")
        assert default_agent is not None
        assert default_agent.model == ""

    def test_load_from_config_with_email_agent(self):
        """从 config 加载 email-agent 并验证工具列表"""
        r = AgentRegistry()
        r.load_from_config({
            "agent": {"model": "mock"},
            "agents": {
                "email-agent": {
                    "name": "邮件助手",
                    "tools": [
                        "bash_command", "read_file", "write_file", "send_message",
                        "send_email", "list_emails", "read_email",
                        "download_attachment", "mark_email", "search_emails",
                    ],
                }
            },
        })
        email_agent = r.get("email-agent")
        assert email_agent is not None
        assert "send_email" in email_agent.tools
        assert "list_emails" in email_agent.tools

    def test_update(self):
        r = AgentRegistry()
        r.register(AgentConfig.create(id="u", name="Old"))
        r.update("u", {"name": "New"})
        assert r.get("u").name == "New"

    def test_update_nonexist(self):
        r = AgentRegistry()
        assert r.update("nope", {"name": "X"}) is None

    def test_system_prompt_in_config_raises_error(self):
        """config.yml 中包含 system_prompt 应报错"""
        import pytest
        r = AgentRegistry()
        with pytest.raises(ValueError, match="system_prompt 不应写在 config.yml"):
            r.load_from_config({
                "agents": {
                    "bad-agent": {
                        "name": "Bad",
                        "system_prompt": "不应在这里",
                    }
                },
            })

    def test_system_prompt_loaded_from_file(self, tmp_path):
        """system_prompt 应从 SYSTEM_PROMPT.md 文件加载"""
        prompt_dir = tmp_path / "agents" / "test-agent"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "SYSTEM_PROMPT.md").write_text("你是测试助手。", encoding="utf-8")

        r = AgentRegistry(sensenova_claw_home=tmp_path)
        r.load_from_config({
            "agents": {"test-agent": {"name": "Test"}},
        })
        agent = r.get("test-agent")
        assert agent.system_prompt == "你是测试助手。"

    def test_system_prompt_fallback_to_global(self):
        """无 SYSTEM_PROMPT.md 文件时回退到全局 agent.system_prompt"""
        r = AgentRegistry()
        r.load_from_config({
            "agent": {"system_prompt": "全局默认"},
            "agents": {"test-agent": {"name": "Test"}},
        })
        agent = r.get("test-agent")
        assert agent.system_prompt == "全局默认"

    def test_get_sendable_includes_self_when_empty_whitelist(self):
        """空 can_send_message_to 时，get_sendable 应包含自身（支持自我委派）"""
        r = AgentRegistry()
        r.register(AgentConfig.create(id="search", name="Search", can_send_message_to=[]))
        r.register(AgentConfig.create(id="helper", name="Helper"))
        sendable_ids = [a.id for a in r.get_sendable("search")]
        assert "search" in sendable_ids
        assert "helper" in sendable_ids

    def test_get_sendable_explicit_whitelist_unchanged(self):
        """显式 can_send_message_to 列表行为不变"""
        r = AgentRegistry()
        r.register(AgentConfig.create(id="main", name="M", can_send_message_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        sendable_ids = [a.id for a in r.get_sendable("main")]
        assert sendable_ids == ["a"]
