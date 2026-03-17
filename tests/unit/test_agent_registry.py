"""A02/A03/A04: AgentRegistry CRUD + 持久化 + Agent 发现"""
from pathlib import Path
from agentos.capabilities.agents.config import AgentConfig
from agentos.capabilities.agents.registry import AgentRegistry


class TestAgentRegistry:
    def test_register_get(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="x", name="X"))
        assert r.get("x").name == "X"

    def test_list_all_filters_disabled(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="a", name="A", enabled=True))
        r.register(AgentConfig.create(id="b", name="B", enabled=False))
        assert len(r.list_all()) == 1

    def test_delete_default_forbidden(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig(id="default", name="D"))
        assert r.delete("default") is False

    def test_delete_nonexist(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        assert r.delete("nonexist") is False

    def test_save_load_roundtrip(self, tmp_path):
        d = tmp_path / "a"
        r1 = AgentRegistry(config_dir=d)
        a = AgentConfig.create(id="p", name="P")
        r1.register(a)
        r1.save(a)

        r2 = AgentRegistry(config_dir=d)
        r2.load_from_dir()
        assert r2.get("p").name == "P"

    def test_load_from_config(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.load_from_config({
            "agent": {"provider": "openai"},
            "agents": {"res": {"name": "Res"}},
        })
        assert r.get("default") is not None
        assert r.get("res") is not None

    def test_get_delegatable_all(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=[]))
        r.register(AgentConfig.create(id="h", name="H"))
        assert any(a.id == "h" for a in r.get_delegatable("main"))

    def test_get_delegatable_filtered(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        assert [x.id for x in r.get_delegatable("main")] == ["a"]

    def test_get_delegatable_nonexist(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        assert r.get_delegatable("nope") == []

    def test_get_sendable_filtered(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="main", name="M", can_send_message_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        assert [x.id for x in r.get_sendable("main")] == ["a"]

    def test_load_from_config_supports_send_message_keys(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
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

    def test_update(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="u", name="Old"))
        r.update("u", {"name": "New"})
        assert r.get("u").name == "New"

    def test_update_nonexist(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        assert r.update("nope", {"name": "X"}) is None
