from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

from agentos.app.main import _spawn_managed_process, _terminate_managed_process


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
