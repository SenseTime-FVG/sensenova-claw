from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import sensenova_claw.app.main as app_main
from sensenova_claw.app.main import (
    _check_port,
    _build_frontend_dev_cmd,
    _build_frontend_prod_cmd,
    _spawn_managed_process,
    _terminate_managed_process,
    _wait_for_port_listen,
)


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


def test_build_frontend_dev_cmd_prefers_direct_next(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    web_dir = tmp_path / "web"
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin"
    next_cli.mkdir(parents=True)
    (next_cli / "next").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_main, "_find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(app_main, "_find_npm", lambda: "/usr/bin/npm")

    cmd = _build_frontend_dev_cmd(web_dir, 3456)

    assert cmd == ["/usr/bin/node", str(next_cli / "next"), "dev", "-p", "3456"]


def test_build_frontend_prod_cmd_requires_build_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    web_dir = tmp_path / "web"
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin"
    next_cli.mkdir(parents=True)
    (next_cli / "next").write_text("", encoding="utf-8")
    (web_dir / ".next").mkdir(parents=True)

    monkeypatch.setattr(app_main, "_find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(app_main, "_find_npm", lambda: "/usr/bin/npm")

    assert _build_frontend_prod_cmd(web_dir, 3000) == []


def test_build_frontend_prod_cmd_uses_direct_next_when_build_id_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    web_dir = tmp_path / "web"
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin"
    next_cli.mkdir(parents=True)
    (next_cli / "next").write_text("", encoding="utf-8")
    build_id = web_dir / ".next" / "BUILD_ID"
    build_id.parent.mkdir(parents=True)
    build_id.write_text("build-123", encoding="utf-8")

    monkeypatch.setattr(app_main, "_find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(app_main, "_find_npm", lambda: "/usr/bin/npm")

    assert _build_frontend_prod_cmd(web_dir, 3000) == [
        "/usr/bin/node",
        str(next_cli / "next"),
        "start",
        "-p",
        "3000",
    ]


def test_wait_for_port_listen_fails_when_process_exits_early(monkeypatch: pytest.MonkeyPatch):
    states = iter([True, True])
    monkeypatch.setattr(app_main, "_check_port", lambda port: next(states, True))

    proc = SimpleNamespace(poll=lambda: 1)

    assert _wait_for_port_listen(3000, timeout=0.01, proc=proc) is False


def test_wait_for_port_listen_allows_long_startup_when_process_still_alive(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(app_main, "_check_port", lambda port: True)

    proc = SimpleNamespace(poll=lambda: None)

    assert _wait_for_port_listen(3000, timeout=0.01, proc=proc) is True


def test_check_port_treats_system_listener_as_occupied(monkeypatch: pytest.MonkeyPatch):
    class DummySocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def settimeout(self, timeout):
            return None

        def connect(self, address):
            raise ConnectionRefusedError

    monkeypatch.setattr(app_main.shutil, "which", lambda name: "/usr/bin/lsof" if name == "lsof" else None)
    monkeypatch.setattr(app_main.socket, "socket", lambda *args, **kwargs: DummySocket())
    monkeypatch.setattr(
        app_main.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    assert _check_port(3000) is False


def test_terminate_managed_process_uses_taskkill_on_windows(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, object]] = []

    class DummyProc:
        pid = 4321

        def __init__(self):
            self._poll_calls = 0

        def poll(self):
            self._poll_calls += 1
            return None if self._poll_calls == 1 else 0

        def send_signal(self, sig):
            calls.append(("send_signal", sig))

        def wait(self, timeout):
            raise app_main.subprocess.TimeoutExpired(cmd="dummy", timeout=timeout)

    proc = DummyProc()

    monkeypatch.setattr(app_main.os, "name", "nt")
    monkeypatch.setattr(
        app_main.subprocess,
        "run",
        lambda cmd, stdout, stderr, check: calls.append(("taskkill", cmd)),
    )

    _terminate_managed_process(proc, timeout=0.01)

    assert ("taskkill", ["taskkill", "/PID", "4321", "/T", "/F"]) in calls
