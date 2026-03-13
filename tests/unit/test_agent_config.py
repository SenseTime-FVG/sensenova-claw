"""A01: AgentConfig to_dict/from_dict"""
from agentos.capabilities.agents.config import AgentConfig


class TestAgentConfig:
    def test_create_timestamps(self):
        a = AgentConfig.create(id="t", name="T")
        assert a.created_at > 0
        assert a.updated_at > 0

    def test_roundtrip(self):
        a = AgentConfig.create(
            id="t", name="T",
            tools=["bash_command"],
            can_delegate_to=["b"],
        )
        b = AgentConfig.from_dict(a.to_dict())
        assert b.id == a.id
        assert b.tools == a.tools
        assert b.can_delegate_to == a.can_delegate_to

    def test_defaults(self):
        a = AgentConfig(id="m", name="M")
        assert a.provider == "openai"
        assert a.enabled is True
        assert a.temperature == 0.2
        assert a.max_delegation_depth == 3

    def test_from_dict_defaults(self):
        a = AgentConfig.from_dict({"id": "x"})
        assert a.name == "x"
        assert a.provider == "openai"

    def test_to_dict_keys(self):
        a = AgentConfig(id="k", name="K")
        d = a.to_dict()
        expected_keys = {
            "id", "name", "description", "provider", "model",
            "temperature", "max_tokens", "system_prompt", "tools",
            "skills", "can_delegate_to", "max_delegation_depth",
            "enabled", "created_at", "updated_at",
        }
        assert set(d.keys()) == expected_keys
