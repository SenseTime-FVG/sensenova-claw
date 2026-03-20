"""AgentOS Home 目录管理

管理 AGENTOS_HOME（默认 ~/.agentos/）目录结构：
- agents/{agent_id}/   — per-agent 配置（SYSTEM_PROMPT.md、AGENTS.md、USER.md）
- workdir/{agent_id}/  — per-agent 工作目录（bash_command 默认 cwd）
- data/                — 数据库
- skills/              — 用户安装的 skills

首次启动时从代码仓库 .agentos/ 复制内置资源到用户目录（不覆盖已有）。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from agentos.kernel.runtime.prompt_builder import ContextFile

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


# ---------- AGENTOS_HOME 解析 ----------

def resolve_agentos_home(config: Any = None) -> Path:
    """解析 AGENTOS_HOME 路径。

    优先级：config 中显式设置 > 环境变量 AGENTOS_HOME > 默认 ~/.agentos
    """
    import os
    home = None
    if config:
        raw = config.get("system.agentos_home", "") if hasattr(config, "get") else ""
        if raw and raw != "${AGENTOS_HOME}":
            home = raw
    if not home:
        home = os.environ.get("AGENTOS_HOME", "")
    if not home:
        home = str(Path.home() / ".agentos")
    return Path(home).expanduser().resolve()


async def ensure_agentos_home(home: Path, project_root: Path | None = None) -> None:
    """确保 AGENTOS_HOME 目录结构存在，从代码仓库复制内置资源（不覆盖已有）。

    目录结构：
        {home}/agents/default/   — 默认 agent（AGENTS.md、USER.md）
        {home}/workdir/default/  — 默认工作目录
        {home}/data/             — 数据库
        {home}/skills/           — 用户 skills
    """
    # 创建核心子目录
    for subdir in ["agents/default", "data", "skills", "workdir/default"]:
        (home / subdir).mkdir(parents=True, exist_ok=True)

    # 从代码仓库 .agentos/ 复制内置资源
    if project_root:
        builtin_dir = project_root / ".agentos"
        if builtin_dir.is_dir():
            _copy_builtin_resources(builtin_dir, home)

    # 确保 default agent 有 AGENTS.md / USER.md
    default_agent_dir = home / "agents" / "default"
    _ensure_file(default_agent_dir / "AGENTS.md", DEFAULT_AGENTS_MD)
    _ensure_file(default_agent_dir / "USER.md", DEFAULT_USER_MD)

    logger.info("AGENTOS_HOME initialized: %s", home)


def _copy_builtin_resources(builtin_dir: Path, home: Path) -> None:
    """从代码仓库 .agentos/ 复制内置 agent 配置和 skills 到用户目录（不覆盖）"""
    # 复制内置 agent 模板
    builtin_agents = builtin_dir / "agents"
    if builtin_agents.is_dir():
        for agent_dir in builtin_agents.iterdir():
            if agent_dir.is_dir():
                target = home / "agents" / agent_dir.name
                target.mkdir(parents=True, exist_ok=True)
                for f in agent_dir.iterdir():
                    if f.is_file():
                        target_file = target / f.name
                        if not target_file.exists():
                            shutil.copy2(f, target_file)
                            logger.info("Copied builtin agent file: %s", target_file)


def _ensure_file(path: Path, default_content: str) -> None:
    """确保文件存在，不存在时写入默认内容"""
    if not path.exists():
        path.write_text(default_content, encoding="utf-8")
        logger.info("Created file: %s", path)


# ---------- per-agent workspace ----------

async def ensure_agent_workspace(agentos_home: str, agent_id: str) -> None:
    """确保指定 agent 的目录存在（agents/{id}/ + workdir/{id}/）"""
    home = Path(agentos_home)
    agent_dir = home / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    # 从 default agent 复制模板，否则用默认内容
    default_dir = home / "agents" / "default"
    templates = {
        "AGENTS.md": DEFAULT_AGENTS_MD,
        "USER.md": DEFAULT_USER_MD,
    }
    for filename, default_content in templates.items():
        agent_file = agent_dir / filename
        if not agent_file.exists():
            source = default_dir / filename
            if source.exists():
                content = source.read_text(encoding="utf-8")
            else:
                content = default_content
            agent_file.write_text(content, encoding="utf-8")
            logger.info("Created agent file: %s", agent_file)

    # 创建 workdir
    workdir = home / "workdir" / agent_id
    workdir.mkdir(parents=True, exist_ok=True)


def resolve_agent_workdir(agentos_home: str, agent_config: Any = None) -> str:
    """解析 agent 实际 workdir：优先用配置值，否则默认 {agentos_home}/workdir/{agent_id}"""
    if agent_config and getattr(agent_config, "workdir", ""):
        return str(Path(agent_config.workdir).expanduser().resolve())
    agent_id = getattr(agent_config, "id", "default") if agent_config else "default"
    return str((Path(agentos_home).resolve() / "workdir" / agent_id))


# ---------- 加载 workspace 文件 ----------

async def load_workspace_files(
    agentos_home: str, agent_id: str | None = None,
) -> list[ContextFile]:
    """读取 agent 引导文件（AGENTS.md / USER.md），缺失或空文件自动跳过。

    从 {agentos_home}/agents/{agent_id}/ 加载；
    不传 agent_id 时从 agents/default/ 加载。
    """
    aid = agent_id or "default"
    dir_path = Path(agentos_home) / "agents" / aid

    files: list[ContextFile] = []
    for name in ["AGENTS.md", "USER.md"]:
        path = dir_path / name
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                files.append(ContextFile(name=name, content=content))
    return files


# ---------- 向后兼容（已废弃） ----------

async def ensure_workspace(workspace_dir: str) -> None:
    """已废弃，保留向后兼容。请使用 ensure_agentos_home()。"""
    dir_path = Path(workspace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    _ensure_file(dir_path / "AGENTS.md", DEFAULT_AGENTS_MD)
    _ensure_file(dir_path / "USER.md", DEFAULT_USER_MD)
