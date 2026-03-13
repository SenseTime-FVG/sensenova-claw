"""编排工具：在对话中创建 Agent 和 Workflow。

LLM 可通过这两个工具直接根据用户需求创建新的 Agent 配置或 Workflow 定义，
无需用户手动到管理界面操作。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agentos.capabilities.tools.base import Tool, ToolRiskLevel

logger = logging.getLogger(__name__)


class CreateAgentTool(Tool):
    """创建新 Agent 配置"""

    name = "create_agent"
    description = (
        "创建一个新的 AI Agent。可以指定名称、描述、模型、系统提示词等参数。"
        "创建后 Agent 立即可用，可在后续对话中通过委托机制调用。"
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
            "provider": {
                "type": "string",
                "description": "LLM 提供商，如 'openai'、'anthropic'，留空则继承默认配置",
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
            "can_delegate_to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可委托的目标 Agent ID 列表，空数组表示可委托给所有",
            },
        },
        "required": ["id", "name"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agentos.capabilities.agents.config import AgentConfig
        from agentos.capabilities.agents.registry import AgentRegistry

        registry: AgentRegistry | None = kwargs.pop("_agent_registry", None)
        kwargs.pop("_workflow_registry", None)
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
        provider = kwargs.get("provider") or (default.provider if default else "openai")
        model = kwargs.get("model") or (default.model if default else "gpt-4o-mini")
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = default.temperature if default else 0.2

        agent = AgentConfig.create(
            id=agent_id,
            name=name,
            description=str(kwargs.get("description", "")),
            provider=provider,
            model=model,
            temperature=float(temperature),
            system_prompt=str(kwargs.get("system_prompt", "")),
            tools=list(kwargs.get("tools", [])),
            can_delegate_to=list(kwargs.get("can_delegate_to", [])),
        )

        registry.register(agent)
        registry.save(agent)
        logger.info("Agent created via tool: %s (%s)", agent_id, name)

        return {
            "success": True,
            "agent_id": agent_id,
            "name": name,
            "provider": provider,
            "model": model,
            "message": f"Agent '{name}' (id={agent_id}) 已创建成功，可在委托或新会话中使用",
        }


class CreateWorkflowTool(Tool):
    """创建新 Workflow 定义"""

    name = "create_workflow"
    description = (
        "创建一个多步骤工作流（DAG）。工作流由多个节点（每个节点绑定一个 Agent）和边（连接节点的执行路径）组成。"
        "创建后可通过 Workflow 运行接口执行。"
    )
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Workflow 唯一标识，slug 格式，例如 'data-pipeline'",
            },
            "name": {
                "type": "string",
                "description": "Workflow 名称",
            },
            "description": {
                "type": "string",
                "description": "Workflow 描述",
            },
            "nodes": {
                "type": "array",
                "description": "节点列表，每个节点包含 id、agent_id、description、input_template 字段",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "节点 ID"},
                        "agent_id": {"type": "string", "description": "执行该节点的 Agent ID，默认 'default'"},
                        "description": {"type": "string", "description": "节点描述"},
                        "input_template": {
                            "type": "string",
                            "description": "输入模板，支持变量如 {workflow.input}、{node_id.output}",
                        },
                        "timeout": {"type": "number", "description": "超时秒数，默认 300"},
                        "retry": {"type": "integer", "description": "重试次数，默认 0"},
                    },
                    "required": ["id"],
                },
            },
            "edges": {
                "type": "array",
                "description": "边列表，定义节点间的执行路径",
                "items": {
                    "type": "object",
                    "properties": {
                        "from_node": {"type": "string", "description": "起始节点 ID"},
                        "to_node": {"type": "string", "description": "目标节点 ID"},
                        "condition": {"type": "string", "description": "条件表达式（可选）"},
                        "label": {"type": "string", "description": "边标签（可选）"},
                    },
                    "required": ["from_node", "to_node"],
                },
            },
            "entry_node": {
                "type": "string",
                "description": "入口节点 ID，留空则自动检测（无入度节点）",
            },
            "exit_nodes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "出口节点 ID 列表，留空则自动检测（无出度节点）",
            },
            "max_iterations": {
                "type": "integer",
                "description": "最大迭代次数，默认 10",
            },
            "timeout": {
                "type": "number",
                "description": "整体超时秒数，默认 1800",
            },
        },
        "required": ["id", "name", "nodes"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agentos.capabilities.workflows.models import Workflow, WorkflowEdge, WorkflowNode
        from agentos.capabilities.workflows.registry import WorkflowRegistry

        registry: WorkflowRegistry | None = kwargs.pop("_workflow_registry", None)
        kwargs.pop("_agent_registry", None)
        kwargs.pop("_path_policy", None)
        kwargs.pop("_session_id", None)

        if not registry:
            return {"success": False, "error": "WorkflowRegistry 未注入，无法创建 Workflow"}

        wf_id = str(kwargs.get("id", "")).strip()
        name = str(kwargs.get("name", "")).strip()

        if not wf_id or not name:
            return {"success": False, "error": "id 和 name 为必填参数"}

        if registry.get(wf_id):
            return {"success": False, "error": f"Workflow '{wf_id}' 已存在"}

        raw_nodes = kwargs.get("nodes", [])
        raw_edges = kwargs.get("edges", [])

        if not raw_nodes:
            return {"success": False, "error": "至少需要一个节点"}

        now = time.time()

        try:
            nodes = [
                WorkflowNode(
                    id=str(n.get("id", "")),
                    agent_id=str(n.get("agent_id", "default")),
                    input_template=str(n.get("input_template", "")),
                    description=str(n.get("description", "")),
                    timeout=float(n.get("timeout", 300)),
                    retry=int(n.get("retry", 0)),
                    node_type=str(n.get("node_type", "agent")),
                )
                for n in raw_nodes
            ]
        except Exception as e:
            return {"success": False, "error": f"节点格式错误: {e}"}

        try:
            edges = [
                WorkflowEdge(
                    from_node=str(e.get("from_node", "")),
                    to_node=str(e.get("to_node", "")),
                    condition=e.get("condition"),
                    label=str(e.get("label", "")),
                )
                for e in raw_edges
            ]
        except Exception as e:
            return {"success": False, "error": f"边格式错误: {e}"}

        wf = Workflow(
            id=wf_id,
            name=name,
            description=str(kwargs.get("description", "")),
            version=str(kwargs.get("version", "1.0")),
            nodes=nodes,
            edges=edges,
            entry_node=str(kwargs.get("entry_node", "")),
            exit_nodes=list(kwargs.get("exit_nodes", [])),
            max_iterations=int(kwargs.get("max_iterations", 10)),
            timeout=float(kwargs.get("timeout", 1800)),
            enabled=True,
            created_at=now,
            updated_at=now,
        )

        registry.register(wf)
        registry.save(wf)
        logger.info("Workflow created via tool: %s (%s) with %d nodes, %d edges",
                     wf_id, name, len(nodes), len(edges))

        return {
            "success": True,
            "workflow_id": wf_id,
            "name": name,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "message": f"Workflow '{name}' (id={wf_id}) 已创建成功，包含 {len(nodes)} 个节点和 {len(edges)} 条边",
        }
