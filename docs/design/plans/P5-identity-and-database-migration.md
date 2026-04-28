# P5 多团队 Identity 与数据库迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入多团队 `Identity` 抽象、按 visibility 过滤 plugin、给 Registry 注入 namespace 前缀、为存储层加 `team_id` 列与 `plugin_kv` 表，使 sensenova-claw 同进程内可以承载多个互不可见的 team，且现有用户在 `local-team` 默认下行为完全不变。

**Architecture:** 在 `sensenova_claw/platform/identity/` 新增 `Identity` 数据类与四级来源链解析器（显式 > env > file > default），由 P3 Control Protocol 的 `initialize` 握手注入到 `SessionContext`；P1 已实现的 `PluginLoader` 增加 `is_visible(manifest, identity)` 过滤与 `f"{plugin.id}::{contribution.id}"` namespace 前缀；存储层做加列式向后兼容迁移（`team_id TEXT NOT NULL DEFAULT 'local-team'` + 新表 `plugin_kv`），所有 Repository 读写自动按 `SessionContext.team_id` 过滤；Plugin 通过 `ctx.storage.get/set` API 访问 `(team_id, plugin_id)` 隔离的 KV。

**Tech Stack:** Python 3.12 + dataclasses + PyYAML + sqlite3 (`asyncio.to_thread`) + pytest + jsonschema（可选）；不引入新依赖，复用 P1 的 `PluginLoader`、P3 的 Control Protocol Server、P4 的 SDK 握手参数。

---

## 范围边界

**P5 覆盖：**
- `sensenova_claw/platform/identity/` 新包：`Identity` 数据类 + `default_local()` + `from_env()` + `from_file()` + `resolve()` 优先级链
- `PluginLoader.load_all(identity)` 接入 `is_visible()` 过滤
- `PluginLoader.install_into_registries()` 给每个 `RegistryEntry.id` 打 `f"{plugin.id}::{contribution.id}"` namespace
- `SessionContext` 新增 `team_id` 字段（与 P3 已占位 `local-team` 对接）
- 数据库迁移 `0XX_team_id.py`：`sessions/turns/messages/events/agent_messages` 加 `team_id TEXT NOT NULL DEFAULT 'local-team'`；新增 `plugin_kv (team_id, plugin_id, key, value)` 表
- `python3 -m sensenova_claw.adapters.storage.migrate up` 子命令（idempotent）
- `Repository` 关键读写按 `team_id` 过滤
- `PluginStorageContext.get/set` API（plugin in-context KV）
- Control Protocol `initialize` 解析 `params.identity`，缺失时 fall back `Identity.default_local()` **并打印 warning**
- Identity 不可在 session 中途切换（验证：`session.create` 拒绝 cross-identity 访问）

**P5 不覆盖：**
- 不改 Control Protocol wire 格式（仅消费 `params.identity`）
- 不实现新的 SDK API（仅 P4 已有 `Harness(identity=...)` 透传）
- 不实现 PostgreSQL Repository 或 marketplace（蓝图）
- 不实现 plugin marketplace 来源（仅 builtin + user，与 P1 一致）
- 不改任何 EventEnvelope 字段
- 不实现 hook / MCP（P6 范围）

**关键不变量：**
- 所有 builtin plugin（P2 创建）的 manifest 都声明 `visibility: public`，过滤启用后照常可见
- 老数据库 upgrade 后 `team_id` 一律填 `local-team`，老用户体验零差异
- Migration 是 idempotent + 加列式，**不改任何老列、不删任何老数据**

---

## 文件结构

新建文件：

| 路径 | 责任 |
|---|---|
| `sensenova_claw/platform/identity/__init__.py` | 包导出（`Identity`, `resolve_identity`, `IdentityError`） |
| `sensenova_claw/platform/identity/identity.py` | `Identity` 数据类、`default_local()`、`from_env()`、`from_file()`、`resolve()` |
| `sensenova_claw/platform/identity/errors.py` | `IdentityError`、`IdentityFileError` |
| `sensenova_claw/platform/plugins/visibility.py` | `is_visible(manifest, identity)` 纯函数（被 PluginLoader 调用） |
| `sensenova_claw/platform/plugins/storage.py` | `PluginStorageContext`（plugin 用 `ctx.storage.get/set`） |
| `sensenova_claw/adapters/storage/migrations/__init__.py` | migrations 包初始化 |
| `sensenova_claw/adapters/storage/migrations/runner.py` | `MigrationRunner`：扫描 + 执行 + 记录 `_schema_migrations` 表 |
| `sensenova_claw/adapters/storage/migrations/001_team_id.py` | 加 team_id 列 + plugin_kv 表 |
| `sensenova_claw/adapters/storage/migrate.py` | `python3 -m sensenova_claw.adapters.storage.migrate up` 入口 |
| `tests/unit/platform/identity/test_identity.py` | Identity 来源链 |
| `tests/unit/platform/plugins/test_visibility.py` | visibility 真值表 |
| `tests/unit/platform/plugins/test_namespace.py` | namespace 前缀 |
| `tests/unit/adapters/storage/test_plugin_storage.py` | PluginStorageContext 隔离 |
| `tests/unit/adapters/storage/test_migration_runner.py` | runner 幂等性 |
| `tests/integration/storage/test_migration_001.py` | v0 DB 升级到 v1 |
| `tests/integration/plugins/test_loader_visibility.py` | 双 team 加载 |
| `tests/integration/plugins/test_storage_isolation.py` | plugin A vs plugin B |
| `tests/integration/control/test_initialize_identity.py` | initialize 注入 + warning |

修改文件（最小切口）：

| 路径 | 改动 |
|---|---|
| `sensenova_claw/platform/plugins/loader.py` (P1 产出) | `load_all(identity)` 调 `is_visible`；`install_into_registries` 用 `f"{plugin.id}::{contribution.id}"` |
| `sensenova_claw/platform/plugins/registry_entry.py` (P1 产出) | 已有 `id` 字段，无改动 |
| `sensenova_claw/kernel/runtime/state_store.py` 或等价 SessionContext | 新增 `team_id: str = "local-team"` 字段 |
| `sensenova_claw/adapters/storage/repository.py` | `init` 调 `MigrationRunner.run`；新增按 `team_id` 过滤的读写方法；新增 `plugin_kv` CRUD |
| `sensenova_claw/interfaces/control/server.py` (P3 产出) | `initialize` 解析 `params.identity`，缺失打 warning + 用 default |
| `sensenova_claw/sdk/__init__.py` 或 `harness.py` (P4 产出) | `Harness.__init__(identity=None)` → `resolve_identity()` → 握手 params |

---

## Task 总览

| Task | 主题 | 依赖 |
|---|---|---|
| 1 | `Identity` 数据类 + `default_local()` | 无 |
| 2 | `Identity.from_env()` | T1 |
| 3 | `Identity.from_file()` | T1 |
| 4 | `resolve_identity()` 优先级链 | T1-3 |
| 5 | `is_visible()` 真值表 | 无（P1 已有 PluginManifest） |
| 6 | PluginLoader 接入 visibility 过滤 | T5 |
| 7 | PluginLoader namespace 前缀 | 无 |
| 8 | SessionContext 注入 team_id | T1 |
| 9 | MigrationRunner 框架 | 无 |
| 10 | 001_team_id 迁移脚本 | T9 |
| 11 | `python3 -m ... migrate up` 入口 | T9-10 |
| 12 | Repository 加 team_id 过滤（写路径） | T10 |
| 13 | Repository 加 team_id 过滤（读路径） | T10 |
| 14 | `plugin_kv` Repository CRUD | T10 |
| 15 | `PluginStorageContext` API | T14 |
| 16 | Control Protocol `initialize` 注入 + warning | T1, T8 |
| 17 | 集成测试：双 team 加载隔离 | T6 |
| 18 | 集成测试：v0 DB 迁移回归 | T10-11 |
| 19 | 集成测试：plugin storage 隔离 | T15 |
| 20 | 集成测试：initialize identity 端到端 | T16 |

---

## Task 1: Identity 数据类与 default_local

**Files:**
- Create: `sensenova_claw/platform/identity/__init__.py`
- Create: `sensenova_claw/platform/identity/identity.py`
- Create: `sensenova_claw/platform/identity/errors.py`
- Test: `tests/unit/platform/identity/test_identity.py`
- Test: `tests/unit/platform/identity/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/platform/identity/test_identity.py
from sensenova_claw.platform.identity import Identity


def test_identity_default_local_returns_canonical_values():
    ident = Identity.default_local()
    assert ident.user_id == "local-dev"
    assert ident.team_id == "local-team"
    assert ident.org_id == "local-org"
    # default 的来源标记必须是 "default"，便于诊断
    assert ident.source == "default"


def test_identity_dataclass_immutable_fields():
    ident = Identity(user_id="u1", team_id="t1", org_id="o1", source="explicit")
    assert ident.user_id == "u1"
    assert ident.team_id == "t1"
    assert ident.org_id == "o1"
    assert ident.source == "explicit"


def test_identity_default_source_is_placeholder():
    """契约保护：无参构造的 source 默认是 "placeholder"，
    避免 P3/P4 占位实例被误标为 "explicit"。
    （契约：docs/design/2026-04-27-plan-decomposition.md §3.4）
    """
    ident = Identity(user_id="u1", team_id="t1", org_id="o1")
    assert ident.source == "placeholder"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: `ModuleNotFoundError: No module named 'sensenova_claw.platform.identity'`

- [ ] **Step 3: Write minimal implementation**

```python
# sensenova_claw/platform/identity/errors.py
class IdentityError(Exception):
    """Identity 解析失败的基类。"""


class IdentityFileError(IdentityError):
    """identity.yaml 文件存在但格式非法。"""
```

```python
# sensenova_claw/platform/identity/identity.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IdentitySource = Literal["explicit", "env", "file", "default", "placeholder"]


@dataclass(frozen=True)
class Identity:
    """用户/团队/组织三元组。整个 session 生命周期内不可变。

    `source` 为诊断日志字段，下游业务逻辑不读取。默认值 "placeholder"
    用于让 P3/P4 上线前的临时占位实例可以无参构造而不会被错误地
    标记为 "explicit"；resolve() / from_env() / from_file() /
    default_local() 等工厂方法会显式覆盖为正确值。
    （契约定义：docs/design/2026-04-27-plan-decomposition.md §3.4）
    """

    user_id: str
    team_id: str
    org_id: str
    source: IdentitySource = "placeholder"

    @classmethod
    def default_local(cls) -> "Identity":
        """本地开发占位 identity；云端/CI 应显式覆盖。"""
        return cls(
            user_id="local-dev",
            team_id="local-team",
            org_id="local-org",
            source="default",
        )
```

```python
# sensenova_claw/platform/identity/__init__.py
from sensenova_claw.platform.identity.errors import IdentityError, IdentityFileError
from sensenova_claw.platform.identity.identity import Identity

