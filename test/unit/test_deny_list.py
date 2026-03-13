"""P04: deny_list 系统目录"""
import platform
from pathlib import Path
from app.security.deny_list import is_system_path


class TestDenyList:
    def test_system_paths_denied(self):
        if platform.system() == "Windows":
            assert is_system_path(Path("C:\\Windows\\System32")) is True
            assert is_system_path(Path("C:\\Program Files\\test")) is True
        else:
            assert is_system_path(Path("/etc/passwd")) is True
            assert is_system_path(Path("/usr/bin/python")) is True
            assert is_system_path(Path("/proc/1")) is True

    def test_normal_paths_allowed(self, tmp_path):
        assert is_system_path(tmp_path) is False
        assert is_system_path(tmp_path / "test.py") is False

    def test_home_allowed(self):
        assert is_system_path(Path.home()) is False

    def test_workspace_allowed(self, tmp_workspace):
        assert is_system_path(tmp_workspace) is False
        assert is_system_path(tmp_workspace / "notes.md") is False
