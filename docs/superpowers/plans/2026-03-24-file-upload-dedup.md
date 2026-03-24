# 文件上传去重与工作目录同步 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现文件/文件夹上传时自动与 Agent workdir 去重，已存在则直接引用绝对路径，不存在则上传到 workdir 并引用。

**Architecture:** 前端选择文件后，先通过 HTTP API 向后端发送文件元信息（名称+大小）进行快速匹配；若 name+size 匹配，前端计算 SHA-256 发给后端精确比对；匹配成功返回绝对路径直接引用，否则上传文件到 `workdir/{agent_id}/` 并返回绝对路径。文件夹上传采用全量匹配策略（任一文件不匹配则整体重新上传）。

**Tech Stack:** FastAPI (后端 API), hashlib (SHA-256), Web Crypto API (前端 SHA-256), XMLHttpRequest (上传进度), Next.js/React

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `sensenova_claw/interfaces/http/files.py` | 新增 `POST /api/files/check`、`POST /api/files/check-dir` 接口；修改 `POST /api/files/upload` 目标目录和重名策略 |
| `sensenova_claw/app/web/lib/fileUpload.ts` | **新建** — 前端文件上传工具：SHA-256 计算、check API 调用、上传（含进度）、去重流程编排 |
| `sensenova_claw/app/web/components/chat/ChatInput.tsx` | 修改 `handleFileSelect` — 调用 fileUpload 工具完成去重+上传流程，插入绝对路径 |
| `sensenova_claw/app/web/components/chat/UploadProgress.tsx` | **新建** — 上传进度条 UI 组件（>1MB 文件显示进度条） |
| `tests/unit/test_file_check.py` | **新建** — 后端 check/check-dir/upload 重名逻辑单元测试 |

---

### Task 1: 后端 — 文件存在性检查接口 `POST /api/files/check`

**Files:**
- Modify: `sensenova_claw/interfaces/http/files.py`
- Test: `tests/unit/test_file_check.py`

- [ ] **Step 1: 编写 `POST /api/files/check` 的单元测试**

```python
# tests/unit/test_file_check.py
"""文件存在性检查 API 单元测试"""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http.files import router


@pytest.fixture
def app(tmp_path):
    """创建带 workdir 的测试 app"""
    app = FastAPI()
    app.include_router(router)
    app.state.sensenova_claw_home = str(tmp_path)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestFileCheck:
    """POST /api/files/check 测试"""

    def test_file_not_found(self, client, tmp_path):
        """workdir 下无同名文件 → exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": 100,
            "agent_id": "default",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is False

    def test_file_same_name_different_size(self, client, tmp_path):
        """同名但 size 不同 → exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        (workdir / "test.txt").write_text("hello")
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": 999,
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is False

    def test_file_same_name_same_size_no_hash(self, client, tmp_path):
        """同名同 size，未提供 hash → need_hash=True"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        content = b"hello world"
        (workdir / "test.txt").write_bytes(content)
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": len(content),
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is True

    def test_file_same_name_same_size_hash_match(self, client, tmp_path):
        """同名同 size 同 hash → exists=True，返回绝对路径"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        content = b"hello world"
        (workdir / "test.txt").write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": len(content),
            "hash": sha256,
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is True
        assert data["path"] == str(workdir / "test.txt")

    def test_file_same_name_same_size_hash_mismatch(self, client, tmp_path):
        """同名同 size 但 hash 不同 → exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        (workdir / "test.txt").write_bytes(b"hello world")
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": 11,
            "hash": "0000000000000000000000000000000000000000000000000000000000000000",
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_file_check.py -v`
Expected: FAIL（`POST /api/files/check` 路由不存在，405 或 404）

- [ ] **Step 3: 实现 `POST /api/files/check` 接口**

在 `sensenova_claw/interfaces/http/files.py` 中添加：

