from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sensenova_claw.capabilities.agents.preferences import (
    load_preferences,
    resolve_tool_enabled_from_prefs,
)
from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.runtime.prompt_builder import (
    ContextFile,
    RuntimeInfo,
    SystemPromptParams,
    build_system_prompt,
)

if TYPE_CHECKING:
    from sensenova_claw.capabilities.agents.config import AgentConfig
    from sensenova_claw.capabilities.agents.registry import AgentRegistry
    from sensenova_claw.capabilities.skills.registry import SkillRegistry
    from sensenova_claw.capabilities.tools.registry import ToolRegistry


class ContextBuilder:
    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
        sensenova_claw_home: str | None = None,
        workspace_dir: str | None = None,  # 向后兼容，等同 sensenova_claw_home
    ):
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.sensenova_claw_home = sensenova_claw_home or workspace_dir

    def build_messages(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        context_files: list[ContextFile] | None = None,
        agent_config: AgentConfig | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """构建 LLM 调用的完整消息列表"""
        # 收集工具信息（根据 agent_config 过滤）
        tool_names: list[str] = []
        tool_summaries: dict[str, str] = {}
        prefs: dict[str, Any] = {}
        home = self.sensenova_claw_home or str(resolve_sensenova_claw_home_default())
        if agent_config:
            prefs = load_preferences(home)
        if self.tool_registry:
            tools = self.tool_registry.as_llm_tools(session_id=session_id, agent_config=agent_config)
            # 根据 agent_config 过滤工具信息注入 prompt
            if agent_config and agent_config.tools:
                allowed = set(agent_config.tools)
                # 保留 send_message（除非 can_delegate_to 为 None 表示禁止委托）
                if agent_config.can_delegate_to is not None:
                    allowed.add("send_message")
                tools = [t for t in tools if t["name"].startswith("mcp__") or t["name"] in allowed]
            if agent_config and agent_config.can_delegate_to is None:
                tools = [t for t in tools if t["name"] != "send_message"]
            if agent_config:
                tools = [
                    t for t in tools
                    if resolve_tool_enabled_from_prefs(prefs, agent_config.id, t["name"], default=True)
                ]
            for t in tools:
                tool_names.append(t["name"])
                tool_summaries[t["name"]] = t.get("description", "")

        # 根据 agent_config 选择 system prompt
        base_prompt = (
            agent_config.system_prompt
            if agent_config and agent_config.system_prompt
            else config.get("agent.system_prompt", "")
        )

        # 构建多 Agent 通信信息
        delegation_prompt = self._build_agent_to_agent_prompt(agent_config)

        # 独立读取 extra_system_prompt（不混入 delegation）
        extra = config.get("agent.extra_system_prompt")

        # 解析 per-agent workdir 注入 system prompt
        from sensenova_claw.platform.config.workspace import resolve_agent_workdir
        effective_workdir = resolve_agent_workdir(home, agent_config)

        params = SystemPromptParams(
            base_prompt=base_prompt,
            tool_names=tool_names,
            tool_summaries=tool_summaries,
            skills_prompt=self._build_skills_section(agent_config),
            delegation_prompt=delegation_prompt,
            memory_context=memory_context,
            context_files=context_files or [],
            extra_system_prompt=extra,
            runtime_info=self._collect_runtime_info(agent_config),
            workspace_dir=effective_workdir,
        )
        system_prompt = build_system_prompt(params)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)

        # 在用户消息前添加当前时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_message = f"[{current_time}] {user_input}"
        messages.append({"role": "user", "content": user_message})
        return messages

    def append_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        result: Any,
        tool_call_id: str | None = None,
    ) -> list[dict[str, Any]]:
        next_messages = list(messages)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        tool_message: dict[str, Any] = {
            "role": "tool",
            "name": tool_name,
            "content": content,
        }
        if tool_call_id:
            tool_message["tool_call_id"] = tool_call_id
        next_messages.append(tool_message)
        return next_messages

    def _build_skills_section(self, agent_config: AgentConfig | None = None) -> str | None:
        """格式化 skills 列表为 prompt 文本（支持 agent_config 过滤）"""
        if not self.skill_registry:
            return None
        skills = self.skill_registry.get_all()
        # 按 agent_config 过滤 skills
        if agent_config and agent_config.skills:
            allowed = set(agent_config.skills)
            skills = [s for s in skills if s.name in allowed]
        if not skills:
            return None
        lines = [
            "## Skill Usage",
            "当用户请求匹配到某个 skill 的名称或描述时，先用 read_file 读取对应 `<location>` 路径下的 `SKILL.md`，再继续执行。",
            "",
            "<available_skills>",
        ]
        for skill in skills:
            skill_md = skill.path / "SKILL.md"
            lines.extend([
                "<skill>",
                f"<name>{skill.name}</name>",
                f"<description>{skill.description}</description>",
                f"<location>{skill_md}</location>",
                "</skill>",
            ])
        lines.append("</available_skills>")
        return "\n".join(lines)

    def _build_agent_to_agent_prompt(self, agent_config: AgentConfig | None) -> str | None:
        """构建可通信 Agent 的信息（注入到 system prompt）"""
        if not self.agent_registry or not agent_config:
            return None
        home = self.sensenova_claw_home or str(resolve_sensenova_claw_home_default())
        prefs = load_preferences(home)
        if not resolve_tool_enabled_from_prefs(prefs, agent_config.id, "send_message", default=True):
            return None
        sendable = self.agent_registry.get_sendable(agent_config.id)
        if not sendable:
            return None
        lines = ["<available_agents>"]
        for agent in sendable:
            lines.append(f"- {agent.id}: {agent.description}")
        lines.append("</available_agents>")
        lines.append("")
        lines.append("你可以使用 send_message 工具向以上 Agent 发送任务或追问。")
        return "\n".join(lines)

    def _collect_runtime_info(self, agent_config: AgentConfig | None = None) -> RuntimeInfo:
        """收集运行时信息"""
        model_key = (
            agent_config.model
            if agent_config and agent_config.model
            else config.get("llm.default_model", "mock")
        )
        _, model = config.resolve_model(model_key)
        return RuntimeInfo(
            os=f"{platform.system()} ({platform.machine()})",
            python=platform.python_version(),
            model=model,
            channel=None,  # 由调用方根据场景填充
        )


def resolve_sensenova_claw_home_default() -> str:
    """快速获取 sensenova_claw_home 默认值（不依赖 config 对象）"""
    from sensenova_claw.platform.config.workspace import default_sensenova_claw_home

    return str(default_sensenova_claw_home())
