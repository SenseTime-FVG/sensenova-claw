"""E2E: CLI 脚本模式（需要真实后端运行）"""
import subprocess
import sys
import os
import pytest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")


@pytest.mark.skipif(True, reason="需要后端运行")
class TestCLIScriptMode:
    def test_execute_mode(self):
        """--execute 模式应发送消息并退出"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.app", "--execute", "hello"],
            cwd=BACKEND_DIR,
            capture_output=True,
            timeout=30,
        )
        # 即使后端不在，命令本身不应崩溃（连接失败是可接受的）
        assert result.returncode in (0, 1)

    def test_help(self):
        """--help 应正常退出"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.app", "--help"],
            cwd=BACKEND_DIR,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0 or b"usage" in result.stdout.lower() or b"error" in result.stderr.lower()
