from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from sensenova_claw.platform.security.deny_list import is_system_path

logger = logging.getLogger(__name__)


class PathZone(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class PathVerdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEED_GRANT = "need_grant"


class PathPolicy:
    """无状态路径策略判定器。相对路径一律基于 workspace 解析。"""

    def __init__(self, workspace: Path, granted_paths: list[str] | None = None):
        self.workspace = workspace.expanduser().resolve()
        self._granted: list[Path] = []
        for p in granted_paths or []:
            try:
                resolved = Path(p).expanduser().resolve()
                if resolved.is_dir():
                    self._granted.append(resolved)
            except (OSError, ValueError):
                logger.warning("Invalid granted path, skipping: %s", p)

    def grant(self, dir_path: str) -> Path:
        resolved = Path(dir_path).expanduser().resolve()
        if is_system_path(resolved):
            raise ValueError(f"系统目录不允许授权: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"目录不存在: {resolved}")
        if resolved not in self._granted:
            self._granted.append(resolved)
            logger.info("Path granted: %s", resolved)
        return resolved

    def revoke(self, dir_path: str) -> None:
        resolved = Path(dir_path).expanduser().resolve()
        self._granted = [p for p in self._granted if p != resolved]

    @property
    def granted_paths(self) -> list[str]:
        return [str(p) for p in self._granted]

    def classify(self, target: Path) -> PathZone:
        resolved = target.expanduser().resolve()
        if _is_within(resolved, self.workspace):
            return PathZone.GREEN
        for granted in self._granted:
            if _is_within(resolved, granted):
                return PathZone.YELLOW
        return PathZone.RED

    def check_read(self, file_path: str) -> PathVerdict:
        return self._check(self._resolve(file_path))

    def check_write(self, file_path: str) -> PathVerdict:
        return self._check(self._resolve(file_path))

    def check_cwd(self, dir_path: str) -> PathVerdict:
        return self._check(self._resolve(dir_path))

    def safe_resolve(self, file_path: str) -> Path:
        return self._resolve(file_path)

    def _resolve(self, user_path: str) -> Path:
        p = Path(user_path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace / p).resolve()

    def _check(self, resolved: Path) -> PathVerdict:
        zone = self.classify(resolved)
        if zone in (PathZone.GREEN, PathZone.YELLOW):
            return PathVerdict.ALLOW
        if is_system_path(resolved):
            return PathVerdict.DENY
        return PathVerdict.NEED_GRANT


def _is_within(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False
