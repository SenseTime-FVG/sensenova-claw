"""WorkflowRegistry — 管理 Workflow 定义的注册表。

职责：
1. CRUD Workflow 定义
2. 从 YAML 文件加载 Workflow
3. 验证 Workflow 的 DAG 合法性（无环、入口/出口正确、节点 ID 唯一）
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from agentos.capabilities.workflows.models import Workflow, WorkflowEdge, WorkflowNode

logger = logging.getLogger(__name__)


class WorkflowRegistry:

    def __init__(self, config_dir: Path):
        self._workflows: dict[str, Workflow] = {}
        self._config_dir = config_dir

    # ── CRUD ──────────────────────────────────────────

    def register(self, workflow: Workflow) -> None:
        """注册工作流（含 DAG 合法性验证）"""
        self._validate(workflow)
        self._workflows[workflow.id] = workflow

    def get(self, workflow_id: str) -> Workflow | None:
        return self._workflows.get(workflow_id)

    def list_all(self) -> list[Workflow]:
        return [w for w in self._workflows.values() if w.enabled]

    def delete(self, workflow_id: str) -> bool:
        wf = self._workflows.pop(workflow_id, None)
        if wf is None:
            return False
        fp = self._config_dir / f"{workflow_id}.yaml"
        if fp.exists():
            fp.unlink()
        fp_json = self._config_dir / f"{workflow_id}.json"
        if fp_json.exists():
            fp_json.unlink()
        return True

    def update(self, workflow_id: str, updates: dict[str, Any]) -> Workflow | None:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        for key, value in updates.items():
            if hasattr(wf, key) and key not in ("id", "created_at"):
                setattr(wf, key, value)
        wf.updated_at = time.time()
        return wf

    # ── DAG 验证 ──────────────────────────────────────

    def _validate(self, workflow: Workflow) -> None:
        """验证 DAG 合法性"""
        node_ids = {n.id for n in workflow.nodes}

        # 1. 节点 ID 唯一
        if len(node_ids) != len(workflow.nodes):
            raise ValueError("Duplicate node IDs detected")

        # 2. 边引用的节点必须存在
        for edge in workflow.edges:
            if edge.from_node not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.from_node}")
            if edge.to_node not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.to_node}")

        # 3. 入口节点必须存在
        if workflow.entry_node and workflow.entry_node not in node_ids:
            raise ValueError(f"Entry node not found: {workflow.entry_node}")

        # 4. DAG 无环检测（拓扑排序）
        self._check_acyclic(workflow)

    def _check_acyclic(self, workflow: Workflow) -> None:
        """拓扑排序检测环"""
        adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
        in_degree: dict[str, int] = {n.id: 0 for n in workflow.nodes}
        for edge in workflow.edges:
            adj[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            nid = queue.pop(0)
            visited += 1
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(workflow.nodes):
            raise ValueError("Workflow contains a cycle")

    # ── 从磁盘加载 ──────────────────────────────────

    def load_from_dir(self, directory: Path | None = None) -> None:
        """从目录加载 YAML/JSON 格式的 Workflow 定义"""
        target = directory or self._config_dir
        if not target.exists():
            return
        for fp in list(target.glob("*.yaml")) + list(target.glob("*.yml")):
            try:
                data = yaml.safe_load(fp.read_text(encoding="utf-8"))
                if not data or not isinstance(data, dict):
                    continue
                workflow = Workflow.from_dict(data)
                self.register(workflow)
                logger.info("Loaded workflow from YAML: %s", fp.name)
            except Exception:
                logger.exception("Failed to load workflow from %s", fp)

        for fp in target.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                workflow = Workflow.from_dict(data)
                self.register(workflow)
                logger.info("Loaded workflow from JSON: %s", fp.name)
            except Exception:
                logger.exception("Failed to load workflow from %s", fp)

    def save(self, workflow: Workflow) -> None:
        """持久化 Workflow 定义到磁盘（YAML 格式）"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        fp = self._config_dir / f"{workflow.id}.yaml"
        fp.write_text(
            yaml.dump(workflow.to_dict(), allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
