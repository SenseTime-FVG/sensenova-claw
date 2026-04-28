# P1 — PluginLoader 与 Registry 抽象 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 抽出 `PluginLoader` / `Registry` 抽象，钉死 plugin manifest schema 与 `RegistryEntry` 数据契约，为后续 P2~P6 提供共享地基；本期不迁移既有内置能力，也不引入 visibility 过滤或 hook/mcp 执行。

**Architecture:** 在 `sensenova_claw/platform/plugins/` 新建一个独立子模块，包含 `PluginManifest` + `RegistryEntry` 数据类、Pydantic 校验模型、`PluginSource` 抽象（builtin / user 两种实现）、以及 `PluginLoader`。在五个既有 Registry（`ToolRegistry` / `SkillRegistry` / `LLMProviderRegistry` / `ChannelRegistry` / `AgentRegistry`）上加一个 thin `register_from_plugin(entry)` 方法（不改原有逻辑）；新增两个空 Registry：`HookRegistry` / `CommandRegistry`，给 P6 留位。`PluginLoader.install_into_registries()` 把每条 contribution 解析成 `RegistryEntry` 并按类型分发；失败用 `InstallReport` 收集而不抛异常。

**Tech Stack:** Python 3.12 / `pydantic>=2.9` / `pyyaml>=6.0.2` / `pytest`；Windows 环境下解释器是 `python3`（仓库现有约定）。

**Scope reminders（来自 docs/design/2026-04-27-plan-decomposition.md §2.P1）:**
- ✓ `PluginLoader` 类（扫描、读 manifest、校验、注入 registry）
- ✓ `RegistryEntry` 数据类（带 owner_plugin / namespace / visibility 字段）
- ✓ 各 Registry 增加 `register_from_plugin(entry)` 方法
- ✓ Plugin manifest YAML schema 校验器（Pydantic）
- ✓ `PluginSource` 抽象 + `BuiltinPluginSource` / `UserPluginSource` 两种实现
- ✓ 新增空 `HookRegistry` / `CommandRegistry`（P6 填充）
- ✗ 不实际把现有内置能力包成 plugin（P2 做）
- ✗ 不做 visibility 过滤（P5 做）——`load_all(identity)` 实现里 P1 阶段忽略 identity
- ✗ 不实例化 contribution 实现（不动态 import Python 类、不 spawn MCP server、不读 SKILL.md）；`RegistryEntry.impl=None`，metadata 携带原始 contribution dict 即可，待 P2 实现真正的实例化

**冻结接口契约（来自 docs/design/2026-04-27-plan-decomposition.md §3）:** `PluginManifest`、`PluginPermissions`、`RegistryEntry`、`PluginLoader.load_all` / `install_into_registries` 的签名必须与文档 §3.1~§3.3 一致。**不要擅自改字段名**——其他 plan 已经按这些签名编写。

---

## File Structure

将创建/修改的文件清单：

**新建（platform 层 plugin 基础设施）**
- `sensenova_claw/platform/plugins/__init__.py` — 暴露公开 API（`PluginManifest`、`RegistryEntry`、`PluginLoader`、`InstallReport`、`PluginSource`、`BuiltinPluginSource`、`UserPluginSource`）
- `sensenova_claw/platform/plugins/manifest.py` — `PluginManifest` / `PluginPermissions` 数据类 + Pydantic 校验模型 + `load_manifest_from_yaml(path)`
- `sensenova_claw/platform/plugins/registry_entry.py` — `RegistryEntry` 数据类
- `sensenova_claw/platform/plugins/sources.py` — `PluginSource` 协议 + `BuiltinPluginSource` / `UserPluginSource`
- `sensenova_claw/platform/plugins/loader.py` — `PluginLoader` + `InstallReport`

**新建（空 Registry，P6 填充）**
- `sensenova_claw/capabilities/hooks/__init__.py`
- `sensenova_claw/capabilities/hooks/registry.py` — `HookRegistry`
- `sensenova_claw/capabilities/commands/__init__.py`
- `sensenova_claw/capabilities/commands/registry.py` — `CommandRegistry`

**修改既有 Registry（仅追加 `register_from_plugin` 方法，不改原有方法）**
- `sensenova_claw/capabilities/tools/registry.py`
- `sensenova_claw/capabilities/skills/registry.py`
- `sensenova_claw/capabilities/agents/registry.py`
- `sensenova_claw/adapters/llm/factory.py` — 在文件中给 `LLMFactory` 类追加 `register_from_plugin`
- `sensenova_claw/adapters/channels/__init__.py` — 引出新建 `channel_registry.py`
- `sensenova_claw/adapters/channels/channel_registry.py`（新建）— 既有项目里 channel 没有显式 Registry 类，本 plan 新建一个最简版以满足契约（plugin id → entry）

**新建测试**
- `tests/unit/platform/__init__.py`
- `tests/unit/platform/plugins/__init__.py`
- `tests/unit/platform/plugins/test_manifest.py`
- `tests/unit/platform/plugins/test_sources.py`
- `tests/unit/platform/plugins/test_loader.py`
- `tests/unit/platform/plugins/test_registry_entry.py`
- `tests/unit/capabilities/__init__.py`
- `tests/unit/capabilities/test_hook_registry.py`
- `tests/unit/capabilities/test_command_registry.py`
- `tests/unit/capabilities/test_channel_registry.py`
- `tests/unit/capabilities/test_register_from_plugin.py` — 覆盖既有 5 个 Registry 的 `register_from_plugin`

**辅助测试 fixture**
- `tests/unit/platform/plugins/fixtures/valid_plugin/plugin.yaml` — 单元测试用 manifest（不在生产代码里）

---

## Task 1: 平台 plugin 包骨架 + RegistryEntry

**Files:**
- Create: `sensenova_claw/platform/plugins/__init__.py`
- Create: `sensenova_claw/platform/plugins/registry_entry.py`
- Create: `tests/unit/platform/__init__.py`
- Create: `tests/unit/platform/plugins/__init__.py`
- Create: `tests/unit/platform/plugins/test_registry_entry.py`

- [ ] **Step 1: 写失败测试 — RegistryEntry 字段与默认值**

