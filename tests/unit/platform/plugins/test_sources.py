"""测试 PluginSource 抽象 + builtin/user 两种实现。"""
from pathlib import Path

import pytest

from sensenova_claw.platform.plugins import (
    PluginManifest,
    BuiltinPluginSource,
    UserPluginSource,
)


def _write_plugin(root: Path, plugin_id: str, owner: str = "team-x") -> Path:
    """在 root 下建一个最小合法 plugin。"""
    safe_dir = plugin_id.replace("/", "__")
    pdir = root / safe_dir
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "plugin.yaml").write_text(
        f"""schema_version: "1"
id: {plugin_id}
version: 0.1.0
name: {plugin_id}
description: test plugin
owner: {owner}
visibility: public
""",
        encoding="utf-8",
    )
    return pdir


def test_builtin_source_scans_plugin_directories(tmp_path: Path):
    _write_plugin(tmp_path, "core/builtin-tools", owner="core")
    _write_plugin(tmp_path, "core/builtin-llm", owner="core")
    source = BuiltinPluginSource(tmp_path)
    manifests = list(source.list())
    ids = sorted(m.id for m in manifests)
    assert ids == ["core/builtin-llm", "core/builtin-tools"]
    assert all(isinstance(m, PluginManifest) for m in manifests)


def test_user_source_scans_user_dir(tmp_path: Path):
    _write_plugin(tmp_path, "team-a/crm")
    source = UserPluginSource(tmp_path)
    manifests = list(source.list())
    assert [m.id for m in manifests] == ["team-a/crm"]


def test_source_skips_directories_without_plugin_yaml(tmp_path: Path):
    (tmp_path / "not-a-plugin").mkdir()
    (tmp_path / "not-a-plugin" / "README.md").write_text("noop", encoding="utf-8")
    _write_plugin(tmp_path, "team-a/ok")
    source = UserPluginSource(tmp_path)
    assert [m.id for m in source.list()] == ["team-a/ok"]


def test_source_skips_invalid_manifests_silently(tmp_path: Path):
    """坏 manifest 不应让整个 list() 崩溃，应跳过并记录。"""
    bad_dir = tmp_path / "bad-plugin"
    bad_dir.mkdir()
    (bad_dir / "plugin.yaml").write_text(
        'schema_version: "1"\nid: incomplete\n', encoding="utf-8"
    )
    _write_plugin(tmp_path, "team-a/ok")
    source = UserPluginSource(tmp_path)
    manifests = list(source.list())
    # 只有合法的 ok 出现；bad-plugin 的失败原因记录在 source.errors
    assert [m.id for m in manifests] == ["team-a/ok"]
    assert len(source.errors) == 1
    assert "incomplete" in source.errors[0].path.name or "bad-plugin" in str(
        source.errors[0].path
    )


def test_source_returns_empty_when_root_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    source = UserPluginSource(missing)
    assert list(source.list()) == []
