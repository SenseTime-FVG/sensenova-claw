"""WorkflowTool — 让 Agent 能触发预定义工作流。"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from agentos.capabilities.tools.base import Tool, ToolRiskLevel

if TYPE_CHECKING:
    from agentos.capabilities.workflows.runtime import WorkflowRuntime


class WorkflowTool(Tool):
    name = "run_workflow"
    description = (
        "启动一个预定义的工作流。"
        "workflow_id: 工作流 ID。"
        "input: 传递给工作流的输入文本。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "工作流 ID",
            },
            "input": {
                "type": "string",
                "description": "传递给工作流的输入",
            },
        },
        "required": ["workflow_id", "input"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, workflow_runtime: WorkflowRuntime):
        self._runtime = workflow_runtime

    async def execute(self, **kwargs: Any) -> Any:
        workflow_id = kwargs.get("workflow_id", "")
        input_text = kwargs.get("input", "")
        session_id = kwargs.get("_session_id", "")

        try:
            run = await self._runtime.execute(workflow_id, input_text, session_id)
            return {
                "success": run.status == "completed",
                "run_id": run.run_id,
                "status": run.status,
                "output": run.output,
                "node_count": len(run.node_results),
                "duration": round(run.completed_at - run.started_at, 2),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