写入 `tests/unit/platform/plugins/test_registry_entry.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/platform/plugins/test_registry_entry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sensenova_claw.platform.plugins'`

- [ ] **Step 3: 写最小实现 — registry_entry.py**

写入 `sensenova_claw/platform/plugins/registry_entry.py`：

```python
"""RegistryEntry — Plugin 注入到各 Registry 时的统一条目结构。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.2。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegistryEntry:
    """一个 plugin contribution 在 Registry 中的注册条目。

    - id: 全局唯一，格式 ``f"{plugin.id}::{contribution.id}"``。
    - short_id: plugin 内部短名，用于 plugin 内引用。
    - owner_plugin: plugin id（如 ``core/builtin-tools``）。
    - owner_team: plugin manifest 中的 owner（如 ``core`` / ``team-a``）。
    - visibility: ``public`` / ``internal`` / ``private``，P5 接入时使用。
    - impl: 实际实现引用；P1 阶段统一为 None，P2 真正实例化时填入。
    - metadata: Registry 自定义字段，例如 ``{"type": "python", "python": "..."}``。
    """

    id: str
    short_id: str
    owner_plugin: str
    owner_team: str
    visibility: str
    impl: Any
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: 写公开 API — __init__.py**

写入 `sensenova_claw/platform/plugins/__init__.py`：

```python
"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry

__all__ = ["RegistryEntry"]
```

- [ ] **Step 5: 写测试包占位 __init__.py**

写入 `tests/unit/platform/__init__.py`（空文件）和 `tests/unit/platform/plugins/__init__.py`（空文件）。

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_registry_entry.py -v`
Expected: PASS（2 个用例）

- [ ] **Step 7: 提交**

```bash
git add sensenova_claw/platform/plugins/__init__.py \
        sensenova_claw/platform/plugins/registry_entry.py \
        tests/unit/platform/__init__.py \
        tests/unit/platform/plugins/__init__.py \
        tests/unit/platform/plugins/test_registry_entry.py
git commit -m "feat(plugins): add RegistryEntry dataclass (P1 task 1)"
```

---

## Task 2: PluginManifest + Pydantic 校验

**Files:**
- Create: `sensenova_claw/platform/plugins/manifest.py`
- Modify: `sensenova_claw/platform/plugins/__init__.py`
- Create: `tests/unit/platform/plugins/test_manifest.py`
- Create: `tests/unit/platform/plugins/fixtures/valid_plugin/plugin.yaml`

- [ ] **Step 1: 写 fixture — 一个合法 manifest**

写入 `tests/unit/platform/plugins/fixtures/valid_plugin/plugin.yaml`：

```yaml
schema_version: "1"
id: team-a/crm-assistant
version: 1.2.0
name: CRM Assistant
description: 客服 CRM 工具集
author: team-a@company.com
owner: team-a
visibility: private
allowed_teams: []
allowed_users: []
sensenova_claw:
  min_version: "1.2.0"
  max_version: "2.0.0"
permissions:
  network:
    - "https://api.crm.internal/**"
  filesystem:
    - read: ["./data/**"]
    - write: ["./cache/**"]
  env:
    - CRM_API_TOKEN
config:
  schema:
    type: object
    required: [api_endpoint]
    properties:
      api_endpoint: { type: string }
contributes:
  tools:
    - id: send_email
      type: python
      python: tools/email.py:SendEmailTool
```

- [ ] **Step 2: 写失败测试 — PluginManifest 加载与字段**

写入 `tests/unit/platform/plugins/test_manifest.py`：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/platform/plugins/test_manifest.py -v`
Expected: FAIL — `ImportError: cannot import name 'PluginManifest'`

- [ ] **Step 4: 写实现 — manifest.py**

写入 `sensenova_claw/platform/plugins/manifest.py`：

```python
"""PluginManifest — plugin.yaml 的数据契约 + 校验。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.1。
spec 字段定义见 docs/design/2026-04-27-agent-harness-sdk-design.md §4.1。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


Visibility = Literal["public", "internal", "private"]


# ── 数据类（外部使用） ────────────────────────────────────────────


@dataclass
class PluginPermissions:
    """plugin 自报的 sandbox 限制。

    P1 仅做字段持有；真正的 enforcement 由 P5/P6 实现。
    """

    network: list[str] = field(default_factory=list)
    filesystem_read: list[str] = field(default_factory=list)
    filesystem_write: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)


@dataclass
class PluginManifest:
    """plugin.yaml 反序列化后的内存表示。"""

    schema_version: str
    id: str
    version: str
    name: str
    description: str
    owner: str
    visibility: Visibility
    allowed_teams: list[str] = field(default_factory=list)
    allowed_users: list[str] = field(default_factory=list)
    min_core_version: str = "1.2.0"
    max_core_version: str | None = None
    permissions: PluginPermissions = field(default_factory=PluginPermissions)
    config_schema: dict[str, Any] | None = None
    contributes: dict[str, Any] = field(default_factory=dict)
    root_path: Path = field(default_factory=Path)


# ── Pydantic 校验模型（内部使用） ─────────────────────────────────


class _PermissionsModel(BaseModel):
    """spec §4.1 中 permissions 段的原始 YAML 形态。

    YAML 形态：

    .. code-block:: yaml

        permissions:
          network:
            - "https://api.crm.internal/**"
          filesystem:
            - read: ["./data/**"]
            - write: ["./cache/**"]
          env:
            - CRM_API_TOKEN
    """

    model_config = ConfigDict(extra="allow")

    network: list[str] = Field(default_factory=list)
    filesystem: list[dict[str, list[str]]] = Field(default_factory=list)
    env: list[str] = Field(default_factory=list)


class _SensenovaClawModel(BaseModel):
    """spec §4.1 中 sensenova_claw 段。"""

    model_config = ConfigDict(extra="allow")
    min_version: str = "1.2.0"
    max_version: str | None = None


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")


class _ManifestModel(BaseModel):
    """plugin.yaml 顶层结构。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str
    id: str
    version: str
    name: str
    description: str
    owner: str
    visibility: str
    allowed_teams: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    sensenova_claw: _SensenovaClawModel = Field(default_factory=_SensenovaClawModel)
    permissions: _PermissionsModel = Field(default_factory=_PermissionsModel)
    config: _ConfigModel = Field(default_factory=_ConfigModel)
    contributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("visibility")
    @classmethod
    def _check_visibility(cls, v: str) -> str:
        if v not in ("public", "internal", "private"):
            raise ValueError(
                f"visibility 必须是 public|internal|private 之一，实际：{v!r}"
            )
        return v


