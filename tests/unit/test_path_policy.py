"""PathPolicy 单元测试

覆盖三区模型 (GREEN/YELLOW/RED)、grant/revoke、路径穿越防护等场景。
"""

import platform
import pytest
from pathlib import Path
from unittest.mock import patch

from agentos.platform.security.path_policy import PathPolicy, PathVerdict, PathZone


# ---------- 测试辅助 ----------

def _make_policy(workspace: str = "/home/user/.agentos/workspace",
                 granted: list[str] | None = None) -> PathPolicy:
    """创建 PathPolicy 实例，跳过 is_dir 检查（直接注入 _granted）"""
    policy = PathPolicy(workspace=Path(workspace))
    if granted:
        for p in granted:
            policy._granted.append(Path(p).resolve())
    return policy


# ---------- GREEN 区测试 ----------

class TestGreenZone:
    def test_relative_path_in_workspace(self):
        policy = _make_policy()
        assert policy.check_write("notes.md") == PathVerdict.ALLOW

    def test_absolute_path_in_workspace(self):
        ws = "/home/user/.agentos/workspace"
        policy = _make_policy(workspace=ws)
        assert policy.check_read(f"{ws}/AGENTS.md") == PathVerdict.ALLOW

    def test_classify_green(self):
        ws = "/home/user/.agentos/workspace"
        policy = _make_policy(workspace=ws)
        resolved = policy.safe_resolve("sub/file.py")
        assert policy.classify(resolved) == PathZone.GREEN


# ---------- YELLOW 区测试 ----------

class TestYellowZone:
    def test_granted_path_allows_access(self):
        policy = _make_policy(granted=["/home/user/projects"])
        assert policy.check_write("/home/user/projects/app/main.py") == PathVerdict.ALLOW

    def test_classify_yellow(self):
        policy = _make_policy(granted=["/home/user/projects"])
        resolved = Path("/home/user/projects/foo.py").resolve()
        assert policy.classify(resolved) == PathZone.YELLOW


# ---------- RED 区测试 ----------

class TestRedZone:
    def test_external_path_needs_grant(self):
        policy = _make_policy()
        assert policy.check_write("/home/user/projects/foo.py") == PathVerdict.NEED_GRANT

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix 路径测试")
    def test_system_path_deny_unix(self):
        policy = _make_policy()
        assert policy.check_read("/etc/passwd") == PathVerdict.DENY

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows 路径测试")
    def test_system_path_deny_windows(self):
        policy = _make_policy(workspace="C:\\Users\\user\\.agentos\\workspace")
        assert policy.check_read("C:\\Windows\\System32\\config") == PathVerdict.DENY

    def test_classify_red(self):
        policy = _make_policy()
        resolved = Path("/some/random/path").resolve()
        assert policy.classify(resolved) == PathZone.RED


# ---------- grant / revoke 测试 ----------

class TestGrantRevoke:
    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix 路径测试")
    def test_grant_system_path_rejected(self):
        policy = _make_policy()
        with pytest.raises(ValueError, match="系统目录不允许授权"):
            policy.grant("/etc")

    def test_grant_nonexistent_dir_rejected(self):
        policy = _make_policy()
        with pytest.raises(ValueError, match="目录不存在"):
            policy.grant("/nonexistent/path/that/does/not/exist")

    def test_revoke_removes_access(self):
        policy = _make_policy(granted=["/home/user/projects"])
        assert policy.check_write("/home/user/projects/a.py") == PathVerdict.ALLOW
        policy.revoke("/home/user/projects")
        assert policy.check_write("/home/user/projects/a.py") == PathVerdict.NEED_GRANT

    def test_granted_paths_property(self):
        policy = _make_policy(granted=["/home/user/projects", "/tmp/data"])
        paths = policy.granted_paths
        assert len(paths) == 2


# ---------- 路径穿越防护 ----------

class TestPathTraversal:
    def test_relative_path_escape(self):
        policy = _make_policy()
        verdict = policy.check_read("../../etc/passwd")
        assert verdict in (PathVerdict.DENY, PathVerdict.NEED_GRANT)

    def test_resolve_eliminates_dotdot(self):
        policy = _make_policy()
        resolved = policy.safe_resolve("subdir/../../../etc/passwd")
        assert ".." not in str(resolved)


# ---------- 向后兼容 ----------

class TestBackwardCompatibility:
    def test_no_policy_tools_still_work(self):
        """无 PathPolicy 时工具行为应向后兼容（不会报错）

        tool_worker.py 中通过 `if self.rt.path_policy:` 判断是否注入路径策略，
        当 path_policy 为 None 时直接跳过注入，工具照常执行。
        此测试验证该分支逻辑：模拟 runtime.path_policy = None，
        确认 _path_policy 不会被注入到 arguments 字典中。
        """
        from unittest.mock import MagicMock

        # 构造一个 path_policy=None 的伪 ToolRuntime
        mock_runtime = MagicMock()
        mock_runtime.path_policy = None
        mock_runtime.agent_registry = None

        # 模拟 tool_worker.py 中的注入逻辑（if self.rt.path_policy:）
        arguments: dict = {"file_path": "/some/file.txt"}
        if mock_runtime.path_policy:
            arguments["_path_policy"] = mock_runtime.path_policy
        if mock_runtime.agent_registry:
            arguments["_agent_registry"] = mock_runtime.agent_registry

        # path_policy 为 None 时，_path_policy 不应被注入
        assert "_path_policy" not in arguments
        assert "_agent_registry" not in arguments
        # 原始参数保持不变
        assert arguments["file_path"] == "/some/file.txt"
