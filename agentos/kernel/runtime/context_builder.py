from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from typing import Any, TYPE_CHECKING

from agentos.platform.config.config import config
from agentos.kernel.runtime.prompt_builder import (
    ContextFile,
    RuntimeInfo,
    SystemPromptParams,
    build_system_prompt,
)

if TYPE_CHECKING:
    from agentos.capabilities.agents.config import AgentConfig
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.capabilities.skills.registry import SkillRegistry
    from agentos.capabilities.tools.registry import ToolRegistry


class ContextBuilder:
    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
        workspace_dir: str | None = None,
    ):
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.workspace_dir = workspace_dir

    def build_messages(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        context_files: list[ContextFile] | None = None,
        agent_config: AgentConfig | None = None,
    ) -> list[dict[str, Any]]:
        """构建 LLM 调用的完整消息列表"""
        # 收集工具信息（根据 agent_config 过滤）
        tool_names: list[str] = []
        tool_summaries: dict[str, str] = {}
        if self.tool_registry:
            tools = self.tool_registry.as_llm_tools()
            # 根据 agent_config 过滤工具信息注入 prompt
            if agent_config and agent_config.tools:
                allowed = set(agent_config.tools) | {"delegate"}
                tools = [t for t in tools if t["name"] in allowed]
            for t in tools:
                tool_names.append(t["name"])
                tool_summaries[t["name"]] = t.get("description", "")

        # 根据 agent_config 选择 system prompt
        base_prompt = (
            agent_config.system_prompt
            if agent_config and agent_config.system_prompt
            else config.get("agent.system_prompt", "")
        )

        # 构建委托 Agent 信息
        delegation_prompt = self._build_delegation_prompt(agent_config)

        # 合并 extra_system_prompt
        extra = config.get("agent.extra_system_prompt")
        if delegation_prompt:
            extra = f"{extra}\n\n{delegation_prompt}" if extra else delegation_prompt

        params = SystemPromptParams(
            base_prompt=base_prompt,
            tool_names=tool_names,
            tool_summaries=tool_summaries,
            skills_prompt=self._build_skills_section(agent_config),
            memory_context=memory_context,
            context_files=context_files or [],
            extra_system_prompt=extra,
            runtime_info=self._collect_runtime_info(agent_config),
            workspace_dir=self.workspace_dir,
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
        lines = ["<available_skills>"]
        for skill in skills:
            skill_md = skill.path / "SKILL.md"
            lines.append(f"- {skill.name}: {skill.description} <location>{skill_md}</location>")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def _build_delegation_prompt(self, agent_config: AgentConfig | None) -> str | None:
        """构建可委托 Agent 的信息（注入到 system prompt）"""
        if not self.agent_registry or not agent_config:
            return None
        delegatable = self.agent_registry.get_delegatable(agent_config.id)
        if not delegatable:
            return None
        lines = ["<available_agents>"]
        for agent in delegatable:
            lines.append(f"- {agent.id}: {agent.description}")
        lines.append("</available_agents>")
        lines.append("")
        lines.append("你可以使用 delegate 工具将子任务委托给以上 Agent。")
        return "\n".join(lines)

    def _collect_runtime_info(self, agent_config: AgentConfig | None = None) -> RuntimeInfo:
        """收集运行时信息"""
        model = (
            agent_config.model
            if agent_config and agent_config.model
            else config.get("agent.default_model")
        )
        return RuntimeInfo(
            os=f"{platform.system()} ({platform.machine()})",
            python=platform.python_version(),
            model=model,
            channel=None,  # 由调用方根据场景填充
        )
