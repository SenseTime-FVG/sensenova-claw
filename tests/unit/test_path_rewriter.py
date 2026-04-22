"""path_rewriter 单元测试：验证 assistant 回复中相对路径自动转绝对路径"""

import platform
import tempfile
from pathlib import Path
from urllib.parse import quote

from sensenova_claw.kernel.runtime.path_rewriter import (
    _is_absolute_pathlike,
    _looks_like_relative_file_path,
    rewrite_file_link_hrefs,
    rewrite_relative_paths,
)


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


class TestIsAbsolutePathlike:
    """不依赖运行平台的绝对路径判定。"""

    def test_posix_absolute(self):
        assert _is_absolute_pathlike("/sandbox/foo.md") is True

    def test_backslash_root(self):
        assert _is_absolute_pathlike("\\share\\foo") is True

    def test_windows_drive(self):
        assert _is_absolute_pathlike("C:\\Users\\a.md") is True
        assert _is_absolute_pathlike("D:/tmp/a.md") is True

    def test_tilde(self):
        assert _is_absolute_pathlike("~/report.md") is True

    def test_relative_simple(self):
        assert _is_absolute_pathlike("report.md") is False

    def test_relative_nested(self):
        assert _is_absolute_pathlike("sub/a.md") is False

    def test_relative_dotdot(self):
        assert _is_absolute_pathlike("../escape.md") is False

    def test_empty(self):
        assert _is_absolute_pathlike("") is False


class TestRewriteFileLinkHrefs:
    """覆盖 LLM 在 [text](#sensenova-claw-file:PATH) 里写相对路径的场景。"""

    @staticmethod
    def _workdir() -> str:
        return str(Path(tempfile.gettempdir()).resolve() / "sensenova_claw_test_workdir")

    def test_rewrites_bare_filename(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = "已生成文件：[自我介绍.md](#sensenova-claw-file:自我介绍.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert f"(#sensenova-claw-file:{wd_fwd}/自我介绍.md)" in result

    def test_rewrites_dot_slash_prefix(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = "[report](#sensenova-claw-file:./out/report.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert f"(#sensenova-claw-file:{wd_fwd}/out/report.md)" in result

    def test_preserves_absolute_posix(self):
        wd = self._workdir()
        text = "[x](#sensenova-claw-file:/sandbox/.sensenova-claw/workdir/default/x.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert result == text

    def test_preserves_absolute_windows_drive(self):
        wd = self._workdir()
        text = r"[x](#sensenova-claw-file:C:\Users\alice\x.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert result == text

    def test_preserves_tilde(self):
        wd = self._workdir()
        text = "[x](#sensenova-claw-file:~/Documents/x.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert result == text

    def test_handles_url_encoded_chinese(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        encoded = quote("自我介绍.md", safe="")
        text = f"[x](#sensenova-claw-file:{encoded})"
        result = rewrite_file_link_hrefs(text, wd)
        # 输出恢复成原始中文，前端 decodeURIComponent 仍能正常打开
        assert f"(#sensenova-claw-file:{wd_fwd}/自我介绍.md)" in result

    def test_handles_backslash_relative(self):
        """Windows 风格反斜杠相对路径：统一转正斜杠。"""
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = r"[x](#sensenova-claw-file:sub\dir\x.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert f"(#sensenova-claw-file:{wd_fwd}/sub/dir/x.md)" in result

    def test_normalizes_dotdot(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = "[x](#sensenova-claw-file:sub/../x.md)"
        result = rewrite_file_link_hrefs(text, wd)
        assert f"(#sensenova-claw-file:{wd_fwd}/x.md)" in result

    def test_empty_workdir_keeps_original(self):
        """agent 在开发机/非沙箱场景可能没有 workdir，不得误改。"""
        text = "[x](#sensenova-claw-file:report.md)"
        assert rewrite_file_link_hrefs(text, "") == text
        assert rewrite_file_link_hrefs(text, None) == text  # type: ignore[arg-type]

    def test_empty_content(self):
        assert rewrite_file_link_hrefs("", self._workdir()) == ""

    def test_empty_href_left_as_is(self):
        wd = self._workdir()
        text = "[x](#sensenova-claw-file:)"
        assert rewrite_file_link_hrefs(text, wd) == text

    def test_ignores_workdir_prefix_link(self):
        """#sensenova-claw-workdir: 前端要求相对路径，不能改写。"""
        wd = self._workdir()
        text = "[slides](#sensenova-claw-workdir:my-ppt/page_01.html)"
        assert rewrite_file_link_hrefs(text, wd) == text

    def test_leaves_plain_markdown_link_untouched(self):
        wd = self._workdir()
        text = "参考 [repo](https://github.com/foo/bar) 和 [doc](./a.md)"
        assert rewrite_file_link_hrefs(text, wd) == text

    def test_multiple_links_in_one_message(self):
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = (
            "[a.md](#sensenova-claw-file:a.md) 和 "
            "[b.md](#sensenova-claw-file:sub/b.md)"
        )
        result = rewrite_file_link_hrefs(text, wd)
        assert f"(#sensenova-claw-file:{wd_fwd}/a.md)" in result
        assert f"(#sensenova-claw-file:{wd_fwd}/sub/b.md)" in result

    def test_combined_with_code_span_rewrite(self):
        """两个函数串联：inline code + link href 各管一边。"""
        wd = self._workdir()
        wd_fwd = wd.replace("\\", "/")
        text = (
            "已生成 [自我介绍.md](#sensenova-claw-file:自我介绍.md)\n"
            "位置: `自我介绍.md`"
        )
        step1 = rewrite_relative_paths(text, wd)
        step2 = rewrite_file_link_hrefs(step1, wd)
        assert f"`{wd_fwd}/自我介绍.md`" in step2
        assert f"(#sensenova-claw-file:{wd_fwd}/自我介绍.md)" in step2
