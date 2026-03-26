"""Sensenova-Claw Home 目录管理

管理 SENSENOVA_CLAW_HOME（默认 ~/.sensenova-claw/）目录结构：
- agents/AGENTS.md     — 全局 Agent 规则（所有 Agent 共享）
- agents/USER.md       — 全局用户画像（所有 Agent 共享）
- agents/{agent_id}/   — per-agent 配置（SYSTEM_PROMPT.md、AGENTS.md）
- workdir/{agent_id}/  — per-agent 工作目录（bash_command 默认 cwd）
- data/                — 数据库
- skills/              — 用户安装的 skills

首次启动时从代码仓库 .sensenova-claw/ 复制内置资源到用户目录（不覆盖已有）。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sensenova_claw.kernel.runtime.prompt_builder import ContextFile

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


# ---------- SENSENOVA_CLAW_HOME 解析 ----------

def default_sensenova_claw_home() -> Path:
    """返回默认 SENSENOVA_CLAW_HOME。

    规则：
    1. 优先读取环境变量 SENSENOVA_CLAW_HOME
    2. 未设置时，回退到用户目录下的 .sensenova-claw

    Windows 下 Path.home() 会解析到 %USERPROFILE%，因此默认目录会落到
    %USERPROFILE%\\.sensenova-claw。
    """
    import os

    home = os.environ.get("SENSENOVA_CLAW_HOME", "")
    if not home:
        home = str(Path.home() / ".sensenova-claw")
    return Path(home).expanduser().resolve()


def resolve_sensenova_claw_home(config: Any = None) -> Path:
    """解析 SENSENOVA_CLAW_HOME 路径。

    config 参数仅为兼容旧调用保留，当前不再读取
    system.sensenova_claw_home 配置项，统一由环境变量控制。
    """
    return default_sensenova_claw_home()


async def ensure_sensenova_claw_home(home: Path, project_root: Path | None = None) -> None:
    """确保 SENSENOVA_CLAW_HOME 目录结构存在，从代码仓库复制内置资源（不覆盖已有）。

    目录结构：
        {home}/agents/AGENTS.md  — 全局 Agent 规则（所有 Agent 共享）
        {home}/agents/USER.md    — 全局用户画像（所有 Agent 共享）
        {home}/agents/default/   — 默认 agent（AGENTS.md）
        {home}/workdir/default/  — 默认工作目录
        {home}/data/             — 数据库
        {home}/skills/           — 用户 skills
    """
    # 创建核心子目录
    for subdir in ["agents/default", "data", "skills", "workdir/default"]:
        (home / subdir).mkdir(parents=True, exist_ok=True)

    # 从代码仓库 .sensenova-claw/ 复制内置资源
    if project_root:
        builtin_dir = project_root / ".sensenova-claw"
        if builtin_dir.is_dir():
            _copy_builtin_resources(builtin_dir, home)

    # 全局文件（所有 Agent 共享）
    (home / "agents").mkdir(parents=True, exist_ok=True)
    _ensure_file(home / "agents" / "AGENTS.md", DEFAULT_AGENTS_MD)
    _ensure_file(home / "agents" / "USER.md", DEFAULT_USER_MD)

    # 确保 default agent 有 per-agent AGENTS.md
    default_agent_dir = home / "agents" / "default"
    _ensure_file(default_agent_dir / "AGENTS.md", DEFAULT_AGENTS_MD)

    logger.info("SENSENOVA_CLAW_HOME initialized: %s", home)


def _copy_builtin_resources(builtin_dir: Path, home: Path) -> None:
    """从代码仓库 .sensenova-claw/ 复制内置资源到用户目录（不覆盖）"""
    # 复制内置 agent 模板
    builtin_agents = builtin_dir / "agents"
    if builtin_agents.is_dir():
        # 复制 agents/ 下的根级文件（如 USER.md）到 {home}/agents/
        agents_target = home / "agents"
        agents_target.mkdir(parents=True, exist_ok=True)
        for f in builtin_agents.iterdir():
            if f.is_file():
                target_file = agents_target / f.name
                if not target_file.exists():
                    shutil.copy2(f, target_file)
                    logger.info("Copied builtin file: %s", target_file)
        # 复制 agents/ 下的子目录（per-agent 配置）
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

async def ensure_agent_workspace(sensenova_claw_home: str, agent_id: str) -> None:
    """确保指定 agent 的目录存在（agents/{id}/ + workdir/{id}/）"""
    home = Path(sensenova_claw_home)
    agent_dir = home / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    # 确保 AGENTS.md 存在（从 default agent 复制模板，否则用默认内容）
    agents_file = agent_dir / "AGENTS.md"
    if not agents_file.exists():
        default_source = home / "agents" / "default" / "AGENTS.md"
        if default_source.exists():
            content = default_source.read_text(encoding="utf-8")
        else:
            content = DEFAULT_AGENTS_MD
        agents_file.write_text(content, encoding="utf-8")
        logger.info("Created agent file: %s", agents_file)

    # 创建 workdir
    workdir = home / "workdir" / agent_id
    workdir.mkdir(parents=True, exist_ok=True)


def resolve_agent_workdir(sensenova_claw_home: str, agent_config: Any = None) -> str:
    """解析 agent 实际 workdir：优先用配置值，否则默认 {sensenova_claw_home}/workdir/{agent_id}"""
    if agent_config and getattr(agent_config, "workdir", ""):
        return str(Path(agent_config.workdir).expanduser().resolve())
    agent_id = getattr(agent_config, "id", "default") if agent_config else "default"
    return str((Path(sensenova_claw_home).resolve() / "workdir" / agent_id))


def resolve_session_artifact_dir(
    sensenova_claw_home: str | Path,
    session_id: str,
    agent_id: str | None = None,
) -> Path:
    """解析 session 附件目录。

    统一布局：
        {sensenova_claw_home}/agents/{agent_id}/sessions/{session_id}/

    这里专门存放与 session 相关的落盘附件，例如：
    - tool_result_*.txt
    - compression_phase*.json
    """
    home = Path(sensenova_claw_home).expanduser().resolve()
    safe_agent = str(agent_id or "").strip() or "default"
    safe_agent = safe_agent.replace("/", "_").replace("\\", "_")
    safe_session = str(session_id).replace("/", "_").replace("\\", "_")
    return home / "agents" / safe_agent / "sessions" / safe_session


# ---------- 加载 workspace 文件 ----------

async def load_workspace_files(
    sensenova_claw_home: str, agent_id: str | None = None,
) -> list[ContextFile]:
    """读取全局和 per-agent 引导文件，缺失或空文件自动跳过。

    加载顺序（注入 system prompt 的优先级从高到低）：
    1. 全局 AGENTS.md — {sensenova_claw_home}/agents/AGENTS.md（所有 Agent 共享的基础规则）
    2. per-agent AGENTS.md — {sensenova_claw_home}/agents/{agent_id}/AGENTS.md（Agent 专属指令）
    3. 全局 USER.md — {sensenova_claw_home}/agents/USER.md（用户画像）
    """
    home = Path(sensenova_claw_home)
    aid = agent_id or "default"

    files: list[ContextFile] = []

    # 全局 AGENTS.md（所有 Agent 共享的基础规则）
    global_agents_md = home / "agents" / "AGENTS.md"
    if global_agents_md.exists():
        content = global_agents_md.read_text(encoding="utf-8").strip()
        if content:
            files.append(ContextFile(name="AGENTS.md", content=content))

    # per-agent AGENTS.md（Agent 专属指令，可覆盖全局规则）
    agent_agents_md = home / "agents" / aid / "AGENTS.md"
    if agent_agents_md.exists():
        content = agent_agents_md.read_text(encoding="utf-8").strip()
        if content:
            files.append(ContextFile(name=f"{aid}/AGENTS.md", content=content))

    # 全局 USER.md（用户画像）
    user_md = home / "agents" / "USER.md"
    if user_md.exists():
        content = user_md.read_text(encoding="utf-8").strip()
        if content:
            files.append(ContextFile(name="USER.md", content=content))

    return files


# ---------- 向后兼容（已废弃） ----------

async def ensure_workspace(workspace_dir: str) -> None:
    """已废弃，保留向后兼容。请使用 ensure_sensenova_claw_home()。"""
    dir_path = Path(workspace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    _ensure_file(dir_path / "AGENTS.md", DEFAULT_AGENTS_MD)
    _ensure_file(dir_path / "USER.md", DEFAULT_USER_MD)  # 兼容旧逻辑
