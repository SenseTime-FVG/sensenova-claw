"""X03: Workflow 节点委托嵌套"""
import pytest
from pathlib import Path
from app.workflows.models import Workflow, WorkflowNode, WorkflowEdge
from app.workflows.registry import WorkflowRegistry
from app.agents.config import AgentConfig
from app.agents.registry import AgentRegistry


class TestWorkflowDelegation:
    def test_workflow_nodes_can_use_different_agents(self, tmp_path):
        """Workflow 的不同节点可以绑定不同 Agent"""
        reg = AgentRegistry(config_dir=tmp_path / "agents")
        reg.register(AgentConfig.create(id="research", name="Research Agent"))
        reg.register(AgentConfig.create(id="writer", name="Writer Agent"))

        wf = Workflow(
            id="multi_agent_wf", name="Multi Agent Workflow",
            nodes=[
                WorkflowNode(id="research", agent_id="research",
                             input_template="Research: {workflow.input}"),
                WorkflowNode(id="write", agent_id="writer",
                             input_template="Write based on: {research.output}"),
            ],
            edges=[WorkflowEdge(from_node="research", to_node="write")],
            entry_node="research",
            exit_nodes=["write"],
        )

        wf_reg = WorkflowRegistry(config_dir=tmp_path / "workflows")
        wf_reg.register(wf)

        retrieved = wf_reg.get("multi_agent_wf")
        assert len(retrieved.nodes) == 2
        assert retrieved.nodes[0].agent_id == "research"
        assert retrieved.nodes[1].agent_id == "writer"

    def test_workflow_delegation_depth_config(self, tmp_path):
        """Agent 可以限制委托深度"""
        reg = AgentRegistry(config_dir=tmp_path / "agents")
        reg.register(AgentConfig.create(id="shallow", name="S", max_delegation_depth=1))
        reg.register(AgentConfig.create(id="deep", name="D", max_delegation_depth=5))

        assert reg.get("shallow").max_delegation_depth == 1
        assert reg.get("deep").max_delegation_depth == 5

    def test_workflow_conditional_edges(self, tmp_path):
        """带条件边的 DAG 验证应通过"""
        wf = Workflow(
            id="cond_wf", name="Conditional",
            nodes=[
                WorkflowNode(id="check"),
                WorkflowNode(id="yes"),
                WorkflowNode(id="no"),
            ],
            edges=[
                WorkflowEdge(from_node="check", to_node="yes", condition="ok"),
                WorkflowEdge(from_node="check", to_node="no", condition="fail"),
            ],
            entry_node="check",
            exit_nodes=["yes", "no"],
        )

        wf_reg = WorkflowRegistry(config_dir=tmp_path / "workflows")
        wf_reg.register(wf)  # 不应抛异常
        assert wf_reg.get("cond_wf") is not None
