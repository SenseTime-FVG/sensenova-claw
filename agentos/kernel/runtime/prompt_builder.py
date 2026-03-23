"""模块化 System Prompt 构建器

纯函数 `build_system_prompt()` 负责将各 Section 拼接为完整 system prompt。
每个 Section 由独立 builder 函数生成，返回 `list[str]`，空则跳过。
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

PromptMode = Literal["full", "none"]

# ---------- 截断常量 ----------
_MAX_SINGLE_FILE_CHARS = 20000
_MAX_TOTAL_CHARS = 50000


# ---------- 数据结构 ----------

@dataclass
class ContextFile:
    """Workspace 上下文文件（如 AGENTS.md（per-agent）/ USER.md（全局））"""
    name: str
    content: str


@dataclass
class RuntimeInfo:
    """运行时信息，附加在 system prompt 末尾"""
    host: str | None = None
    os: str | None = None
    python: str | None = None
    model: str | None = None
    channel: str | None = None


@dataclass
class SystemPromptParams:
    """build_system_prompt 的输入参数"""
    prompt_mode: PromptMode = "full"
    base_prompt: str = ""
    tool_names: list[str] = field(default_factory=list)
    tool_summaries: dict[str, str] = field(default_factory=dict)
    skills_prompt: str | None = None
    memory_context: str | None = None          # v0.6 预留
    context_files: list[ContextFile] = field(default_factory=list)
    extra_system_prompt: str | None = None
    runtime_info: RuntimeInfo | None = None
    workspace_dir: str | None = None           # v1.2: 工作目录


# ---------- 公开接口 ----------

def build_system_prompt(params: SystemPromptParams) -> str:
    """根据参数构建完整的 system prompt（纯函数，不做文件 I/O）"""
    if params.prompt_mode == "none":
        return "You are a personal assistant running inside AgentOS."

    sections = [
        _build_identity(params.base_prompt),
        _build_workspace(params.workspace_dir),
        _build_tooling(params.tool_names, params.tool_summaries),
        _build_skills(params.skills_prompt),
        _build_memory(params.memory_context),
        _build_context_files(params.context_files),
        _build_datetime(),
        _build_extra(params.extra_system_prompt),
        _build_runtime(params.runtime_info),
    ]

    lines: list[str] = []
    for section in sections:
        if section:
            lines.extend(section)
    return "\n".join(lines)


# ---------- Section Builders ----------

def _build_identity(base_prompt: str) -> list[str]:
    """Section 1: 身份声明 + 基础行为规范（必选）"""
    if base_prompt.strip():
        return [base_prompt.strip()]
    return ["You are a helpful AI assistant running inside AgentOS."]


def _build_workspace(workspace_dir: str | None) -> list[str]:
    """Section 2: Workspace 路径提示（有 workspace 时）"""
    if not workspace_dir:
        return []
    return [
        "",
        "## Workspace",
        f"Your working directory is: {workspace_dir}",
        "Relative paths resolve against this directory.",
        "To access files outside workspace, use absolute paths — you may need user permission.",
        "Do NOT maintain a 'current directory' state — each tool call is independent.",
    ]


def _build_tooling(tool_names: list[str], tool_summaries: dict[str, str]) -> list[str]:
    """Section 2: 可用工具列表 + 调用规范（有工具时）"""
    if not tool_names:
        return []
    lines = [
        "",
        "## Available Tools",
        "以下工具可供调用，请在需要时使用：",
        "",
    ]
    for name in tool_names:
        summary = tool_summaries.get(name, "")
        if summary:
            lines.append(f"- **{name}**: {summary}")
        else:
            lines.append(f"- **{name}**")
    return lines


def _build_skills(skills_prompt: str | None) -> list[str]:
    """Section 3: 可用技能列表 + 使用说明（有 skills 时）"""
    if not skills_prompt or not skills_prompt.strip():
        return []
    return ["", skills_prompt.strip()]


def _build_memory(memory_context: str | None) -> list[str]:
    """Section 4: 长期记忆召回结果（v0.6 填充）"""
    if not memory_context or not memory_context.strip():
        return []
    return [
        "",
        "## Memory",
        memory_context.strip(),
    ]


def _build_context_files(context_files: list[ContextFile]) -> list[str]:
    """Section 5: AGENTS.md（per-agent）/ USER.md（全局）上下文文件内容（有时）"""
    if not context_files:
        return []

    # 截断处理
    truncated = _truncate_context_files(context_files)
    if not truncated:
        return []

    lines = [
        "",
        "## Project Context",
        "The following workspace files have been loaded:",
    ]
    for cf in truncated:
        lines.append(f"### {cf.name}")
        lines.append(cf.content)
    return lines


def _build_datetime() -> list[str]:
    """Section 6: 当前日期时间 + 系统信息（必选）"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_type = platform.system()
    return [
        "",
        f"当前时间: {current_time} | 系统: {system_type}",
    ]


def _build_extra(extra: str | None) -> list[str]:
    """Section 7: 用户自定义额外上下文（有时）"""
    if not extra or not extra.strip():
        return []
    return [
        "",
        "## Extra Context",
        extra.strip(),
    ]


def _build_runtime(info: RuntimeInfo | None) -> list[str]:
    """Section 8: 运行时信息行（调试用，必选）"""
    if not info:
        return []
    parts: list[str] = []
    if info.os:
        parts.append(f"os={info.os}")
    if info.python:
        parts.append(f"python={info.python}")
    if info.model:
        parts.append(f"model={info.model}")
    if info.channel:
        parts.append(f"channel={info.channel}")
    if not parts:
        return []
    return ["", f"Runtime: {' | '.join(parts)}"]


# ---------- 辅助函数 ----------

def _truncate_context_files(files: list[ContextFile]) -> list[ContextFile]:
    """截断超长的上下文文件。

    规则：
    - 单文件 > 20000 字符截断
    - 总计 > 50000 字符按优先级裁剪（全局 AGENTS.md > per-agent AGENTS.md > USER.md）
    """
    # 优先级排序：AGENTS.md 类文件优先于 USER.md，其余按原顺序
    def _priority(name: str) -> int:
        if name == "AGENTS.md":
            return 0  # 全局 AGENTS.md
        if name.endswith("/AGENTS.md"):
            return 1  # per-agent AGENTS.md
        if name == "USER.md":
            return 2
        return 99
    priority_order = {}  # 保留变量兼容下方排序
    sorted_files = sorted(files, key=lambda f: _priority(f.name))

    # 第一步：单文件截断
    truncated: list[ContextFile] = []
    for cf in sorted_files:
        content = cf.content
        if len(content) > _MAX_SINGLE_FILE_CHARS:
            content = content[:_MAX_SINGLE_FILE_CHARS] + "\n...[truncated]"
        truncated.append(ContextFile(name=cf.name, content=content))

    # 第二步：总量截断（按优先级保留）
    total = sum(len(cf.content) for cf in truncated)
    if total > _MAX_TOTAL_CHARS:
        result: list[ContextFile] = []
        remaining = _MAX_TOTAL_CHARS
        for cf in truncated:
            if remaining <= 0:
                break
            if len(cf.content) <= remaining:
                result.append(cf)
                remaining -= len(cf.content)
            else:
                result.append(ContextFile(
                    name=cf.name,
                    content=cf.content[:remaining] + "\n...[truncated]",
                ))
                remaining = 0
        truncated = result

    return truncated
