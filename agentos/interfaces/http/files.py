"""通用文件列表 API - 浏览服务端文件系统目录 & 文件上传"""
from __future__ import annotations

import logging
import os
import platform
import string
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File as FastAPIFile

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


@router.get("/files/roots")
async def list_roots(request: Request):
    """返回可用的文件系统根路径（Windows 返回盘符，Unix 返回 / 和用户目录）"""
    roots: list[dict] = []

    if platform.system() == "Windows":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                roots.append({"name": f"{letter}:", "path": drive, "type": "folder"})
    else:
        roots.append({"name": "/", "path": "/", "type": "folder"})

    home = str(Path.home())
    if os.path.isdir(home) and not any(r["path"] == home for r in roots):
        roots.append({"name": f"Home ({Path.home().name})", "path": home, "type": "folder"})

    workspace = _resolve_workspace_dir(request)
    workdir = str(workspace / "workdir")
    if os.path.isdir(workdir):
        roots.append({"name": "Agent 工作区", "path": workdir, "type": "folder"})

    return {"roots": roots}


@router.get("/files")
async def list_files(
    request: Request,
    path: str = Query(..., description="要列出的目录路径"),
):
    """列出指定目录下的文件和文件夹（单层）

    path="workspace" 映射到 ${AGENTOS_HOME}/workdir
    """
    workspace = _resolve_workspace_dir(request)

    if path == "workspace":
        target = workspace / "workdir"
        target.mkdir(parents=True, exist_ok=True)
    else:
        target = Path(path)

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {path}")

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


def _uploads_dir(request: Request) -> Path:
    """用户上传文件存储目录"""
    workspace = _resolve_workspace_dir(request)
    uploads = workspace / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


@router.post("/files/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = FastAPIFile(...),
):
    """接收文件上传，支持单文件、多文件和文件夹（webkitdirectory）。

    文件夹上传时 filename 包含相对路径（如 ``mydir/sub/file.txt``），
    服务端会在 uploads 目录下保留对应的目录结构。
    """
    logger.info("收到上传请求: %d 个文件", len(files))
    uploads = _uploads_dir(request)
    results = []

    for file in files:
        if not file.filename:
            logger.warning("跳过: 空文件名")
            continue

        # 规范化路径分隔符，去掉前导 / 或 \
        rel_path = file.filename.replace("\\", "/").lstrip("/")
        parts = [p for p in rel_path.split("/") if p and p != ".." and not p.startswith(".")]
        if not parts:
            logger.warning("跳过: 非法文件名 %r", file.filename)
            continue

        # 构建目标路径（保留目录结构）
        target = uploads / Path(*parts)

        # 确保父目录存在
        target.parent.mkdir(parents=True, exist_ok=True)

        # 同名文件加时间戳后缀
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            target = target.parent / f"{stem}_{int(time.time() * 1000)}{suffix}"

        try:
            content = await file.read()
            target.write_bytes(content)
            results.append({
                "name": target.name,
                "path": str(target),
                "size": len(content),
                "type": "file",
            })
            logger.info("文件上传成功: %s (%d bytes)", target, len(content))
        except Exception as exc:
            logger.error("文件上传失败: %s - %s", rel_path, exc)
            raise HTTPException(500, f"保存文件失败: {rel_path}")

    return {"uploaded": results}


@router.get("/files/uploads")
async def list_uploads(request: Request):
    """列出用户已上传的文件和文件夹（单层，与 /files 接口格式一致）"""
    uploads = _uploads_dir(request)
    items = []
    try:
        for entry in sorted(uploads.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith('.'):
                continue
            item: dict = {
                "name": entry.name,
                "path": str(entry),
                "type": "folder" if entry.is_dir() else "file",
            }
            if entry.is_file():
                try:
                    item["size"] = entry.stat().st_size
                except OSError:
                    item["size"] = 0
            items.append(item)
    except OSError:
        pass
    return {"path": str(uploads), "items": items}


@router.delete("/files/uploads/{filename}")
async def delete_upload(request: Request, filename: str):
    """删除一个已上传的文件"""
    uploads = _uploads_dir(request)
    target = uploads / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"文件不存在: {filename}")
    try:
        resolved = target.resolve()
        resolved.relative_to(uploads.resolve())
    except (OSError, ValueError):
        raise HTTPException(403, "路径非法")
    target.unlink()
    return {"ok": True}
