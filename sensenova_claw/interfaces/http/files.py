"""通用文件列表 API - 浏览服务端文件系统目录 & 文件上传 & 文件下载"""
from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
import platform
import string
import time
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])


def _resolve_workspace_dir(request: Request) -> Path:
    """获取 workspace 根目录"""
    home = getattr(request.app.state, "sensenova_claw_home", "") or str(Path.home() / ".sensenova-claw")
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

    path="workspace" 映射到 ${SENSENOVA_CLAW_HOME}/workdir
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


@router.get("/files/workdir/{filepath:path}")
async def serve_workdir_file(request: Request, filepath: str):
    """以原始 MIME 类型提供 workdir 下的文件。

    路径相对于 ${SENSENOVA_CLAW_HOME}/workdir，例如
    ``/api/files/workdir/default/gold_price_ppt/page_01.html``
    对应 ``~/.sensenova-claw/workdir/default/gold_price_ppt/page_01.html``。

    HTML 中引用的相对路径（如 ``images/page1_bg.jpg``）会被浏览器
    基于当前 URL 目录自动解析到同级子路径。
    """
    workspace = _resolve_workspace_dir(request)
    workdir = workspace / "workdir"
    target = workdir / filepath

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {filepath}")

    # 只允许访问 workdir 下的文件
    try:
        resolved.relative_to(workdir.resolve())
    except ValueError:
        raise HTTPException(403, "路径越界")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {filepath}")

    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(path=str(resolved), media_type=media_type)


@router.get("/files/workdir-list")
async def list_workdir_slides(
    request: Request,
    dir: str = Query(..., description="相对于 workdir 的目录路径"),
):
    """列出指定 workdir 子目录下的 HTML 幻灯片文件（按文件名排序）"""
    workspace = _resolve_workspace_dir(request)
    workdir = workspace / "workdir"
    target = workdir / dir

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {dir}")

    try:
        resolved.relative_to(workdir.resolve())
    except ValueError:
        raise HTTPException(403, "路径越界")

    if not resolved.is_dir():
        raise HTTPException(404, f"目录不存在: {dir}")

    slides: list[dict] = []
    for entry in sorted(resolved.iterdir(), key=lambda e: e.name):
        if entry.is_file() and entry.suffix.lower() == ".html":
            slides.append({
                "name": entry.name,
                "path": str(entry.relative_to(workdir)).replace("\\", "/"),
            })

    return {"dir": dir, "slides": slides}


def _encode_dir_token(dir_path: str) -> str:
    """将目录绝对路径编码为 URL-safe base64 token"""
    raw = base64.urlsafe_b64encode(dir_path.encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def _decode_dir_token(token: str) -> str:
    """将 URL-safe base64 token 解码为目录绝对路径"""
    padded = token + "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8")


@router.get("/files/dir-token")
async def get_dir_token(
    request: Request,
    path: str = Query(..., description="要编码的目录绝对路径"),
):
    """为指定目录返回可用于 /files/serve/ 的 token 及其中的 HTML 幻灯片列表"""
    workspace = _resolve_workspace_dir(request)
    target = Path(path)

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {path}")

    if not _is_path_allowed(resolved, workspace):
        raise HTTPException(403, f"无权访问: {path}")

    if not resolved.is_dir():
        raise HTTPException(404, f"目录不存在: {path}")

    token = _encode_dir_token(str(resolved))

    slides: list[dict] = []
    for entry in sorted(resolved.iterdir(), key=lambda e: e.name):
        if entry.is_file() and entry.suffix.lower() == ".html":
            slides.append({"name": entry.name, "path": entry.name})

    return {"token": token, "dir": str(resolved), "slides": slides}


@router.get("/files/serve/{dir_token}/{filepath:path}")
async def serve_dir_file(request: Request, dir_token: str, filepath: str):
    """通过 token 提供目录下的文件，HTML 相对引用能够自动解析。

    dir_token 是 /files/dir-token 返回的 URL-safe base64 编码目录路径，
    filepath 是该目录下的相对路径。
    """
    workspace = _resolve_workspace_dir(request)
    try:
        base_dir = Path(_decode_dir_token(dir_token))
    except Exception:
        raise HTTPException(400, "无效的目录 token")

    target = base_dir / filepath

    try:
        resolved = target.resolve()
        base_resolved = base_dir.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {filepath}")

    # 必须在 base_dir 内
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(403, "路径越界")

    if not _is_path_allowed(resolved, workspace):
        raise HTTPException(403, f"无权访问")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {filepath}")

    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(path=str(resolved), media_type=media_type)


@router.get("/files/download")
async def download_file(
    request: Request,
    path: str = Query(..., description="要下载的文件绝对路径"),
):
    """下载/预览指定路径的文件，Content-Type 根据扩展名自动推断"""
    workspace = _resolve_workspace_dir(request)
    target = Path(path)

    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, f"无效路径: {path}")

    if not _is_path_allowed(resolved, workspace):
        raise HTTPException(403, f"无权访问: {path}")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {path}")

    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type=media_type,
    )


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


# ---------------------------------------------------------------------------
# 文件存在性检查
# ---------------------------------------------------------------------------

def _resolve_agent_workdir(request: Request, agent_id: str) -> Path:
    """获取指定 agent 的 workdir 绝对路径"""
    home = getattr(request.app.state, "sensenova_claw_home", "") or str(Path.home() / ".sensenova-claw")
    return Path(home) / "workdir" / agent_id


def _sha256_file(filepath: Path) -> str:
    """计算文件的 SHA-256 哈希"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class FileCheckRequest(BaseModel):
    name: str
    size: int
    hash: str | None = None
    agent_id: str = "default"


class FileCheckResponse(BaseModel):
    exists: bool
    path: str = ""
    need_hash: bool = False


@router.post("/files/check")
async def check_file(request: Request, body: FileCheckRequest) -> FileCheckResponse:
    """检查文件是否已存在于 agent workdir 中。

    比对策略：先比文件名+大小，匹配后再比 SHA-256 哈希。
    """
    workdir = _resolve_agent_workdir(request, body.agent_id)
    # 防止路径穿越
    parts = [p for p in body.name.replace("\\", "/").split("/") if p and p != ".."]
    if not parts:
        return FileCheckResponse(exists=False)
    target = workdir / Path(*parts)

    if not target.exists() or not target.is_file():
        return FileCheckResponse(exists=False)

    try:
        file_size = target.stat().st_size
    except OSError:
        return FileCheckResponse(exists=False)

    if file_size != body.size:
        return FileCheckResponse(exists=False)

    # name + size 匹配，需要 hash 精确比对
    if not body.hash:
        return FileCheckResponse(exists=False, need_hash=True)

    file_hash = _sha256_file(target)
    if file_hash == body.hash:
        return FileCheckResponse(exists=True, path=str(target.resolve()))
    return FileCheckResponse(exists=False)
