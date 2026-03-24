"""编排工具：在对话中创建 Agent。

LLM 可通过此工具直接根据用户需求创建新的 Agent 配置，
无需用户手动到管理界面操作。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel

logger = logging.getLogger(__name__)


class CreateAgentTool(Tool):
    """创建新 Agent 配置"""

    name = "create_agent"
    description = (
        "创建一个新的 AI Agent。可以指定名称、描述、模型、系统提示词等参数。"
        "创建后 Agent 立即可用，可在后续对话中通过 send_message 调用。"
    )
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Agent 唯一标识，slug 格式，例如 'research-agent'、'code-reviewer'",
            },
            "name": {
                "type": "string",
                "description": "Agent 名称，人类可读",
            },
            "description": {
                "type": "string",
                "description": "Agent 描述，说明其用途和能力",
            },
            "system_prompt": {
                "type": "string",
                "description": "系统提示词，定义 Agent 的角色和行为",
            },
            "model": {
                "type": "string",
                "description": "模型名称，如 'gpt-4o-mini'、'claude-3-haiku'，留空则继承默认配置",
            },
            "temperature": {
                "type": "number",
                "description": "温度参数 (0-2)，控制输出随机性，留空则默认 0.2",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "允许使用的工具名称列表，空数组表示允许全部工具",
            },
            "can_send_message_to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可发送消息的目标 Agent ID 列表，空数组表示可向所有 Agent 发送消息",
            },
        },
        "required": ["id", "name"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from sensenova_claw.capabilities.agents.config import AgentConfig
        from sensenova_claw.capabilities.agents.registry import AgentRegistry

        registry: AgentRegistry | None = kwargs.pop("_agent_registry", None)
        kwargs.pop("_path_policy", None)
        kwargs.pop("_session_id", None)

        if not registry:
            return {"success": False, "error": "AgentRegistry 未注入，无法创建 Agent"}

        agent_id = str(kwargs.get("id", "")).strip()
        name = str(kwargs.get("name", "")).strip()

        if not agent_id or not name:
            return {"success": False, "error": "id 和 name 为必填参数"}

        if registry.get(agent_id):
            return {"success": False, "error": f"Agent '{agent_id}' 已存在"}

        # 从 default Agent 继承未指定的配置
        default = registry.get("default")
        model = kwargs.get("model") or (default.model if default else "gpt-4o-mini")
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = default.temperature if default else 0.2

        agent = AgentConfig.create(
            id=agent_id,
            name=name,
            description=str(kwargs.get("description", "")),
            model=model,
            temperature=float(temperature),
            system_prompt=str(kwargs.get("system_prompt", "")),
            tools=list(kwargs.get("tools", [])),
            can_send_message_to=list(
                kwargs.get("can_send_message_to", kwargs.get("can_delegate_to", []))
            ),
        )

        registry.register(agent)
        logger.info("Agent created via tool: %s (%s)", agent_id, name)

        return {
            "success": True,
            "agent_id": agent_id,
            "name": name,
            "model": model,
            "message": f"Agent '{name}' (id={agent_id}) 已创建成功，可通过 send_message 或新会话使用",
        }