# ── 公开 API ─────────────────────────────────────────────────────


class ManifestValidationError(ValueError):
    """manifest 校验失败时抛出。包装 pydantic ValidationError 的人类可读消息。"""


def load_manifest_from_yaml(path: Path | str) -> PluginManifest:
    """从 plugin.yaml 加载并校验，返回 PluginManifest。

    抛出：
      - FileNotFoundError：文件不存在
      - ManifestValidationError：YAML 合法但字段不符合 schema
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"plugin.yaml 不存在：{path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestValidationError(
            f"plugin.yaml 顶层必须是 mapping，实际：{type(raw).__name__}"
        )

    try:
        model = _ManifestModel.model_validate(raw)
    except ValidationError as e:
        raise ManifestValidationError(
            f"plugin.yaml 校验失败（{path}）：{e}"
        ) from e

    perms = _flatten_permissions(model.permissions)

    return PluginManifest(
        schema_version=model.schema_version,
        id=model.id,
        version=model.version,
        name=model.name,
        description=model.description,
        owner=model.owner,
        visibility=model.visibility,  # type: ignore[arg-type]
        allowed_teams=list(model.allowed_teams),
        allowed_users=list(model.allowed_users),
        min_core_version=model.sensenova_claw.min_version,
        max_core_version=model.sensenova_claw.max_version,
        permissions=perms,
        config_schema=model.config.schema_,
        contributes=dict(model.contributes),
        root_path=path.parent,
    )


def _flatten_permissions(model: _PermissionsModel) -> PluginPermissions:
    """把 YAML 中 ``filesystem: [{read: [...]}, {write: [...]}]`` 拍成两个数组。"""
    fs_read: list[str] = []
    fs_write: list[str] = []
    for entry in model.filesystem:
        for key, paths in entry.items():
            if key == "read":
                fs_read.extend(paths)
            elif key == "write":
                fs_write.extend(paths)
    return PluginPermissions(
        network=list(model.network),
        filesystem_read=fs_read,
        filesystem_write=fs_write,
        env=list(model.env),
    )
```

- [ ] **Step 5: 在公开 API 中导出 manifest 类**

替换 `sensenova_claw/platform/plugins/__init__.py` 全部内容为：

```python
"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry

__all__ = [
    "ManifestValidationError",
    "PluginManifest",
    "PluginPermissions",
    "RegistryEntry",
    "load_manifest_from_yaml",
]
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_manifest.py -v`
Expected: PASS（6 个用例）

- [ ] **Step 7: 提交**

```bash
git add sensenova_claw/platform/plugins/manifest.py \
        sensenova_claw/platform/plugins/__init__.py \
        tests/unit/platform/plugins/fixtures \
        tests/unit/platform/plugins/test_manifest.py
git commit -m "feat(plugins): add PluginManifest + pydantic validator (P1 task 2)"
```

---

## Task 3: PluginSource 抽象 + BuiltinPluginSource / UserPluginSource

**Files:**
- Create: `sensenova_claw/platform/plugins/sources.py`
- Modify: `sensenova_claw/platform/plugins/__init__.py`
- Create: `tests/unit/platform/plugins/test_sources.py`

- [ ] **Step 1: 写失败测试 — Source 扫描行为**

写入 `tests/unit/platform/plugins/test_sources.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/platform/plugins/test_sources.py -v`
Expected: FAIL — `ImportError: cannot import name 'BuiltinPluginSource'`

- [ ] **Step 3: 写实现 — sources.py**

写入 `sensenova_claw/platform/plugins/sources.py`：

```python
"""PluginSource — plugin 来源抽象 + 两种本期实现。

P1 范围：
  - BuiltinPluginSource：扫描 core 自带目录（P2 会写入 core/builtin-* 子目录）
  - UserPluginSource：扫描 ~/.sensenova-claw/plugins/

不实现：
  - org marketplace（蓝图）
  - team git 仓库（蓝图）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    load_manifest_from_yaml,
)

logger = logging.getLogger(__name__)


@dataclass
class SourceError:
    """source 扫描时遇到的单个错误（坏 manifest、读不动文件等）。"""

    path: Path
    message: str


class PluginSource(Protocol):
    """plugin 来源协议 — 给一个目录，吐出 PluginManifest 序列。"""

    errors: list[SourceError]

    def list(self) -> Iterable[PluginManifest]:
        """扫描 source，懒加载返回所有合法 manifest。

        坏 manifest 静默跳过，错误信息追加到 ``self.errors``。
        """


