"""通用文件列表 API - 浏览服务端文件系统目录"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])


def _resolve_workspace_dir(request: Request) -> Path:
    """获取 workspace 根目录"""
    home = getattr(request.app.state, "agentos_home", "") or str(Path.home() / ".agentos")
    return Path(home)


def _is_path_allowed(target: Path, workspace: Path) -> bool:
    """检查路径是否在允许的范围内"""
    try:
        resolved = target.resolve()
        ws_resolved = workspace.resolve()
        try:
            resolved.relative_to(ws_resolved)
            return True
        except ValueError:
            pass
        # 不允许访问系统关键目录
        deny_prefixes = ["/etc", "/root", "/var/run", "/proc", "/sys"]
        str_path = str(resolved)
        for prefix in deny_prefixes:
            if str_path.startswith(prefix):
                return False
        return True
    except (OSError, ValueError):
        return False


@router.get("/files")
async def list_files(
    request: Request,
    path: str = Query(..., description="要列出的目录路径"),
):
    """列出指定目录下的文件和文件夹（单层）"""
    target = Path(path)

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {path}")

    workspace = _resolve_workspace_dir(request)

    if not _is_path_allowed(resolved, workspace):
        raise HTTPException(403, f"无权访问: {path}")

    if not resolved.exists():
        raise HTTPException(404, f"路径不存在: {path}")

    if not resolved.is_dir():
        raise HTTPException(400, f"不是目录: {path}")

    items = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith('.'):
                continue
            item = {
                "name": entry.name,
                "type": "folder" if entry.is_dir() else "file",
                "path": str(entry),
            }
            if entry.is_file():
                try:
                    item["size"] = entry.stat().st_size
                except OSError:
                    item["size"] = 0
            items.append(item)
    except PermissionError:
        raise HTTPException(403, f"无权读取目录: {path}")

    return {"path": str(resolved), "items": items}
