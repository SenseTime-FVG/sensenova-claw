"""测试 ChannelRegistry — P1 新建的最简 channel 注册表。"""
from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry
from sensenova_claw.platform.plugins import RegistryEntry


def _entry(short_id: str = "slack") -> RegistryEntry:
    return RegistryEntry(
        id=f"team-a/crm::{short_id}",
        short_id=short_id,
        owner_plugin="team-a/crm",
        owner_team="team-a",
        visibility="public",
        impl=None,
        metadata={"type": "python", "python": "channels/slack.py:SlackChannel"},
    )


def test_register_and_get():
    reg = ChannelRegistry()
    e = _entry()
    reg.register_from_plugin(e)
    assert reg.get(e.id) is e


def test_get_all():
    reg = ChannelRegistry()
    reg.register_from_plugin(_entry("slack"))
    reg.register_from_plugin(_entry("feishu"))
    assert {e.short_id for e in reg.get_all()} == {"slack", "feishu"}


def test_missing_returns_none():
    assert ChannelRegistry().get("nope::nope") is None
