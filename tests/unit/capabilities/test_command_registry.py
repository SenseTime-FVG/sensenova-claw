"""测试 CommandRegistry — P1 仅提供空注册表。"""
from sensenova_claw.capabilities.commands.registry import CommandRegistry
from sensenova_claw.platform.plugins import RegistryEntry


def _make_entry(short_id: str = "analyze") -> RegistryEntry:
    return RegistryEntry(
        id=f"team-a/crm::{short_id}",
        short_id=short_id,
        owner_plugin="team-a/crm",
        owner_team="team-a",
        visibility="public",
        impl=None,
        metadata={"path": "commands/analyze.md"},
    )


def test_register_from_plugin_stores_entry():
    reg = CommandRegistry()
    entry = _make_entry()
    reg.register_from_plugin(entry)
    assert reg.get(entry.id) is entry


def test_get_all_returns_registered_entries():
    reg = CommandRegistry()
    reg.register_from_plugin(_make_entry("a"))
    reg.register_from_plugin(_make_entry("b"))
    assert {e.short_id for e in reg.get_all()} == {"a", "b"}


def test_get_missing_returns_none():
    reg = CommandRegistry()
    assert reg.get("nope::nope") is None