class _DirectoryPluginSource:
    """共享实现：扫描一个根目录下所有含 plugin.yaml 的子目录。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.errors: list[SourceError] = []

    def list(self) -> Iterable[PluginManifest]:
        self.errors.clear()
        if not self.root.exists():
            return []
        results: list[PluginManifest] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "plugin.yaml"
            if not manifest_path.exists():
                continue
            try:
                manifest = load_manifest_from_yaml(manifest_path)
            except (ManifestValidationError, OSError) as e:
                logger.warning(
                    "PluginSource: 跳过坏 manifest %s: %s", manifest_path, e
                )
                self.errors.append(SourceError(path=manifest_path, message=str(e)))
                continue
            results.append(manifest)
        return results


class BuiltinPluginSource(_DirectoryPluginSource):
    """扫描 core 内置 plugin 目录（P2 写入 core/builtin-*）。"""


class UserPluginSource(_DirectoryPluginSource):
    """扫描用户本地 plugin 目录（默认 ``~/.sensenova-claw/plugins/``）。"""
```

- [ ] **Step 4: 把 source 类加到公开 API**

修改 `sensenova_claw/platform/plugins/__init__.py`，把 import 与 `__all__` 替换为：

```python
"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry
from sensenova_claw.platform.plugins.sources import (
    BuiltinPluginSource,
    PluginSource,
    SourceError,
    UserPluginSource,
)

__all__ = [
    "BuiltinPluginSource",
    "ManifestValidationError",
    "PluginManifest",
    "PluginPermissions",
    "PluginSource",
    "RegistryEntry",
    "SourceError",
    "UserPluginSource",
    "load_manifest_from_yaml",
]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_sources.py -v`
Expected: PASS（5 个用例）

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/platform/plugins/sources.py \
        sensenova_claw/platform/plugins/__init__.py \
        tests/unit/platform/plugins/test_sources.py
git commit -m "feat(plugins): add PluginSource + builtin/user impls (P1 task 3)"
```

---

## Task 4: 新建 HookRegistry / CommandRegistry（空 Registry）

**Files:**
- Create: `sensenova_claw/capabilities/hooks/__init__.py`
- Create: `sensenova_claw/capabilities/hooks/registry.py`
- Create: `sensenova_claw/capabilities/commands/__init__.py`
- Create: `sensenova_claw/capabilities/commands/registry.py`
- Create: `tests/unit/capabilities/__init__.py`
- Create: `tests/unit/capabilities/test_hook_registry.py`
- Create: `tests/unit/capabilities/test_command_registry.py`

- [ ] **Step 1: 写失败测试 — HookRegistry**

写入 `tests/unit/capabilities/__init__.py`（空文件）和 `tests/unit/capabilities/test_hook_registry.py`：

```python
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
```

- [ ] **Step 2: 写失败测试 — CommandRegistry**

写入 `tests/unit/capabilities/test_command_registry.py`：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/capabilities/test_hook_registry.py tests/unit/capabilities/test_command_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sensenova_claw.capabilities.hooks'`

- [ ] **Step 4: 写 HookRegistry**

写入 `sensenova_claw/capabilities/hooks/__init__.py`：

```python
"""Hook 子系统骨架 — P1 仅 Registry，P6 接入 HookPipeline。"""
from sensenova_claw.capabilities.hooks.registry import HookRegistry

__all__ = ["HookRegistry"]
```

写入 `sensenova_claw/capabilities/hooks/registry.py`：

```python
"""HookRegistry — 收集 plugin 贡献的 hook 条目，给 P6 的 HookPipeline 消费。

P1 阶段：只做 (id -> entry) 的字典存储。
P6 阶段：HookPipeline 会按 metadata['event'] 索引并 spawn 子进程。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class HookRegistry:
    """plugin 贡献的 hook 条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        """注入一条 plugin contribution。同 id 覆盖旧值。"""
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
```

- [ ] **Step 5: 写 CommandRegistry**

写入 `sensenova_claw/capabilities/commands/__init__.py`：

```python
"""斜杠命令子系统骨架 — P1 仅 Registry。"""
from sensenova_claw.capabilities.commands.registry import CommandRegistry

__all__ = ["CommandRegistry"]
```

写入 `sensenova_claw/capabilities/commands/registry.py`：

```python
"""CommandRegistry — 收集 plugin 贡献的斜杠命令。

P1：占位空 Registry。后续由命令分发器消费 metadata['path'] 指向的 Markdown。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class CommandRegistry:
    """plugin 贡献的命令条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/capabilities/test_hook_registry.py tests/unit/capabilities/test_command_registry.py -v`
Expected: PASS（4 + 3 = 7 个用例）

- [ ] **Step 7: 提交**

```bash
git add sensenova_claw/capabilities/hooks \
        sensenova_claw/capabilities/commands \
        tests/unit/capabilities/__init__.py \
        tests/unit/capabilities/test_hook_registry.py \
        tests/unit/capabilities/test_command_registry.py
git commit -m "feat(registries): add empty HookRegistry + CommandRegistry (P1 task 4)"
```

---

## Task 5: 新建 ChannelRegistry（既有项目里没有显式 Registry 类）

**Files:**
- Create: `sensenova_claw/adapters/channels/channel_registry.py`
- Modify: `sensenova_claw/adapters/channels/__init__.py`
- Create: `tests/unit/capabilities/test_channel_registry.py`

> **背景**：既有 `sensenova_claw/adapters/channels/` 只有 `base.py` / `websocket_channel.py`，没有像 ToolRegistry 那样的注册表类。本 plan 的 §3 接口契约要求 `install_into_registries(..., channel_registry, ...)` 接收一个 `ChannelRegistry`。所以 P1 需要新建一个最简版。
> 不动 gateway / channel 启动逻辑——那是 P2 的事。

- [ ] **Step 1: 检查既有 channels 目录的 __init__.py**

Run: `cat sensenova_claw/adapters/channels/__init__.py`

记下当前内容（很可能为空或只有注释）。Step 4 在末尾追加导出。

- [ ] **Step 2: 写失败测试 — ChannelRegistry**

写入 `tests/unit/capabilities/test_channel_registry.py`：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/capabilities/test_channel_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sensenova_claw.adapters.channels.channel_registry'`

- [ ] **Step 4: 写 ChannelRegistry**

写入 `sensenova_claw/adapters/channels/channel_registry.py`：

```python
"""ChannelRegistry — plugin 贡献的 Channel 条目。

