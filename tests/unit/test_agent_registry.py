"""A02/A03/A04: AgentRegistry CRUD + 持久化 + Agent 发现"""
import json
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

    def test_load_email_agent_config_contains_all_email_tools(self):
        project_root = Path(__file__).resolve().parents[2]
        registry = AgentRegistry(config_dir=project_root / ".agentos" / "agents")
        registry.load_from_config(
            {
                "agent": {"model": "mock"},
                "agents": ["email-agent"],
            }
        )

        email_agent = registry.get("email-agent")
        assert email_agent is not None
        assert email_agent.tools == [
            "bash_command",
            "read_file",
            "write_file",
            "send_message",
            "send_email",
            "list_emails",
            "read_email",
            "download_attachment",
            "mark_email",
            "search_emails",
        ]

    def test_update(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="u", name="Old"))
        r.update("u", {"name": "New"})
        assert r.get("u").name == "New"

    def test_update_nonexist(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        assert r.update("nope", {"name": "X"}) is None


# ── per-agent 目录结构持久化测试 ──────────────────────


class TestAgentRegistryDirLayout:

    def test_save_creates_agent_dir_with_config_json(self, tmp_path):
        """save() 将配置写入 agents/{id}/config.json"""
        registry = AgentRegistry(config_dir=tmp_path)
        agent = AgentConfig.create(id="researcher", name="Researcher")
        registry.save(agent)

        config_file = tmp_path / "researcher" / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data["id"] == "researcher"

    def test_load_from_dir_reads_subdir_config_json(self, tmp_path):
        """load_from_dir() 从 agents/{id}/config.json 加载"""
        agent_dir = tmp_path / "writer"
        agent_dir.mkdir()
        data = {"id": "writer", "name": "Writer"}
        (agent_dir / "config.json").write_text(json.dumps(data), encoding="utf-8")

        registry = AgentRegistry(config_dir=tmp_path)
        registry.load_from_dir()
        assert registry.get("writer") is not None
        assert registry.get("writer").name == "Writer"

    def test_load_from_dir_backward_compat_flat_json(self, tmp_path):
        """向后兼容：仍能加载旧的 {id}.json 扁平文件"""
        data = {"id": "legacy", "name": "Legacy Agent"}
        (tmp_path / "legacy.json").write_text(json.dumps(data), encoding="utf-8")

        registry = AgentRegistry(config_dir=tmp_path)
        registry.load_from_dir()
        assert registry.get("legacy") is not None

    def test_delete_removes_agent_dir(self, tmp_path):
        """delete() 删除整个 agent 子目录"""
        registry = AgentRegistry(config_dir=tmp_path)
        agent = AgentConfig.create(id="researcher", name="Researcher")
        registry.register(agent)
        registry.save(agent)

        assert (tmp_path / "researcher" / "config.json").exists()
        registry.delete("researcher")
        assert not (tmp_path / "researcher").exists()
