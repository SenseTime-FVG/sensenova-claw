"""W01: Workflow 数据模型 roundtrip"""
from agentos.capabilities.workflows.models import (
    Workflow, WorkflowNode, WorkflowEdge,
    WorkflowRun, WorkflowNodeResult,
)


class TestWorkflowModels:
    def test_node_roundtrip(self):
        n = WorkflowNode(id="n1", agent_id="default", input_template="{input}")
        d = n.to_dict()
        n2 = WorkflowNode.from_dict(d)
        assert n2.input_template == "{input}"
        assert n2.agent_id == "default"

    def test_edge_roundtrip(self):
        e = WorkflowEdge(from_node="a", to_node="b", condition="ok")
        d = e.to_dict()
        e2 = WorkflowEdge.from_dict(d)
        assert e2.condition == "ok"
        assert e2.from_node == "a"
        assert e2.to_node == "b"

    def test_edge_from_key_compat(self):
        """支持 from/to 的 key（JSON 序列化结果）"""
        e = WorkflowEdge.from_dict({"from": "x", "to": "y"})
        assert e.from_node == "x"
        assert e.to_node == "y"

    def test_workflow_roundtrip(self):
        wf = Workflow(
            id="w", name="W",
            nodes=[WorkflowNode(id="n1")],
            edges=[WorkflowEdge(from_node="n1", to_node="n1")],
            entry_node="n1", exit_nodes=["n1"],
        )
        r = Workflow.from_dict(wf.to_dict())
        assert len(r.nodes) == 1
        assert r.entry_node == "n1"

    def test_run_to_dict(self):
        run = WorkflowRun(
            run_id="r", workflow_id="w", status="completed",
            node_results={"n1": WorkflowNodeResult(node_id="n1", status="completed")},
        )
        d = run.to_dict()
        assert d["status"] == "completed"
        assert "n1" in d["node_results"]
        assert d["node_results"]["n1"]["status"] == "completed"

    def test_node_defaults(self):
        n = WorkflowNode(id="x")
        assert n.agent_id == "default"
        assert n.timeout == 300
        assert n.node_type == "agent"
        assert n.allow_tools is True