P1 引入这个类的唯一动机：满足 PluginLoader.install_into_registries 的接口契约。
真正的 channel 启动（websocket / feishu / slack）在 P2 之后接入。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class ChannelRegistry:
    """plugin 贡献的 Channel 条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        """同 id 覆盖。"""
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
```

- [ ] **Step 5: 在 channels 包暴露 ChannelRegistry**

读 `sensenova_claw/adapters/channels/__init__.py`（如有现有内容则保留），在文件**末尾**追加：

```python
from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry  # noqa: E402

__all__ = list(globals().get("__all__", [])) + ["ChannelRegistry"]
```

如果原文件为空（除空白/注释外无可执行代码），直接整个写为：

```python
"""Channel adapters。"""
from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry

__all__ = ["ChannelRegistry"]
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/capabilities/test_channel_registry.py -v`
Expected: PASS（3 个用例）

- [ ] **Step 7: 跑既有 channel 相关测试，确认没破坏**

Run: `python3 -m pytest tests/unit/test_feishu_plugin.py tests/unit/test_feishu_outbound.py -q`
Expected: PASS（与原状态一致；如果原本就有失败，记下基线，跟 P1 改动无关）

- [ ] **Step 8: 提交**

```bash
git add sensenova_claw/adapters/channels/channel_registry.py \
        sensenova_claw/adapters/channels/__init__.py \
        tests/unit/capabilities/test_channel_registry.py
git commit -m "feat(channels): add ChannelRegistry for plugin contributions (P1 task 5)"
```

---

## Task 6: 给 5 个既有 Registry 加 register_from_plugin

**Files:**
- Modify: `sensenova_claw/capabilities/tools/registry.py`（追加方法）
- Modify: `sensenova_claw/capabilities/skills/registry.py`（追加方法）
- Modify: `sensenova_claw/capabilities/agents/registry.py`（追加方法）
- Modify: `sensenova_claw/adapters/llm/factory.py`（给 LLMFactory 类追加方法 + 别名导出 LLMProviderRegistry）
- Modify: `sensenova_claw/adapters/llm/__init__.py`（导出别名）
- Create: `tests/unit/capabilities/test_register_from_plugin.py`

> **关键约束**：`register_from_plugin` 只往内部 dict 存 `RegistryEntry`，不动既有 `register()` / `get()` 行为；不实例化 contribution（impl 阶段还没到）。每个 Registry 暴露 `get_plugin_entry(entry_id)` / `list_plugin_entries()` 让 loader 验证。

- [ ] **Step 1: 写失败测试 — 5 个 Registry 都接受 register_from_plugin**

写入 `tests/unit/capabilities/test_register_from_plugin.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/capabilities/test_register_from_plugin.py -v`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute 'register_from_plugin'`

- [ ] **Step 3: 给 ToolRegistry 加 register_from_plugin**

在 `sensenova_claw/capabilities/tools/registry.py` 的 `class ToolRegistry:` 末尾（`as_llm_tools` 方法之后），追加：

```python
    # ── P1 plugin loader 接入（不动既有 register/get） ─────────────

    def register_from_plugin(self, entry: "RegistryEntry") -> None:
        """收下 plugin contribution。

        P1 阶段：只存条目，不实例化 impl（P2 会在 install 时实例化 Tool 子类
        并把实例放到 entry.impl，再统一调既有 self.register(tool)）。
        """
        if not hasattr(self, "_plugin_entries"):
            self._plugin_entries = {}
        self._plugin_entries[entry.id] = entry

    def get_plugin_entry(self, entry_id: str) -> "RegistryEntry | None":
        return getattr(self, "_plugin_entries", {}).get(entry_id)

    def list_plugin_entries(self) -> "list[RegistryEntry]":
        return list(getattr(self, "_plugin_entries", {}).values())
```

并在文件顶部 import 区追加（紧跟现有 import 之后）：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.platform.plugins import RegistryEntry
```

- [ ] **Step 4: 给 SkillRegistry 加 register_from_plugin**

在 `sensenova_claw/capabilities/skills/registry.py` 的 `class SkillRegistry:` 末尾（`get` 方法之后），追加：

```python
    # ── P1 plugin loader 接入 ────────────────────────────────────

    def register_from_plugin(self, entry: "RegistryEntry") -> None:
        """收下 plugin contribution（不与 SKILL.md 文件加载冲突）。"""
        if not hasattr(self, "_plugin_entries"):
            self._plugin_entries = {}
        self._plugin_entries[entry.id] = entry

    def get_plugin_entry(self, entry_id: str) -> "RegistryEntry | None":
        return getattr(self, "_plugin_entries", {}).get(entry_id)

    def list_plugin_entries(self) -> "list[RegistryEntry]":
        return list(getattr(self, "_plugin_entries", {}).values())
```

文件顶部 import 区追加：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.platform.plugins import RegistryEntry
```

- [ ] **Step 5: 给 AgentRegistry 加 register_from_plugin**

在 `sensenova_claw/capabilities/agents/registry.py` 的 `class AgentRegistry:` 末尾追加（在 `update` 方法之后）：

```python
    # ── P1 plugin loader 接入 ────────────────────────────────────

    def register_from_plugin(self, entry: "RegistryEntry") -> None:
        if not hasattr(self, "_plugin_entries"):
            self._plugin_entries = {}
        self._plugin_entries[entry.id] = entry

    def get_plugin_entry(self, entry_id: str) -> "RegistryEntry | None":
        return getattr(self, "_plugin_entries", {}).get(entry_id)

    def list_plugin_entries(self) -> "list[RegistryEntry]":
        return list(getattr(self, "_plugin_entries", {}).values())
```

文件顶部已有 `if TYPE_CHECKING:` 块（管 `PublicEventBus` / `Config`），把以下行追加进去：

```python
    from sensenova_claw.platform.plugins import RegistryEntry
```

- [ ] **Step 6: 给 LLMFactory 加 register_from_plugin + 暴露 LLMProviderRegistry 别名**

在 `sensenova_claw/adapters/llm/factory.py` 的 `class LLMFactory:` 末尾追加（在文件结尾的最后一个方法之后）：

```python
    # ── P1 plugin loader 接入 ────────────────────────────────────

    def register_from_plugin(self, entry: "RegistryEntry") -> None:
        """收下 plugin LLM provider contribution。

        P1 仅存条目；P2 在 install 时根据 metadata['type'] / metadata['python']
        反射出 LLMProvider 子类并调既有 _PROVIDER_FACTORIES 路径接入。
        """
        if not hasattr(self, "_plugin_entries"):
            self._plugin_entries = {}
        self._plugin_entries[entry.id] = entry

    def get_plugin_entry(self, entry_id: str) -> "RegistryEntry | None":
        return getattr(self, "_plugin_entries", {}).get(entry_id)

    def list_plugin_entries(self) -> "list[RegistryEntry]":
        return list(getattr(self, "_plugin_entries", {}).values())


# 兼容别名：plan-decomposition.md §3.3 引用名 LLMProviderRegistry。
LLMProviderRegistry = LLMFactory
```

文件顶部追加：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.platform.plugins import RegistryEntry
```

- [ ] **Step 7: 在 adapters/llm 包级导出别名**

读 `sensenova_claw/adapters/llm/__init__.py`，如其中尚未导出 `LLMProviderRegistry`，在末尾追加：

```python
from sensenova_claw.adapters.llm.factory import LLMFactory, LLMProviderRegistry  # noqa: E402

__all__ = list(globals().get("__all__", [])) + ["LLMFactory", "LLMProviderRegistry"]
```

如原文件几乎为空，整个写成：

```python
"""LLM adapters。"""
from sensenova_claw.adapters.llm.factory import LLMFactory, LLMProviderRegistry

__all__ = ["LLMFactory", "LLMProviderRegistry"]
```

- [ ] **Step 8: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/capabilities/test_register_from_plugin.py -v`
Expected: PASS（5 个用例）

- [ ] **Step 9: 跑既有 Registry 相关回归测试，确认没破坏既有行为**

Run: `python3 -m pytest tests/unit/test_skill_registry.py tests/unit/test_agent_registry.py tests/unit/test_llm_factory_source_type.py -q`
Expected: PASS（与原基线一致；P1 没改既有方法，理论上 100% 通过）

- [ ] **Step 10: 提交**

```bash
git add sensenova_claw/capabilities/tools/registry.py \
        sensenova_claw/capabilities/skills/registry.py \
        sensenova_claw/capabilities/agents/registry.py \
        sensenova_claw/adapters/llm/factory.py \
        sensenova_claw/adapters/llm/__init__.py \
        tests/unit/capabilities/test_register_from_plugin.py
git commit -m "feat(registries): add register_from_plugin to existing 5 registries (P1 task 6)"
```

---

## Task 7: PluginLoader.load_all + InstallReport 数据类

**Files:**
- Create: `sensenova_claw/platform/plugins/loader.py`
- Modify: `sensenova_claw/platform/plugins/__init__.py`
- Create: `tests/unit/platform/plugins/test_loader.py`

- [ ] **Step 1: 写失败测试 — load_all 扫描多个 source 并合并**

写入 `tests/unit/platform/plugins/test_loader.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/platform/plugins/test_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'PluginLoader'`

- [ ] **Step 3: 写实现 — loader.py（仅 load_all + InstallReport 类）**

写入 `sensenova_claw/platform/plugins/loader.py`：

```python
"""PluginLoader — 扫描所有 source、按 identity 过滤、把 contribution 注入 Registry。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.3。

