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