```python
import hashlib
from pydantic import BaseModel


class FileCheckRequest(BaseModel):
    name: str
    size: int
    hash: str | None = None
    agent_id: str = "default"


class FileCheckResponse(BaseModel):
    exists: bool
    path: str = ""
    need_hash: bool = False


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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_file_check.py::TestFileCheck -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/http/files.py tests/unit/test_file_check.py
git commit -m "feat(api): 新增 POST /api/files/check 文件存在性检查接口"
```

---

### Task 2: 后端 — 文件夹存在性检查接口 `POST /api/files/check-dir`

**Files:**
- Modify: `sensenova_claw/interfaces/http/files.py`
- Test: `tests/unit/test_file_check.py`

- [ ] **Step 1: 编写 `POST /api/files/check-dir` 的单元测试**

在 `tests/unit/test_file_check.py` 中追加：

```python
class TestDirCheck:
    """POST /api/files/check-dir 测试"""

    def test_dir_not_exists(self, client, tmp_path):
        """目标文件夹不存在 → exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": 5}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is False

    def test_dir_file_missing(self, client, tmp_path):
        """文件夹存在但缺少文件 → exists=False"""
        workdir = tmp_path / "workdir" / "default" / "mydir"
        workdir.mkdir(parents=True)
        (workdir / "a.txt").write_bytes(b"hello")
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5},
                {"rel_path": "b.txt", "size": 3},
            ],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_size_mismatch(self, client, tmp_path):
        """所有文件都存在但某个 size 不同 → exists=False"""
        workdir = tmp_path / "workdir" / "default" / "mydir"
        workdir.mkdir(parents=True)
        (workdir / "a.txt").write_bytes(b"hello")
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": 999}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_all_match_no_hash(self, client, tmp_path):
        """所有文件 name+size 匹配但未提供 hash → need_hash=True"""
        workdir = tmp_path / "workdir" / "default" / "mydir"
        workdir.mkdir(parents=True)
        content = b"hello"
        (workdir / "a.txt").write_bytes(content)
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": len(content)}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is True

    def test_dir_all_match_with_hash(self, client, tmp_path):
        """所有文件 name+size+hash 完全匹配 → exists=True"""
        workdir = tmp_path / "workdir" / "default" / "mydir"
        workdir.mkdir(parents=True)
        content = b"hello"
        (workdir / "a.txt").write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": len(content), "hash": sha}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is True
        assert "mydir" in data["path"]

    def test_dir_hash_mismatch(self, client, tmp_path):
        """某个文件 hash 不匹配 → exists=False"""
        workdir = tmp_path / "workdir" / "default" / "mydir"
        workdir.mkdir(parents=True)
        (workdir / "a.txt").write_bytes(b"hello")
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": 5, "hash": "bad_hash"}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_nested_structure(self, client, tmp_path):
        """嵌套目录结构匹配"""
        workdir = tmp_path / "workdir" / "default" / "mydir" / "sub"
        workdir.mkdir(parents=True)
        content = b"nested"
        (workdir / "deep.txt").write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "sub/deep.txt", "size": len(content), "hash": sha}],
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_file_check.py::TestDirCheck -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 `POST /api/files/check-dir` 接口**

在 `sensenova_claw/interfaces/http/files.py` 中添加：

```python
class DirFileItem(BaseModel):
    rel_path: str
    size: int
    hash: str | None = None


class DirCheckRequest(BaseModel):
    folder_name: str
    files: list[DirFileItem]
    agent_id: str = "default"


class DirCheckResponse(BaseModel):
    exists: bool
    path: str = ""
    need_hash: bool = False


