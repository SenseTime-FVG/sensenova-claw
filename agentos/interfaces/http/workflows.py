"""
Workflow API — 工作流定义 CRUD 与执行管理
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agentos.capabilities.workflows.models import Workflow, WorkflowNode, WorkflowEdge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _get_workflow_registry(request: Request):
    return request.app.state.workflow_registry


def _get_workflow_runtime(request: Request):
    return request.app.state.workflow_runtime


# ── Pydantic 模型 ──────────────────────────────────


class WorkflowNodeCreate(BaseModel):
    id: str
    agent_id: str = "default"
    input_template: str = ""
    description: str = ""
    timeout: float = 300
    retry: int = 0
    node_type: str = "agent"


class WorkflowEdgeCreate(BaseModel):
    from_node: str
    to_node: str
    condition: str | None = None
    label: str = ""


class WorkflowCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    nodes: list[WorkflowNodeCreate] = []
    edges: list[WorkflowEdgeCreate] = []
    entry_node: str = ""
    exit_nodes: list[str] = []
    max_iterations: int = 10
    timeout: float = 1800


class WorkflowRunRequest(BaseModel):
    input: str
    session_id: str | None = None


# ── 路由 ──────────────────────────────────────────


@router.get("")
async def list_workflows(request: Request):
    """列出所有 Workflow"""
    registry = _get_workflow_registry(request)
    workflows = registry.list_all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "version": w.version,
            "nodeCount": len(w.nodes),
            "edgeCount": len(w.edges),
            "enabled": w.enabled,
            "createdAt": w.created_at,
            "updatedAt": w.updated_at,
        }
        for w in workflows
    ]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, request: Request):
    """获取 Workflow 定义"""
    registry = _get_workflow_registry(request)
    wf = registry.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return wf.to_dict()


@router.post("")
async def create_workflow(body: WorkflowCreate, request: Request):
    """创建新 Workflow"""
    registry = _get_workflow_registry(request)

    if registry.get(body.id):
        raise HTTPException(status_code=409, detail=f"Workflow '{body.id}' already exists")

    now = time.time()
    nodes = [
        WorkflowNode(
            id=n.id,
            agent_id=n.agent_id,
            input_template=n.input_template,
            description=n.description,
            timeout=n.timeout,
            retry=n.retry,
            node_type=n.node_type,
        )
        for n in body.nodes
    ]
    edges = [
        WorkflowEdge(
            from_node=e.from_node,
            to_node=e.to_node,
            condition=e.condition,
            label=e.label,
        )
        for e in body.edges
    ]
    workflow = Workflow(
        id=body.id,
        name=body.name,
        description=body.description,
        version=body.version,
        nodes=nodes,
        edges=edges,
        entry_node=body.entry_node,
        exit_nodes=body.exit_nodes,
        max_iterations=body.max_iterations,
        timeout=body.timeout,
        created_at=now,
        updated_at=now,
    )

    try:
        registry.register(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    registry.save(workflow)
    logger.info("Created workflow: %s", workflow.id)
    return workflow.to_dict()


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowCreate, request: Request):
    """更新 Workflow 定义（全量替换）"""
    registry = _get_workflow_registry(request)
    if not registry.get(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    # 删除旧的，注册新的
    registry.delete(workflow_id)

    now = time.time()
    nodes = [
        WorkflowNode(
            id=n.id,
            agent_id=n.agent_id,
            input_template=n.input_template,
            description=n.description,
            timeout=n.timeout,
            retry=n.retry,
            node_type=n.node_type,
        )
        for n in body.nodes
    ]
    edges = [
        WorkflowEdge(
            from_node=e.from_node,
            to_node=e.to_node,
            condition=e.condition,
            label=e.label,
        )
        for e in body.edges
    ]
    workflow = Workflow(
        id=body.id,
        name=body.name,
        description=body.description,
        version=body.version,
        nodes=nodes,
        edges=edges,
        entry_node=body.entry_node,
        exit_nodes=body.exit_nodes,
        max_iterations=body.max_iterations,
        timeout=body.timeout,
        created_at=now,
        updated_at=now,
    )

    try:
        registry.register(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    registry.save(workflow)
    return workflow.to_dict()


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request):
    """删除 Workflow"""
    registry = _get_workflow_registry(request)
    if not registry.delete(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    logger.info("Deleted workflow: %s", workflow_id)
    return {"status": "deleted", "workflow_id": workflow_id}


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: WorkflowRunRequest, request: Request):
    """手动触发 Workflow 执行"""
    registry = _get_workflow_registry(request)
    runtime = _get_workflow_runtime(request)

    if not registry.get(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    session_id = body.session_id or f"wf_sess_{workflow_id}"

    try:
        run = await runtime.execute(workflow_id, body.input, session_id)
        return run.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/runs/active")
async def list_active_runs(request: Request):
    """列出所有活跃的执行记录"""
    runtime = _get_workflow_runtime(request)
    runs = runtime.get_active_runs()
    return [r.to_dict() for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    """获取执行详情"""
    runtime = _get_workflow_runtime(request)
    run = runtime.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found or already completed")
    return run.to_dict()
