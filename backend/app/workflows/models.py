"""Workflow 数据模型定义。

包含工作流定义（Workflow / WorkflowNode / WorkflowEdge）
和执行实例（WorkflowRun / WorkflowNodeResult）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class WorkflowNode:
    """工作流节点：一个执行单元"""

    id: str                                   # 节点唯一 ID
    agent_id: str = "default"                 # 绑定的 Agent ID
    input_template: str = ""                  # 输入模板，支持 {var} 变量引用
    description: str = ""                     # 节点描述

    # 执行配置
    timeout: float = 300                      # 单节点超时（秒）
    retry: int = 0                            # 失败重试次数
    allow_tools: bool = True                  # 是否允许使用工具

    # 特殊节点类型
    node_type: Literal["agent", "condition", "merge"] = "agent"

    # condition 节点专用
    condition_expr: str = ""

    # merge 节点专用
    merge_strategy: Literal["concat", "template"] = "template"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "input_template": self.input_template,
            "description": self.description,
            "timeout": self.timeout,
            "retry": self.retry,
            "allow_tools": self.allow_tools,
            "node_type": self.node_type,
            "condition_expr": self.condition_expr,
            "merge_strategy": self.merge_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        return cls(
            id=data["id"],
            agent_id=data.get("agent_id", "default"),
            input_template=data.get("input_template", data.get("input", "")),
            description=data.get("description", ""),
            timeout=data.get("timeout", 300),
            retry=data.get("retry", 0),
            allow_tools=data.get("allow_tools", True),
            node_type=data.get("node_type", "agent"),
            condition_expr=data.get("condition_expr", ""),
            merge_strategy=data.get("merge_strategy", "template"),
        )


@dataclass
class WorkflowEdge:
    """工作流边：连接两个节点"""

    from_node: str
    to_node: str
    condition: str | None = None              # 条件表达式
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "from": self.from_node,
            "to": self.to_node,
        }
        if self.condition:
            d["condition"] = self.condition
        if self.label:
            d["label"] = self.label
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEdge:
        return cls(
            from_node=data.get("from_node", data.get("from", "")),
            to_node=data.get("to_node", data.get("to", "")),
            condition=data.get("condition"),
            label=data.get("label", ""),
        )


@dataclass
class Workflow:
    """工作流定义"""

    id: str
    name: str
    description: str = ""
    version: str = "1.0"

    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)

    entry_node: str = ""
    exit_nodes: list[str] = field(default_factory=list)

    max_iterations: int = 10
    timeout: float = 1800

    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "entry_node": self.entry_node,
            "exit_nodes": list(self.exit_nodes),
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        now = time.time()
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            nodes=[WorkflowNode.from_dict(n) for n in data.get("nodes", [])],
            edges=[WorkflowEdge.from_dict(e) for e in data.get("edges", [])],
            entry_node=data.get("entry_node", ""),
            exit_nodes=list(data.get("exit_nodes", [])),
            max_iterations=data.get("max_iterations", 10),
            timeout=data.get("timeout", 1800),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", now),
            updated_at=data.get("updated_at", now),
        )


@dataclass
class WorkflowNodeResult:
    """节点执行结果"""

    node_id: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    output: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "agent_id": self.agent_id,
        }


@dataclass
class WorkflowRun:
    """一次工作流执行实例"""

    run_id: str
    workflow_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    input: str = ""
    output: str = ""
    node_results: dict[str, WorkflowNodeResult] = field(default_factory=dict)
    iteration_count: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "node_results": {k: v.to_dict() for k, v in self.node_results.items()},
            "iteration_count": self.iteration_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "session_id": self.session_id,
        }
