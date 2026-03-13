# 彻底测试方案

> 版本: v1.5 | 日期: 2026-03-12
>
> 2026-03-14 更新：当前自动化测试的唯一正式根目录为 `tests/`。`test/` 目录仅保留兼容脚本与历史材料，不再作为 pytest 主入口。agent 核心 LLM 链路现由 `tests/e2e/test_agent_llm_core_flow.py` 覆盖“首轮 LLM -> 工具调用 -> 二轮 LLM -> 最终完成”。

---

## 1. 目录结构

```
D:\code\agentos\test\
├── conftest.py                  # 全局 fixtures
├── helpers.py                   # 辅助函数
├── generate_matrix.py           # 结果汇总脚本
├── run_all.ps1                  # Windows 一键运行
├── results/                     # 测试结果输出
│
├── unit/                        # L1 单元测试
│   ├── test_event_envelope.py
│   ├── test_event_bus.py
│   ├── test_config.py
│   ├── test_repository.py
│   ├── test_agent_config.py
│   ├── test_agent_registry.py
│   ├── test_workflow_models.py
│   ├── test_workflow_registry.py
│   ├── test_tool_registry.py
│   ├── test_skill_registry.py
│   ├── test_skill_arg_substitutor.py
│   ├── test_path_policy.py
│   ├── test_deny_list.py
│   ├── test_prompt_builder.py
│   ├── test_context_builder.py
│   ├── test_cron_models.py
│   ├── test_cron_scheduler.py
│   ├── test_heartbeat_protocol.py
│   └── test_cli_commands.py
│
├── integration/                 # L2 集成测试
│   ├── test_bus_router.py
│   ├── test_tool_execution.py
│   ├── test_tool_confirmation.py
│   ├── test_delegate_tool.py
│   ├── test_workflow_runtime.py
│   ├── test_path_policy_tools.py
│   ├── test_gateway_channel.py
│   └── test_cli_app.py
│
├── api/                         # L3 API 测试
│   ├── test_agents_api.py
│   ├── test_tools_api.py
│   ├── test_skills_api.py
│   ├── test_workflows_api.py
│   ├── test_workspace_api.py
│   ├── test_sessions_api.py
│   └── test_websocket_protocol.py
│
├── e2e/                         # L4 端到端
│   ├── backend/
│   │   ├── test_chat_flow.py
│   │   └── test_multi_agent.py
│   ├── cli/
│   │   └── test_cli_script_mode.py
│   └── frontend/
│       ├── test_chat.spec.ts
│       ├── test_agents.spec.ts
│       ├── test_skills.spec.ts
│       ├── test_workflows.spec.ts
│       └── test_navigation.spec.ts
│
└── cross_feature/               # 跨功能冲突
    ├── test_agent_skill.py
    ├── test_agent_path_policy.py
    └── test_workflow_delegation.py
```

---

## 2. 功能覆盖清单

每行 = 一个必须有测试用例覆盖的功能点。

### 基础架构

| ID | 功能 | 测试文件 |
|----|------|---------|
| B01 | EventEnvelope 创建/序列化 | unit/test_event_envelope |
| B02 | PublicEventBus 发布/订阅 | unit/test_event_bus |
| B03 | PrivateEventBus 会话隔离 | unit/test_event_bus |
| B04 | BusRouter Public↔Private 路由 | integration/test_bus_router |
| B05 | Repository CRUD | unit/test_repository |
| B06 | Config 加载 + 环境变量替换 | unit/test_config |
| B07 | PromptBuilder | unit/test_prompt_builder |
| B08 | ContextBuilder | unit/test_context_builder |

### 工具系统

| ID | 功能 | 测试文件 |
|----|------|---------|
| T01 | bash_command + PathPolicy | integration/test_path_policy_tools |
| T02 | read_file + PathPolicy | integration/test_path_policy_tools |
| T03 | write_file + PathPolicy | integration/test_path_policy_tools |
| T04 | ToolRegistry 注册/发现 | unit/test_tool_registry |
| T05 | 工具确认流程(HIGH risk) | integration/test_tool_confirmation |
| T06 | 工具结果截断 | integration/test_tool_execution |

### 多 Agent (v1.0)

