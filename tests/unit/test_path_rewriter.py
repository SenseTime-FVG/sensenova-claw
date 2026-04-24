"""path_rewriter 单元测试：验证 assistant 回复中相对路径自动转绝对路径"""

import platform
import tempfile
from pathlib import Path
from urllib.parse import quote

from sensenova_claw.kernel.runtime.path_rewriter import (
    _is_absolute_pathlike,
    _join_and_normalize,
    _looks_like_relative_file_path,
    _normalize_workdir,
    _split_drive,
    encode_file_link_parens,
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


class TestSplitDrive:
    def test_forward_slash_drive(self):
        assert _split_drive("C:/foo") == ("C:", "/foo")

    def test_backslash_drive(self):
        assert _split_drive("D:\\foo\\bar") == ("D:", "\\foo\\bar")

    def test_no_drive_posix(self):
        assert _split_drive("/home/user") == ("", "/home/user")

    def test_no_drive_relative(self):
        assert _split_drive("foo/bar") == ("", "foo/bar")

    def test_colon_without_separator_not_drive(self):
        # `C:foo` 这种无分隔符形式不当作盘符（和 _is_absolute_pathlike 一致）
        assert _split_drive("C:foo") == ("", "C:foo")

    def test_empty(self):
        assert _split_drive("") == ("", "")


class TestNormalizeWorkdir:
    def test_posix_absolute_unchanged(self):
        # 即使在 Windows 宿主跑到这里，也不得拼当前盘符
        assert _normalize_workdir("/home/user/work") == "/home/user/work"

    def test_windows_drive_forward_slash(self):
        assert _normalize_workdir("C:/sandbox/work") == "C:/sandbox/work"

    def test_windows_drive_backslash(self):
        assert _normalize_workdir("C:\\sandbox\\work") == "C:/sandbox/work"

    def test_empty(self):
        assert _normalize_workdir("") == ""

    def test_dotdot_normalized(self):
        assert _normalize_workdir("C:/sandbox/../work") == "C:/work"

    def test_trailing_slash_trimmed(self):
        # posixpath.normpath 会去掉尾部 /（保留根目录 / 本身）
        assert _normalize_workdir("/a/b/") == "/a/b"


class TestJoinAndNormalize:
    """核心断言：Windows 盘符不能被 .. 吃掉。"""

    def test_simple_join_posix(self):
        assert _join_and_normalize("/sandbox", "a.md") == "/sandbox/a.md"

    def test_simple_join_windows(self):
        assert _join_and_normalize("C:/sandbox", "a.md") == "C:/sandbox/a.md"

    def test_dotdot_stops_at_root_posix(self):
        # POSIX 根目录上 .. 不会退出根
        assert _join_and_normalize("/sandbox", "../../../a.md") == "/a.md"

    def test_dotdot_stops_at_drive_root_windows(self):
        # 关键 Bug A 回归：.. 越界应停在盘符根，而不是把盘符吃掉
        result = _join_and_normalize("C:/sandbox", "../../../Windows/System32/x.txt")
        assert result == "C:/Windows/System32/x.txt"
        # 对比 posixpath.normpath 原生行为（会退化成 "Windows/System32/x.txt"）
        assert result.startswith("C:")

    def test_backslash_relative_normalized(self):
        # Bug C：反斜杠形式的相对路径要归一
        assert _join_and_normalize("/sandbox", "sub\\dir\\a.md") == "/sandbox/sub/dir/a.md"

    def test_backslash_relative_with_drive(self):
        assert (
            _join_and_normalize("C:/sandbox", "sub\\dir\\a.md")
            == "C:/sandbox/sub/dir/a.md"
        )

    def test_dot_slash_prefix(self):
        assert _join_and_normalize("/sandbox", "./a.md") == "/sandbox/a.md"

    def test_nested_dotdot_inside_workdir(self):
        # workdir 内合法的 .. 仍然能走
        assert _join_and_normalize("/sandbox/a/b", "../c.md") == "/sandbox/a/c.md"


class TestRewriteFileLinkHrefsWindows:
    """Bug A/C/D 在 file link 场景下的回归。"""

    def test_dotdot_cannot_eat_windows_drive(self):
        """Bug A：.. 越界时盘符必须保留。"""
        text = "[x](#sensenova-claw-file:../../../Windows/System32/x.txt)"
        result = rewrite_file_link_hrefs(text, "C:/sandbox")
        assert "(#sensenova-claw-file:C:/Windows/System32/x.txt)" in result
        # 保证输出没有退化成相对路径
        assert "(#sensenova-claw-file:Windows/" not in result

    def test_backslash_workdir_input(self):
        """Bug D：workdir 传入 Windows 反斜杠形式也能正常归一。"""
        text = "[x](#sensenova-claw-file:a.md)"
        result = rewrite_file_link_hrefs(text, "C:\\sandbox\\work")
        assert "(#sensenova-claw-file:C:/sandbox/work/a.md)" in result

    def test_posix_workdir_not_prefixed_with_drive(self):
        """Bug D：宿主是 Windows 时，传入 POSIX 风格 workdir 也不该被拼盘符。

        模拟：_normalize_workdir 直接走字符串归一分支。
        """
        text = "[x](#sensenova-claw-file:a.md)"
        result = rewrite_file_link_hrefs(text, "/home/user/work")
        assert "(#sensenova-claw-file:/home/user/work/a.md)" in result
        # 不应出现任何 <letter>: 盘符前缀
        import re as _re
        assert not _re.search(r"#sensenova-claw-file:[A-Za-z]:", result)

    def test_dotdot_cannot_escape_posix_root(self):
        """越界回退到 POSIX 根，不影响下游白名单。"""
        text = "[x](#sensenova-claw-file:../../../etc/passwd)"
        result = rewrite_file_link_hrefs(text, "/sandbox/work")
        # 退到根目录，但不丢前导 /
        assert "(#sensenova-claw-file:/etc/passwd)" in result


class TestEncodeFileLinkParens:
    """Bug B：Windows 路径中未转义的 () 必须被编码，避免 markdown 截断。"""

    def test_program_files_x86(self):
        text = "[foo](#sensenova-claw-file:C:/Program Files (x86)/foo.md)"
        result = encode_file_link_parens(text)
        assert (
            "[foo](#sensenova-claw-file:C:/Program Files %28x86%29/foo.md)" in result
        )

    def test_no_parens_no_change(self):
        text = "[foo](#sensenova-claw-file:/sandbox/a.md)"
        assert encode_file_link_parens(text) == text

    def test_multiple_file_links(self):
        text = (
            "[a](#sensenova-claw-file:a.md) 和 "
            "[b](#sensenova-claw-file:Files (x86)/b.md)"
        )
        result = encode_file_link_parens(text)
        assert "[a](#sensenova-claw-file:a.md)" in result
        assert "[b](#sensenova-claw-file:Files %28x86%29/b.md)" in result

    def test_workdir_prefix_not_touched(self):
        # 只编码 file 前缀，workdir 前缀维持原样
        text = "[slides](#sensenova-claw-workdir:my-ppt (draft)/page.html)"
        assert encode_file_link_parens(text) == text

    def test_plain_link_not_touched(self):
        text = "参考 [wiki](https://en.wikipedia.org/wiki/Foo_(bar))"
        assert encode_file_link_parens(text) == text

    def test_combined_with_rewrite(self):
        """关键场景：含括号的 Windows 路径能完整走完 encode → rewrite 链路。"""
        text = "[报告](#sensenova-claw-file:Program Files (x86)/report.md)"
        step1 = encode_file_link_parens(text)
        step2 = rewrite_file_link_hrefs(step1, "C:/sandbox")
        assert (
            "(#sensenova-claw-file:C:/sandbox/Program Files %28x86%29/report.md)"
            in step2
        )

    def test_empty_content(self):
        assert encode_file_link_parens("") == ""


class TestRewriteRelativePathsWindows:
    """inline code span 的跨平台路径回归。"""

    def test_backslash_relative_in_posix_workdir(self):
        """Bug C：POSIX 后端处理 Windows 风格反斜杠路径也要归一。"""
        wd = "/sandbox/work"
        text = "结果在 `docs\\report.md`"
        result = rewrite_relative_paths(text, wd)
        assert "`/sandbox/work/docs/report.md`" in result

    def test_drive_root_escape_stops_at_drive(self):
        """Bug A：inline code span 的 .. 越界同样要保留盘符。"""
        wd = "C:/sandbox"
        text = "这个文件 `../../../Windows/System32/x.txt`"
        result = rewrite_relative_paths(text, wd)
        # 由于 () 被排除在"路径样"判定外，这里用简单的 ../ 链
        # _looks_like_relative_file_path 会识别 .txt → 触发改写
        assert "`C:/Windows/System32/x.txt`" in result

    def test_posix_workdir_on_windows_host(self):
        """Bug D：用 POSIX 风格 workdir 不应被拼盘符。"""
        wd = "/home/user/work"
        text = "文件在 `report.md`"
        result = rewrite_relative_paths(text, wd)
        assert "`/home/user/work/report.md`" in result
