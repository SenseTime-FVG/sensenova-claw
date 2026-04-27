"""Assistant 消息中的相对路径 → 绝对路径后处理。

模型在回复用户时经常使用相对路径（如 `report.md`、`./output/data.csv`），
用户看到后无法直接定位文件。此模块在发送给前端之前，将文本中可识别的
相对路径改写为基于 agent workdir 的绝对路径。

跨平台注意：LLM 与后端运行宿主的平台组合是正交的（Windows 后端处理
POSIX 路径、Linux 后端处理 Windows 路径都要兼容），因此本模块不依赖
``pathlib.Path`` 的运行时平台行为，统一以正斜杠 + 手写盘符处理为规范。
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote


# 匹配 Markdown 行内代码 `...` 中包含的文件路径
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")

# 匹配 [text](#sensenova-claw-file:PATH) 形式的文件链接。
# PATH 允许包含一层 ``(...)`` 嵌套（典型例子：``C:\Program Files (x86)\foo.md``），
# 再深的嵌套在实际路径里极罕见，且 markdown 规范本身也要求 URL 里对 ``)`` 做转义。
_FILE_LINK_RE = re.compile(
    r"(\]\(#sensenova-claw-file:)"
    r"((?:[^)(]|\([^)(]*\))*)"
    r"(\))"
)

# 匹配普通 Markdown 链接，用于把 ``[报告](/tmp/report.md)`` 这类本地
# 绝对路径链接转成前端可拦截的 ``#sensenova-claw-file:`` 链接。
_MARKDOWN_LINK_RE = re.compile(
    r"(\[[^\]]+?\]\()"
    r"((?:[^)(]|\([^)(]*\))*)"
    r"(\))"
)

# 常见文件扩展名，用于判定是否像一个文件路径
_FILE_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".jsonl", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz",
    ".sh", ".bash", ".bat", ".ps1", ".log", ".xml", ".toml",
    ".env", ".cfg", ".ini", ".sql", ".r", ".ipynb",
}


def _is_absolute_pathlike(text: str) -> bool:
    """跨平台判断路径是否已是绝对形式。

    不依赖 ``Path.is_absolute()`` 的运行时平台行为：
    - POSIX 上 ``PurePath('C:\\foo').is_absolute()`` 会返回 False
    - Windows 上 ``PurePath('/a').is_absolute()`` 会返回 False
    我们需要一个对两端输入都正确的判断（agent 可能在 Linux 沙箱跑，
    也可能在开发机 Windows 跑；LLM 的输出平台无关）。
    """
    if not text:
        return False
    if text[0] in ("/", "\\"):
        return True
    # 视 ``~`` 起始为用户显式引用，不再二次解析
    if text.startswith("~"):
        return True
    # Windows 盘符: C:\foo  或  C:/foo
    if (
        len(text) >= 3
        and text[0].isalpha()
        and text[1] == ":"
        and text[2] in ("/", "\\")
    ):
        return True
    return False


def _split_drive(text: str) -> tuple[str, str]:
    """分离 Windows 盘符前缀，返回 ``(drive, rest)``。

    - ``"C:/foo"`` → ``("C:", "/foo")``
    - ``"C:\\foo"`` → ``("C:", "/foo")``（调用方应先做反斜杠归一）
    - ``"/foo"``   → ``("", "/foo")``
    - ``"foo"``    → ``("", "foo")``

    仅识别 ``<letter>:/`` 或 ``<letter>:\\`` 形式。``C:relative`` 这种
    无分隔符的 Windows 旧式写法（极罕见）不视为盘符，保持和
    ``_is_absolute_pathlike`` 一致。
    """
    if (
        len(text) >= 3
        and text[0].isalpha()
        and text[1] == ":"
        and text[2] in ("/", "\\")
    ):
        return text[:2], text[2:]
    return "", text


def _join_and_normalize(workdir_abs: str, relative: str) -> str:
    """拼接绝对 workdir 与相对路径并规范化 ``.``/``..``。

    关键差异 vs. ``posixpath.normpath("C:/sandbox/../../x")``:
    - ``posixpath`` 不认识 ``C:``，会把盘符当作一级目录被 ``..`` 吃掉，
      得到 ``"x"`` — 盘符丢失，语义错乱，还可能绕过下游路径白名单。
    - 此函数先剥离盘符，对剩余部分以 ``/`` 为根做规范化，``..`` 最多
      退到盘符根（``"/"``），然后拼回盘符前缀。

    假设 ``workdir_abs`` 已经过 ``_normalize_workdir`` 处理：使用正斜杠、
    盘符形如 ``"C:"``、根以 ``/`` 起始。``relative`` 可以含反斜杠，内部
    统一转正斜杠。
    """
    drive, root = _split_drive(workdir_abs)
    if not root.startswith("/"):
        # workdir 已被 _normalize_workdir 保证绝对，这里是兜底
        root = "/" + root
    rel = relative.replace("\\", "/")
    joined = posixpath.join(root, rel)
    normalized = posixpath.normpath(joined)
    return drive + normalized


def _normalize_workdir(workdir: str) -> str:
    """把 workdir 归一为正斜杠绝对路径，且不依赖宿主 Path 的平台行为。

    - 若 ``workdir`` 已是绝对路径（POSIX / Windows 盘符 / UNC ``\\\\server``），
      直接做字符串归一，**不调用 ``Path.resolve()``**。这能避免 Windows
      宿主处理 ``/home/user/work`` 时被当作"当前盘符下的目录"拼出
      ``C:\\home\\user\\work`` 的错误。
    - ``~`` 用 ``os.path.expanduser`` 展开（POSIX 上展开为 ``$HOME``，
      Windows 上展开为用户 Profile）。
    - 相对 workdir（少见；通常来自配置误写）仍走 ``Path.resolve()`` 拼
      当前 CWD —— 这部分行为无法跨平台做得比宿主 Path 更好。
    """
    if not workdir:
        return ""
    expanded = os.path.expanduser(workdir)
    if _is_absolute_pathlike(expanded):
        unified = expanded.replace("\\", "/")
        drive, rest = _split_drive(unified)
        if not rest.startswith("/"):
            rest = "/" + rest
        return drive + posixpath.normpath(rest)
    # 相对路径：只能依赖宿主解析
    try:
        return str(Path(expanded).resolve()).replace("\\", "/")
    except (OSError, ValueError):
        return expanded.replace("\\", "/")


def _looks_like_relative_file_path(text: str) -> bool:
    """判断 text 是否看起来像一个相对文件路径（而非代码片段、URL、命令等）。"""
    text = text.strip()
    if not text:
        return False
    # 排除 URL
    if text.startswith(("http://", "https://", "ftp://", "data:")):
        return False
    # 排除已是绝对路径（Unix / Windows）
    if _is_absolute_pathlike(text):
        return False
    # 判断扩展名时先归一反斜杠，避免 ``docs\a.md`` 在 POSIX 上被拆不出后缀
    unified = text.replace("\\", "/")
    # 获取扩展名
    suffix = posixpath.splitext(unified)[1].lower()
    # 必须有已知扩展名才认定为文件路径
    if not suffix or suffix not in _FILE_EXTENSIONS:
        return False
    # 排除太长的字符串（不太像路径）
    if len(text) > 200:
        return False
    # 排除含有明显非路径字符（注意：``(`` / ``)`` 在 Windows 路径中合法，
    # 此处扫描的是 inline code span，里面若出现括号更可能是代码调用，
    # 因此仍保留排除）
    if any(c in text for c in ("(", ")", "{", "}", "<", ">", "|", ";", "&", "=", "?")):
        return False
    return True


def _looks_like_absolute_path_reference(text: str) -> bool:
    """判断 text 是否像本地绝对路径引用，供前端文件链接改写使用。"""
    text = text.strip()
    if not text:
        return False
    if text.startswith(("http://", "https://", "ftp://", "data:", "mailto:")):
        return False
    if not _is_absolute_pathlike(text):
        return False
    if len(text) > 300:
        return False
    if any(c in text for c in ("{", "}", "<", ">", "|", ";", "&", "=")):
        return False
    unified = text.replace("\\", "/")
    suffix = posixpath.splitext(unified)[1].lower()
    if suffix in _FILE_EXTENSIONS:
        return True
    # 目录型引用只在行内代码或 Markdown 链接中改写，范围较窄，可以接受。
    return unified.startswith(("/tmp", "/var/folders", "~/")) or bool(re.match(r"^[A-Za-z]:/", unified))


def _encode_file_link_path(path: str) -> str:
    return (
        path.replace("\\", "/")
            .replace("(", "%28")
            .replace(")", "%29")
    )


def rewrite_relative_paths(content: str, workdir: str) -> str:
    """将 assistant 回复文本中 `...` 引用的相对路径改写为绝对路径。

    仅处理 Markdown 行内代码块 `...` 中的内容，避免误改自然语言。
    内部统一走 ``_join_and_normalize``，保证与 ``rewrite_file_link_hrefs``
    在跨平台场景下的输出一致。
    """
    if not content or not workdir:
        return content

    workdir_abs = _normalize_workdir(workdir)
    if not workdir_abs:
        return content

    def _replace(match: re.Match) -> str:
        raw = match.group(1)
        if not _looks_like_relative_file_path(raw):
            return match.group(0)
        abs_path = _join_and_normalize(workdir_abs, raw.strip())
        return f"`{abs_path}`"

    return _CODE_SPAN_RE.sub(_replace, content)


def rewrite_absolute_path_references(content: str) -> str:
    """将本地绝对路径引用改写为前端可点击的内部文件链接。

    覆盖两类常见 LLM 输出：
    - 普通 Markdown 链接：``[报告](/tmp/report.md)``
    - 行内代码路径：`` `/tmp/report.md` ``
    """
    if not content:
        return content

    def _replace_link(match: re.Match) -> str:
        prefix = match.group(1)
        raw_href = match.group(2).strip()
        suffix = match.group(3)
        try:
            decoded = unquote(raw_href)
        except Exception:
            decoded = raw_href
        if decoded.startswith(("#sensenova-claw-file:", "#sensenova-claw-workdir:")):
            return match.group(0)
        if not _looks_like_absolute_path_reference(decoded):
            return match.group(0)
        return f"{prefix}#sensenova-claw-file:{_encode_file_link_path(decoded)}{suffix}"

    content = _MARKDOWN_LINK_RE.sub(_replace_link, content)

    def _replace_code(match: re.Match) -> str:
        start, end = match.span()
        # 跳过已经作为 Markdown 链接文本的 code span，避免生成嵌套链接。
        if start > 0 and content[start - 1] == "[" and content[end:end + 2] == "](":
            return match.group(0)
        raw = match.group(1).strip()
        if not _looks_like_absolute_path_reference(raw):
            return match.group(0)
        encoded = _encode_file_link_path(raw)
        return f"[`{raw}`](#sensenova-claw-file:{encoded})"

    return _CODE_SPAN_RE.sub(_replace_code, content)


def sanitize_file_link_href(content: str) -> str:
    """规避 markdown link destination 中对 ``#sensenova-claw-file:`` href 的错误解析。

    两类字符会被 markdown parser 误处理，必须在 LLM 输出落地前转写：

    - **未转义的 ``(`` / ``)``**：Windows 典型路径 ``C:\\Program Files (x86)\\...``
      里带裸括号，虽然 CommonMark 允许一层 balanced parens，但多种渲染器
      （包括本模块正则和前端 react-markdown）在嵌套/配对失衡时会在第一个
      ``)`` 处截断 link，href 缺尾，点击必 404。替换为 ``%28`` / ``%29``。
    - **反斜杠 + ASCII 标点（``\\.``、``\\_``、``\\-`` 等）**：CommonMark 把
      link destination 中的 ``\\ + 标点`` 识别为 backslash-escape，反斜杠
      被吃掉。Windows 路径 ``C:\\Users\\foo\\.sensenova-claw\\...`` 里的
      ``\\.`` 会退化成 ``.``，得到 ``C:\\Users\\foo.sensenova-claw\\...``
      这种少一级分隔符的错误路径，下游 ``/api/files/download`` 必然 404。
      做法：把 href body 中所有 ``\\`` 统一换成 ``/``。Windows Python
      ``Path`` 同时接受 ``/`` / ``\\``，语义无损；下游匹配走 ``norm()`` 再
      归一，不会因分隔符差异失败。

    用支持一层 ``(...)`` 平衡嵌套的正则定位完整 href，后续
    ``rewrite_file_link_hrefs`` 与前端 ``decodeURIComponent`` 均能正常工作。
    """
    if not content:
        return content

    def _replace(match: re.Match) -> str:
        prefix = match.group(1)
        body = match.group(2)
        suffix = match.group(3)
        if "(" not in body and ")" not in body and "\\" not in body:
            return match.group(0)
        sanitized = (
            body.replace("\\", "/")
                .replace("(", "%28")
                .replace(")", "%29")
        )
        return f"{prefix}{sanitized}{suffix}"

    return _FILE_LINK_RE.sub(_replace, content)


# 保留旧名作为别名，避免外部 import 失败（过渡期，后续可移除）
encode_file_link_parens = sanitize_file_link_href


def rewrite_file_link_hrefs(content: str, workdir: str) -> str:
    """将 ``[text](#sensenova-claw-file:PATH)`` 中非绝对的 PATH 拼成绝对路径。

    设计要点：

    - **workdir 为空/未配置**：直接返回原文（agent 可能在开发机本地运行，
      或未配置 workdir，此时强行拼接反而误导）。
    - **PATH 已是绝对形式**：不改（POSIX / Windows 盘符 / ``~`` 三种）。
    - **反斜杠归一**：Python 在 POSIX 上不把 ``\\`` 当分隔符，因此先把
      ``\\`` 替换为 ``/``；再走 ``_join_and_normalize`` 处理 ``.``/``..``
      与 Windows 盘符边界。拒绝依赖当前运行平台的 Path 行为。
    - **URL 编码兼容**：LLM 多数直接写原始路径，也可能产出百分号编码；
      ``unquote`` 对普通文本是 no-op，对编码文本能正确解码。
      输出统一用解码后的原始路径，前端 ``decodeURIComponent`` 仍是 no-op。
    - **安全边界**：越出 workdir 的 ``..`` 组合在盘符根/根目录处停住
      （不会把 ``C:`` 吃掉导致路径退化），下游 ``/api/files/download``
      自带 path_policy 校验，这里只负责语义归一。
    """
    if not content or not workdir:
        return content

    workdir_abs = _normalize_workdir(workdir)
    if not workdir_abs:
        return content

    def _replace(match: re.Match) -> str:
        prefix = match.group(1)
        raw_href = match.group(2).strip()
        suffix = match.group(3)

        try:
            decoded = unquote(raw_href)
        except Exception:
            decoded = raw_href

        if not decoded or _is_absolute_pathlike(decoded):
            return match.group(0)

        abs_path = _join_and_normalize(workdir_abs, decoded)
        return f"{prefix}{abs_path}{suffix}"

    return _FILE_LINK_RE.sub(_replace, content)