| ID | 功能 | 测试文件 |
|----|------|---------|
| A01 | AgentConfig to_dict/from_dict | unit/test_agent_config |
| A02 | AgentRegistry CRUD + 持久化 | unit/test_agent_registry |
| A03 | AgentRegistry 从 config.yml 加载 | unit/test_agent_registry |
| A04 | AgentRegistry 委托发现 | unit/test_agent_registry |
| A05 | DelegateTool 执行 + 深度限制 | integration/test_delegate_tool |
| A06 | Agent API 全部端点 | api/test_agents_api |
| A07 | WS create_session agent_id | api/test_websocket_protocol |
| A08 | WS list_agents | api/test_websocket_protocol |

### Workflow (v1.0)

| ID | 功能 | 测试文件 |
|----|------|---------|
| W01 | 数据模型 roundtrip | unit/test_workflow_models |
| W02 | WorkflowRegistry CRUD | unit/test_workflow_registry |
| W03 | WorkflowRuntime DAG 调度 | integration/test_workflow_runtime |
| W04 | Workflow API 全部端点 | api/test_workflows_api |
| W05 | WS run_workflow | api/test_websocket_protocol |

### Skills 市场 (v1.1)

| ID | 功能 | 测试文件 |
|----|------|---------|
| S01 | SkillRegistry 加载/分类/启停 | unit/test_skill_registry |
| S02 | ArgSubstitutor | unit/test_skill_arg_substitutor |
| S03 | Skills API 全部端点 | api/test_skills_api |

### PathPolicy (v1.2)

| ID | 功能 | 测试文件 |
|----|------|---------|
| P01 | GREEN/YELLOW/RED zone 判定 | unit/test_path_policy |
| P02 | grant/revoke | unit/test_path_policy |
| P03 | 路径逃逸防御 | unit/test_path_policy |
| P04 | deny_list 系统目录 | unit/test_deny_list |
| P05 | 与 builtin tools 集成 | integration/test_path_policy_tools |

### CLI (v1.4)

| ID | 功能 | 测试文件 |
|----|------|---------|
| C01 | CommandDispatcher 命令分派 | unit/test_cli_commands |
| C02 | CLIApp 会话管理 | integration/test_cli_app |
| C03 | --execute 脚本模式 | e2e/cli/test_cli_script_mode |

### Cron/Heartbeat (v0.8)

| ID | 功能 | 测试文件 |
|----|------|---------|
| R01 | CronJob 模型 | unit/test_cron_models |
| R02 | CronScheduler 时间计算 | unit/test_cron_scheduler |
| R03 | HeartbeatProtocol | unit/test_heartbeat_protocol |

### 前端

| ID | 功能 | 测试文件 |
|----|------|---------|
| F01 | Chat 页面消息收发 | e2e/frontend/test_chat.spec.ts |
| F02 | Agents 页面列表+详情 | e2e/frontend/test_agents.spec.ts |
| F03 | Skills 页面列表+搜索 | e2e/frontend/test_skills.spec.ts |
| F04 | Workflows 页面 | e2e/frontend/test_workflows.spec.ts |
| F05 | 导航完整性 | e2e/frontend/test_navigation.spec.ts |

### 跨功能冲突

| ID | 冲突场景 | 测试文件 |
|----|---------|---------|
| X01 | Agent 限定 skills/tools 过滤 | cross_feature/test_agent_skill |
| X02 | 不同 Agent 的 PathPolicy 隔离 | cross_feature/test_agent_path_policy |
| X03 | Workflow 节点委托嵌套 | cross_feature/test_workflow_delegation |

---

## 3. 实现代码

### 3.1 conftest.py

```python
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def tmp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws

@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"

@pytest_asyncio.fixture
async def test_repo(tmp_db):
    from app.db.repository import Repository
    repo = Repository(db_path=str(tmp_db))
    await repo.init()
    yield repo

@pytest_asyncio.fixture
async def test_app():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

### 3.2 helpers.py

```python
import asyncio, json
from typing import Any
import websockets

async def collect_ws_events(ws, timeout=30) -> list[dict]:
    events = []
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(raw)
            events.append(data)
            if data.get("type") in ("turn_completed", "error"):
                break
    except asyncio.TimeoutError:
        pass
    return events

class MockCLIApp:
    def __init__(self):
        self.debug = False
        self.current_session_id = None
        self.current_agent_id = "default"
        self.console = type("C", (), {"print": lambda *a, **k: None, "output": []})()
        self._sent = []
    async def _send(self, msg): self._sent.append(msg)
    async def _create_session(self, aid=None):
        self.current_session_id = "mock_sess"
        self.current_agent_id = aid or "default"
        return self.current_session_id
    async def _load_session(self, sid): self.current_session_id = sid
    async def _wait_for_turn(self): pass
