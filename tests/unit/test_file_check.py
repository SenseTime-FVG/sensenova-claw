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