P1 范围：
  - load_all：识别 identity 参数但**不实施过滤**（P5 接入）
  - install_into_registries：把 contributes 解析成 RegistryEntry 注入对应 Registry
  - 不实例化 impl（P2 会在 install 时反射 Python 类）

不在 P1 范围：
  - visibility/identity 过滤算法（P5）
  - mcp_servers / hooks 的实际执行（P6）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sensenova_claw.platform.plugins.manifest import PluginManifest
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry
from sensenova_claw.platform.plugins.sources import PluginSource

if TYPE_CHECKING:
    from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry
    from sensenova_claw.adapters.llm.factory import LLMFactory
    from sensenova_claw.capabilities.agents.registry import AgentRegistry
    from sensenova_claw.capabilities.commands.registry import CommandRegistry
    from sensenova_claw.capabilities.hooks.registry import HookRegistry
    from sensenova_claw.capabilities.skills.registry import SkillRegistry
    from sensenova_claw.capabilities.tools.registry import ToolRegistry
    from sensenova_claw.platform.identity.identity import Identity  # P5 占位

logger = logging.getLogger(__name__)


@dataclass
class InstallFailure:
    """单条 contribution 注入失败的诊断信息。"""

    plugin_id: str
    contribution_kind: str         # llm_providers / tools / ...
    contribution_id: str | None    # 短 id；解析失败时可能为 None
    reason: str


@dataclass
class InstallReport:
    """install_into_registries 的结果汇总。

    永远不抛异常——失败的条目记在这里，方便诊断 / 上报事件。
    """

    installed: int = 0
    failures: list[InstallFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class PluginLoader:
    """plugin 加载与注入入口。"""

    def __init__(self, sources: list[PluginSource]) -> None:
        self._sources = sources

    # ── 扫描 ───────────────────────────────────────────────────

    def load_all(self, identity: "Identity | None" = None) -> list[PluginManifest]:
        """扫描所有 source，返回（按 identity 过滤后的）可见 plugin manifest。

        P1 实现：忽略 identity（参数保留兼容签名）。P5 接入真实过滤。
        """
        if identity is not None:
            logger.debug(
                "PluginLoader.load_all: identity=%r 已收到，但 P1 阶段不做过滤"
                "（P5 会接入 visibility 过滤）",
                identity,
            )
        manifests: list[PluginManifest] = []
        for source in self._sources:
            manifests.extend(source.list())
        return manifests

    # install_into_registries 在 Task 8 实现
```

- [ ] **Step 4: 在公开 API 暴露 PluginLoader / InstallReport / InstallFailure**

修改 `sensenova_claw/platform/plugins/__init__.py`：

```python
"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.loader import (
    InstallFailure,
    InstallReport,
    PluginLoader,
)
from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry
from sensenova_claw.platform.plugins.sources import (
    BuiltinPluginSource,
    PluginSource,
    SourceError,
    UserPluginSource,
)

__all__ = [
    "BuiltinPluginSource",
    "InstallFailure",
    "InstallReport",
    "ManifestValidationError",
    "PluginLoader",
    "PluginManifest",
    "PluginPermissions",
    "PluginSource",
    "RegistryEntry",
    "SourceError",
    "UserPluginSource",
    "load_manifest_from_yaml",
]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_loader.py -v`
Expected: PASS（3 个用例 — Task 7 阶段）

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/platform/plugins/loader.py \
        sensenova_claw/platform/plugins/__init__.py \
        tests/unit/platform/plugins/test_loader.py
git commit -m "feat(plugins): add PluginLoader.load_all + InstallReport (P1 task 7)"
```

---

## Task 8: PluginLoader.install_into_registries — 把 contribution 注入到 Registry

