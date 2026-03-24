"""文件存在性检查 API 单元测试"""
import hashlib
from pathlib import Path

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
        """workdir 下无同名文件 -> exists=False"""
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
        """同名但 size 不同 -> exists=False"""
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
        """同名同 size，未提供 hash -> need_hash=True"""
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
        """同名同 size 同 hash -> exists=True，返回绝对路径"""
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
        """同名同 size 但 hash 不同 -> exists=False"""
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

    def test_agent_id_traversal_blocked(self, client, tmp_path):
        """agent_id 路径穿越 → 回退到 default"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post("/api/files/check", json={
            "name": "test.txt",
            "size": 100,
            "agent_id": "../../etc",
        })
        data = resp.json()
        assert data["exists"] is False

    def test_path_traversal_blocked(self, client, tmp_path):
        """路径穿越尝试 -> exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post("/api/files/check", json={
            "name": "../../../etc/passwd",
            "size": 100,
            "agent_id": "default",
        })
        data = resp.json()
        assert data["exists"] is False


class TestDirCheck:
    """POST /api/files/check-dir 测试"""

    def _make_dir(self, tmp_path, rel_files: dict[str, bytes]):
        """在 tmp_path/workdir/default/mydir 下创建文件，返回 mydir 路径"""
        mydir = tmp_path / "workdir" / "default" / "mydir"
        for rel, content in rel_files.items():
            p = mydir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        return mydir

    def _hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def test_dir_not_exists(self, client, tmp_path):
        """文件夹不存在 -> exists=False"""
        workdir = tmp_path / "workdir" / "default"
        workdir.mkdir(parents=True)
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [{"rel_path": "a.txt", "size": 5}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False

    def test_dir_file_missing(self, client, tmp_path):
        """文件夹存在但缺少文件 -> exists=False"""
        self._make_dir(tmp_path, {"a.txt": b"hello"})
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5},
                {"rel_path": "b.txt", "size": 3},
            ],
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_size_mismatch(self, client, tmp_path):
        """文件都在但 size 不匹配 -> exists=False"""
        self._make_dir(tmp_path, {"a.txt": b"hello", "b.txt": b"world"})
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5},
                {"rel_path": "b.txt", "size": 999},
            ],
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_all_match_no_hash(self, client, tmp_path):
        """name+size 全部匹配但未提供 hash -> need_hash=True"""
        self._make_dir(tmp_path, {"a.txt": b"hello", "b.txt": b"world"})
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5},
                {"rel_path": "b.txt", "size": 5},
            ],
        })
        data = resp.json()
        assert data["exists"] is False
        assert data["need_hash"] is True

    def test_dir_all_match_with_hash(self, client, tmp_path):
        """name+size+hash 全部匹配 -> exists=True，返回路径"""
        content_a = b"hello"
        content_b = b"world"
        mydir = self._make_dir(tmp_path, {"a.txt": content_a, "b.txt": content_b})
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5, "hash": self._hash(content_a)},
                {"rel_path": "b.txt", "size": 5, "hash": self._hash(content_b)},
            ],
        })
        data = resp.json()
        assert data["exists"] is True
        assert data["path"] == str(mydir.resolve())

    def test_dir_hash_mismatch(self, client, tmp_path):
        """hash 不匹配 -> exists=False"""
        self._make_dir(tmp_path, {"a.txt": b"hello"})
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": 5, "hash": "0" * 64},
            ],
        })
        data = resp.json()
        assert data["exists"] is False

    def test_dir_nested_structure(self, client, tmp_path):
        """嵌套子目录结构全部匹配 -> exists=True"""
        content_a = b"file_a"
        content_b = b"nested_b"
        mydir = self._make_dir(tmp_path, {
            "a.txt": content_a,
            "sub/b.txt": content_b,
        })
        resp = client.post("/api/files/check-dir", json={
            "folder_name": "mydir",
            "files": [
                {"rel_path": "a.txt", "size": len(content_a), "hash": self._hash(content_a)},
                {"rel_path": "sub/b.txt", "size": len(content_b), "hash": self._hash(content_b)},
            ],
        })
        data = resp.json()
        assert data["exists"] is True
        assert data["path"] == str(mydir.resolve())
