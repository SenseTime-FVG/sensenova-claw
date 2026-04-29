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