**Files:**
- Modify: `sensenova_claw/platform/plugins/loader.py`（追加方法）
- Modify: `tests/unit/platform/plugins/test_loader.py`（追加用例）

> **关键设计**：每条 contribution 解析成 `RegistryEntry`，按 contribution kind 路由到对应 Registry：
>
> | contributes 段 | 目标 Registry |
> |---|---|
> | `llm_providers` | LLMFactory（注入用 `register_from_plugin`） |
> | `tools` | ToolRegistry |
> | `channels` | ChannelRegistry |
> | `skills` | SkillRegistry |
> | `agents` | AgentRegistry |
> | `hooks` | HookRegistry |
> | `commands` | CommandRegistry |
> | `mcp_servers` | （本期不路由——P6 自己读 manifest.contributes['mcp_servers']） |
>
> RegistryEntry.id 统一：`f"{manifest.id}::{short_id}"`；hook 的 short_id 用 `f"{event}_{idx}"`（spec §4.3.6 hook 没有 id 字段）。

- [ ] **Step 1: 追加失败测试 — install_into_registries 把 contribution 路由到正确的 Registry**

把以下用例**追加**到 `tests/unit/platform/plugins/test_loader.py` 文件末尾：

```python
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
    _write_full_plugin(user_root, "team-a/full")

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/platform/plugins/test_loader.py -v`
Expected: FAIL — `AttributeError: 'PluginLoader' object has no attribute 'install_into_registries'`

- [ ] **Step 3: 实现 install_into_registries**

在 `sensenova_claw/platform/plugins/loader.py` 的 `class PluginLoader:` 内（`load_all` 之后）追加：

```python
    # ── 注入 Registry ─────────────────────────────────────────

    def install_into_registries(
        self,
        manifests: list[PluginManifest],
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        llm_registry: "LLMFactory",
        channel_registry: "ChannelRegistry",
        agent_registry: "AgentRegistry",
        hook_registry: "HookRegistry",
        command_registry: "CommandRegistry",
    ) -> InstallReport:
        """把每个 manifest 的 contributes 解析成 RegistryEntry 注入到对应 Registry。

        失败的 contribution 进入 InstallReport.failures，永不抛异常。
        ``mcp_servers`` 段在 P1 阶段不由本方法路由（P6 由 McpSessionManager 自取
        manifest.contributes['mcp_servers']）。
        """
        report = InstallReport()

        # contribution kind -> (target registry, has-id?)
        # has-id=True：contribution 必须自带 ``id`` 字段；False：用 event+idx 生成
        routes: dict[str, tuple[Any, bool]] = {
            "llm_providers": (llm_registry, True),
            "tools": (tool_registry, True),
            "channels": (channel_registry, True),
            "skills": (skill_registry, True),
            "agents": (agent_registry, True),
            "commands": (command_registry, True),
            "hooks": (hook_registry, False),
        }
        # P1 阶段 mcp_servers 由 P6 自己消费；这里识别但不路由也不报错
        ignored_kinds = {"mcp_servers"}

        for manifest in manifests:
            for kind, items in manifest.contributes.items():
                if kind in ignored_kinds:
                    continue
                if kind not in routes:
                    report.failures.append(
                        InstallFailure(
                            plugin_id=manifest.id,
                            contribution_kind=kind,
                            contribution_id=None,
                            reason=f"unknown contribution kind: {kind!r}",
                        )
                    )
                    continue
                if not isinstance(items, list):
                    report.failures.append(
                        InstallFailure(
                            plugin_id=manifest.id,
                            contribution_kind=kind,
                            contribution_id=None,
                            reason=f"{kind} must be a list, got {type(items).__name__}",
                        )
                    )
                    continue

                target_registry, requires_id = routes[kind]
                for idx, raw in enumerate(items):
                    self._install_one(
                        manifest=manifest,
                        kind=kind,
                        index=idx,
                        raw=raw,
                        target_registry=target_registry,
                        requires_id=requires_id,
                        report=report,
                    )

        return report

    # ── 内部：注入一条 contribution ──────────────────────────

    def _install_one(
        self,
        *,
        manifest: PluginManifest,
        kind: str,
        index: int,
        raw: Any,
        target_registry: Any,
        requires_id: bool,
        report: InstallReport,
    ) -> None:
        if not isinstance(raw, dict):
            report.failures.append(
                InstallFailure(
                    plugin_id=manifest.id,
                    contribution_kind=kind,
                    contribution_id=None,
                    reason=f"contribution must be a mapping, got {type(raw).__name__}",
                )
            )
            return

        # 计算 short_id
        if requires_id:
            short_id = raw.get("id")
            if not isinstance(short_id, str) or not short_id:
                report.failures.append(
                    InstallFailure(
                        plugin_id=manifest.id,
                        contribution_kind=kind,
                        contribution_id=None,
                        reason=f"{kind}[{index}] missing required 'id'",
                    )
                )
                return
        else:
            # hooks 没有 id 字段 — 用 event 名 + 索引生成
            event = raw.get("event", "Unknown")
            short_id = f"{event}_{index}"

        entry = RegistryEntry(
            id=f"{manifest.id}::{short_id}",
            short_id=short_id,
            owner_plugin=manifest.id,
            owner_team=manifest.owner,
            visibility=manifest.visibility,
            impl=None,                       # P1 不实例化
            metadata=dict(raw),              # 原样透传给 P2/P6
        )

        try:
            target_registry.register_from_plugin(entry)
        except Exception as e:  # 防御：register_from_plugin 不应抛，但兜底
            report.failures.append(
                InstallFailure(
                    plugin_id=manifest.id,
                    contribution_kind=kind,
                    contribution_id=short_id,
                    reason=f"register_from_plugin failed: {e}",
                )
            )
            return

        report.installed += 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_loader.py -v`
Expected: PASS（3 + 5 = 8 个用例）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/platform/plugins/loader.py \
        tests/unit/platform/plugins/test_loader.py
