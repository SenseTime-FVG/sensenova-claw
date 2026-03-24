"""path_rewriter 单元测试：验证 assistant 回复中相对路径自动转绝对路径"""

import platform
import tempfile
from pathlib import Path
from sensenova_claw.kernel.runtime.path_rewriter import rewrite_relative_paths, _looks_like_relative_file_path


class TestLooksLikeRelativeFilePath:
    def test_simple_file(self):
        assert _looks_like_relative_file_path("report.md") is True

    def test_nested_relative(self):
        assert _looks_like_relative_file_path("output/data.csv") is True

    def test_dot_relative(self):
        assert _looks_like_relative_file_path("./result.json") is True

    def test_absolute_unix(self):
        assert _looks_like_relative_file_path("/home/user/file.txt") is False

    def test_absolute_windows(self):
        assert _looks_like_relative_file_path("C:/Users/test/file.txt") is False

    def test_tilde_path(self):
        assert _looks_like_relative_file_path("~/.sensenova-claw/config.yml") is False

    def test_url(self):
        assert _looks_like_relative_file_path("https://example.com/file.txt") is False

    def test_pure_word(self):
        assert _looks_like_relative_file_path("hello") is False

    def test_code_snippet(self):
        assert _looks_like_relative_file_path("print('hello')") is False

    def test_no_extension_but_has_separator(self):
        assert _looks_like_relative_file_path("output/data") is False

    def test_unknown_extension(self):
        assert _looks_like_relative_file_path("file.xyz123") is False

    def test_empty(self):
        assert _looks_like_relative_file_path("") is False


class TestRewriteRelativePaths:
    """使用真实临时目录做 workdir，避免 Windows resolve() 加盘符导致路径不匹配"""

    @staticmethod
    def _workdir() -> str:
        return str(Path(tempfile.gettempdir()).resolve() / "sensenova_claw_test_workdir")

    def test_rewrites_simple_file(self):
        wd = self._workdir()
        text = "文件已保存到 `report.md`"
        result = rewrite_relative_paths(text, wd)
        assert "report.md" in result
        assert wd.replace("\\", "/") in result

    def test_rewrites_nested_path(self):
        wd = self._workdir()
        text = "结果在 `output/data.csv` 中"
        result = rewrite_relative_paths(text, wd)
        expected = f"{wd}/output/data.csv".replace("\\", "/")
        assert expected in result

    def test_preserves_absolute_path(self):
        wd = self._workdir()
        if platform.system() == "Windows":
            text = "文件在 `C:/Windows/config.yml` 中"
            result = rewrite_relative_paths(text, wd)
            assert "C:/Windows/config.yml" in result
        else:
            text = "文件在 `/etc/config.yml` 中"
            result = rewrite_relative_paths(text, wd)
            assert "`/etc/config.yml`" in result

    def test_preserves_tilde_path(self):
        wd = self._workdir()
        text = "配置在 `~/.sensenova-claw/config.yml`"
        result = rewrite_relative_paths(text, wd)
        assert "`~/.sensenova-claw/config.yml`" in result

    def test_preserves_url(self):
        wd = self._workdir()
        text = "参考 `https://example.com/doc.md`"
        result = rewrite_relative_paths(text, wd)
        assert "`https://example.com/doc.md`" in result

    def test_preserves_code_snippet(self):
        wd = self._workdir()
        text = "运行 `python main.py` 来启动"
        result = rewrite_relative_paths(text, wd)
        assert "`" in result

    def test_preserves_non_file_code(self):
        wd = self._workdir()
        text = "使用 `json.loads(data)` 解析"
        result = rewrite_relative_paths(text, wd)
        assert "`json.loads(data)`" in result

    def test_empty_content(self):
        assert rewrite_relative_paths("", self._workdir()) == ""

    def test_no_backticks(self):
        wd = self._workdir()
        text = "这段文字没有代码引用"
        assert rewrite_relative_paths(text, wd) == text

    def test_empty_workdir(self):
        text = "文件在 `report.md`"
        assert rewrite_relative_paths(text, "") == text

    def test_multiple_paths(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = "生成了 `report.md` 和 `data/output.csv`"
        result = rewrite_relative_paths(text, wd)
        assert f"`{wd_fwd}/report.md`" in result
        assert f"`{wd_fwd}/data/output.csv`" in result

    def test_dot_slash_prefix(self):
        wd = self._workdir()
        text = "保存到 `./output.md`"
        result = rewrite_relative_paths(text, wd)
        wd_fwd = wd.replace("\\", "/")
        assert wd_fwd in result
        assert "output.md" in result
