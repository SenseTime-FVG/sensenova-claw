"""GET /api/files 端点测试"""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http.files import router


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "子目录").mkdir()
        Path(d, "子目录", "文档.pdf").write_text("内容", encoding="utf-8")
        Path(d, "数据.xlsx").write_bytes(b"\x00" * 100)
        Path(d, "说明.txt").write_text("hello", encoding="utf-8")
        yield d


@pytest.fixture
def app(temp_dir):
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.state.config = {}
    test_app.state.sensenova_claw_home = temp_dir
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_directory(client, temp_dir):
    resp = client.get("/api/files", params={"path": temp_dir})
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    names = [i["name"] for i in items]
    assert "子目录" in names
    assert "数据.xlsx" in names


def test_list_subdirectory(client, temp_dir):
    subdir = os.path.join(temp_dir, "子目录")
    resp = client.get("/api/files", params={"path": subdir})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "文档.pdf"
    assert items[0]["type"] == "file"


def test_path_not_found(client):
    resp = client.get("/api/files", params={"path": "/nonexistent/path_12345"})
    assert resp.status_code == 404


def test_path_is_file_not_dir(client, temp_dir):
    file_path = os.path.join(temp_dir, "说明.txt")
    resp = client.get("/api/files", params={"path": file_path})
    assert resp.status_code == 400


def test_folders_before_files(client, temp_dir):
    resp = client.get("/api/files", params={"path": temp_dir})
    items = resp.json()["items"]
    folders = [i for i in items if i["type"] == "folder"]
    files = [i for i in items if i["type"] == "file"]
    if folders and files:
        last_folder_idx = max(items.index(f) for f in folders)
        first_file_idx = min(items.index(f) for f in files)
        assert last_folder_idx < first_file_idx


def test_hidden_files_excluded(client, temp_dir):
    Path(temp_dir, ".hidden").write_text("secret", encoding="utf-8")
    resp = client.get("/api/files", params={"path": temp_dir})
    names = [i["name"] for i in resp.json()["items"]]
    assert ".hidden" not in names


def test_file_has_size(client, temp_dir):
    resp = client.get("/api/files", params={"path": temp_dir})
    items = resp.json()["items"]
    file_items = [i for i in items if i["type"] == "file"]
    for fi in file_items:
        assert "size" in fi
        assert isinstance(fi["size"], int)
