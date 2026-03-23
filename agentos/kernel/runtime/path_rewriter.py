"""Assistant 消息中的相对路径 → 绝对路径后处理。

模型在回复用户时经常使用相对路径（如 `report.md`、`./output/data.csv`），
用户看到后无法直接定位文件。此模块在发送给前端之前，将文本中可识别的
相对路径改写为基于 agent workdir 的绝对路径。
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath


# 匹配 Markdown 行内代码 `...` 中包含的文件路径
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")

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
