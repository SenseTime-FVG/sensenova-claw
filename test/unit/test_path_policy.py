"""P01-P04: PathPolicy + deny_list"""
import platform
import pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict, PathZone


class TestPathPolicy:
    def test_green_zone(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_write("notes.md") == PathVerdict.ALLOW

    def test_red_zone_need_grant(self, tmp_workspace, tmp_path):
        d = tmp_path / "other"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_write(str(d / "f.py")) == PathVerdict.NEED_GRANT

    def test_red_zone_system_deny(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows\\System32" if platform.system() == "Windows" else "/etc/passwd"
        assert p.check_read(target) == PathVerdict.DENY

    def test_yellow_after_grant(self, tmp_workspace, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        assert p.check_write(str(d / "m.py")) == PathVerdict.ALLOW

    def test_grant_system_rejected(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows" if platform.system() == "Windows" else "/etc"
        with pytest.raises(ValueError):
            p.grant(target)

    def test_revoke(self, tmp_workspace, tmp_path):
        d = tmp_path / "rv"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        p.revoke(str(d))
        assert p.check_read(str(d / "f")) == PathVerdict.NEED_GRANT

    def test_relative_escape(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_read("../../etc/passwd") in (PathVerdict.NEED_GRANT, PathVerdict.DENY)

    def test_classify(self, tmp_workspace, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace, granted_paths=[str(d)])
        assert p.classify(tmp_workspace / "f") == PathZone.GREEN
        assert p.classify(d / "f") == PathZone.YELLOW
        assert p.classify(tmp_path / "x" / "f") == PathZone.RED

    def test_safe_resolve_absolute(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        abs_path = str(tmp_workspace / "a.txt")
        resolved = p.safe_resolve(abs_path)
        assert resolved == Path(abs_path).resolve()

    def test_safe_resolve_relative(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        resolved = p.safe_resolve("a.txt")
        assert resolved == (tmp_workspace / "a.txt").resolve()

    def test_granted_paths_property(self, tmp_workspace, tmp_path):
        d = tmp_path / "gp"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        assert str(d.resolve()) in p.granted_paths
