"""测试 RegistryEntry 数据类。"""
from sensenova_claw.platform.plugins import RegistryEntry


def test_registry_entry_required_fields():
    entry = RegistryEntry(
        id="core/builtin-tools::bash_command",
        short_id="bash_command",
        owner_plugin="core/builtin-tools",
        owner_team="core",
        visibility="public",
        impl=None,
        metadata={"type": "python"},
    )
    assert entry.id == "core/builtin-tools::bash_command"
    assert entry.short_id == "bash_command"
    assert entry.owner_plugin == "core/builtin-tools"
    assert entry.owner_team == "core"
    assert entry.visibility == "public"
    assert entry.impl is None
    assert entry.metadata == {"type": "python"}


def test_registry_entry_metadata_default_factory_isolates_instances():
    """两个 entry 共享 default_factory 时不能互相污染。"""
    a = RegistryEntry(
        id="a::x", short_id="x", owner_plugin="a",
        owner_team="t", visibility="public", impl=None,
    )
    b = RegistryEntry(
        id="b::y", short_id="y", owner_plugin="b",
        owner_team="t", visibility="public", impl=None,
    )
    a.metadata["k"] = 1
    assert "k" not in b.metadata