@router.post("/files/check-dir")
async def check_dir(request: Request, body: DirCheckRequest) -> DirCheckResponse:
    """检查文件夹是否已完整存在于 agent workdir 中。

    全量匹配策略：所有文件的 name+size+hash 必须全部匹配才返回 exists=True。
    """
    workdir = _resolve_agent_workdir(request, body.agent_id)
    # 防止路径穿越
    folder_parts = [p for p in body.folder_name.replace("\\", "/").split("/") if p and p != ".."]
    if not folder_parts:
        return DirCheckResponse(exists=False)
    folder = workdir / Path(*folder_parts)

    if not folder.exists() or not folder.is_dir():
        return DirCheckResponse(exists=False)

    # 逐个检查文件
    all_size_match = True
    for file_item in body.files:
        # 清理路径，防止路径穿越
        parts = [p for p in file_item.rel_path.split("/") if p and p != ".."]
        if not parts:
            return DirCheckResponse(exists=False)
        target = folder / Path(*parts)

        if not target.exists() or not target.is_file():
            return DirCheckResponse(exists=False)

        try:
            if target.stat().st_size != file_item.size:
                all_size_match = False
                break
        except OSError:
            return DirCheckResponse(exists=False)

    if not all_size_match:
        return DirCheckResponse(exists=False)

    # name+size 全部匹配，检查是否需要 hash
    has_all_hashes = all(f.hash for f in body.files)
    if not has_all_hashes:
        return DirCheckResponse(exists=False, need_hash=True)

    # 逐个比对 hash
    for file_item in body.files:
        parts = [p for p in file_item.rel_path.split("/") if p and p != ".."]
        target = folder / Path(*parts)
        file_hash = _sha256_file(target)
        if file_hash != file_item.hash:
            return DirCheckResponse(exists=False)

    return DirCheckResponse(exists=True, path=str(folder.resolve()))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_file_check.py::TestDirCheck -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/http/files.py tests/unit/test_file_check.py
git commit -m "feat(api): 新增 POST /api/files/check-dir 文件夹存在性检查接口"
```

---

### Task 3: 后端 — 修改 upload 接口支持 workdir 目标和数字递增重名

**Files:**
- Modify: `sensenova_claw/interfaces/http/files.py`
- Test: `tests/unit/test_file_check.py`

- [ ] **Step 1: 编写上传到 workdir + 数字递增重名的单元测试**

在 `tests/unit/test_file_check.py` 中追加：

```python
from io import BytesIO