git commit -m "feat(plugins): implement PluginLoader.install_into_registries (P1 task 8)"
```

---

## Task 9: 端到端集成测试 — 从目录扫描到 7 个 Registry

**Files:**
- Modify: `tests/unit/platform/plugins/test_loader.py`（追加 e2e 用例）

> 这一步把 Task 7/8 串起来，验证一个 `BuiltinPluginSource` + 一个 `UserPluginSource` 真目录下、含 7 类 contribution 的两个 plugin 全部正确注入。

- [ ] **Step 1: 追加 e2e 测试**

把以下用例追加到 `tests/unit/platform/plugins/test_loader.py` 末尾：

```python
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
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/platform/plugins/test_loader.py -v`
Expected: PASS（8 + 1 = 9 个用例）

- [ ] **Step 3: 跑 P1 全部新增测试**

Run: `python3 -m pytest tests/unit/platform/plugins tests/unit/capabilities -v`
Expected: PASS（manifest 6 + sources 5 + registry_entry 2 + loader 9 + hook 4 + command 3 + channel 3 + register_from_plugin 5 = 37 个用例全过）

- [ ] **Step 4: 跑既有相关回归（确认 P1 没破坏 Task 6 修改的 Registry）**

Run: `python3 -m pytest tests/unit/test_skill_registry.py tests/unit/test_agent_registry.py tests/unit/test_llm_factory_source_type.py tests/unit/test_feishu_plugin.py -q`
Expected: PASS（与 P1 第一个任务前的基线一致）

- [ ] **Step 5: 提交**

```bash
git add tests/unit/platform/plugins/test_loader.py
git commit -m "test(plugins): end-to-end scan + install across 2 sources (P1 task 9)"
```

---

## Task 10: 最终提交 — 把整份 P1 plan 文件入库

**Files:**
- Verify: `docs/design/plans/P1-plugin-loader-and-registry-abstraction.md`（本文件，已经在 worktree 上由父代理写入）

> 本任务已由父代理单独执行（参见仓库历史第一个提交，commit message：`docs(plan): P1 PluginLoader + Registry abstraction`）。后续执行 plan 的工程师 **不要重复提交本文件**。

- [ ] **Step 1: 确认 plan 文件已经入库**

Run: `git log --oneline -- docs/design/plans/P1-plugin-loader-and-registry-abstraction.md`
Expected: 一行提交记录，message 含 `P1 PluginLoader + Registry abstraction`

- [ ] **Step 2: 确认目前共 9 次新增提交（任务 1~9）+ 1 次 plan 提交 = 10 次**

Run: `git log --oneline spec/plan-p1-plugin-loader ^main | wc -l`
Expected: `10`

---

## Self-Review

下面是写完 plan 后的自检结果（每条都已经在上面任务里覆盖）：

**1. Spec coverage（against decomposition §2 P1 范围）：**

| 范围条目 | 覆盖任务 |
|---|---|
| `PluginLoader` 类 | Task 7 / Task 8 |
| `RegistryEntry` 数据类 | Task 1 |
| 各 Registry 增加 `register_from_plugin` | Task 4（空 Registry）/ Task 5（ChannelRegistry）/ Task 6（既有 5 个） |
| Plugin manifest YAML schema 校验器 | Task 2（pydantic） |
| `PluginSource` 抽象 + builtin/user 实现 | Task 3 |
| `HookRegistry` / `CommandRegistry`（空） | Task 4 |
| `InstallReport`（不抛异常） | Task 7 / Task 8 |
| 不迁移既有内置能力 | 任务清单中**没有**改 `_register_builtin()` 的步骤——P2 做 |
| 不做 visibility 过滤 | Task 7 测试 `test_load_all_with_identity_none_does_not_filter` 显式验证 |
| 不做 mcp_servers / hooks 执行 | Task 8 测试 `test_install_ignores_mcp_servers_in_p1` 验证 |

**2. Placeholder scan：** 无 TBD / TODO / "implement later" / "fill in details" / "appropriate error handling" / "similar to Task N"。每个代码 step 都给了完整代码块。

**3. Type consistency：**
- `PluginManifest` 字段：与 §3.1 完全一致（`schema_version` / `id` / `version` / `name` / `description` / `owner` / `visibility` / `allowed_teams` / `allowed_users` / `min_core_version` / `max_core_version` / `permissions` / `config_schema` / `contributes` / `root_path`）
- `RegistryEntry` 字段：与 §3.2 完全一致（`id` / `short_id` / `owner_plugin` / `owner_team` / `visibility` / `impl` / `metadata`）
- `PluginLoader.load_all` / `install_into_registries` 的关键字参数名与 §3.3 完全一致（`tool_registry` / `skill_registry` / `llm_registry` / `channel_registry` / `agent_registry` / `hook_registry` / `command_registry`）
- 整篇 plan 中 `register_from_plugin` 名字不变；7 个 Registry 全部用同一签名 `register_from_plugin(entry: RegistryEntry) -> None`

**4. 决策记录与契约边界：**
- contract 文档（`docs/design/2026-04-27-plan-decomposition.md` §3.3）使用名 `LLMProviderRegistry`；既有代码里实际类名是 `LLMFactory`。本 plan 的 Task 6 在 `factory.py` 末尾加 `LLMProviderRegistry = LLMFactory` 别名以同时满足两边。
- 既有 `sensenova_claw/adapters/channels/` 没有显式 Registry 类。本 plan 在 Task 5 新建一个最简版 `ChannelRegistry`（仅满足契约），不动现有 `WebSocketChannel` / 飞书 channel 启动逻辑。
- hooks 的 contribution 没有 `id` 字段（spec §4.3.6），所以 Task 8 的实现里给 hook 单独走 `f"{event}_{idx}"` 命名规则。其他 6 类按 contribution.id 直接生成 namespace。
- mcp_servers 段不被 P1 的 `install_into_registries` 路由（spec 把 MCP 实例化放在 P6）；测试 `test_install_ignores_mcp_servers_in_p1` 把这个边界钉死。

---

**Plan complete and saved to `docs/design/plans/P1-plugin-loader-and-registry-abstraction.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 我每个 task 派一个 fresh subagent，每完成一个 task 我审一轮，节奏快。

**2. Inline Execution** - 在当前会话顺序执行 task 1~9，每 2~3 个 task 一个 checkpoint。

**Which approach?**
