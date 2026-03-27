from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from sensenova_claw.app import main as app_main
from sensenova_claw.app.main import _spawn_managed_process, _terminate_managed_process


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="该测试仅覆盖类 Unix 进程组行为")
def test_terminate_managed_process_kills_child_process_tree(tmp_path: Path):
    child_pid_file = tmp_path / "child.pid"
    script = tmp_path / "spawn_child.py"
    script.write_text(
        """
import subprocess
import sys
import time
from pathlib import Path

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
time.sleep(60)
""".strip(),
        encoding="utf-8",
    )

    proc = _spawn_managed_process(
        [sys.executable, str(script), str(child_pid_file)],
        cwd=str(tmp_path),
        env=os.environ.copy(),
    )

    deadline = time.time() + 5
    while not child_pid_file.exists() and time.time() < deadline:
        time.sleep(0.05)

    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
    assert proc.poll() is None
    os.kill(child_pid, 0)

    _terminate_managed_process(proc, timeout=1)

    assert proc.poll() is not None
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


@pytest.mark.skipif(os.name == "nt", reason="该测试仅覆盖类 Unix 进程组行为")
def test_spawn_managed_process_creates_new_process_group(tmp_path: Path):
    proc = _spawn_managed_process(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(tmp_path),
        env=os.environ.copy(),
    )
    try:
        assert os.getpgid(proc.pid) == proc.pid
    finally:
        _terminate_managed_process(proc, timeout=1)


def test_build_frontend_dev_cmd_prefers_next_cli(tmp_path, monkeypatch):
    web_dir = tmp_path / "web"
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    _touch(next_cli)

    monkeypatch.setattr(app_main, "_find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(app_main, "_find_npm", lambda: "/usr/bin/npm")

    assert app_main._build_frontend_dev_cmd(web_dir, 3000) == [
        "/usr/bin/node",
        str(next_cli),
        "dev",
        "-p",
        "3000",
    ]


def test_build_frontend_prod_cmd_requires_build_artifact(tmp_path, monkeypatch):
    web_dir = tmp_path / "web"
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    _touch(next_cli)

    monkeypatch.setattr(app_main, "_find_node", lambda: "")
    monkeypatch.setattr(app_main, "_find_npm", lambda: "/usr/bin/npm")

    assert app_main._build_frontend_prod_cmd(web_dir, 3000) == []

    (web_dir / ".next").mkdir(parents=True, exist_ok=True)

    assert app_main._build_frontend_prod_cmd(web_dir, 3000) == [
        "/usr/bin/npm",
        "run",
        "start",
        "--",
        "-p",
        "3000",
    ]