class TestUploadToWorkdir:
    """POST /api/files/upload 上传到 workdir 测试"""

    def test_upload_single_file(self, client, tmp_path):
        """单文件上传到 workdir/{agent_id}/"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post(
            "/api/files/upload",
            data={"agent_id": "default"},
            files=[("files", ("test.txt", BytesIO(b"hello"), "text/plain"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["uploaded"]) == 1
        uploaded_path = Path(data["uploaded"][0]["path"])
        assert uploaded_path.parent == workdir
        assert uploaded_path.read_bytes() == b"hello"

    def test_upload_numeric_suffix_on_conflict(self, client, tmp_path):
        """同名文件使用数字递增后缀: test_1.txt, test_2.txt"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        (workdir / "test.txt").write_text("existing")

        resp = client.post(
            "/api/files/upload",
            data={"agent_id": "default"},
            files=[("files", ("test.txt", BytesIO(b"new content"), "text/plain"))],
        )
        data = resp.json()
        assert data["uploaded"][0]["name"] == "test_1.txt"

        # 再上传一次，应变为 test_2.txt
        (workdir / "test_1.txt").write_text("v1")
        resp2 = client.post(
            "/api/files/upload",
            data={"agent_id": "default"},
            files=[("files", ("test.txt", BytesIO(b"another"), "text/plain"))],
        )
        data2 = resp2.json()
        assert data2["uploaded"][0]["name"] == "test_2.txt"

    def test_upload_folder_preserves_structure(self, client, tmp_path):
        """文件夹上传保留目录结构"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post(
            "/api/files/upload",
            data={"agent_id": "default"},
            files=[
                ("files", ("mydir/a.txt", BytesIO(b"aaa"), "text/plain")),
                ("files", ("mydir/sub/b.txt", BytesIO(b"bbb"), "text/plain")),
            ],
        )
        data = resp.json()
        assert len(data["uploaded"]) == 2
        assert (workdir / "mydir" / "a.txt").exists()
        assert (workdir / "mydir" / "sub" / "b.txt").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_file_check.py::TestUploadToWorkdir -v`
Expected: FAIL（upload 仍然写入 uploads/ 目录）

- [ ] **Step 3: 修改 `upload_files` 接口**

修改 `sensenova_claw/interfaces/http/files.py` 中的 `upload_files`：

```python
def _next_available_path(target: Path) -> Path:
    """数字递增查找可用文件名: file.txt → file_1.txt → file_2.txt"""
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


@router.post("/files/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = FastAPIFile(...),
    agent_id: str = Form("default"),
):
    """接收文件上传到 agent workdir，支持单文件、多文件和文件夹。

    文件夹上传时 filename 包含相对路径（如 ``mydir/sub/file.txt``），
    服务端会在 workdir/{agent_id}/ 下保留对应的目录结构。
    重名文件使用数字递增后缀（file_1.txt, file_2.txt）。
    """
    logger.info("收到上传请求: %d 个文件, agent_id=%s", len(files), agent_id)
    workdir = _resolve_agent_workdir(request, agent_id)
    workdir.mkdir(parents=True, exist_ok=True)
    results = []

    for file in files:
        if not file.filename:
            logger.warning("跳过: 空文件名")
            continue

        rel_path = file.filename.replace("\\", "/").lstrip("/")
        parts = [p for p in rel_path.split("/") if p and p != ".." and not p.startswith(".")]
        if not parts:
            logger.warning("跳过: 非法文件名 %r", file.filename)
            continue

        target = workdir / Path(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)

        # 数字递增重名处理
        target = _next_available_path(target)

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
```

- [ ] **Step 4: 运行全部后端测试确认通过**

Run: `python3 -m pytest tests/unit/test_file_check.py -v`
Expected: ALL passed

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/http/files.py tests/unit/test_file_check.py
git commit -m "feat(api): upload 接口改为写入 workdir，重名使用数字递增后缀"
```

---

### Task 4: 前端 — 文件上传工具库 `fileUpload.ts`

**Files:**
- Create: `sensenova_claw/app/web/lib/fileUpload.ts`

- [ ] **Step 1: 创建 `fileUpload.ts`**

```typescript
// sensenova_claw/app/web/lib/fileUpload.ts
/**
 * 文件上传工具：SHA-256 计算、存在性检查、上传（含进度）
 */
import { authFetch, API_BASE } from './authFetch';

/** 单文件检查结果 */
export interface FileCheckResult {
  exists: boolean;
  path: string;
  need_hash: boolean;
}

/** 文件夹检查结果 */
export interface DirCheckResult {
  exists: boolean;
  path: string;
  need_hash: boolean;
}

/** 上传进度回调 */
export type ProgressCallback = (loaded: number, total: number) => void;

/** 上传结果 */
export interface UploadResult {
  name: string;
  path: string;
  size: number;
}

// ---------- SHA-256 ----------

/** 文件大小上限（100MB），超过此大小跳过哈希计算直接上传 */
const MAX_HASH_SIZE = 100 * 1024 * 1024;

/** 计算文件的 SHA-256 哈希（Web Crypto API）。超过 100MB 返回 null。 */
export async function computeSHA256(file: File): Promise<string | null> {
  if (file.size > MAX_HASH_SIZE) return null;
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ---------- 检查接口 ----------

/** 检查单个文件是否已存在于 agent workdir */
export async function checkFile(
  name: string, size: number, agentId: string, hash?: string,
): Promise<FileCheckResult> {
  const resp = await authFetch(`${API_BASE}/api/files/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, size, agent_id: agentId, hash }),
  });
  if (!resp.ok) throw new Error(`文件检查失败: ${resp.status}`);
  return resp.json();
}

/** 检查文件夹是否已完整存在于 agent workdir */
export async function checkDir(
  folderName: string,
  files: { rel_path: string; size: number; hash?: string }[],
  agentId: string,
): Promise<DirCheckResult> {
  const resp = await authFetch(`${API_BASE}/api/files/check-dir`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_name: folderName, files, agent_id: agentId }),
  });
  if (!resp.ok) throw new Error(`文件夹检查失败: ${resp.status}`);
  return resp.json();
}

// ---------- 上传 ----------

const PROGRESS_THRESHOLD = 1024 * 1024; // 1MB

/** 上传文件到 agent workdir，>1MB 时通过 onProgress 回调进度 */
export function uploadFiles(
  files: { file: File; filename: string }[],
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<UploadResult[]> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('agent_id', agentId);
    let totalSize = 0;
    for (const { file, filename } of files) {
      formData.append('files', file, filename);
      totalSize += file.size;
    }

    // 小文件用 fetch，大文件用 XMLHttpRequest 获取进度
    if (totalSize <= PROGRESS_THRESHOLD || !onProgress) {
      authFetch(`${API_BASE}/api/files/upload`, {
        method: 'POST',
        body: formData,
      })
        .then(resp => resp.json())
        .then(data => resolve(data.uploaded || []))
        .catch(reject);
      return;
    }

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/files/upload`);
    xhr.withCredentials = true;

    // 从 cookie 读取 token
    const tokenMatch = document.cookie.match(/(?:^|; )sensenova_claw_token=([^;]*)/);
    if (tokenMatch) {
      xhr.setRequestHeader('Authorization', `Bearer ${decodeURIComponent(tokenMatch[1])}`);
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve(data.uploaded || []);
        } catch {
          reject(new Error('上传响应解析失败'));
        }
      } else {
        reject(new Error(`上传失败: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error('上传网络错误'));
    xhr.send(formData);
  });
}

// ---------- 编排：单文件去重+上传 ----------

export interface FileUploadFlowResult {
  path: string;           // 绝对路径
  uploaded: boolean;       // true=新上传，false=已存在
}

/** 单文件去重+上传流程 */
export async function singleFileFlow(
  file: File,
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<FileUploadFlowResult> {
  // 1. 检查 name + size
  const check1 = await checkFile(file.name, file.size, agentId);
  if (check1.exists) {
    return { path: check1.path, uploaded: false };
  }

  // 2. 如果 need_hash，计算 SHA-256 再检查
  if (check1.need_hash) {
    const hash = await computeSHA256(file);
    const check2 = await checkFile(file.name, file.size, agentId, hash);
    if (check2.exists) {
      return { path: check2.path, uploaded: false };
    }
  }

  // 3. 上传
  const results = await uploadFiles(
    [{ file, filename: file.name }],
    agentId,
    onProgress,
  );
  if (results.length === 0) throw new Error('上传返回空结果');
  return { path: results[0].path, uploaded: true };
}

// ---------- 编排：文件夹去重+上传 ----------

export interface DirUploadFlowResult {
  path: string;           // 文件夹绝对路径
  uploaded: boolean;
}

/** 文件夹去重+上传流程 */
export async function dirUploadFlow(
  folderName: string,
  files: File[],
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<DirUploadFlowResult> {
  // 构造文件列表（包含相对路径和大小）
  const fileItems = files.map(f => {
    const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    // 去掉顶层文件夹名前缀，因为 check-dir 已经有 folder_name
    const parts = relPath.split('/');
    const withoutTop = parts.slice(1).join('/');
    return { rel_path: withoutTop || f.name, size: f.size, file: f };
  });

  // 1. 检查 name + size
  const check1 = await checkDir(
    folderName,
    fileItems.map(f => ({ rel_path: f.rel_path, size: f.size })),
    agentId,
  );
  if (check1.exists) {
    return { path: check1.path, uploaded: false };
  }

  // 2. 如果 need_hash，计算所有文件 SHA-256 再检查
  if (check1.need_hash) {
    const itemsWithHash = await Promise.all(
      fileItems.map(async f => ({
        rel_path: f.rel_path,
        size: f.size,
        hash: await computeSHA256(f.file),
      })),
    );
    const check2 = await checkDir(folderName, itemsWithHash, agentId);
    if (check2.exists) {
      return { path: check2.path, uploaded: false };
    }
  }

  // 3. 整个文件夹重新上传
  const uploadItems = files.map(f => {
    const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    return { file: f, filename: relPath };
  });
  const results = await uploadFiles(uploadItems, agentId, onProgress);
  if (results.length === 0) throw new Error('上传返回空结果');

  // 从第一个上传结果推算文件夹绝对路径
  const firstPath = results[0].path;
  const folderIdx = firstPath.indexOf(`/${folderName}/`);
  const folderPath = folderIdx >= 0
    ? firstPath.substring(0, folderIdx + folderName.length + 1)
    : firstPath.substring(0, firstPath.lastIndexOf('/'));

  return { path: folderPath, uploaded: true };
}
```

- [ ] **Step 2: 提交**

```bash
git add sensenova_claw/app/web/lib/fileUpload.ts
git commit -m "feat(web): 新增 fileUpload.ts 文件上传工具库（去重+进度+SHA-256）"
```

---

### Task 5: 前端 — 上传进度条组件 `UploadProgress.tsx`

**Files:**
- Create: `sensenova_claw/app/web/components/chat/UploadProgress.tsx`

- [ ] **Step 1: 创建 `UploadProgress.tsx`**

```tsx
// sensenova_claw/app/web/components/chat/UploadProgress.tsx
'use client';

import { Loader2 } from 'lucide-react';

export interface UploadProgressItem {
  id: string;
  name: string;
  /** 0~100，null 表示不确定进度（小文件 loading 状态） */
  percent: number | null;
  status: 'uploading' | 'checking' | 'done' | 'error';
  error?: string;
}

interface UploadProgressProps {
  items: UploadProgressItem[];
}

export function UploadProgress({ items }: UploadProgressProps) {
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5 px-4 py-2">
      {items.map(item => (
        <div key={item.id} className="flex items-center gap-2 text-xs text-muted-foreground">
          {item.status === 'done' ? (
            <span className="text-green-500">✓</span>
          ) : item.status === 'error' ? (
            <span className="text-destructive">✗</span>
          ) : (
            <Loader2 size={12} className="animate-spin" />
          )}
          <span className="truncate max-w-[200px]">{item.name}</span>
          {item.status === 'checking' && <span>检查中...</span>}
          {item.status === 'uploading' && item.percent !== null && (
            <div className="flex-1 max-w-[120px] h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-300"
                style={{ width: `${item.percent}%` }}
              />
            </div>
          )}
          {item.status === 'uploading' && item.percent !== null && (
            <span>{item.percent}%</span>
          )}
          {item.status === 'uploading' && item.percent === null && (
            <span>上传中...</span>
          )}
          {item.status === 'error' && (
            <span className="text-destructive">{item.error || '失败'}</span>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add sensenova_claw/app/web/components/chat/UploadProgress.tsx
git commit -m "feat(web): 新增 UploadProgress 上传进度条组件"
```

---

### Task 6: 前端 — 改造 ChatInput 集成去重上传流程

**Files:**
- Modify: `sensenova_claw/app/web/components/chat/ChatInput.tsx`

- [ ] **Step 1: 修改 ChatInput 组件**

主要改动点：

1. **复用现有 `selectedAgent` prop** 作为 agent ID 传给 check/upload API（无需新增 prop）。

2. **新增状态**：

```typescript
import { useState } from 'react';
import { singleFileFlow, dirUploadFlow, type ProgressCallback } from '@/lib/fileUpload';
import { UploadProgress, type UploadProgressItem } from './UploadProgress';

// 在组件内：
const [uploadItems, setUploadItems] = useState<UploadProgressItem[]>([]);
```

3. **替换 `handleFileSelect`**：

```typescript
const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
  const selectedFiles = e.target.files;
  if (!selectedFiles || selectedFiles.length === 0) return;

  const fileList = Array.from(selectedFiles);
  const firstFile = fileList[0];
  const relPath = (firstFile as File & { webkitRelativePath?: string }).webkitRelativePath;
  const isFolder = Boolean(relPath);

  if (isFolder) {
    // 文件夹上传
    const topFolder = relPath!.split('/')[0];
    const itemId = `upload_${Date.now()}`;
    const totalSize = fileList.reduce((sum, f) => sum + f.size, 0);
    const showProgress = totalSize > 1024 * 1024;

    setUploadItems(prev => [...prev, {
      id: itemId, name: topFolder,
      percent: showProgress ? 0 : null,
      status: 'checking',
    }]);

    try {
      const onProgress: ProgressCallback | undefined = showProgress
        ? (loaded, total) => setUploadItems(prev =>
            prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
        : undefined;

      const result = await dirUploadFlow(topFolder, fileList, selectedAgent, onProgress);
      insertAtRef(result.path);
      setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
    } catch (err) {
      setUploadItems(prev => prev.map(it => it.id === itemId
        ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
    }
  } else {
    // 单文件或多文件上传
    for (const file of fileList) {
      const itemId = `upload_${Date.now()}_${file.name}`;
      const showProgress = file.size > 1024 * 1024;

      setUploadItems(prev => [...prev, {
        id: itemId, name: file.name,
        percent: showProgress ? 0 : null,
        status: 'checking',
      }]);

      try {
        const onProgress: ProgressCallback | undefined = showProgress
          ? (loaded, total) => setUploadItems(prev =>
              prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
          : undefined;

        const result = await singleFileFlow(file, selectedAgent, onProgress);
        insertAtRef(result.path);
        setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
      } catch (err) {
        setUploadItems(prev => prev.map(it => it.id === itemId
          ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
      }
    }
  }

  // 3秒后清除已完成的进度项
  setTimeout(() => {
    setUploadItems(prev => prev.filter(it => it.status !== 'done'));
  }, 3000);

  if (fileInputRef.current) fileInputRef.current.value = '';
  if (folderInputRef.current) folderInputRef.current.value = '';
}, [selectedAgent, insertAtRef]);
```

4. **在输入框上方渲染进度条**：

在 textarea 前面添加：

```tsx
<UploadProgress items={uploadItems} />
```

- [ ] **Step 2: 手动测试**

1. 启动 `sensenova-claw run`
2. 在对话框点击回形针 → 选择文件
3. 验证：首次上传显示进度（大文件）或 loading（小文件），完成后输入框出现 `@/绝对路径`
4. 再次选择相同文件 → 应直接出现 `@绝对路径`，无需重新上传
5. 选择文件夹 → 同样逻辑

- [ ] **Step 3: 提交**

```bash
git add sensenova_claw/app/web/components/chat/ChatInput.tsx
git commit -m "feat(web): ChatInput 集成文件去重上传流程，插入绝对路径引用"
```

---

### Task 7: 集成验证与清理

**Files:**
- All modified files

- [ ] **Step 1: 运行全部后端单元测试**

Run: `python3 -m pytest tests/unit/test_file_check.py -v`
Expected: ALL passed

- [ ] **Step 2: 运行前端构建确认无编译错误**

Run: `cd sensenova_claw/app/web && npm run build`
Expected: 编译成功

- [ ] **Step 3: 端到端验证**

启动 `sensenova-claw run`，在浏览器中：
1. 上传一个小文件（<1MB）→ 检查 loading 状态 → 输入框出现绝对路径
2. 上传一个大文件（>1MB）→ 检查进度条 → 输入框出现绝对路径
3. 再次上传相同文件 → 快速返回，无重新上传
4. 上传文件夹 → 所有文件同步到 workdir → 输入框出现文件夹绝对路径
5. 再次上传相同文件夹 → 快速返回

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: 文件上传去重与工作目录同步功能完成"
```
