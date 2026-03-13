"""WorkflowRuntime — DAG 调度引擎。

职责：
1. 接收工作流执行请求
2. 按 DAG 拓扑顺序调度节点
3. 管理并行执行和聚合
4. 处理条件分支
5. 通过事件总线报告执行状态

核心算法：
- 使用就绪队列（ready queue）驱动执行
- 节点就绪条件：所有入边的源节点都已完成
- 并行：多个节点同时就绪时并发执行
- 聚合：等待所有入边完成后执行
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any, TYPE_CHECKING

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    USER_INPUT,
    WORKFLOW_NODE_COMPLETED,
    WORKFLOW_NODE_STARTED,
    WORKFLOW_RUN_COMPLETED,
    WORKFLOW_RUN_FAILED,
    WORKFLOW_RUN_STARTED,
)
from agentos.capabilities.workflows.models import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeResult,
    WorkflowRun,
)

if TYPE_CHECKING:
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.adapters.storage.repository import Repository
    from agentos.kernel.events.router import BusRouter
    from agentos.kernel.runtime.publisher import EventPublisher
    from agentos.capabilities.workflows.registry import WorkflowRegistry

logger = logging.getLogger(__name__)


class WorkflowRuntime:

    def __init__(
        self,
        agent_registry: AgentRegistry,
        workflow_registry: WorkflowRegistry,
        bus_router: BusRouter,
        repo: Repository,
        publisher: EventPublisher,
    ):
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry
        self.bus_router = bus_router
        self.repo = repo
        self.publisher = publisher
        self._active_runs: dict[str, WorkflowRun] = {}

    async def execute(
        self,
        workflow_id: str,
        input_text: str,
        session_id: str,
    ) -> WorkflowRun:
        """执行一个工作流"""
        workflow = self.workflow_registry.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        run = WorkflowRun(
            run_id=f"wf_run_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            status="running",
            input=input_text,
            started_at=time.time(),
            session_id=session_id,
        )
        self._active_runs[run.run_id] = run

        await self._emit(WORKFLOW_RUN_STARTED, session_id, {
            "run_id": run.run_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
        })

        try:
            await asyncio.wait_for(
                self._run_dag(workflow, run),
                timeout=workflow.timeout,
            )
        except asyncio.TimeoutError:
            run.status = "failed"
            await self._emit(WORKFLOW_RUN_FAILED, session_id, {
                "run_id": run.run_id,
                "error": "Workflow execution timed out",
            })
        except Exception as exc:
            run.status = "failed"
            logger.exception("Workflow execution error: %s", exc)
            await self._emit(WORKFLOW_RUN_FAILED, session_id, {
                "run_id": run.run_id,
                "error": str(exc),
            })
        finally:
            run.completed_at = time.time()
            self._active_runs.pop(run.run_id, None)

        return run

    def get_active_runs(self) -> list[WorkflowRun]:
        return list(self._active_runs.values())

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._active_runs.get(run_id)

    # ── DAG 调度核心 ──────────────────────────────────

    async def _run_dag(self, workflow: Workflow, run: WorkflowRun) -> None:
        """DAG 调度核心算法"""
        adj, in_edges = self._build_graph(workflow)
        remaining_in_degree = {n.id: len(in_edges.get(n.id, [])) for n in workflow.nodes}

        # 初始化所有节点状态
        for node in workflow.nodes:
            run.node_results[node.id] = WorkflowNodeResult(
                node_id=node.id,
                status="pending",
                agent_id=node.agent_id,
            )

        # 找到入口节点（入度为 0）
        ready_queue = [nid for nid, deg in remaining_in_degree.items() if deg == 0]

        while ready_queue and run.iteration_count < workflow.max_iterations:
            run.iteration_count += 1

            # 并行执行所有就绪节点
            tasks = []
            executing = []
            for node_id in ready_queue:
                node = self._find_node(workflow, node_id)
                if not node:
                    continue

                if self._should_skip_node(node, workflow, run):
                    run.node_results[node_id].status = "skipped"
                    executing.append(node_id)
                    continue

                tasks.append(self._execute_node(node, workflow, run))
                executing.append(node_id)

            ready_queue.clear()

            if tasks:
                await asyncio.gather(*tasks)

            # 更新入度，找到新的就绪节点
            for node_id in executing:
                for neighbor_id in adj.get(node_id, []):
                    edge = self._find_edge(workflow, node_id, neighbor_id)
                    if edge and edge.condition:
                        if not self._evaluate_condition(edge.condition, run):
                            continue
                    remaining_in_degree[neighbor_id] -= 1
                    if remaining_in_degree[neighbor_id] <= 0:
                        ready_queue.append(neighbor_id)

            # 检查是否卡住
            if not ready_queue and not self._all_exit_nodes_done(workflow, run):
                blocked = [nid for nid, deg in remaining_in_degree.items()
                           if deg > 0 and run.node_results[nid].status == "pending"]
                if blocked:
                    logger.warning("Workflow stuck: blocked nodes = %s", blocked)
                    break

        # 收集输出
        run.output = self._collect_output(workflow, run)
        run.status = "completed" if self._all_exit_nodes_done(workflow, run) else "failed"

        await self._emit(WORKFLOW_RUN_COMPLETED, run.session_id, {
            "run_id": run.run_id,
            "status": run.status,
            "output_preview": run.output[:500],
        })

    # ── 节点执行 ──────────────────────────────────────

    async def _execute_node(
        self,
        node: WorkflowNode,
        workflow: Workflow,
        run: WorkflowRun,
    ) -> None:
        """执行单个节点"""
        result = run.node_results[node.id]
        result.status = "running"
        result.started_at = time.time()

        await self._emit(WORKFLOW_NODE_STARTED, run.session_id, {
            "run_id": run.run_id,
            "node_id": node.id,
            "agent_id": node.agent_id,
        })

        try:
            input_text = self._resolve_template(node.input_template, workflow, run)

            sub_session_id = f"wf_{run.run_id}_{node.id}"
            await self.repo.create_session(
                session_id=sub_session_id,
                meta={
                    "title": f"[workflow:{workflow.id}] {node.id}",
                    "agent_id": node.agent_id,
                    "workflow_run_id": run.run_id,
                    "workflow_node_id": node.id,
                },
            )

            output = await self._run_agent_session(sub_session_id, input_text, node.timeout)
            result.output = output
            result.status = "completed"

        except asyncio.TimeoutError:
            result.status = "failed"
            result.error = f"Node timed out after {node.timeout}s"
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)

        result.completed_at = time.time()

        await self._emit(WORKFLOW_NODE_COMPLETED, run.session_id, {
            "run_id": run.run_id,
            "node_id": node.id,
            "status": result.status,
            "output_preview": result.output[:200] if result.output else "",
            "error": result.error,
        })

    async def _run_agent_session(
        self,
        session_id: str,
        input_text: str,
        timeout: float,
    ) -> str:
        """创建子 session 并等待 Agent 完成"""
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _listener():
            async for event in self.bus_router.public_bus.subscribe():
                if event.session_id != session_id:
                    continue
                if event.type == AGENT_STEP_COMPLETED:
                    content = event.payload.get("result", {}).get("content", "")
                    if not future.done():
                        future.set_result(content)
                    return
                if event.type == ERROR_RAISED:
                    if not future.done():
                        future.set_exception(
                            RuntimeError(event.payload.get("error_message", "Agent error"))
                        )
                    return

        task = asyncio.create_task(_listener())
        await asyncio.sleep(0)

        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        await self.bus_router.public_bus.publish(EventEnvelope(
            type=USER_INPUT,
            session_id=session_id,
            turn_id=turn_id,
            source="workflow",
            payload={"content": input_text},
        ))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # ── 模板解析 ──────────────────────────────────────

    def _resolve_template(
        self, template: str, workflow: Workflow, run: WorkflowRun,
    ) -> str:
        """解析输入模板中的变量引用

        支持的变量：
        - {workflow.input}  → 工作流的初始输入
        - {node_id.output}  → 某个节点的完整输出
        """
        result = template
        result = result.replace("{workflow.input}", run.input)

        for node_id, node_result in run.node_results.items():
            placeholder = f"{{{node_id}.output}}"
            if placeholder in result:
                result = result.replace(placeholder, node_result.output or "(无输出)")

        return result

    # ── 条件评估 ──────────────────────────────────────

    def _evaluate_condition(self, condition: str, run: WorkflowRun) -> bool:
        """评估条件表达式

        支持的语法：
        - "{node_id.output} contains '关键词'"
        - "{node_id.status} == 'completed'"
        """
        resolved = condition
        for node_id, node_result in run.node_results.items():
            resolved = resolved.replace(f"{{{node_id}.output}}", node_result.output or "")
            resolved = resolved.replace(f"{{{node_id}.status}}", node_result.status)

        if " contains " in resolved:
            parts = resolved.split(" contains ", 1)
            return parts[1].strip("'\"") in parts[0]
        if " == " in resolved:
            parts = resolved.split(" == ", 1)
            return parts[0].strip() == parts[1].strip("'\"")

        return True  # 无法解析的条件默认为真

    # ── 图操作辅助 ────────────────────────────────────

    def _build_graph(self, workflow: Workflow):
        adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
        in_edges: dict[str, list[WorkflowEdge]] = {n.id: [] for n in workflow.nodes}
        for edge in workflow.edges:
            adj[edge.from_node].append(edge.to_node)
            in_edges[edge.to_node].append(edge)
        return adj, in_edges

    def _find_node(self, workflow: Workflow, node_id: str) -> WorkflowNode | None:
        return next((n for n in workflow.nodes if n.id == node_id), None)

    def _find_edge(self, workflow: Workflow, from_id: str, to_id: str) -> WorkflowEdge | None:
        return next((e for e in workflow.edges
                      if e.from_node == from_id and e.to_node == to_id), None)

    def _should_skip_node(self, node: WorkflowNode, workflow: Workflow, run: WorkflowRun) -> bool:
        """判断节点是否应被跳过（所有入边的条件都不满足）"""
        in_edges = [e for e in workflow.edges if e.to_node == node.id]
        if not in_edges:
            return False
        conditional_edges = [e for e in in_edges if e.condition]
        if not conditional_edges:
            return False
        return not any(self._evaluate_condition(e.condition, run) for e in conditional_edges)

    def _all_exit_nodes_done(self, workflow: Workflow, run: WorkflowRun) -> bool:
        exit_ids = workflow.exit_nodes or [
            n.id for n in workflow.nodes
            if not any(e.from_node == n.id for e in workflow.edges)
        ]
        return all(
            run.node_results.get(nid, WorkflowNodeResult(node_id=nid, status="pending")).status
            in ("completed", "skipped")
            for nid in exit_ids
        )

    def _collect_output(self, workflow: Workflow, run: WorkflowRun) -> str:
        """收集出口节点的输出作为工作流最终输出"""
        exit_ids = workflow.exit_nodes or [
            n.id for n in workflow.nodes
            if not any(e.from_node == n.id for e in workflow.edges)
        ]
        outputs = []
        for nid in exit_ids:
            result = run.node_results.get(nid)
            if result and result.output:
                outputs.append(result.output)
        return "\n\n".join(outputs)

    async def _emit(self, event_type: str, session_id: str, payload: dict) -> None:
        """发布工作流事件到公共总线"""
        await self.publisher.publish(EventEnvelope(
            type=event_type,
            session_id=session_id,
            source="workflow",
            payload=payload,
        ))