```

### 3.3 unit/test_agent_config.py

```python
from app.agents.config import AgentConfig

class TestAgentConfig:
    def test_create_timestamps(self):
        a = AgentConfig.create(id="t", name="T")
        assert a.created_at > 0

    def test_roundtrip(self):
        a = AgentConfig.create(id="t", name="T", tools=["bash_command"], can_delegate_to=["b"])
        b = AgentConfig.from_dict(a.to_dict())
        assert b.id == a.id and b.tools == a.tools and b.can_delegate_to == a.can_delegate_to

    def test_defaults(self):
        a = AgentConfig(id="m", name="M")
        assert a.provider == "openai" and a.enabled is True
```

### 3.4 unit/test_agent_registry.py

```python
from pathlib import Path
from app.agents.config import AgentConfig
from app.agents.registry import AgentRegistry

class TestAgentRegistry:
    def test_register_get(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="x", name="X"))
        assert r.get("x").name == "X"

    def test_list_all_filters_disabled(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="a", name="A", enabled=True))
        r.register(AgentConfig.create(id="b", name="B", enabled=False))
        assert len(r.list_all()) == 1

    def test_delete_default_forbidden(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig(id="default", name="D"))
        assert r.delete("default") is False

    def test_save_load_roundtrip(self, tmp_path):
        d = tmp_path / "a"
        r1 = AgentRegistry(config_dir=d)
        a = AgentConfig.create(id="p", name="P")
        r1.register(a); r1.save(a)
        r2 = AgentRegistry(config_dir=d)
        r2.load_from_dir()
        assert r2.get("p").name == "P"

    def test_load_from_config(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.load_from_config({"agent": {"provider": "openai"}, "agents": {"res": {"name": "Res"}}})
        assert r.get("default") and r.get("res")

    def test_get_delegatable_all(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=[]))
        r.register(AgentConfig.create(id="h", name="H"))
        assert any(a.id == "h" for a in r.get_delegatable("main"))

    def test_get_delegatable_filtered(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="main", name="M", can_delegate_to=["a"]))
        r.register(AgentConfig.create(id="a", name="A"))
        r.register(AgentConfig.create(id="b", name="B"))
        assert [x.id for x in r.get_delegatable("main")] == ["a"]

    def test_update(self, tmp_path):
        r = AgentRegistry(config_dir=tmp_path / "a")
        r.register(AgentConfig.create(id="u", name="Old"))
        r.update("u", {"name": "New"})
        assert r.get("u").name == "New"
```

### 3.5 unit/test_workflow_models.py

```python
from app.workflows.models import Workflow, WorkflowNode, WorkflowEdge, WorkflowRun, WorkflowNodeResult

class TestWorkflowModels:
    def test_node_roundtrip(self):
        n = WorkflowNode(id="n1", agent_id="default", input_template="{input}")
        assert WorkflowNode.from_dict(n.to_dict()).input_template == "{input}"

    def test_edge_roundtrip(self):
        e = WorkflowEdge(from_node="a", to_node="b", condition="ok")
        assert WorkflowEdge.from_dict(e.to_dict()).condition == "ok"

    def test_workflow_roundtrip(self):
        wf = Workflow(id="w", name="W", nodes=[WorkflowNode(id="n1")],
                      edges=[WorkflowEdge(from_node="n1", to_node="n1")],
                      entry_node="n1", exit_nodes=["n1"])
        r = Workflow.from_dict(wf.to_dict())
        assert len(r.nodes) == 1 and r.entry_node == "n1"

    def test_run_to_dict(self):
        run = WorkflowRun(run_id="r", workflow_id="w", status="completed",
                          node_results={"n1": WorkflowNodeResult(node_id="n1", status="completed")})
        assert run.to_dict()["status"] == "completed"
```

### 3.6 unit/test_path_policy.py

```python
import platform, pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict, PathZone

