"""
Workspace 文件管理 API - 读写 AGENTS.md / USER.md / MEMORY.md 等 Markdown 文件
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

ALLOWED_FILES = {"AGENTS.md", "USER.md", "MEMORY.md", "HEARTBEAT.md"}
ALLOWED_EXTENSION = ".md"


def _workspace_dir(request: Request) -> Path:
    cfg = request.app.state.config
    home = getattr(request.app.state, "agentos_home", "") or str(Path.home() / ".agentos")
    return Path(home)


class FileContent(BaseModel):
    content: str


@router.get("/files")
async def list_workspace_files(request: Request):
    """列出 workspace 目录下所有 .md 文件"""
    ws_dir = _workspace_dir(request)
    if not ws_dir.exists():
        return []

    files = []
    for p in sorted(ws_dir.iterdir()):
        if p.is_file() and p.suffix == ALLOWED_EXTENSION:
            files.append({
                "name": p.name,
                "size": p.stat().st_size,
                "editable": True,
            })
    return files


@router.get("/files/{filename}")
async def read_workspace_file(filename: str, request: Request):
    """读取指定 workspace 文件"""
    if not filename.endswith(ALLOWED_EXTENSION):
        raise HTTPException(400, "仅支持 .md 文件")

    ws_dir = _workspace_dir(request)
    file_path = ws_dir / filename

    if not file_path.exists():
        raise HTTPException(404, f"文件不存在: {filename}")

    content = file_path.read_text(encoding="utf-8")
    return {"name": filename, "content": content}


@router.put("/files/{filename}")
async def write_workspace_file(filename: str, body: FileContent, request: Request):
    """写入/更新 workspace 文件"""
    if not filename.endswith(ALLOWED_EXTENSION):
        raise HTTPException(400, "仅支持 .md 文件")

    ws_dir = _workspace_dir(request)
    ws_dir.mkdir(parents=True, exist_ok=True)
    file_path = ws_dir / filename

    file_path.write_text(body.content, encoding="utf-8")
    logger.info("Workspace file written: %s", file_path)
    return {"name": filename, "size": file_path.stat().st_size, "status": "saved"}


@router.delete("/files/{filename}")
async def delete_workspace_file(filename: str, request: Request):
    """删除 workspace 文件（仅允许用户自建文件，核心文件不可删）"""
    if not filename.endswith(ALLOWED_EXTENSION):
        raise HTTPException(400, "仅支持 .md 文件")

    if filename in {"AGENTS.md", "USER.md"}:
        raise HTTPException(403, f"核心文件 {filename} 不允许删除")

    ws_dir = _workspace_dir(request)
    file_path = ws_dir / filename

    if not file_path.exists():
        raise HTTPException(404, f"文件不存在: {filename}")

    file_path.unlink()
    logger.info("Workspace file deleted: %s", file_path)
    return {"status": "deleted", "name": filename}
