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


# ── install_into_registries 行为 ──────────────────────────────


def _make_registries():
    return {
        "tool_registry": ToolRegistry(),
        "skill_registry": SkillRegistry(),
        "llm_registry": LLMFactory(),
        "channel_registry": ChannelRegistry(),
        "agent_registry": AgentRegistry(),
        "hook_registry": HookRegistry(),
        "command_registry": CommandRegistry(),
    }


def test_install_routes_each_contribution_to_correct_registry(tmp_path: Path):
    user_root = tmp_path / "user"
    user_root.mkdir()
    _write_full_plugin(user_root, "team-a/full")

    loader = PluginLoader(sources=[UserPluginSource(user_root)])
    manifests = loader.load_all()
    regs = _make_registries()

    report = loader.install_into_registries(manifests, **regs)

    assert isinstance(report, InstallReport)
    assert report.ok, f"failures={report.failures!r}"
    # 7 类各 1 条
    assert report.installed == 7

    # 每个 Registry 都拿到一条带正确 namespace 的 entry
    assert regs["llm_registry"].get_plugin_entry("team-a/full::internal-model") is not None
    assert regs["tool_registry"].get_plugin_entry("team-a/full::send_email") is not None
    assert regs["channel_registry"].get("team-a/full::slack") is not None
    assert regs["skill_registry"].get_plugin_entry("team-a/full::refund-flow") is not None
    assert regs["agent_registry"].get_plugin_entry("team-a/full::customer-support") is not None
    assert regs["command_registry"].get("team-a/full::analyze") is not None
    # hook 没有 id 字段，按 event_idx 生成 short_id
    hook_ids = [e.id for e in regs["hook_registry"].get_all()]
    assert hook_ids == ["team-a/full::PreTool_0"]


def test_install_namespace_format_and_entry_fields(tmp_path: Path):
    user_root = tmp_path / "user"
    user_root.mkdir()
    _write_full_plugin(user_root, "team-a/full", owner="team-a")

    loader = PluginLoader(sources=[UserPluginSource(user_root)])
    [manifest] = loader.load_all()
    regs = _make_registries()
    loader.install_into_registries([manifest], **regs)

    entry = regs["tool_registry"].get_plugin_entry("team-a/full::send_email")
    assert entry.short_id == "send_email"
    assert entry.owner_plugin == "team-a/full"
    assert entry.owner_team == "team-a"
    assert entry.visibility == "public"
    assert entry.impl is None  # P1 不实例化
    # metadata 透传 contribution 原始字段，给 P2 用
    assert entry.metadata["type"] == "python"
    assert entry.metadata["python"] == "tools/email.py:SendEmailTool"


def test_install_failure_records_in_report_without_raising(tmp_path: Path):
    """缺 id 字段的 contribution 应进 failures 而不是抛异常。"""
    pdir = tmp_path / "team-a__broken"
    pdir.mkdir()
    (pdir / "plugin.yaml").write_text(
        """schema_version: "1"
id: team-a/broken
version: 0.1.0
name: broken
description: missing tool id
owner: team-a
visibility: public
contributes:
  tools:
    - type: python
      python: tools/x.py:X
""",
        encoding="utf-8",
    )

    loader = PluginLoader(sources=[UserPluginSource(tmp_path)])
    manifests = loader.load_all()
    regs = _make_registries()
    report = loader.install_into_registries(manifests, **regs)

    assert report.installed == 0
    assert len(report.failures) == 1
    fail = report.failures[0]
    assert fail.plugin_id == "team-a/broken"
    assert fail.contribution_kind == "tools"
    assert "id" in fail.reason


def test_install_unknown_contribution_kind_records_failure(tmp_path: Path):
    pdir = tmp_path / "team-a__weird"
    pdir.mkdir()
    (pdir / "plugin.yaml").write_text(
        """schema_version: "1"
id: team-a/weird
version: 0.1.0
name: weird
description: unknown contribution kind
owner: team-a
visibility: public
contributes:
  somethings_new:
    - id: foo
""",
        encoding="utf-8",
    )

    loader = PluginLoader(sources=[UserPluginSource(tmp_path)])
    manifests = loader.load_all()
    regs = _make_registries()
    report = loader.install_into_registries(manifests, **regs)

    assert report.installed == 0
    assert len(report.failures) == 1
    assert report.failures[0].contribution_kind == "somethings_new"
    assert "unknown" in report.failures[0].reason.lower()


def test_install_ignores_mcp_servers_in_p1(tmp_path: Path):
    """mcp_servers 由 P6 处理；P1 的 install 路径不解析它，也不报错。"""
    pdir = tmp_path / "team-a__mcp"
    pdir.mkdir()
    (pdir / "plugin.yaml").write_text(
        """schema_version: "1"
id: team-a/mcp
version: 0.1.0
name: mcp
description: has only mcp_servers
owner: team-a
visibility: public
contributes:
  mcp_servers:
    - id: crm-server
      transport: stdio
      command: ["node", "mcp/crm.js"]
""",
        encoding="utf-8",
    )

    loader = PluginLoader(sources=[UserPluginSource(tmp_path)])
    manifests = loader.load_all()
    regs = _make_registries()
    report = loader.install_into_registries(manifests, **regs)
    # 不算 installed、不算 failure；mcp_servers 全程沉默
    assert report.installed == 0
    assert report.failures == []


# ── 端到端 ────────────────────────────────────────────────────


def test_end_to_end_two_sources_two_plugins(tmp_path: Path):
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
    regs = _make_registries()
    report = loader.install_into_registries(manifests, **regs)

    assert report.ok
    assert report.installed == 14   # 2 个 plugin × 7 contribution
    # 不同 plugin 的 namespace 隔离：相同短名共存
    assert regs["tool_registry"].get_plugin_entry("core/builtin-tools::send_email") is not None
    assert regs["tool_registry"].get_plugin_entry("team-a/crm::send_email") is not None
    # owner_team 正确传递
    core_entry = regs["tool_registry"].get_plugin_entry("core/builtin-tools::send_email")
    crm_entry = regs["tool_registry"].get_plugin_entry("team-a/crm::send_email")
    assert core_entry.owner_team == "core"
    assert crm_entry.owner_team == "team-a"
