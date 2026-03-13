"""W02: WorkflowRegistry CRUD + DAG 验证"""
import pytest
from pathlib import Path
from app.workflows.models import Workflow, WorkflowNode, WorkflowEdge
from app.workflows.registry import WorkflowRegistry


class TestWorkflowRegistry:
    def test_register_get(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="w1", name="W1",
                      nodes=[WorkflowNode(id="n1")],
                      edges=[], entry_node="n1", exit_nodes=["n1"])
        r.register(wf)
        assert r.get("w1").name == "W1"

    def test_list_all(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf1 = Workflow(id="a", name="A", nodes=[WorkflowNode(id="n")], edges=[])
        wf2 = Workflow(id="b", name="B", nodes=[WorkflowNode(id="n")], edges=[], enabled=False)
        r.register(wf1)
        r.register(wf2)
        assert len(r.list_all()) == 1  # 只返回 enabled

    def test_delete(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="d1", name="D", nodes=[WorkflowNode(id="n")], edges=[])
        r.register(wf)
        assert r.delete("d1") is True
        assert r.get("d1") is None
        assert r.delete("d1") is False

    def test_update(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="u1", name="Old", nodes=[WorkflowNode(id="n")], edges=[])
        r.register(wf)
        r.update("u1", {"name": "New"})
        assert r.get("u1").name == "New"

    def test_update_nonexist(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        assert r.update("nope", {"name": "X"}) is None

    def test_duplicate_node_ids_rejected(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="dup", name="D",
                      nodes=[WorkflowNode(id="n"), WorkflowNode(id="n")],
                      edges=[])
        with pytest.raises(ValueError, match="Duplicate"):
            r.register(wf)

    def test_invalid_edge_ref_rejected(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="bad", name="B",
                      nodes=[WorkflowNode(id="n1")],
                      edges=[WorkflowEdge(from_node="n1", to_node="n2")])
        with pytest.raises(ValueError, match="unknown node"):
            r.register(wf)

    def test_invalid_entry_node_rejected(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="entry", name="E",
                      nodes=[WorkflowNode(id="n1")],
                      edges=[], entry_node="n_bad")
        with pytest.raises(ValueError, match="Entry node"):
            r.register(wf)

    def test_cycle_detected(self, tmp_path):
        r = WorkflowRegistry(config_dir=tmp_path / "w")
        wf = Workflow(id="cyc", name="C",
                      nodes=[WorkflowNode(id="a"), WorkflowNode(id="b")],
                      edges=[
                          WorkflowEdge(from_node="a", to_node="b"),
                          WorkflowEdge(from_node="b", to_node="a"),
                      ])
        with pytest.raises(ValueError, match="cycle"):
            r.register(wf)

    def test_save_and_load(self, tmp_path):
        d = tmp_path / "w"
        r1 = WorkflowRegistry(config_dir=d)
        wf = Workflow(id="sl", name="SL",
                      nodes=[WorkflowNode(id="n1"), WorkflowNode(id="n2")],
                      edges=[WorkflowEdge(from_node="n1", to_node="n2")],
                      entry_node="n1", exit_nodes=["n2"])
        r1.register(wf)
        r1.save(wf)

        r2 = WorkflowRegistry(config_dir=d)
        r2.load_from_dir()
        assert r2.get("sl").name == "SL"
