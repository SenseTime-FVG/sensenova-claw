"""Workspace 文件管理

负责创建/加载 workspace 目录下的引导文件（AGENTS.md / USER.md）。
这些文件在 session 首轮注入 system prompt，为 Agent 提供操作指令和用户偏好。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.runtime.prompt_builder import ContextFile

logger = logging.getLogger(__name__)

# ---------- 默认内容 ----------

DEFAULT_AGENTS_MD = """\
# Agent Instructions

## 工具使用规范
- 在需要时主动调用工具，不要猜测结果
- 优先使用 bash_command 执行系统命令
- 使用 serper_search 获取最新信息
- 文件操作前先用 read_file 确认内容

## 回复风格
- 简洁明了，避免冗余
- 代码块使用正确的语言标记
- 默认使用中文回复，除非用户使用其他语言
- 对不确定的内容如实说明，不要编造
"""

DEFAULT_USER_MD = """\
# User Profile

## 基本信息
- 称呼: （请填写你希望 AI 如何称呼你）
- 语言偏好: 中文

## 工作环境
- 操作系统: （自动检测）
- 常用工具: （请填写）

## 偏好设置
- 回复详细程度: 适中
- 代码风格: （请填写偏好的代码风格）
"""


# ---------- 公开接口 ----------

async def ensure_workspace(workspace_dir: str) -> None:
    """确保 workspace 存在，创建缺失的核心文件（不覆盖已有）"""
    dir_path = Path(workspace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    defaults = {
        "AGENTS.md": DEFAULT_AGENTS_MD,
        "USER.md": DEFAULT_USER_MD,
    }
    for filename, content in defaults.items():
        file_path = dir_path / filename
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            logger.info("Created workspace file: %s", file_path)


async def load_workspace_files(workspace_dir: str) -> list[ContextFile]:
    """读取引导文件，缺失或空文件自动跳过"""
    files: list[ContextFile] = []
    dir_path = Path(workspace_dir)
    for name in ["AGENTS.md", "USER.md"]:
        path = dir_path / name
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                files.append(ContextFile(name=name, content=content))
    return files
