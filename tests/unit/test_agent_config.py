"""A01: AgentConfig to_dict/from_dict"""
from sensenova_claw.capabilities.agents.config import AgentConfig


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
        assert a.model == "gpt-4o-mini"
        assert a.enabled is True
        assert a.temperature == 1.0
        assert a.max_delegation_depth == 3
        assert a.max_pingpong_turns == 10

    def test_from_dict_defaults(self):
        a = AgentConfig.from_dict({"id": "x"})
        assert a.name == "x"
        assert a.model == "gpt-4o-mini"

    def test_to_dict_keys(self):
        a = AgentConfig(id="k", name="K")
        d = a.to_dict()
        expected_keys = {
            "id", "name", "description", "model",
            "temperature", "max_tokens", "extra_body", "system_prompt", "tools",
            "skills", "mcp_servers", "mcp_tools", "workdir", "can_delegate_to", "max_delegation_depth",
            "max_pingpong_turns",
            "enabled", "created_at", "updated_at",
        }
        assert set(d.keys()) == expected_keys

    def test_mcp_policy_roundtrip(self):
        a = AgentConfig.create(
            id="mcp",
            name="MCP",
            mcp_servers=["docs", "browser"],
            mcp_tools=["docs/search", "browser/click"],
        )
        b = AgentConfig.from_dict(a.to_dict())
        assert b.mcp_servers == ["docs", "browser"]
        assert b.mcp_tools == ["docs/search", "browser/click"]

    def test_tri_state_lists_preserve_none(self):
        a = AgentConfig.create(
            id="tri",
            name="Tri",
            tools=None,
            skills=None,
            mcp_servers=None,
            mcp_tools=None,
        )
        d = a.to_dict()
        assert d["tools"] is None
        assert d["skills"] is None
        assert d["mcp_servers"] is None
        assert d["mcp_tools"] is None

        b = AgentConfig.from_dict(d)
        assert b.tools is None
        assert b.skills is None
        assert b.mcp_servers is None
        assert b.mcp_tools is None

    def test_create_supports_send_message_aliases(self):
        a = AgentConfig.create(
            id="alias",
            name="Alias",
            can_send_message_to=["helper"],
            max_send_depth=5,
        )
        assert a.can_delegate_to == ["helper"]
        assert a.can_send_message_to == ["helper"]
        assert a.max_delegation_depth == 5
        assert a.max_send_depth == 5

    def test_from_dict_supports_send_message_aliases(self):
        a = AgentConfig.from_dict(
            {
                "id": "alias",
                "can_send_message_to": ["writer"],
                "max_send_depth": 4,
                "max_pingpong_turns": 7,
            }
        )
        assert a.can_send_message_to == ["writer"]
        assert a.max_send_depth == 4
        assert a.max_pingpong_turns == 7

    def test_extra_body_default_empty(self):
        a = AgentConfig(id="x", name="X")
        assert a.extra_body == {}

    def test_extra_body_roundtrip(self):
        eb = {"thinking": {"type": "adaptive"}, "reasoning_effort": "high"}
        a = AgentConfig.create(id="x", name="X", extra_body=eb)
        d = a.to_dict()
        assert d["extra_body"] == eb
        b = AgentConfig.from_dict(d)
        assert b.extra_body == eb

    def test_extra_body_from_dict_missing(self):
        """extra_body 未配置时默认为空 dict"""
        a = AgentConfig.from_dict({"id": "x"})
        assert a.extra_body == {}

    def test_workdir_default_empty(self):
        a = AgentConfig(id="x", name="X")
        assert a.workdir == ""

    def test_workdir_roundtrip(self):
        a = AgentConfig.create(id="x", name="X", workdir="/custom/path")
        d = a.to_dict()
        assert d["workdir"] == "/custom/path"
        b = AgentConfig.from_dict(d)
        assert b.workdir == "/custom/path"
