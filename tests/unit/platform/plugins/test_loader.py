"""测试 PluginLoader 的扫描与注入行为。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.3。
"""
from pathlib import Path

import pytest

from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.commands.registry import CommandRegistry
from sensenova_claw.capabilities.hooks.registry import HookRegistry
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.platform.plugins import (
    BuiltinPluginSource,
    InstallReport,
    PluginLoader,
    PluginManifest,
    UserPluginSource,
)


def _write_full_plugin(root: Path, plugin_id: str, owner: str = "core") -> Path:
    """写一个声明全部 7 类 contribution 的合法 plugin。"""
    pdir = root / plugin_id.replace("/", "__")
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "plugin.yaml").write_text(
        f"""schema_version: "1"
id: {plugin_id}
version: 0.1.0
name: {plugin_id}
description: full plugin
owner: {owner}
visibility: public
contributes:
  llm_providers:
    - id: internal-model
      type: python
      python: providers/internal.py:InternalProvider
  tools:
    - id: send_email
      type: python
      python: tools/email.py:SendEmailTool
  channels:
    - id: slack
      type: python
      python: channels/slack.py:SlackChannel
  skills:
    - id: refund-flow
      path: skills/refund-flow/SKILL.md
  agents:
    - id: customer-support
      path: agents/support/agent.md
  hooks:
    - event: PreTool
      type: subprocess
      command: ["bash", "hooks/audit.sh"]
  commands:
    - id: analyze
      path: commands/analyze.md
""",
        encoding="utf-8",
    )
    return pdir


# ── load_all 行为 ─────────────────────────────────────────────


def test_load_all_returns_manifests_from_all_sources(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    user_root = tmp_path / "user"
    builtin_root.mkdir()
    user_root.mkdir()
    _write_full_plugin(builtin_root, "core/builtin-tools", owner="core")
    _write_full_plugin(user_root, "team-a/crm", owner="team-a")

    loader = PluginLoader(
        sources=[BuiltinPluginSource(builtin_root), UserPluginSource(user_root)]
    )
    manifests = loader.load_all(identity=None)
    ids = sorted(m.id for m in manifests)
    assert ids == ["core/builtin-tools", "team-a/crm"]
    assert all(isinstance(m, PluginManifest) for m in manifests)


def test_load_all_with_identity_none_does_not_filter(tmp_path: Path):
    """P1 阶段 identity=None 不做过滤——P5 才接入 visibility。"""
    user_root = tmp_path / "user"
    user_root.mkdir()
    _write_full_plugin(user_root, "team-a/private-plugin", owner="team-a")
    # 改一份是 private 的
    private = user_root / "team-a__private-plugin" / "plugin.yaml"
    private.write_text(
        private.read_text(encoding="utf-8").replace(
            "visibility: public", "visibility: private"
        ),
        encoding="utf-8",
    )

    loader = PluginLoader(sources=[UserPluginSource(user_root)])
    manifests = loader.load_all(identity=None)
    # 即便 visibility=private，identity=None 时仍然返回
    assert [m.id for m in manifests] == ["team-a/private-plugin"]
    assert manifests[0].visibility == "private"


def test_load_all_empty_when_no_sources():
    loader = PluginLoader(sources=[])
    assert loader.load_all(identity=None) == []
