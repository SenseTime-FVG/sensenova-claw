"""测试 HookRegistry — P1 仅提供空注册表，P6 真正消费 entry。"""
from sensenova_claw.capabilities.hooks.registry import HookRegistry
from sensenova_claw.platform.plugins import RegistryEntry


def _make_entry(short_id: str = "audit", event: str = "PreTool") -> RegistryEntry:
    return RegistryEntry(
        id=f"team-a/crm::{short_id}",
        short_id=short_id,
        owner_plugin="team-a/crm",
        owner_team="team-a",
        visibility="private",
        impl=None,
        metadata={"event": event, "type": "subprocess", "command": ["bash", "audit.sh"]},
    )


def test_register_from_plugin_stores_entry():
    reg = HookRegistry()
    entry = _make_entry()
    reg.register_from_plugin(entry)
    assert reg.get(entry.id) is entry


def test_get_all_returns_registered_entries():
    reg = HookRegistry()
    a = _make_entry("audit", "PreTool")
    b = _make_entry("redact", "PostLLM")
    reg.register_from_plugin(a)
    reg.register_from_plugin(b)
    ids = sorted(e.id for e in reg.get_all())
    assert ids == [a.id, b.id]


def test_register_same_id_overwrites():
    reg = HookRegistry()
    first = _make_entry("audit", "PreTool")
    second = _make_entry("audit", "PreLLM")
    reg.register_from_plugin(first)
    reg.register_from_plugin(second)
    assert reg.get(first.id).metadata["event"] == "PreLLM"
    assert len(reg.get_all()) == 1


def test_get_missing_returns_none():
    reg = HookRegistry()
    assert reg.get("does/not::exist") is None
