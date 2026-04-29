"""测试既有 5 个 Registry 都暴露 register_from_plugin。"""
import pytest

from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.platform.plugins import RegistryEntry


def _entry(short_id: str, plugin: str = "core/builtin-tools", team: str = "core") -> RegistryEntry:
    return RegistryEntry(
        id=f"{plugin}::{short_id}",
        short_id=short_id,
        owner_plugin=plugin,
        owner_team=team,
        visibility="public",
        impl=None,
        metadata={"type": "python"},
    )


def test_tool_registry_register_from_plugin():
    reg = ToolRegistry()
    e = _entry("send_email")
    reg.register_from_plugin(e)
    assert reg.get_plugin_entry(e.id) is e
    assert e in reg.list_plugin_entries()


def test_skill_registry_register_from_plugin():
    reg = SkillRegistry()
    e = _entry("refund-flow", plugin="team-a/crm", team="team-a")
    reg.register_from_plugin(e)
    assert reg.get_plugin_entry(e.id) is e
    assert e in reg.list_plugin_entries()


def test_agent_registry_register_from_plugin():
    reg = AgentRegistry()
    e = _entry("customer-support", plugin="team-a/crm", team="team-a")
    reg.register_from_plugin(e)
    assert reg.get_plugin_entry(e.id) is e
    assert e in reg.list_plugin_entries()


def test_llm_factory_register_from_plugin():
    factory = LLMFactory()
    e = _entry("internal-model", plugin="core/builtin-llm")
    factory.register_from_plugin(e)
    assert factory.get_plugin_entry(e.id) is e
    assert e in factory.list_plugin_entries()


def test_channel_registry_register_from_plugin():
    reg = ChannelRegistry()
    e = _entry("slack", plugin="team-a/crm", team="team-a")
    reg.register_from_plugin(e)
    assert reg.get(e.id) is e
