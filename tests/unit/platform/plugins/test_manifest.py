"""测试 PluginManifest 数据类与 YAML 校验。"""
from pathlib import Path
import textwrap

import pytest

from sensenova_claw.platform.plugins import (
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.manifest import ManifestValidationError


FIXTURE = Path(__file__).parent / "fixtures" / "valid_plugin" / "plugin.yaml"


def test_load_valid_manifest_from_yaml():
    manifest = load_manifest_from_yaml(FIXTURE)
    assert isinstance(manifest, PluginManifest)
    assert manifest.id == "team-a/crm-assistant"
    assert manifest.version == "1.2.0"
    assert manifest.name == "CRM Assistant"
    assert manifest.owner == "team-a"
    assert manifest.visibility == "private"
    assert manifest.min_core_version == "1.2.0"
    assert manifest.max_core_version == "2.0.0"
    assert manifest.contributes["tools"][0]["id"] == "send_email"
    assert manifest.root_path == FIXTURE.parent


def test_permissions_parsed():
    manifest = load_manifest_from_yaml(FIXTURE)
    assert isinstance(manifest.permissions, PluginPermissions)
    assert manifest.permissions.network == ["https://api.crm.internal/**"]
    assert manifest.permissions.filesystem_read == ["./data/**"]
    assert manifest.permissions.filesystem_write == ["./cache/**"]
    assert manifest.permissions.env == ["CRM_API_TOKEN"]


def test_missing_required_field_fails(tmp_path: Path):
    bad = tmp_path / "plugin.yaml"
    # 缺少 owner / visibility / version
    bad.write_text(textwrap.dedent("""
        schema_version: "1"
        id: team-x/no-owner
        name: incomplete
        description: missing fields
    """).strip(), encoding="utf-8")
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest_from_yaml(bad)
    msg = str(excinfo.value)
    assert "owner" in msg or "visibility" in msg or "version" in msg


def test_bad_visibility_fails(tmp_path: Path):
    bad = tmp_path / "plugin.yaml"
    bad.write_text(textwrap.dedent("""
        schema_version: "1"
        id: team-x/bad-vis
        version: 0.1.0
        name: bad-vis
        description: invalid visibility
        owner: team-x
        visibility: world-readable
    """).strip(), encoding="utf-8")
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest_from_yaml(bad)
    assert "visibility" in str(excinfo.value)


def test_default_contributes_is_empty_dict(tmp_path: Path):
    minimal = tmp_path / "plugin.yaml"
    minimal.write_text(textwrap.dedent("""
        schema_version: "1"
        id: team-x/minimal
        version: 0.1.0
        name: minimal
        description: bare-bones
        owner: team-x
        visibility: public
    """).strip(), encoding="utf-8")
    manifest = load_manifest_from_yaml(minimal)
    assert manifest.contributes == {}
    assert manifest.permissions == PluginPermissions()
    assert manifest.allowed_teams == []
    assert manifest.allowed_users == []
    assert manifest.config_schema is None
    assert manifest.max_core_version is None


def test_yaml_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_manifest_from_yaml(tmp_path / "missing.yaml")
