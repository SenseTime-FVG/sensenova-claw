"""Assistant 消息中的相对路径 → 绝对路径后处理。

模型在回复用户时经常使用相对路径（如 `report.md`、`./output/data.csv`），
用户看到后无法直接定位文件。此模块在发送给前端之前，将文本中可识别的
相对路径改写为基于 agent workdir 的绝对路径。
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote


# 匹配 Markdown 行内代码 `...` 中包含的文件路径
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")

# 匹配 [text](#sensenova-claw-file:PATH) 形式的文件链接
# 前端 Markdown.tsx 以此前缀识别并渲染成可点击卡片；PATH 由 LLM 产出，
# 常因路径规则理解偏差出现相对形式，导致点击打开失败。
_FILE_LINK_RE = re.compile(r"(\]\(#sensenova-claw-file:)([^)]*?)(\))")

# 常见文件扩展名，用于判定是否像一个文件路径
_FILE_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".jsonl", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz",
    ".sh", ".bash", ".bat", ".ps1", ".log", ".xml", ".toml",
    ".env", ".cfg", ".ini", ".sql", ".r", ".ipynb",
}


def _looks_like_relative_file_path(text: str) -> bool:
    """判断 text 是否看起来像一个相对文件路径（而非代码片段、URL、命令等）。"""
    text = text.strip()
    if not text:
        return False
    # 排除 URL
    if text.startswith(("http://", "https://", "ftp://", "data:")):
        return False
    # 排除已是绝对路径（Unix / Windows）
    if text.startswith("/") or text.startswith("~"):
        return False
    if len(text) >= 3 and text[1] == ":" and text[2] in ("/", "\\"):
        return False
    # 排除纯变量名/单词（无路径分隔符也无扩展名）
    # 排除包含空格但无路径分隔符的（更像自然语言）
    # 获取扩展名
    try:
        suffix = PurePosixPath(text).suffix.lower()
    except Exception:
        suffix = ""
    # 必须有已知扩展名才认定为文件路径
    if not suffix or suffix not in _FILE_EXTENSIONS:
        return False
    # 排除太长的字符串（不太像路径）
    if len(text) > 200:
        return False
    # 排除含有明显非路径字符
    if any(c in text for c in ("(", ")", "{", "}", "<", ">", "|", ";", "&", "=", "?")):
        return False
    return True


def rewrite_relative_paths(content: str, workdir: str) -> str:
    """将 assistant 回复文本中 `...` 引用的相对路径改写为绝对路径。

    仅处理 Markdown 行内代码块 `...` 中的内容，避免误改自然语言。
    """
    if not content or not workdir:
        return content

    workdir_resolved = str(Path(workdir).resolve())

    def _replace(match: re.Match) -> str:
        raw = match.group(1)
        if not _looks_like_relative_file_path(raw):
            return match.group(0)
        # 构建绝对路径
        abs_path = str((Path(workdir_resolved) / raw).resolve())
        # 统一使用正斜杠（跨平台友好）
        abs_path = abs_path.replace("\\", "/")
        return f"`{abs_path}`"

    return _CODE_SPAN_RE.sub(_replace, content)


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


def rewrite_file_link_hrefs(content: str, workdir: str) -> str:
    """将 ``[text](#sensenova-claw-file:PATH)`` 中非绝对的 PATH 拼成绝对路径。

    设计要点：

    - **workdir 为空/未配置**：直接返回原文（agent 可能在开发机本地运行，
      或未配置 workdir，此时强行拼接反而误导）。
    - **PATH 已是绝对形式**：不改（POSIX / Windows 盘符 / ``~`` 三种）。
    - **反斜杠归一**：Python 在 POSIX 上不把 ``\\`` 当分隔符，因此先把
      ``\\`` 替换为 ``/``，再用 ``posixpath.normpath`` 统一处理
      ``.``、``..``、冗余斜杠。拒绝依赖当前运行平台的 Path 行为。
    - **URL 编码兼容**：LLM 多数直接写原始路径，也可能产出百分号编码；
      ``unquote`` 对普通文本是 no-op，对编码文本能正确解码。
      输出统一用解码后的原始路径，前端 ``decodeURIComponent`` 仍是 no-op。
    - **安全边界**：越出 workdir 的 ``..`` 组合会按字面规范化，不会额外
      阻断；下游 ``/api/files/download`` 自带 path_policy 校验，这里
      只负责语义归一。
    """
    if not content or not workdir:
        return content

    try:
        # 统一以正斜杠作为输出分隔符，避免 Windows ``\\`` 进入 markdown 后被
        # 下游 ``decodeURIComponent`` 或 URL 解析误判。
        workdir_abs = str(Path(workdir).expanduser().resolve()).replace("\\", "/")
    except Exception:
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

        normalized = decoded.replace("\\", "/")
        # PurePosixPath 保证在任意宿主平台上的行为一致
        joined = str(PurePosixPath(workdir_abs) / normalized)
        abs_path = posixpath.normpath(joined)

        return f"{prefix}{abs_path}{suffix}"

    return _FILE_LINK_RE.sub(_replace, content)