__all__ = ["Identity", "IdentityError", "IdentityFileError"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/identity tests/unit/platform/identity
git commit -m "feat(identity): 引入 Identity 数据类与 default_local 构造器"
```

---

## Task 2: Identity.from_env

**Files:**
- Modify: `sensenova_claw/platform/identity/identity.py`
- Test: `tests/unit/platform/identity/test_identity.py`

- [ ] **Step 1: Write failing test**

```python
# 追加到 tests/unit/platform/identity/test_identity.py
import os
import pytest


def test_from_env_reads_three_env_vars(monkeypatch):
    monkeypatch.setenv("SENSENOVA_CLAW_USER_ID", "u-from-env")
    monkeypatch.setenv("SENSENOVA_CLAW_TEAM_ID", "team-env")
    monkeypatch.setenv("SENSENOVA_CLAW_ORG_ID", "org-env")
    ident = Identity.from_env()
    assert ident is not None
    assert ident.user_id == "u-from-env"
    assert ident.team_id == "team-env"
    assert ident.org_id == "org-env"
    assert ident.source == "env"


def test_from_env_returns_none_when_all_unset(monkeypatch):
    monkeypatch.delenv("SENSENOVA_CLAW_USER_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_TEAM_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_ORG_ID", raising=False)
    assert Identity.from_env() is None


def test_from_env_partial_raises(monkeypatch):
    """部分设置必须报错——避免 team_id 漏配静默回退到 local-team。"""
    monkeypatch.setenv("SENSENOVA_CLAW_USER_ID", "u1")
    monkeypatch.delenv("SENSENOVA_CLAW_TEAM_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_ORG_ID", raising=False)
    from sensenova_claw.platform.identity import IdentityError
    with pytest.raises(IdentityError):
        Identity.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py::test_from_env_reads_three_env_vars -v
```

Expected: `AttributeError: type object 'Identity' has no attribute 'from_env'`

- [ ] **Step 3: Write minimal implementation**

```python
# 追加到 sensenova_claw/platform/identity/identity.py
import os

from sensenova_claw.platform.identity.errors import IdentityError


# 在 Identity class 内追加：
    @classmethod
    def from_env(cls) -> "Identity | None":
        """从 SENSENOVA_CLAW_{USER,TEAM,ORG}_ID 三个环境变量读取。

        - 三个全空：返回 None（让上层链继续）
        - 三个全有：返回 Identity(source="env")
        - 部分设置：抛 IdentityError（防止漏配静默退化）
        """
        user_id = os.environ.get("SENSENOVA_CLAW_USER_ID", "").strip()
        team_id = os.environ.get("SENSENOVA_CLAW_TEAM_ID", "").strip()
        org_id = os.environ.get("SENSENOVA_CLAW_ORG_ID", "").strip()
        present = [bool(v) for v in (user_id, team_id, org_id)]
        if not any(present):
            return None
        if not all(present):
            raise IdentityError(
                "SENSENOVA_CLAW_{USER,TEAM,ORG}_ID 必须三个一起设置，当前部分缺失"
            )
        return cls(user_id=user_id, team_id=team_id, org_id=org_id, source="env")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/identity/identity.py tests/unit/platform/identity/test_identity.py
git commit -m "feat(identity): Identity.from_env 三变量必须同设否则报错"
```

---

## Task 3: Identity.from_file

**Files:**
- Modify: `sensenova_claw/platform/identity/identity.py`
- Test: `tests/unit/platform/identity/test_identity.py`

- [ ] **Step 1: Write failing test**

```python
# 追加到 tests/unit/platform/identity/test_identity.py
def test_from_file_reads_yaml(tmp_path):
    f = tmp_path / "identity.yaml"
    f.write_text(
        "user_id: u-file\nteam_id: team-file\norg_id: org-file\n",
        encoding="utf-8",
    )
    ident = Identity.from_file(f)
    assert ident is not None
    assert ident.user_id == "u-file"
    assert ident.team_id == "team-file"
    assert ident.org_id == "org-file"
    assert ident.source == "file"


def test_from_file_missing_returns_none(tmp_path):
    assert Identity.from_file(tmp_path / "nope.yaml") is None


def test_from_file_invalid_yaml_raises(tmp_path):
    f = tmp_path / "identity.yaml"
    f.write_text("user_id: u\nteam_id\n", encoding="utf-8")  # 故意非法
    from sensenova_claw.platform.identity import IdentityFileError
    with pytest.raises(IdentityFileError):
        Identity.from_file(f)


def test_from_file_missing_keys_raises(tmp_path):
    f = tmp_path / "identity.yaml"
    f.write_text("user_id: u\nteam_id: t\n", encoding="utf-8")  # 缺 org_id
    from sensenova_claw.platform.identity import IdentityFileError
    with pytest.raises(IdentityFileError):
        Identity.from_file(f)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py::test_from_file_reads_yaml -v
```

Expected: `AttributeError: type object 'Identity' has no attribute 'from_file'`

- [ ] **Step 3: Write minimal implementation**

```python
# 追加到 sensenova_claw/platform/identity/identity.py
from pathlib import Path

import yaml

from sensenova_claw.platform.identity.errors import IdentityFileError


# 在 Identity class 内追加：
    @classmethod
    def from_file(cls, path: "str | Path") -> "Identity | None":
        """从 YAML 文件读取 identity（默认 ~/.sensenova-claw/identity.yaml）。

        - 文件不存在：返回 None
        - 文件存在但 YAML 非法：IdentityFileError
        - 缺关键字段：IdentityFileError
        """
        p = Path(path).expanduser()
        if not p.exists():
            return None
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise IdentityFileError(f"解析 {p} 失败: {exc}") from exc
        if not isinstance(data, dict):
            raise IdentityFileError(f"{p} 顶层必须是 mapping")
        for key in ("user_id", "team_id", "org_id"):
            if not data.get(key):
                raise IdentityFileError(f"{p} 缺少必填字段: {key}")
        return cls(
            user_id=str(data["user_id"]),
            team_id=str(data["team_id"]),
            org_id=str(data["org_id"]),
            source="file",
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/identity/identity.py tests/unit/platform/identity/test_identity.py
git commit -m "feat(identity): Identity.from_file 读取 ~/.sensenova-claw/identity.yaml"
```

---

## Task 4: resolve_identity 优先级链

**Files:**
- Modify: `sensenova_claw/platform/identity/identity.py`
- Modify: `sensenova_claw/platform/identity/__init__.py`
- Test: `tests/unit/platform/identity/test_identity.py`

- [ ] **Step 1: Write failing test**

```python
# 追加到 tests/unit/platform/identity/test_identity.py
from sensenova_claw.platform.identity import resolve_identity


def test_resolve_explicit_wins_over_env(monkeypatch):
    monkeypatch.setenv("SENSENOVA_CLAW_USER_ID", "u-env")
    monkeypatch.setenv("SENSENOVA_CLAW_TEAM_ID", "team-env")
    monkeypatch.setenv("SENSENOVA_CLAW_ORG_ID", "org-env")
    explicit = Identity(user_id="u-x", team_id="team-x", org_id="org-x", source="explicit")
    out = resolve_identity(explicit=explicit, file_path=None)
    assert out is explicit  # 显式传入直接返回


def test_resolve_env_wins_over_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SENSENOVA_CLAW_USER_ID", "u-env")
    monkeypatch.setenv("SENSENOVA_CLAW_TEAM_ID", "team-env")
    monkeypatch.setenv("SENSENOVA_CLAW_ORG_ID", "org-env")
    f = tmp_path / "identity.yaml"
    f.write_text("user_id: u-f\nteam_id: team-f\norg_id: org-f\n", encoding="utf-8")
    out = resolve_identity(explicit=None, file_path=f)
    assert out.team_id == "team-env"
    assert out.source == "env"


def test_resolve_file_wins_over_default(monkeypatch, tmp_path):
    monkeypatch.delenv("SENSENOVA_CLAW_USER_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_TEAM_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_ORG_ID", raising=False)
    f = tmp_path / "identity.yaml"
    f.write_text("user_id: u-f\nteam_id: team-f\norg_id: org-f\n", encoding="utf-8")
    out = resolve_identity(explicit=None, file_path=f)
    assert out.source == "file"
    assert out.team_id == "team-f"


def test_resolve_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.delenv("SENSENOVA_CLAW_USER_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_TEAM_ID", raising=False)
    monkeypatch.delenv("SENSENOVA_CLAW_ORG_ID", raising=False)
    out = resolve_identity(explicit=None, file_path=tmp_path / "absent.yaml")
    assert out.source == "default"
    assert out.team_id == "local-team"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: `ImportError: cannot import name 'resolve_identity'`

- [ ] **Step 3: Write minimal implementation**

```python
# 追加到 sensenova_claw/platform/identity/identity.py（文件底部）
def resolve_identity(
    *,
    explicit: "Identity | None" = None,
    file_path: "str | Path | None" = None,
) -> "Identity":
    """按优先级链解析 identity：explicit > env > file > default。

    file_path 默认为 ~/.sensenova-claw/identity.yaml，可被调用方覆盖（测试用）。
    """
    if explicit is not None:
        return explicit
    from_env = Identity.from_env()
    if from_env is not None:
        return from_env
    target = Path(file_path) if file_path is not None else Path("~/.sensenova-claw/identity.yaml")
    from_file = Identity.from_file(target)
    if from_file is not None:
        return from_file
    return Identity.default_local()
```

```python
# 修改 sensenova_claw/platform/identity/__init__.py
from sensenova_claw.platform.identity.errors import IdentityError, IdentityFileError
from sensenova_claw.platform.identity.identity import Identity, resolve_identity

__all__ = ["Identity", "IdentityError", "IdentityFileError", "resolve_identity"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/identity/test_identity.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/identity tests/unit/platform/identity
git commit -m "feat(identity): resolve_identity 实现 explicit>env>file>default 优先级链"
```

---

## Task 5: is_visible 真值表

**Files:**
- Create: `sensenova_claw/platform/plugins/visibility.py`
- Test: `tests/unit/platform/plugins/test_visibility.py`
- Test: `tests/unit/platform/plugins/__init__.py`（如不存在）

注：依赖 P1 已交付 `PluginManifest`（参见 `docs/design/2026-04-27-plan-decomposition.md` §3.1）。

- [ ] **Step 1: Write failing test**

```python
# tests/unit/platform/plugins/test_visibility.py
from pathlib import Path

import pytest

from sensenova_claw.platform.identity import Identity
from sensenova_claw.platform.plugins.manifest import PluginManifest, PluginPermissions
from sensenova_claw.platform.plugins.visibility import is_visible


def make_manifest(*, owner: str, visibility: str, allowed_teams=None) -> PluginManifest:
    return PluginManifest(
        schema_version="1",
        id=f"{owner}/some-plugin",
        version="1.0.0",
        name="P",
        description="d",
        owner=owner,
        visibility=visibility,
        allowed_teams=list(allowed_teams or []),
        allowed_users=[],
        min_core_version="1.2.0",
        max_core_version=None,
        permissions=PluginPermissions(),
        config_schema=None,
        contributes={},
        root_path=Path("."),
    )


@pytest.fixture
def team_a():
    return Identity(user_id="u-a", team_id="team-a", org_id="org", source="explicit")


@pytest.fixture
def team_b():
    return Identity(user_id="u-b", team_id="team-b", org_id="org", source="explicit")


def test_public_always_visible(team_a, team_b):
    m = make_manifest(owner="team-a", visibility="public")
    assert is_visible(m, team_a) is True
    assert is_visible(m, team_b) is True


def test_internal_visible_only_to_allowed_teams(team_a, team_b):
    m = make_manifest(owner="team-a", visibility="internal", allowed_teams=["team-a", "team-b"])
    assert is_visible(m, team_a) is True
    assert is_visible(m, team_b) is True
    other = Identity(user_id="u", team_id="team-c", org_id="org", source="explicit")
    assert is_visible(m, other) is False


def test_internal_with_empty_allowed_teams_visible_only_to_owner(team_a, team_b):
    m = make_manifest(owner="team-a", visibility="internal", allowed_teams=[])
    assert is_visible(m, team_a) is True   # owner 隐式包含
    assert is_visible(m, team_b) is False


def test_private_only_owner(team_a, team_b):
    m = make_manifest(owner="team-a", visibility="private")
    assert is_visible(m, team_a) is True
    assert is_visible(m, team_b) is False


def test_unknown_visibility_denied(team_a):
    m = make_manifest(owner="team-a", visibility="weird")
    assert is_visible(m, team_a) is False  # 未知值默认拒绝（fail-closed）


def test_none_identity_treats_as_default_local():
    """identity=None（loader 兼容旧调用）等价于 default_local，仅 public 可见。"""
    m_pub = make_manifest(owner="team-a", visibility="public")
    m_priv = make_manifest(owner="team-a", visibility="private")
    assert is_visible(m_pub, None) is True
    assert is_visible(m_priv, None) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/plugins/test_visibility.py -v
```

Expected: `ModuleNotFoundError: ... visibility`

- [ ] **Step 3: Write minimal implementation**

```python
# sensenova_claw/platform/plugins/visibility.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.platform.identity import Identity
    from sensenova_claw.platform.plugins.manifest import PluginManifest


def is_visible(manifest: "PluginManifest", identity: "Identity | None") -> bool:
    """按 spec §7.2 的算法判定 manifest 对 identity 是否可见。

    - public:   永远可见
    - internal: identity.team_id == manifest.owner OR in allowed_teams
    - private:  identity.team_id == manifest.owner
    - 其他:     fail-closed，返回 False
    - identity=None: 等价于 default_local，仅 public 可见
    """
    visibility = (manifest.visibility or "").strip().lower()
    if visibility == "public":
        return True

    # identity 缺省时只允许 public（fail-closed）
    if identity is None:
        return False

    team_id = identity.team_id
    owner = manifest.owner

    if visibility == "internal":
        if team_id == owner:
            return True
        return team_id in (manifest.allowed_teams or [])
    if visibility == "private":
        return team_id == owner
    return False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/plugins/test_visibility.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/plugins/visibility.py tests/unit/platform/plugins/test_visibility.py tests/unit/platform/plugins/__init__.py
git commit -m "feat(plugins): is_visible 实现 public/internal/private 三级 + fail-closed"
```

---

## Task 6: PluginLoader 接入 visibility 过滤

**Files:**
- Modify: `sensenova_claw/platform/plugins/loader.py`（P1 已创建）
- Test: `tests/unit/platform/plugins/test_loader_visibility.py`

注：本 task 仅修改 `load_all` 方法的过滤逻辑，不动其他 P1 行为。

- [ ] **Step 1: Write failing test**

```python
# tests/unit/platform/plugins/test_loader_visibility.py
from pathlib import Path

from sensenova_claw.platform.identity import Identity
from sensenova_claw.platform.plugins.loader import PluginLoader
from sensenova_claw.platform.plugins.manifest import PluginManifest, PluginPermissions


class _StubSource:
    """测试用的内存 PluginSource。"""

    def __init__(self, manifests):
        self._manifests = manifests

    def list(self):
        return list(self._manifests)


def _make(id_: str, owner: str, visibility: str, allowed_teams=None) -> PluginManifest:
    return PluginManifest(
        schema_version="1",
        id=id_,
        version="1.0.0",
        name=id_,
        description="",
        owner=owner,
        visibility=visibility,
        allowed_teams=list(allowed_teams or []),
        allowed_users=[],
        min_core_version="1.2.0",
        max_core_version=None,
        permissions=PluginPermissions(),
        config_schema=None,
        contributes={},
        root_path=Path("."),
    )


def test_loader_filters_by_visibility():
    src = _StubSource([
        _make("core/builtin-tools", owner="core", visibility="public"),
        _make("team-a/secret",      owner="team-a", visibility="private"),
        _make("team-b/secret",      owner="team-b", visibility="private"),
        _make("team-a/share",       owner="team-a", visibility="internal", allowed_teams=["team-b"]),
    ])
    loader = PluginLoader(sources=[src])

    ident_a = Identity(user_id="u", team_id="team-a", org_id="org", source="explicit")
    ident_b = Identity(user_id="u", team_id="team-b", org_id="org", source="explicit")

    visible_a = {m.id for m in loader.load_all(identity=ident_a)}
    visible_b = {m.id for m in loader.load_all(identity=ident_b)}

    assert visible_a == {"core/builtin-tools", "team-a/secret", "team-a/share"}
    assert visible_b == {"core/builtin-tools", "team-b/secret", "team-a/share"}


def test_loader_identity_none_only_public():
    src = _StubSource([
        _make("core/x", owner="core", visibility="public"),
        _make("team-a/y", owner="team-a", visibility="private"),
    ])
    loader = PluginLoader(sources=[src])
    visible = {m.id for m in loader.load_all(identity=None)}
    assert visible == {"core/x"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/plugins/test_loader_visibility.py -v
```

Expected: P1 的 `load_all` 不过滤，全部 4 个返回 → 第一个 assert 失败。

- [ ] **Step 3: Modify load_all to apply is_visible**

定位 P1 的 `sensenova_claw/platform/plugins/loader.py`，修改 `load_all`：

```python
# sensenova_claw/platform/plugins/loader.py（diff 提示）
from sensenova_claw.platform.plugins.visibility import is_visible


class PluginLoader:
    # ...

    def load_all(self, identity: "Identity | None" = None) -> list[PluginManifest]:
        """扫描 sources，按 identity 过滤后返回可见 manifest 列表。

        identity=None 时按 fail-closed 处理（仅 public 可见）。
        """
        visible: list[PluginManifest] = []
        for source in self._sources:
            for manifest in source.list():
                if not is_visible(manifest, identity):
                    continue
                visible.append(manifest)
        return visible
```

不可见 plugin **不进入返回值，也不进入任何内存结构**——核心不变量。

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/plugins/test_loader_visibility.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full P1 unit suite to confirm no regression**

```bash
python3 -m pytest tests/unit/platform/plugins/ -v
```

Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/platform/plugins/loader.py tests/unit/platform/plugins/test_loader_visibility.py
git commit -m "feat(plugins): PluginLoader.load_all 按 identity 过滤 visibility"
```

---

## Task 7: PluginLoader namespace 前缀

**Files:**
- Modify: `sensenova_claw/platform/plugins/loader.py`
- Test: `tests/unit/platform/plugins/test_namespace.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/platform/plugins/test_namespace.py
from pathlib import Path
from unittest.mock import MagicMock

from sensenova_claw.platform.plugins.loader import PluginLoader
from sensenova_claw.platform.plugins.manifest import PluginManifest, PluginPermissions
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry


def _manifest_with_one_tool() -> PluginManifest:
    return PluginManifest(
        schema_version="1",
        id="team-a/crm-assistant",
        version="1.0.0",
        name="CRM",
        description="",
        owner="team-a",
        visibility="public",
        allowed_teams=[],
        allowed_users=[],
        min_core_version="1.2.0",
        max_core_version=None,
        permissions=PluginPermissions(),
        config_schema=None,
        contributes={
            "tools": [
                {"id": "crm_lookup", "type": "python", "python": "x.y:Z"},
            ],
        },
        root_path=Path("."),
    )


def test_install_into_registries_uses_qualified_id():
    """RegistryEntry.id 必须为 f"{plugin.id}::{contribution.id}"。"""
    loader = PluginLoader(sources=[])
    tool_registry = MagicMock()
    skill_registry = MagicMock()
    llm_registry = MagicMock()
    channel_registry = MagicMock()
    agent_registry = MagicMock()
    hook_registry = MagicMock()
    command_registry = MagicMock()

    loader.install_into_registries(
        manifests=[_manifest_with_one_tool()],
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        llm_registry=llm_registry,
        channel_registry=channel_registry,
        agent_registry=agent_registry,
        hook_registry=hook_registry,
        command_registry=command_registry,
    )

    # 校验：tool_registry.register_from_plugin 被调用，传入的 RegistryEntry.id
    # = "team-a/crm-assistant::crm_lookup"
    assert tool_registry.register_from_plugin.called
    call = tool_registry.register_from_plugin.call_args
    entry: RegistryEntry = call.args[0]
    assert entry.id == "team-a/crm-assistant::crm_lookup"
    assert entry.short_id == "crm_lookup"
    assert entry.owner_plugin == "team-a/crm-assistant"
    assert entry.owner_team == "team-a"
    assert entry.visibility == "public"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/platform/plugins/test_namespace.py -v
```

Expected: P1 可能用未限定 id 或抛 attribute 错。

- [ ] **Step 3: Modify install_into_registries to format namespaced id**

在 `sensenova_claw/platform/plugins/loader.py` 的 `install_into_registries` 内，定位每条 contribution 构造 `RegistryEntry` 的位置，改成：

```python
# sensenova_claw/platform/plugins/loader.py（关键片段）
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry


def _qualified_id(plugin_id: str, contribution_id: str) -> str:
    """生成全局唯一的 namespaced id，LLM 看到的就是这个值。"""
    return f"{plugin_id}::{contribution_id}"


# ... install_into_registries 内对每个 contribution：
for tool in manifest.contributes.get("tools", []):
    entry = RegistryEntry(
        id=_qualified_id(manifest.id, tool["id"]),
        short_id=tool["id"],
        owner_plugin=manifest.id,
        owner_team=manifest.owner,
        visibility=manifest.visibility,
        impl=...,  # P1 已构造
        metadata={"manifest_entry": tool},
    )
    tool_registry.register_from_plugin(entry)
# 同样模式应用到 skills / llm_providers / channels / agents / hooks / commands
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/platform/plugins/test_namespace.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/plugins/loader.py tests/unit/platform/plugins/test_namespace.py
git commit -m "feat(plugins): RegistryEntry.id 注入 plugin_id 命名空间前缀"
```

---

## Task 8: SessionContext 注入 team_id

**Files:**
- Modify: `sensenova_claw/kernel/runtime/session_context.py`（如不存在则创建；具体路径以 P3 实际产出为准）
- Test: `tests/unit/kernel/runtime/test_session_context.py`

> 实施提示：P3 已经引入了 SessionContext 占位实现（含 `identity: Identity = default_local()`）。本 task 只补全 `team_id` 便利属性 + 测试。如果 P3 路径与本任务不一致，定位实际文件后等价修改。

- [ ] **Step 1: Write failing test**

```python
# tests/unit/kernel/runtime/test_session_context.py
from sensenova_claw.kernel.runtime.session_context import SessionContext
from sensenova_claw.platform.identity import Identity


def test_session_context_default_team_id_is_local_team():
    ctx = SessionContext(session_id="s-1")
    assert ctx.team_id == "local-team"
    assert ctx.identity.source == "default"


def test_session_context_team_id_follows_identity():
    ident = Identity(user_id="u", team_id="team-a", org_id="org", source="explicit")
    ctx = SessionContext(session_id="s-2", identity=ident)
    assert ctx.team_id == "team-a"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/kernel/runtime/test_session_context.py -v
```

Expected: 缺 `team_id` 属性或缺 `identity` 字段。

- [ ] **Step 3: Add team_id property + identity field**

```python
# sensenova_claw/kernel/runtime/session_context.py（关键差异）
from dataclasses import dataclass, field

from sensenova_claw.platform.identity import Identity


@dataclass
class SessionContext:
    session_id: str
    identity: Identity = field(default_factory=Identity.default_local)
    # ... P3 已有的其他字段保留

    @property
    def team_id(self) -> str:
        """便利属性：让 Repository / Storage 直接 ctx.team_id 取值。"""
        return self.identity.team_id
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/kernel/runtime/test_session_context.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/kernel/runtime/session_context.py tests/unit/kernel/runtime/test_session_context.py
git commit -m "feat(runtime): SessionContext 增加 identity 与 team_id 便利属性"
```

---

## Task 9: MigrationRunner 框架

**Files:**
- Create: `sensenova_claw/adapters/storage/migrations/__init__.py`
- Create: `sensenova_claw/adapters/storage/migrations/runner.py`
- Test: `tests/unit/adapters/storage/test_migration_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/adapters/storage/test_migration_runner.py
import sqlite3

import pytest

from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner


class _M:
    """测试用 migration：每个 migration 暴露 version, name, up(conn)。"""

    def __init__(self, version: int, name: str, sql: str):
        self.version = version
        self.name = name
        self.sql = sql

    def up(self, conn):
        conn.executescript(self.sql)


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_runner_creates_meta_table_and_runs_migrations(conn):
    runner = MigrationRunner(migrations=[
        _M(1, "create_x", "CREATE TABLE x (a INTEGER);"),
        _M(2, "create_y", "CREATE TABLE y (b INTEGER);"),
    ])
    applied = runner.run(conn)
    assert applied == [1, 2]
    cur = conn.execute(
        "SELECT version FROM _schema_migrations ORDER BY version"
    ).fetchall()
    assert [r[0] for r in cur] == [1, 2]


def test_runner_is_idempotent(conn):
    """跑两次应不重复执行。"""
    m = [_M(1, "create_x", "CREATE TABLE x (a INTEGER);")]
    runner = MigrationRunner(migrations=m)
    assert runner.run(conn) == [1]
    assert runner.run(conn) == []  # 第二次什么都不做
    rows = conn.execute("SELECT version FROM _schema_migrations").fetchall()
    assert [r[0] for r in rows] == [1]


def test_runner_runs_in_version_order(conn):
    """乱序传入也按 version 升序执行。"""
    m = [
        _M(2, "second", "CREATE TABLE y (b INTEGER);"),
        _M(1, "first", "CREATE TABLE x (a INTEGER);"),
    ]
    runner = MigrationRunner(migrations=m)
    assert runner.run(conn) == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/adapters/storage/test_migration_runner.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# sensenova_claw/adapters/storage/migrations/runner.py
from __future__ import annotations

import logging
import sqlite3
from typing import Protocol

logger = logging.getLogger(__name__)


class Migration(Protocol):
    version: int
    name: str

    def up(self, conn: sqlite3.Connection) -> None:
        ...


_META_SQL = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at REAL NOT NULL
);
"""


class MigrationRunner:
    """按 version 升序串行执行 migration，记录到 _schema_migrations。"""

    def __init__(self, migrations: list[Migration]):
        self._migrations = sorted(migrations, key=lambda m: m.version)

    def run(self, conn: sqlite3.Connection) -> list[int]:
        """返回本次实际新执行的 version 列表（已 applied 不重跑）。"""
        import time

        conn.executescript(_META_SQL)
        applied_rows = conn.execute(
            "SELECT version FROM _schema_migrations"
        ).fetchall()
        applied: set[int] = {row[0] for row in applied_rows}
        ran: list[int] = []
        for m in self._migrations:
            if m.version in applied:
                continue
            logger.info("running migration %d: %s", m.version, m.name)
            m.up(conn)
            conn.execute(
                "INSERT INTO _schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (m.version, m.name, time.time()),
            )
            conn.commit()
            ran.append(m.version)
        return ran
```

```python
# sensenova_claw/adapters/storage/migrations/__init__.py
from sensenova_claw.adapters.storage.migrations.runner import Migration, MigrationRunner

__all__ = ["Migration", "MigrationRunner"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/adapters/storage/test_migration_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/adapters/storage/migrations tests/unit/adapters/storage/test_migration_runner.py
git commit -m "feat(storage): MigrationRunner 按 version 升序幂等执行 migrations"
```

---

## Task 10: 001_team_id 迁移脚本

**Files:**
- Create: `sensenova_claw/adapters/storage/migrations/001_team_id.py`
- Test: `tests/integration/storage/test_migration_001.py`
- Test: `tests/integration/storage/__init__.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/storage/test_migration_001.py
"""验证 001_team_id 在已有数据的旧库上能就地升级，不破坏老数据。"""
import sqlite3
import time

import pytest


@pytest.fixture
def v0_db(tmp_path):
    """构造一个 v0 schema（来自 repository.py SCHEMA_SQL，无 team_id 列）。"""
    db_path = tmp_path / "v0.db"
    conn = sqlite3.connect(db_path)
    # 仅创建本任务关心的表（最小复现）
    conn.executescript("""
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            last_active REAL NOT NULL,
            meta TEXT,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE turns (
            turn_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at REAL NOT NULL,
            ended_at REAL,
            user_input TEXT,
            agent_response TEXT
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls TEXT,
            tool_call_id TEXT,
            tool_name TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT,
            event_type TEXT NOT NULL,
            timestamp REAL NOT NULL,
            source TEXT NOT NULL,
            trace_id TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE agent_messages (
            id TEXT PRIMARY KEY,
            parent_session_id TEXT NOT NULL,
            child_session_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT NOT NULL,
            mode TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at REAL NOT NULL
        );
    """)
    now = time.time()
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
        ("s-old", now, now, "{}", "active"),
    )
    conn.execute(
        "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t-old", "s-old", "completed", now, now, "hi", "hello"),
    )
    conn.execute(
        "INSERT INTO messages (session_id, turn_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("s-old", "t-old", "user", "hi", now),
    )
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("e-old", "s-old", "t-old", "user.input", now, "ui", None, "{}"),
    )
    conn.execute(
        "INSERT INTO agent_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("am-old", "s-old", "s-child", "agent-x", "running", "async", "go", now),
    )
    conn.commit()
    conn.close()
    return db_path


def test_migration_001_adds_team_id_columns_with_default(v0_db):
    from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
    from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001

    conn = sqlite3.connect(v0_db)
    runner = MigrationRunner(migrations=[m001])
    runner.run(conn)

    for table in ("sessions", "turns", "messages", "events", "agent_messages"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert "team_id" in cols, f"{table} 缺 team_id"

    # 老数据自动填入 'local-team'
    for table in ("sessions", "turns", "messages", "events", "agent_messages"):
        rows = conn.execute(f"SELECT team_id FROM {table}").fetchall()
        assert all(r[0] == "local-team" for r in rows), f"{table} 老数据 team_id 应为 local-team"

    conn.close()


def test_migration_001_creates_plugin_kv_table(v0_db):
    from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
    from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001

    conn = sqlite3.connect(v0_db)
    MigrationRunner(migrations=[m001]).run(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(plugin_kv)").fetchall()}
    assert cols == {"team_id", "plugin_id", "key", "value"}

    pk_rows = conn.execute("PRAGMA table_info(plugin_kv)").fetchall()
    pk_cols = sorted([r[1] for r in pk_rows if r[5] > 0])
    assert pk_cols == sorted(["team_id", "plugin_id", "key"])
    conn.close()


def test_migration_001_old_query_still_works(v0_db):
    """加列后老的 SELECT * FROM sessions 等查询不能爆表。"""
    from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
    from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001

    conn = sqlite3.connect(v0_db)
    MigrationRunner(migrations=[m001]).run(conn)
    rows = conn.execute("SELECT * FROM sessions WHERE session_id = ?", ("s-old",)).fetchall()
    assert len(rows) == 1
    conn.close()


def test_migration_001_idempotent(v0_db):
    """跑两次不报错。"""
    from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
    from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001

    conn = sqlite3.connect(v0_db)
    runner = MigrationRunner(migrations=[m001])
    runner.run(conn)
    second = runner.run(conn)
    assert second == []
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/integration/storage/test_migration_001.py -v
```

Expected: `ModuleNotFoundError: ... m001_team_id`

- [ ] **Step 3: Write the migration**

```python
# sensenova_claw/adapters/storage/migrations/m001_team_id.py
"""Migration 001：为现有表加 team_id 列并新建 plugin_kv 表。

设计要求：
- 加列式向后兼容：不改任何老列、不删任何老数据
- DEFAULT 'local-team' 让老行自动填值
- plugin_kv 主键 (team_id, plugin_id, key) 强制按 team 隔离
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class _Migration001:
    version: int = 1
    name: str = "team_id_and_plugin_kv"

    def up(self, conn: sqlite3.Connection) -> None:
        for table in ("sessions", "turns", "messages", "events", "agent_messages"):
            self._add_team_id(conn, table)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plugin_kv (
                team_id   TEXT NOT NULL,
                plugin_id TEXT NOT NULL,
                key       TEXT NOT NULL,
                value     BLOB,
                PRIMARY KEY (team_id, plugin_id, key)
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_kv_team_plugin
              ON plugin_kv(team_id, plugin_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_team_id ON sessions(team_id);
            CREATE INDEX IF NOT EXISTS idx_turns_team_id    ON turns(team_id);
            CREATE INDEX IF NOT EXISTS idx_messages_team_id ON messages(team_id);
            CREATE INDEX IF NOT EXISTS idx_events_team_id   ON events(team_id);
            CREATE INDEX IF NOT EXISTS idx_agent_messages_team_id ON agent_messages(team_id);
            """
        )

    @staticmethod
    def _add_team_id(conn: sqlite3.Connection, table: str) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "team_id" in cols:
            return
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN team_id TEXT NOT NULL DEFAULT 'local-team'"
        )


migration = _Migration001()
```

- [ ] **Step 4: Run integration test to verify it passes**

```bash
python3 -m pytest tests/integration/storage/test_migration_001.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/adapters/storage/migrations/m001_team_id.py tests/integration/storage/test_migration_001.py tests/integration/storage/__init__.py
git commit -m "feat(storage): 001 迁移加 team_id 列与 plugin_kv 表"
```

---

## Task 11: migrate up CLI 入口

**Files:**
- Create: `sensenova_claw/adapters/storage/migrate.py`
- Test: `tests/integration/storage/test_migrate_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/storage/test_migrate_cli.py
import sqlite3
import subprocess
import sys


def test_migrate_up_creates_team_id_columns(tmp_path):
    db_path = tmp_path / "x.db"
    # 先建一个空的旧 schema：sessions 老结构
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, created_at REAL, last_active REAL, meta TEXT, status TEXT);"
        "CREATE TABLE turns (turn_id TEXT PRIMARY KEY, session_id TEXT, status TEXT, started_at REAL);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, turn_id TEXT, role TEXT, created_at REAL);"
        "CREATE TABLE events (event_id TEXT PRIMARY KEY, session_id TEXT, event_type TEXT, timestamp REAL, source TEXT, payload_json TEXT);"
        "CREATE TABLE agent_messages (id TEXT PRIMARY KEY, parent_session_id TEXT, child_session_id TEXT, target_id TEXT, status TEXT, mode TEXT, message TEXT, created_at REAL);"
    )
    conn.commit()
    conn.close()

    result = subprocess.run(
        [sys.executable, "-m", "sensenova_claw.adapters.storage.migrate", "up", "--db", str(db_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "team_id" in cols
    pk_cols = {row[1] for row in conn.execute("PRAGMA table_info(plugin_kv)").fetchall()}
    assert pk_cols == {"team_id", "plugin_id", "key", "value"}
    conn.close()


def test_migrate_up_idempotent(tmp_path):
    db_path = tmp_path / "y.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, created_at REAL, last_active REAL, meta TEXT);"
        "CREATE TABLE turns (turn_id TEXT PRIMARY KEY, session_id TEXT, status TEXT, started_at REAL);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, turn_id TEXT, role TEXT, created_at REAL);"
        "CREATE TABLE events (event_id TEXT PRIMARY KEY, session_id TEXT, event_type TEXT, timestamp REAL, source TEXT, payload_json TEXT);"
        "CREATE TABLE agent_messages (id TEXT PRIMARY KEY, parent_session_id TEXT, child_session_id TEXT, target_id TEXT, status TEXT, mode TEXT, message TEXT, created_at REAL);"
    )
    conn.commit()
    conn.close()

    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "sensenova_claw.adapters.storage.migrate", "up", "--db", str(db_path)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/integration/storage/test_migrate_cli.py -v
```

Expected: subprocess 退出码非 0（模块不存在）。

- [ ] **Step 3: Write CLI entry**

```python
# sensenova_claw/adapters/storage/migrate.py
"""命令行迁移入口：python3 -m sensenova_claw.adapters.storage.migrate up [--db PATH]

幂等：重复运行不重复执行已 applied 的 migration。
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001
from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner

logger = logging.getLogger("sensenova_claw.migrate")

ALL_MIGRATIONS = [m001]


def _resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    # 复用 Repository 的默认逻辑
    from sensenova_claw.platform.config.config import config
    from sensenova_claw.platform.config.workspace import resolve_sensenova_claw_home

    db_path = config.get("system.database_path", "")
    if db_path:
        return Path(db_path).expanduser()
    return resolve_sensenova_claw_home(config) / "data" / "sensenova-claw.db"


def cmd_up(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("migrating database at %s", db_path)
    conn = sqlite3.connect(db_path)
    try:
        runner = MigrationRunner(migrations=ALL_MIGRATIONS)
        applied = runner.run(conn)
        if applied:
            print(f"applied migrations: {applied}")
        else:
            print("no migrations to apply (database already up-to-date)")
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    parser = argparse.ArgumentParser(prog="sensenova_claw.adapters.storage.migrate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up", help="apply pending migrations")
    p_up.add_argument("--db", default=None, help="path to sqlite db (default: config/system.database_path)")
    args = parser.parse_args(argv)
    if args.cmd == "up":
        return cmd_up(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/integration/storage/test_migrate_cli.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/adapters/storage/migrate.py tests/integration/storage/test_migrate_cli.py
git commit -m "feat(storage): 新增 python3 -m ... migrate up 命令行入口"
```

---

## Task 12: Repository 写路径加 team_id

**Files:**
- Modify: `sensenova_claw/adapters/storage/repository.py`
- Test: `tests/unit/adapters/storage/test_repository_team_id.py`
- Test: `tests/unit/adapters/storage/__init__.py`（如不存在）

- [ ] **Step 1: Write failing test**

```python
# tests/unit/adapters/storage/test_repository_team_id.py
import asyncio
import sqlite3

import pytest

from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001
from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
from sensenova_claw.adapters.storage.repository import Repository


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "r.db"
    repo = Repository(db_path=str(db))
    asyncio.run(repo.init())
    # 确保 migration 也跑过（init 内部应该已经调）
    return repo


def test_create_session_writes_team_id(repo):
    asyncio.run(repo.create_session("s-1", meta={}, team_id="team-a"))
    conn = sqlite3.connect(repo.db_path)
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", ("s-1",)
    ).fetchone()
    conn.close()
    assert row[0] == "team-a"


def test_create_session_default_team_id(repo):
    asyncio.run(repo.create_session("s-2", meta={}))
    conn = sqlite3.connect(repo.db_path)
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", ("s-2",)
    ).fetchone()
    conn.close()
    assert row[0] == "local-team"


def test_create_turn_inherits_session_team_id(repo):
    asyncio.run(repo.create_session("s-3", meta={}, team_id="team-b"))
    asyncio.run(repo.create_turn("t-1", "s-3", "hi"))
    conn = sqlite3.connect(repo.db_path)
    row = conn.execute("SELECT team_id FROM turns WHERE turn_id = ?", ("t-1",)).fetchone()
    conn.close()
    assert row[0] == "team-b"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/adapters/storage/test_repository_team_id.py -v
```

Expected: `create_session` 不接受 `team_id` 参数 / `turns.team_id` 为默认值而非继承。

- [ ] **Step 3: Modify Repository write path**

```python
# sensenova_claw/adapters/storage/repository.py（关键差异）

# 1) 在 _sync_init 末尾加 migration runner 调用
def _sync_init(self) -> None:
    conn = self._conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    self._migrate_sessions_table(conn)
    self._migrate_agent_messages_table(conn)
    self._migrate_cron_runs_table(conn)
    # 新增：跑 P5 引入的 migration（含 team_id + plugin_kv）
    from sensenova_claw.adapters.storage.migrations.m001_team_id import migration as m001
    from sensenova_claw.adapters.storage.migrations.runner import MigrationRunner
    MigrationRunner(migrations=[m001]).run(conn)


# 2) create_session 接受 team_id（默认 'local-team'）
async def create_session(
    self,
    session_id: str,
    meta: dict[str, Any] | None = None,
    *,
    team_id: str = "local-team",
) -> None:
    await asyncio.to_thread(self._sync_create_session, session_id, meta, team_id)


def _sync_create_session(
    self, session_id: str, meta: dict[str, Any] | None, team_id: str
) -> None:
    now = time.time()
    meta = meta or {}
    agent_id = meta.get("agent_id", "default")
    conn = self._conn()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, created_at, last_active, meta, agent_id, team_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, now, now, json.dumps(meta, ensure_ascii=False), agent_id, team_id),
    )
    conn.commit()


# 3) create_turn 继承 session.team_id
def _sync_create_turn(self, turn_id: str, session_id: str, user_input: str) -> None:
    conn = self._conn()
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    team_id = row[0] if row else "local-team"
    conn.execute(
        "INSERT INTO turns (turn_id, session_id, status, started_at, user_input, team_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (turn_id, session_id, "started", time.time(), user_input, team_id),
    )
    conn.execute("UPDATE sessions SET status = ? WHERE session_id = ?", ("active", session_id))
    conn.commit()
```

类似地，`_sync_save_message` / `_sync_log_event` / `_sync_save_message_record` 在 INSERT 时增加 `team_id` 列（值从 session 继承）。本任务把这三个写路径一并改完。

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/adapters/storage/test_repository_team_id.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full repository tests to confirm no regression**

```bash
python3 -m pytest tests/unit/adapters/storage/ -v
```

Expected: 全绿；老测试不需要改（默认 team_id='local-team' 兼容）。

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/adapters/storage/repository.py tests/unit/adapters/storage/test_repository_team_id.py tests/unit/adapters/storage/__init__.py
git commit -m "feat(storage): Repository 写入路径自动写 team_id（默认 local-team）"
```

---

## Task 13: Repository 读路径加 team_id 过滤

**Files:**
- Modify: `sensenova_claw/adapters/storage/repository.py`
- Test: `tests/unit/adapters/storage/test_repository_read_filter.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/adapters/storage/test_repository_read_filter.py
import asyncio

import pytest

from sensenova_claw.adapters.storage.repository import Repository


@pytest.fixture
def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "r.db"))
    asyncio.run(r.init())
    # 准备双 team 数据
    asyncio.run(r.create_session("s-a1", meta={}, team_id="team-a"))
    asyncio.run(r.create_session("s-a2", meta={}, team_id="team-a"))
    asyncio.run(r.create_session("s-b1", meta={}, team_id="team-b"))
    return r


def test_list_sessions_filtered_by_team_a(repo):
    sessions = asyncio.run(repo.list_sessions(team_id="team-a"))
    ids = {s["session_id"] for s in sessions}
    assert ids == {"s-a1", "s-a2"}


def test_list_sessions_filtered_by_team_b(repo):
    sessions = asyncio.run(repo.list_sessions(team_id="team-b"))
    ids = {s["session_id"] for s in sessions}
    assert ids == {"s-b1"}


def test_list_sessions_no_filter_returns_all(repo):
    """team_id=None（兼容老调用）不过滤，返回全部。"""
    sessions = asyncio.run(repo.list_sessions(team_id=None))
    ids = {s["session_id"] for s in sessions}
    assert ids == {"s-a1", "s-a2", "s-b1"}


def test_get_session_events_filtered_by_team(repo):
    """跨 team 不能拿对方的 event。"""
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    asyncio.run(repo.log_event(EventEnvelope(
        type="user.input", session_id="s-a1", source="ui", payload={}, team_id="team-a",
    )))
    asyncio.run(repo.log_event(EventEnvelope(
        type="user.input", session_id="s-b1", source="ui", payload={}, team_id="team-b",
    )))
    a_events = asyncio.run(repo.get_session_events("s-a1", team_id="team-a"))
    cross = asyncio.run(repo.get_session_events("s-a1", team_id="team-b"))
    assert len(a_events) == 1
    assert len(cross) == 0  # team-b 看不到 team-a 的事件
```

注：`EventEnvelope` 是否需要 `team_id` 字段？P5 不改 EventEnvelope wire 格式（spec §9.3 承诺 100% 兼容），但 `log_event` 持久化时从 SessionContext 取 `team_id`。把上面测试改为直接传 `team_id` 参数即可——envelope 不动。修正版：

```python
def test_get_session_events_filtered_by_team(repo):
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    asyncio.run(repo.log_event(
        EventEnvelope(type="user.input", session_id="s-a1", source="ui", payload={}),
        team_id="team-a",
    ))
    asyncio.run(repo.log_event(
        EventEnvelope(type="user.input", session_id="s-b1", source="ui", payload={}),
        team_id="team-b",
    ))
    a_events = asyncio.run(repo.get_session_events("s-a1", team_id="team-a"))
    cross_view = asyncio.run(repo.get_session_events("s-a1", team_id="team-b"))
    assert len(a_events) == 1
    assert len(cross_view) == 0
```

（请用此修正版替换上一段。）

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/adapters/storage/test_repository_read_filter.py -v
```

Expected: `list_sessions` / `get_session_events` / `log_event` 不接受 `team_id` 参数。

- [ ] **Step 3: Modify Repository read path**

```python
# sensenova_claw/adapters/storage/repository.py（差异）

# log_event 接受 team_id 关键字参数
async def log_event(self, event: EventEnvelope, *, team_id: str = "local-team") -> None:
    await asyncio.to_thread(self._sync_log_event, event, team_id)


def _sync_log_event(self, event: EventEnvelope, team_id: str) -> None:
    conn = self._conn()
    conn.execute(
        """INSERT INTO events (event_id, session_id, turn_id, event_type, timestamp,
                                source, trace_id, payload_json, team_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.event_id, event.session_id, event.turn_id, event.type,
            event.ts, event.source, event.trace_id,
            json.dumps(event.payload, ensure_ascii=False),
            team_id,
        ),
    )
    conn.commit()


# get_session_events 加 team_id 过滤（None 不过滤兼容老调用）
async def get_session_events(
    self, session_id: str, *, team_id: str | None = None
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(self._sync_get_session_events, session_id, team_id)


def _sync_get_session_events(self, session_id: str, team_id: str | None) -> list[dict[str, Any]]:
    conn = self._conn()
    if team_id is None:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? AND team_id = ? ORDER BY timestamp",
            (session_id, team_id),
        ).fetchall()
    return [dict(row) for row in rows]


# list_sessions 加 team_id 过滤
async def list_sessions(
    self,
    limit: int = 50,
    *,
    include_hidden: bool = False,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        self._sync_list_sessions, limit, include_hidden, team_id
    )


def _sync_list_sessions(
    self, limit: int, include_hidden: bool, team_id: str | None
) -> list[dict[str, Any]]:
    sessions = self._sync_get_visible_sessions(include_hidden)
    if team_id is not None:
        sessions = [s for s in sessions if s.get("team_id") == team_id]
    return self._include_visible_ancestors_within_limit(sessions, limit)
```

类似地，`get_session_messages` / `get_session_turns` / `get_session_meta` 都加 `team_id` 关键字参数。本任务一并改完。

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/adapters/storage/test_repository_read_filter.py -v
```

Expected: 4 passed。

- [ ] **Step 5: Run full storage tests**

```bash
python3 -m pytest tests/unit/adapters/storage/ tests/integration/storage/ -v
```

Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/adapters/storage/repository.py tests/unit/adapters/storage/test_repository_read_filter.py
git commit -m "feat(storage): Repository 读路径按 team_id 过滤（None 时兼容老调用）"
```

---

## Task 14: plugin_kv Repository CRUD

**Files:**
- Modify: `sensenova_claw/adapters/storage/repository.py`
- Test: `tests/unit/adapters/storage/test_plugin_kv.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/adapters/storage/test_plugin_kv.py
import asyncio

import pytest

from sensenova_claw.adapters.storage.repository import Repository


@pytest.fixture
def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "k.db"))
    asyncio.run(r.init())
    return r


def test_plugin_kv_set_and_get(repo):
    asyncio.run(repo.plugin_kv_set("team-a", "team-a/crm", "k1", b"value-1"))
    val = asyncio.run(repo.plugin_kv_get("team-a", "team-a/crm", "k1"))
    assert val == b"value-1"


def test_plugin_kv_isolated_by_team(repo):
    asyncio.run(repo.plugin_kv_set("team-a", "shared/plugin", "k", b"a"))
    asyncio.run(repo.plugin_kv_set("team-b", "shared/plugin", "k", b"b"))
    assert asyncio.run(repo.plugin_kv_get("team-a", "shared/plugin", "k")) == b"a"
    assert asyncio.run(repo.plugin_kv_get("team-b", "shared/plugin", "k")) == b"b"


def test_plugin_kv_isolated_by_plugin(repo):
    asyncio.run(repo.plugin_kv_set("team-a", "plugin-x", "k", b"x"))
    asyncio.run(repo.plugin_kv_set("team-a", "plugin-y", "k", b"y"))
    assert asyncio.run(repo.plugin_kv_get("team-a", "plugin-x", "k")) == b"x"
    assert asyncio.run(repo.plugin_kv_get("team-a", "plugin-y", "k")) == b"y"


def test_plugin_kv_get_missing_returns_none(repo):
    assert asyncio.run(repo.plugin_kv_get("team-a", "p", "missing")) is None


def test_plugin_kv_set_overwrites(repo):
    asyncio.run(repo.plugin_kv_set("team-a", "p", "k", b"v1"))
    asyncio.run(repo.plugin_kv_set("team-a", "p", "k", b"v2"))
    assert asyncio.run(repo.plugin_kv_get("team-a", "p", "k")) == b"v2"


def test_plugin_kv_delete(repo):
    asyncio.run(repo.plugin_kv_set("team-a", "p", "k", b"v"))
    asyncio.run(repo.plugin_kv_delete("team-a", "p", "k"))
    assert asyncio.run(repo.plugin_kv_get("team-a", "p", "k")) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/adapters/storage/test_plugin_kv.py -v
```

Expected: `Repository` 没有 `plugin_kv_*` 方法。

- [ ] **Step 3: Add CRUD methods**

```python
# 追加到 sensenova_claw/adapters/storage/repository.py

    # ---------- plugin_kv 表操作（按 team_id + plugin_id 隔离） ----------

    async def plugin_kv_set(
        self, team_id: str, plugin_id: str, key: str, value: bytes
    ) -> None:
        await asyncio.to_thread(self._sync_plugin_kv_set, team_id, plugin_id, key, value)

    def _sync_plugin_kv_set(
        self, team_id: str, plugin_id: str, key: str, value: bytes
    ) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO plugin_kv (team_id, plugin_id, key, value) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(team_id, plugin_id, key) DO UPDATE SET value = excluded.value",
            (team_id, plugin_id, key, value),
        )
        conn.commit()

    async def plugin_kv_get(
        self, team_id: str, plugin_id: str, key: str
    ) -> bytes | None:
        return await asyncio.to_thread(self._sync_plugin_kv_get, team_id, plugin_id, key)

    def _sync_plugin_kv_get(
        self, team_id: str, plugin_id: str, key: str
    ) -> bytes | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT value FROM plugin_kv WHERE team_id = ? AND plugin_id = ? AND key = ?",
            (team_id, plugin_id, key),
        ).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    async def plugin_kv_delete(
        self, team_id: str, plugin_id: str, key: str
    ) -> None:
        await asyncio.to_thread(self._sync_plugin_kv_delete, team_id, plugin_id, key)

    def _sync_plugin_kv_delete(
        self, team_id: str, plugin_id: str, key: str
    ) -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM plugin_kv WHERE team_id = ? AND plugin_id = ? AND key = ?",
            (team_id, plugin_id, key),
        )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/adapters/storage/test_plugin_kv.py -v
```

Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/adapters/storage/repository.py tests/unit/adapters/storage/test_plugin_kv.py
git commit -m "feat(storage): plugin_kv 表 CRUD 按 (team_id, plugin_id, key) 隔离"
```

---

## Task 15: PluginStorageContext API

**Files:**
- Create: `sensenova_claw/platform/plugins/storage.py`
- Test: `tests/unit/adapters/storage/test_plugin_storage.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/adapters/storage/test_plugin_storage.py
import asyncio

import pytest

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.platform.plugins.storage import PluginStorageContext


@pytest.fixture
def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "s.db"))
    asyncio.run(r.init())
    return r


def test_storage_get_set_in_plugin_context(repo):
    """plugin 视角：ctx.storage.set/get 不需要传 team_id / plugin_id。"""
    ctx = PluginStorageContext(
        repository=repo, team_id="team-a", plugin_id="team-a/crm"
    )
    asyncio.run(ctx.set("color", b"blue"))
    assert asyncio.run(ctx.get("color")) == b"blue"


def test_storage_isolated_between_plugins(repo):
    a = PluginStorageContext(repository=repo, team_id="team-a", plugin_id="plugin-a")
    b = PluginStorageContext(repository=repo, team_id="team-a", plugin_id="plugin-b")
    asyncio.run(a.set("k", b"from-a"))
    assert asyncio.run(b.get("k")) is None  # plugin-b 拿不到 plugin-a 的数据


def test_storage_isolated_between_teams(repo):
    a = PluginStorageContext(repository=repo, team_id="team-a", plugin_id="shared")
    b = PluginStorageContext(repository=repo, team_id="team-b", plugin_id="shared")
    asyncio.run(a.set("k", b"a-data"))
    asyncio.run(b.set("k", b"b-data"))
    assert asyncio.run(a.get("k")) == b"a-data"
    assert asyncio.run(b.get("k")) == b"b-data"


def test_storage_delete(repo):
    ctx = PluginStorageContext(repository=repo, team_id="t", plugin_id="p")
    asyncio.run(ctx.set("k", b"v"))
    asyncio.run(ctx.delete("k"))
    assert asyncio.run(ctx.get("k")) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/adapters/storage/test_plugin_storage.py -v
```

Expected: `ModuleNotFoundError: ... plugins.storage`

- [ ] **Step 3: Write implementation**

```python
# sensenova_claw/platform/plugins/storage.py
"""Plugin 视角的 KV 存储 API。

设计意图：plugin 调 ctx.storage.set/get 时不需要、也无法传 team_id/plugin_id ——
两者由 core 在创建 ctx 时绑定，从根上避免 plugin 越权访问其他 team / plugin 的数据。
"""
from __future__ import annotations

from dataclasses import dataclass

from sensenova_claw.adapters.storage.repository import Repository


@dataclass(frozen=True)
class PluginStorageContext:
    """绑定到 (team_id, plugin_id) 的 KV 视图。

    plugin 在 hook / tool 实现里通过这个对象访问持久化存储；
    core 负责实例化并把 team_id 从 SessionContext 灌进来，plugin 无法篡改。
    """

    repository: Repository
    team_id: str
    plugin_id: str

    async def set(self, key: str, value: bytes) -> None:
        await self.repository.plugin_kv_set(self.team_id, self.plugin_id, key, value)

    async def get(self, key: str) -> bytes | None:
        return await self.repository.plugin_kv_get(self.team_id, self.plugin_id, key)

    async def delete(self, key: str) -> None:
        await self.repository.plugin_kv_delete(self.team_id, self.plugin_id, key)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/unit/adapters/storage/test_plugin_storage.py -v
```

Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/platform/plugins/storage.py tests/unit/adapters/storage/test_plugin_storage.py
git commit -m "feat(plugins): PluginStorageContext 把 (team_id, plugin_id) 绑死"
```

---

## Task 16: Control Protocol initialize 注入 identity + warning

**Files:**
- Modify: `sensenova_claw/interfaces/control/server.py`（P3 已创建）
- Test: `tests/integration/control/test_initialize_identity.py`
- Test: `tests/integration/control/__init__.py`（如不存在）

> 实施提示：P3 的 `initialize` 已经有占位实现，可能用 `Identity.default_local()`。本任务把"读 params.identity → 否则 default_local 并 warning"补全。

- [ ] **Step 1: Write failing test**

```python
# tests/integration/control/test_initialize_identity.py
"""验证 Control Protocol 的 initialize 方法正确解析 params.identity 并落地到 SessionContext。"""
import json
import logging

import pytest

from sensenova_claw.interfaces.control.server import ControlServer  # P3 产出


@pytest.mark.asyncio
async def test_initialize_with_explicit_identity_uses_it():
    """显式传 identity 时，server 应当用它而不是 default。"""
    server = ControlServer()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocol_version": "1",
            "client_info": {"name": "test", "version": "0"},
            "identity": {
                "user_id": "u-real",
                "team_id": "team-real",
                "org_id": "org-real",
            },
        },
    }
    response = await server.handle_request(request)
    assert "result" in response
    # 后续 session.create 应当继承这个 identity
    create_resp = await server.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "session.create",
        "params": {"agent_id": "default"},
    })
    session_id = create_resp["result"]["session_id"]
    ctx = server._registry.get_session(session_id)  # 实现细节由 P3 定，此处是断言入口
    assert ctx.identity.team_id == "team-real"
    assert ctx.identity.source == "explicit"


@pytest.mark.asyncio
async def test_initialize_without_identity_logs_warning(caplog):
    """missing identity → default_local + warning。"""
    server = ControlServer()
    with caplog.at_level(logging.WARNING):
        response = await server.handle_request({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocol_version": "1", "client_info": {"name": "t", "version": "0"}},
        })
    assert "result" in response
    # warning 消息必须明确提示这是 dev-only fallback
    assert any(
        "default identity" in rec.getMessage().lower() and "local dev" in rec.getMessage().lower()
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_initialize_partial_identity_returns_protocol_error():
    """只传 user_id 不传 team_id/org_id → 协议错误（避免静默回退）。"""
    server = ControlServer()
    response = await server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocol_version": "1",
            "client_info": {"name": "t", "version": "0"},
            "identity": {"user_id": "u"},  # 缺 team_id / org_id
        },
    })
    assert "error" in response
    # spec §5.4 中 -32004 是 config_validation_failed，本场景复用
    assert response["error"]["code"] == -32004
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/integration/control/test_initialize_identity.py -v
```

Expected: 缺 warning / 缺 partial 校验。

- [ ] **Step 3: Modify P3 server's initialize handler**

定位 `sensenova_claw/interfaces/control/server.py` 中处理 `initialize` 的方法，改为：

```python
# sensenova_claw/interfaces/control/server.py（关键差异）
import logging

from sensenova_claw.platform.identity import Identity, IdentityError

logger = logging.getLogger(__name__)


def _parse_identity_param(param: dict | None) -> Identity:
    """从 initialize.params.identity 解析 Identity，缺失时 default + warning。

    部分填写视为 protocol error（caller 责任）。
    """
    if not param:
        logger.warning(
            "initialize 未提供 identity，使用 Identity.default_local()。"
            " 注意：default identity is for local dev only —— "
            "云端 / CI / 多租户环境必须显式传 identity，否则可能跨 team 访问数据。"
        )
        return Identity.default_local()
    user_id = str(param.get("user_id") or "").strip()
    team_id = str(param.get("team_id") or "").strip()
    org_id = str(param.get("org_id") or "").strip()
    if not (user_id and team_id and org_id):
        raise IdentityError(
            f"identity 必须同时包含 user_id/team_id/org_id；收到 {sorted(param.keys())}"
        )
    return Identity(user_id=user_id, team_id=team_id, org_id=org_id, source="explicit")


# 在 handle_initialize 内：
async def handle_initialize(self, params: dict) -> dict:
    try:
        identity = _parse_identity_param(params.get("identity"))
    except IdentityError as exc:
        return self._protocol_error(code=-32004, message=str(exc))
    self._client_identity = identity
    # ... P3 已有的握手逻辑（plugin loader 传 identity 等）
    plugins = self._loader.load_all(identity=identity)
    self._loader.install_into_registries(manifests=plugins, ...)
    return self._build_initialize_result()


# session.create 时把 self._client_identity 注入 SessionContext
async def handle_session_create(self, params: dict) -> dict:
    ctx = SessionContext(
        session_id=new_session_id(),
        identity=self._client_identity,
    )
    self._registry.add_session(ctx)
    # 写库时也把 team_id 传给 Repository
    await self._repository.create_session(
        ctx.session_id, meta=params.get("meta", {}), team_id=ctx.team_id
    )
    return {"session_id": ctx.session_id}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/integration/control/test_initialize_identity.py -v
```

Expected: 3 passed。

- [ ] **Step 5: Confirm P3 existing tests still green**

```bash
python3 -m pytest tests/integration/control/ -v
```

Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/interfaces/control/server.py tests/integration/control/test_initialize_identity.py tests/integration/control/__init__.py
git commit -m "feat(control): initialize 解析 params.identity 并把 default 路径标 warning"
```

---

## Task 17: 集成测试——双 team 加载隔离

**Files:**
- Create: `tests/integration/plugins/test_loader_visibility_e2e.py`
- Test: `tests/integration/plugins/__init__.py`（如不存在）

- [ ] **Step 1: Write integration test**

```python
# tests/integration/plugins/test_loader_visibility_e2e.py
"""模拟两个真实 identity 加载同一份 manifest 集合，验证可见性差异。"""
from pathlib import Path

import pytest
import yaml

from sensenova_claw.platform.identity import Identity
from sensenova_claw.platform.plugins.loader import PluginLoader
from sensenova_claw.platform.plugins.sources import LocalDirectorySource  # P1 产出


@pytest.fixture
def plugin_dir(tmp_path):
    """构造目录布局：
       plugins/
         core-pub/plugin.yaml   (public)
         a-priv/plugin.yaml     (private, owner=team-a)
         b-priv/plugin.yaml     (private, owner=team-b)
         a-shared/plugin.yaml   (internal, owner=team-a, allowed=[team-b])
    """
    root = tmp_path / "plugins"
    cases = [
        ("core-pub", {"id": "core/pub", "owner": "core", "visibility": "public"}),
        ("a-priv",   {"id": "team-a/secret", "owner": "team-a", "visibility": "private"}),
        ("b-priv",   {"id": "team-b/secret", "owner": "team-b", "visibility": "private"}),
        ("a-shared", {
            "id": "team-a/shared", "owner": "team-a",
            "visibility": "internal", "allowed_teams": ["team-b"],
        }),
    ]
    for sub, override in cases:
        d = root / sub
        d.mkdir(parents=True)
        manifest = {
            "schema_version": "1",
            "version": "1.0.0",
            "name": override["id"],
            "description": "",
            "contributes": {},
        }
        manifest.update(override)
        (d / "plugin.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
        )
    return root


def test_team_a_sees_own_private_and_internal_and_public(plugin_dir):
    loader = PluginLoader(sources=[LocalDirectorySource(root=plugin_dir)])
    ident = Identity(user_id="u", team_id="team-a", org_id="org", source="explicit")
    visible = {m.id for m in loader.load_all(identity=ident)}
    assert visible == {"core/pub", "team-a/secret", "team-a/shared"}


def test_team_b_sees_public_own_private_and_team_a_internal(plugin_dir):
    loader = PluginLoader(sources=[LocalDirectorySource(root=plugin_dir)])
    ident = Identity(user_id="u", team_id="team-b", org_id="org", source="explicit")
    visible = {m.id for m in loader.load_all(identity=ident)}
    # team-b 看不到 team-a/secret，但能看 team-a/shared（在 allowed_teams 里）
    assert visible == {"core/pub", "team-b/secret", "team-a/shared"}


def test_team_b_cannot_see_team_a_private_in_registry(plugin_dir):
    """关键不变量：被过滤的 plugin 完全不在内存中——registry 也看不到。"""
    from unittest.mock import MagicMock

    loader = PluginLoader(sources=[LocalDirectorySource(root=plugin_dir)])
    ident_b = Identity(user_id="u", team_id="team-b", org_id="org", source="explicit")
    manifests = loader.load_all(identity=ident_b)

    tool_registry = MagicMock()
    skill_registry = MagicMock()
    llm_registry = MagicMock()
    channel_registry = MagicMock()
    agent_registry = MagicMock()
    hook_registry = MagicMock()
    command_registry = MagicMock()

    loader.install_into_registries(
        manifests=manifests,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        llm_registry=llm_registry,
        channel_registry=channel_registry,
        agent_registry=agent_registry,
        hook_registry=hook_registry,
        command_registry=command_registry,
    )

    # team-a/secret 的任何 contribution 都不应出现在 registry 调用里
    for call in tool_registry.register_from_plugin.call_args_list:
        entry = call.args[0]
        assert "team-a/secret" not in entry.id
```

- [ ] **Step 2: Run test**

```bash
python3 -m pytest tests/integration/plugins/test_loader_visibility_e2e.py -v
```

Expected: 3 passed（依赖 Task 6/7 已落地）。

- [ ] **Step 3: Commit**

```bash
git add tests/integration/plugins/test_loader_visibility_e2e.py tests/integration/plugins/__init__.py
git commit -m "test(plugins): 双 team 端到端验证 visibility 过滤与 registry 注入"
```

---

## Task 18: 集成测试——v0 DB 迁移完整回归

**Files:**
- Create: `tests/integration/storage/test_v0_to_v1_full.py`

> Task 10 的 `test_migration_001.py` 用了简化 schema；本 task 用真实 `SCHEMA_SQL`（来自 `repository.py`）建库并填多张表数据，再升级，验证现有读路径在升级后照常工作。

- [ ] **Step 1: Write integration test**

```python
# tests/integration/storage/test_v0_to_v1_full.py
"""真实 schema 上跑完整迁移，验证现有 Repository 读路径无回归。"""
import asyncio
import sqlite3
import time

import pytest

from sensenova_claw.adapters.storage.repository import Repository, SCHEMA_SQL


@pytest.fixture
def populated_v0_db(tmp_path):
    """先用 SCHEMA_SQL 建库（这是 P5 之前的版本），手工插入数据，然后让
    Repository.init() 跑 migration（其内部已经调 MigrationRunner）。"""
    db_path = tmp_path / "v0.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    # 模拟 P5 之前的迁移——给 sessions 加 agent_id 等列（手动复刻 _migrate_sessions_table）
    conn.execute("ALTER TABLE sessions ADD COLUMN channel TEXT")
    conn.execute("ALTER TABLE sessions ADD COLUMN model TEXT")
    conn.execute("ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE sessions ADD COLUMN agent_id TEXT DEFAULT 'default'")
    conn.commit()

    now = time.time()
    conn.execute(
        "INSERT INTO sessions (session_id, created_at, last_active, meta, status, agent_id) VALUES (?, ?, ?, ?, ?, ?)",
        ("s-legacy", now, now, "{}", "active", "agent-x"),
    )
    conn.execute(
        "INSERT INTO turns (turn_id, session_id, status, started_at, user_input) VALUES (?, ?, ?, ?, ?)",
        ("t-legacy", "s-legacy", "completed", now, "hello"),
    )
    conn.execute(
        "INSERT INTO messages (session_id, turn_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("s-legacy", "t-legacy", "user", "hi", now),
    )
    conn.commit()
    conn.close()
    return db_path


def test_repository_init_runs_migration_and_old_data_keeps_working(populated_v0_db):
    repo = Repository(db_path=str(populated_v0_db))
    asyncio.run(repo.init())

    # 1. 老数据 team_id 已经填 local-team
    conn = sqlite3.connect(populated_v0_db)
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", ("s-legacy",)
    ).fetchone()
    assert row[0] == "local-team"
    conn.close()

    # 2. 新方法用 team_id="local-team" 能查到老 session
    sessions = asyncio.run(repo.list_sessions(team_id="local-team"))
    ids = {s["session_id"] for s in sessions}
    assert "s-legacy" in ids

    # 3. 老消息也能拉出来
    messages = asyncio.run(repo.get_session_messages("s-legacy"))
    assert any(m["role"] == "user" for m in messages)


def test_double_init_is_idempotent(populated_v0_db):
    """二次 init 不重复加列（PRAGMA 检查），不破数据。"""
    repo = Repository(db_path=str(populated_v0_db))
    asyncio.run(repo.init())
    asyncio.run(repo.init())  # 第二次不能爆
    sessions = asyncio.run(repo.list_sessions(team_id="local-team"))
    assert any(s["session_id"] == "s-legacy" for s in sessions)
```

- [ ] **Step 2: Run test**

```bash
python3 -m pytest tests/integration/storage/test_v0_to_v1_full.py -v
```

Expected: 2 passed。

- [ ] **Step 3: Commit**

```bash
git add tests/integration/storage/test_v0_to_v1_full.py
git commit -m "test(storage): 真实 schema 上 v0→v1 迁移端到端回归 + 幂等性"
```

---

## Task 19: 集成测试——plugin storage 隔离

**Files:**
- Create: `tests/integration/plugins/test_storage_isolation.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/plugins/test_storage_isolation.py
"""端到端验证：plugin A 通过 ctx.storage.set 写入，plugin B 通过 ctx.storage.get 读取
返回 None（即使在同一 team 也互不可见）；不同 team 之间也互不可见。"""
import asyncio

import pytest

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.platform.plugins.storage import PluginStorageContext


@pytest.fixture
def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "iso.db"))
    asyncio.run(r.init())
    return r


def test_same_team_different_plugins_cannot_see_each_other(repo):
    """plugin A set('shared_key') → plugin B get('shared_key') 返回 None。"""
    plugin_a = PluginStorageContext(
        repository=repo, team_id="team-a", plugin_id="team-a/plugin-a"
    )
    plugin_b = PluginStorageContext(
        repository=repo, team_id="team-a", plugin_id="team-a/plugin-b"
    )
    asyncio.run(plugin_a.set("shared_key", b"a-data"))
    assert asyncio.run(plugin_b.get("shared_key")) is None


def test_different_teams_same_plugin_id_isolated(repo):
    """两个 team 装了同名 plugin，互不可见——核心多租户保证。"""
    a_view = PluginStorageContext(
        repository=repo, team_id="team-a", plugin_id="shared/plugin"
    )
    b_view = PluginStorageContext(
        repository=repo, team_id="team-b", plugin_id="shared/plugin"
    )
    asyncio.run(a_view.set("k", b"a"))
    asyncio.run(b_view.set("k", b"b"))
    assert asyncio.run(a_view.get("k")) == b"a"
    assert asyncio.run(b_view.get("k")) == b"b"


def test_storage_survives_repository_recreate(tmp_path):
    """重启 Repository 后存的值还在。"""
    db = tmp_path / "p.db"
    r1 = Repository(db_path=str(db))
    asyncio.run(r1.init())
    ctx1 = PluginStorageContext(repository=r1, team_id="t", plugin_id="p")
    asyncio.run(ctx1.set("k", b"persisted"))

    r2 = Repository(db_path=str(db))
    asyncio.run(r2.init())  # 重新 init，不破数据
    ctx2 = PluginStorageContext(repository=r2, team_id="t", plugin_id="p")
    assert asyncio.run(ctx2.get("k")) == b"persisted"
```

- [ ] **Step 2: Run test**

```bash
python3 -m pytest tests/integration/plugins/test_storage_isolation.py -v
```

Expected: 3 passed。

- [ ] **Step 3: Commit**

```bash
git add tests/integration/plugins/test_storage_isolation.py
git commit -m "test(plugins): plugin 间 + team 间 storage 双重隔离回归"
```

---

## Task 20: 集成测试——initialize identity 端到端

**Files:**
- Create: `tests/integration/control/test_initialize_e2e.py`

> 比 Task 16 的单测更端到端：起一个真实 ControlServer，喂 JSON-RPC 行，断言事件链上 `team_id` 正确传播到了 DB。

- [ ] **Step 1: Write integration test**

```python
# tests/integration/control/test_initialize_e2e.py
"""端到端：通过 Control Protocol 走完 initialize → session.create → turn.send_input，
验证 sessions / events 表里 team_id 是 initialize 提供的值。"""
import asyncio
import sqlite3

import pytest

from sensenova_claw.interfaces.control.server import ControlServer  # P3 产出


@pytest.mark.asyncio
async def test_full_handshake_persists_team_id(tmp_path):
    db_path = tmp_path / "e.db"
    server = ControlServer(db_path=str(db_path))  # P3 已支持注入

    # 1) initialize 显式带 identity
    init_resp = await server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocol_version": "1",
            "client_info": {"name": "t", "version": "0"},
            "identity": {
                "user_id": "u-x",
                "team_id": "team-x",
                "org_id": "org-x",
            },
        },
    })
    assert "result" in init_resp

    # 2) session.create
    create_resp = await server.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "session.create",
        "params": {"agent_id": "default"},
    })
    session_id = create_resp["result"]["session_id"]

    # 3) 验证 DB
    await asyncio.sleep(0.05)  # 让 to_thread 落盘
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "team-x"


@pytest.mark.asyncio
async def test_default_identity_persists_local_team(tmp_path):
    """没传 identity → fallback default → DB 里写 'local-team'。"""
    server = ControlServer(db_path=str(tmp_path / "f.db"))
    await server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocol_version": "1", "client_info": {"name": "t", "version": "0"}},
    })
    create_resp = await server.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "session.create",
        "params": {"agent_id": "default"},
    })
    session_id = create_resp["result"]["session_id"]
    await asyncio.sleep(0.05)
    conn = sqlite3.connect(tmp_path / "f.db")
    row = conn.execute(
        "SELECT team_id FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "local-team"
```

- [ ] **Step 2: Run test**

```bash
python3 -m pytest tests/integration/control/test_initialize_e2e.py -v
```

Expected: 2 passed。

- [ ] **Step 3: Run all P5 tests together to check for regressions**

```bash
python3 -m pytest \
  tests/unit/platform/identity/ \
  tests/unit/platform/plugins/ \
  tests/unit/kernel/runtime/test_session_context.py \
  tests/unit/adapters/storage/ \
  tests/integration/storage/ \
  tests/integration/plugins/ \
  tests/integration/control/ \
  -v
```

Expected: 全绿；失败的非 P5 测试视为 P3/P4 集成边界问题，记录在 PR 描述中。

- [ ] **Step 4: Final commit**

```bash
git add tests/integration/control/test_initialize_e2e.py
git commit -m "test(control): initialize identity 端到端落盘验证"
```

---

## 完工 checklist（提交 PR 前）

- [ ] 所有 20 个 task 的提交都已推到 `spec/plan-p5-identity-db` 分支
- [ ] `python3 -m pytest tests/unit tests/integration -q` 全绿
- [ ] `python3 -m sensenova_claw.adapters.storage.migrate up --db /tmp/empty.db` 在空库上能跑通且幂等
- [ ] 全 P2 内置 plugin 的 `plugin.yaml` 都声明 `visibility: public`（否则 default 路径下会过滤掉，行为不兼容）
- [ ] 现有 `tests/e2e/` 不需要任何改动就能通过——这是 spec §9 兼容承诺的最直接验证
- [ ] PR 描述包含：
  - 加了 `team_id` 列的 5 张表清单 + 新增 `plugin_kv` 表
  - `Identity` 来源链优先级简表
  - 风险点：default identity warning 在生产/CI 必须由调用方覆盖

---

## Self-Review

**1. 规范覆盖**

| Spec / Decomposition 要求 | 对应 Task |
|---|---|
| §3.4 `Identity` dataclass + `default_local()` | T1 |
| §7.1 来源链：explicit > env > file > default | T1-4 |
| §7.2 `is_visible()` 算法（public/internal/private） | T5 |
| §7.2 PluginLoader 按 visibility 过滤 | T6 |
| §7.3 RegistryEntry namespace 前缀 `f"{plugin.id}::{contribution.id}"` | T7 |
| §7.4 `team_id` 列 + `plugin_kv` 表 | T9-10 |
| §7.4 plugin storage 透明加 `(team_id, plugin_id)` 过滤 | T14-15 |
| §9.4 数据库迁移向后兼容（加列不破数据） | T10, T18 |
| §9.6 步骤 7 默认 `local-team` 不影响现有用户 | T10（DEFAULT 'local-team'）+ T18 |
| §9.6 步骤 8 迁移脚本 idempotent | T9, T11 |
| §11 default identity 安全风险 → warning | T16 |
| Decomposition §3.4 `Identity` 接口签名 | T1（注：本 plan 在 spec 三字段基础上补了 `source` 诊断字段——纯增量，不破契约） |
| Decomposition §3.3 `PluginLoader.load_all(identity)` 签名 | T6 |
| Decomposition §3.3 `install_into_registries` 签名 | T7 |
| 测试覆盖：来源链优先级 | T4 测试 |
| 测试覆盖：`is_visible` 真值表 3×匹配/非匹配 | T5 测试 |
| 测试覆盖：namespace 格式 | T7 测试 |
| 测试覆盖：v0 → v1 迁移 + 老查询 | T10, T18 测试 |
| 测试覆盖：双 identity 同 manifest 集 | T17 测试 |
| 测试覆盖：plugin A set / plugin B get → None | T15, T19 测试 |

**契约扩展声明（不破坏）**：本 plan 在 `Identity` 上加了 `source: IdentitySource` 字段（值之一 `"default"`/`"env"`/`"file"`/`"explicit"`），仅用于诊断和日志，wire 不出现。decomposition §3.4 对应字段以 `default_local()` 返回 `cls(user_id=..., team_id=..., org_id=...)` 的形式定义，本 plan 通过 `dataclass(frozen=True)` 加默认值兼容旧调用。后续如果 P3/P4 的占位代码需要不带 source 的构造，`Identity(user_id=..., team_id=..., org_id=...)` 仍合法（source 默认 `"explicit"`）。

**2. 占位扫描**

- 未发现 "TBD" / "implement later"
- 每个 step 都给出了完整代码与命令
- T6 / T7 / T8 / T16 修改 P1/P3 已有文件时给出了"diff 提示"，标注修改位置而非整文件覆写——避免覆盖 P1/P3 的其他逻辑

**3. 类型一致性**

- `Identity(user_id, team_id, org_id, source)` 在所有 Task 中签名一致
- `is_visible(manifest, identity)` 签名 (`manifest: PluginManifest`, `identity: Identity | None`) 在 T5/T6 一致
- `RegistryEntry.id` 在 T7 / T17 都是 `f"{plugin.id}::{contribution.id}"`
- `Repository.create_session(session_id, meta=None, *, team_id="local-team")` 在 T12/T13/T16/T18 引用一致
- `PluginStorageContext(repository, team_id, plugin_id)` 在 T15/T19 引用一致
- `MigrationRunner(migrations=[...])` + `migration` 模块单例 (`m001_team_id.migration`) 在 T9/T10/T11/T18 引用一致