class TestPathPolicy:
    def test_green_zone(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_write("notes.md") == PathVerdict.ALLOW

    def test_red_zone_need_grant(self, tmp_workspace, tmp_path):
        d = tmp_path / "other"; d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_write(str(d / "f.py")) == PathVerdict.NEED_GRANT

    def test_red_zone_system_deny(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows\\System32" if platform.system() == "Windows" else "/etc/passwd"
        assert p.check_read(target) == PathVerdict.DENY

    def test_yellow_after_grant(self, tmp_workspace, tmp_path):
        d = tmp_path / "proj"; d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        assert p.check_write(str(d / "m.py")) == PathVerdict.ALLOW

    def test_grant_system_rejected(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows" if platform.system() == "Windows" else "/etc"
        with pytest.raises(ValueError):
            p.grant(target)

    def test_revoke(self, tmp_workspace, tmp_path):
        d = tmp_path / "rv"; d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        p.revoke(str(d))
        assert p.check_read(str(d / "f")) == PathVerdict.NEED_GRANT

    def test_relative_escape(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        assert p.check_read("../../etc/passwd") in (PathVerdict.NEED_GRANT, PathVerdict.DENY)

    def test_classify(self, tmp_workspace, tmp_path):
        d = tmp_path / "p"; d.mkdir()
        p = PathPolicy(workspace=tmp_workspace, granted_paths=[str(d)])
        assert p.classify(tmp_workspace / "f") == PathZone.GREEN
        assert p.classify(d / "f") == PathZone.YELLOW
        assert p.classify(tmp_path / "x" / "f") == PathZone.RED
```

### 3.7 unit/test_cli_commands.py

```python
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from helpers import MockCLIApp
from cli.commands import CommandDispatcher

class TestCommandDispatcher:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_quit(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/quit")) == "quit"

    def test_help(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/help")) is None

    def test_debug_toggle(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/debug on"))
        assert app.debug is True
        self._run(d.dispatch("/debug off"))
        assert app.debug is False

    def test_current(self):
        app = MockCLIApp()
        app.current_session_id = "s1"
        d = CommandDispatcher(app)
        assert self._run(d.dispatch("/current")) is None

    def test_unknown(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/xyz")) is None
```

### 3.8 integration/test_path_policy_tools.py

```python
import platform, pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict
from app.tools.builtin import BashCommandTool, ReadFileTool, WriteFileTool

pytestmark = pytest.mark.asyncio

class TestPathPolicyTools:
    async def test_read_in_workspace(self, tmp_workspace):
        (tmp_workspace / "t.md").write_text("hi", encoding="utf-8")
        p = PathPolicy(workspace=tmp_workspace)
        r = await ReadFileTool().execute(file_path=str(tmp_workspace / "t.md"), _path_policy=p)
        assert "hi" in r.get("content", "")

    async def test_write_outside_blocked(self, tmp_workspace, tmp_path):
        p = PathPolicy(workspace=tmp_workspace)
        r = await WriteFileTool().execute(file_path=str(tmp_path / "out.md"), content="x", _path_policy=p)
        assert r.get("action") == "need_grant"

    async def test_bash_default_cwd(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        cmd = "cd" if platform.system() == "Windows" else "pwd"
        r = await BashCommandTool().execute(command=cmd, _path_policy=p)
        assert r.get("return_code") == 0

    async def test_read_system_denied(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows\\System32\\config" if platform.system() == "Windows" else "/etc/shadow"
        r = await ReadFileTool().execute(file_path=target, _path_policy=p)
        assert r.get("success") is False
```

### 3.9 integration/test_delegate_tool.py

```python
import asyncio, pytest
from pathlib import Path
from app.agents.config import AgentConfig
from app.agents.registry import AgentRegistry
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.router import BusRouter
from app.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from app.tools.delegate_tool import DelegateTool

pytestmark = pytest.mark.asyncio

class TestDelegateTool:
    async def test_delegate_success(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        reg.register(AgentConfig.create(id="default", name="D"))
        reg.register(AgentConfig.create(id="helper", name="H"))
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        async def fake_agent():
            async for e in bus_router.public_bus.subscribe():
                if e.type == USER_INPUT and e.session_id.startswith("delegate_"):
                    await asyncio.sleep(0.05)
                    await bus_router.public_bus.publish(EventEnvelope(
                        type=AGENT_STEP_COMPLETED, session_id=e.session_id,
                        source="test", payload={"result": {"content": "done"}},
                    ))
                    return
        task = asyncio.create_task(fake_agent())
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=5)
        result = await tool.execute(target_agent="helper", task="test", _session_id="parent")
        assert result["success"] is True
        task.cancel()
        await bus_router.stop()

    async def test_depth_limit(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        reg.register(AgentConfig.create(id="h", name="H", max_delegation_depth=1))
        await test_repo.create_session("deep", meta={"delegation_depth": 1})
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=5)
        result = await tool.execute(target_agent="h", task="t", _session_id="deep")
        assert result["success"] is False
        await bus_router.stop()
```

### 3.10 api/test_agents_api.py

```python
import pytest
pytestmark = pytest.mark.asyncio

class TestAgentsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/agents")
        assert r.status_code == 200
        assert any(a["id"] == "default" for a in r.json())

    async def test_get_detail(self, test_app):
        r = await test_app.get("/api/agents/default")
        assert r.status_code == 200 and "toolsDetail" in r.json()

    async def test_create(self, test_app):
        r = await test_app.post("/api/agents", json={"id": "t1", "name": "T1"})
        assert r.status_code == 200 and r.json()["id"] == "t1"

    async def test_create_duplicate(self, test_app):
        await test_app.post("/api/agents", json={"id": "dup", "name": "D"})
        assert (await test_app.post("/api/agents", json={"id": "dup", "name": "D"})).status_code == 409

    async def test_update(self, test_app):
        await test_app.post("/api/agents", json={"id": "u1", "name": "Old"})
        r = await test_app.put("/api/agents/u1/config", json={"name": "New"})
        assert r.status_code == 200 and r.json()["name"] == "New"

    async def test_delete(self, test_app):
        await test_app.post("/api/agents", json={"id": "d1", "name": "D"})
        assert (await test_app.delete("/api/agents/d1")).status_code == 200
        assert (await test_app.get("/api/agents/d1")).status_code == 404

    async def test_delete_default_forbidden(self, test_app):
        assert (await test_app.delete("/api/agents/default")).status_code == 400

    async def test_404(self, test_app):
        assert (await test_app.get("/api/agents/nope")).status_code == 404
```

### 3.11 api/test_workflows_api.py

```python
import pytest
pytestmark = pytest.mark.asyncio

class TestWorkflowsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/workflows")
        assert r.status_code == 200

    async def test_create(self, test_app):
        r = await test_app.post("/api/workflows", json={
            "id": "tw", "name": "TW",
            "nodes": [{"id": "n1"}, {"id": "n2"}],
            "edges": [{"from_node": "n1", "to_node": "n2"}],
            "entry_node": "n1", "exit_nodes": ["n2"],
        })
        assert r.status_code == 200

    async def test_get(self, test_app):
        await test_app.post("/api/workflows", json={"id": "g1", "name": "G"})
        assert (await test_app.get("/api/workflows/g1")).status_code == 200

    async def test_delete(self, test_app):
        await test_app.post("/api/workflows", json={"id": "d1", "name": "D"})
        assert (await test_app.delete("/api/workflows/d1")).status_code == 200

    async def test_404(self, test_app):
        assert (await test_app.get("/api/workflows/nope")).status_code == 404
```

### 3.12 api/test_skills_api.py

```python
import pytest
pytestmark = pytest.mark.asyncio

class TestSkillsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/skills")
        assert r.status_code == 200
        for s in r.json():
            assert s["category"] in ("builtin", "workspace", "installed")

    async def test_toggle(self, test_app):
        skills = (await test_app.get("/api/skills")).json()
        if skills:
            r = await test_app.patch(f"/api/skills/{skills[0]['name']}", json={"enabled": False})
            assert r.status_code == 200

    async def test_unified_search(self, test_app):
        r = await test_app.get("/api/skills/search", params={"q": "pdf"})
        assert r.status_code == 200 and "local_results" in r.json()
```

### 3.13 api/test_workspace_api.py

```python
import pytest
pytestmark = pytest.mark.asyncio

class TestWorkspaceAPI:
    async def test_list_files(self, test_app):
        assert (await test_app.get("/api/workspace/files")).status_code == 200

    async def test_write_read(self, test_app):
        await test_app.put("/api/workspace/files/TEST.md", json={"content": "# T"})
        r = await test_app.get("/api/workspace/files/TEST.md")
        assert r.status_code == 200

    async def test_reject_non_md(self, test_app):
        assert (await test_app.get("/api/workspace/files/x.txt")).status_code == 400

    async def test_delete_core_forbidden(self, test_app):
        assert (await test_app.delete("/api/workspace/files/AGENTS.md")).status_code == 403
```

### 3.14 api/test_websocket_protocol.py

```python
import asyncio, json, pytest, websockets

WS_URL = "ws://localhost:8000/ws"

@pytest.mark.skipif(True, reason="需要后端运行")
class TestWebSocketProtocol:
    async def test_create_session(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "create_session", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "session_created" and "session_id" in r

    async def test_list_sessions(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_sessions", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "sessions_list"

    async def test_list_agents(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_agents", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "agents_list"

    async def test_invalid_type(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "bad", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "error"
```

### 3.15 cross_feature/test_agent_skill.py

```python
import pytest
pytestmark = pytest.mark.asyncio

class TestAgentSkillInteraction:
    async def test_agent_tool_filter(self, test_app):
        """Agent 配置 tools 列表后，详情只展示指定工具"""
        await test_app.post("/api/agents", json={
            "id": "lim", "name": "L", "tools": ["serper_search"],
        })
        r = await test_app.get("/api/agents/lim")
        names = [t["name"] for t in r.json().get("toolsDetail", [])]
        assert all(n == "serper_search" for n in names) if names else True

    async def test_agent_skill_filter(self, test_app):
        """Agent 配置 skills 列表后，详情只展示指定 skill"""
        await test_app.post("/api/agents", json={
            "id": "slim", "name": "S", "skills": ["pdf_to_markdown"],
        })
        r = await test_app.get("/api/agents/slim")
        names = [s["name"] for s in r.json().get("skillsDetail", [])]
        assert all(n == "pdf_to_markdown" for n in names) if names else True
```

### 3.16 e2e/frontend/test_navigation.spec.ts

```typescript
import { test, expect } from '@playwright/test';
const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('导航', () => {
  for (const path of ['/chat', '/agents', '/skills', '/tools', '/workflows', '/sessions']) {
    test(`${path} 页面可访问`, async ({ page }) => {
      await page.goto(`${BASE}${path}`);
      await expect(page).not.toHaveTitle(/Error|500|404/);
    });
  }
});
```

### 3.17 generate_matrix.py

```python
"""解析 JUnit XML → feature_matrix.md"""
import xml.etree.ElementTree as ET
from pathlib import Path

RESULTS = Path(__file__).parent / "results"

def main():
    RESULTS.mkdir(exist_ok=True)
    all_r = {}
    for f in RESULTS.glob("*.xml"):
        tree = ET.parse(f)
        for tc in tree.iter("testcase"):
            name = f"{tc.get('classname','')}.{tc.get('name','')}"
            status = "FAIL" if tc.find("failure") is not None else "SKIP" if tc.find("skipped") is not None else "PASS"
            all_r.setdefault(f.stem, {})[name] = status

    total = sum(len(v) for v in all_r.values())
    passed = sum(1 for r in all_r.values() for s in r.values() if s == "PASS")
    failed = sum(1 for r in all_r.values() for s in r.values() if s == "FAIL")
    lines = [f"# 功能验证矩阵\n\n总计: {total} | 通过: {passed} | 失败: {failed}\n"]
    for suite, tests in sorted(all_r.items()):
        lines += [f"## {suite}\n", "| 用例 | 状态 |", "|------|------|"]
        for n, s in sorted(tests.items()):
            lines.append(f"| {n} | {'✅' if s=='PASS' else '❌' if s=='FAIL' else '⏭️'} {s} |")
        lines.append("")
    (RESULTS / "feature_matrix.md").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
```

### 3.18 run_all.ps1

```powershell
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$B = Join-Path $T "..\backend"
$R = Join-Path $T "results"
New-Item -ItemType Directory -Force -Path $R | Out-Null
Set-Location $B

Write-Host "=== L1 单元 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\unit" --junitxml="$R\unit.xml" -q

Write-Host "=== L2 集成 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\integration" --junitxml="$R\integration.xml" -q

Write-Host "=== L3 API ===" -ForegroundColor Cyan
uv run python -m pytest "$T\api" --junitxml="$R\api.xml" -q

Write-Host "=== 跨功能 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\cross_feature" --junitxml="$R\cross.xml" -q

Write-Host "=== 生成矩阵 ===" -ForegroundColor Cyan
uv run python "$T\generate_matrix.py"

Write-Host "完成 → $R" -ForegroundColor Green
```

---

## 4. 实施顺序

| Phase | 内容 | 工期 |
|-------|------|------|
| 1 | 创建目录 + conftest + helpers | 0.5d |
| 2 | unit/ 全部用例 | 1d |
| 3 | api/ 全部用例 | 1d |
| 4 | integration/ 全部用例 | 1d |
| 5 | cross_feature/ + e2e/ | 1d |
| 6 | generate_matrix + run_all + 修 bug | 0.5d |
| **总计** | | **5d** |
