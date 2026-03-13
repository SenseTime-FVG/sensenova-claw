"""全局 fixtures"""
import asyncio
import sys
import os
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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
    from agentos.adapters.storage.repository import Repository
    repo = Repository(db_path=str(tmp_db))
    await repo.init()
    yield repo


@pytest_asyncio.fixture
async def test_app(tmp_path):
    """创建带有完整 app.state 模拟的测试客户端（不启动 lifespan）"""
    from httpx import AsyncClient, ASGITransport
    from agentos.app.gateway.main import app
    from agentos.platform.config.config import Config
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.capabilities.tools.registry import ToolRegistry
    from agentos.capabilities.skills.registry import SkillRegistry
    from agentos.capabilities.workflows.registry import WorkflowRegistry
    from agentos.platform.security.path_policy import PathPolicy
    from agentos.adapters.storage.repository import Repository

    # 使用临时目录避免污染真实环境
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    # 临时 config.yml，使用默认配置
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(workspace_dir))

    # 初始化 Repository
    repo = Repository(db_path=str(tmp_path / "test.db"))
    await repo.init()

    # 初始化 AgentRegistry（含 default Agent）
    agent_config_dir = tmp_path / "agents"
    agent_config_dir.mkdir()
    agent_registry = AgentRegistry(config_dir=agent_config_dir)
    agent_registry.load_from_config(cfg.data)

    # 初始化 ToolRegistry（自动注册 builtin 工具）
    tool_registry = ToolRegistry()

    # 初始化 SkillRegistry
    skills_dir = workspace_dir / "skills"
    skills_dir.mkdir()
    state_file = workspace_dir / "skills_state.json"
    builtin_skills_dir = Path(__file__).resolve().parent.parent / "workspace" / "skills"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=builtin_skills_dir,
    )
    skill_registry.load_skills(cfg.data)

    # 初始化 WorkflowRegistry
    workflow_config_dir = tmp_path / "workflows"
    workflow_config_dir.mkdir()
    workflow_registry = WorkflowRegistry(config_dir=workflow_config_dir)

    # PathPolicy
    path_policy = PathPolicy(workspace=workspace_dir)

    # 模拟 Services（只需 repo）
    @dataclass
    class MockServices:
        repo: Repository

    services = MockServices(repo=repo)

    # 模拟 market_service
    market_service = MagicMock()
    market_service.search = AsyncMock(return_value=[])
    market_service.shutdown = AsyncMock()

    # 模拟 workflow_runtime
    workflow_runtime = MagicMock()
    workflow_runtime.execute = AsyncMock()
    workflow_runtime.list_active_runs = MagicMock(return_value=[])
    workflow_runtime.get_run = MagicMock(return_value=None)

    # 挂载到 app.state
    app.state.services = services
    app.state.agent_registry = agent_registry
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.config = cfg
    app.state.market_service = market_service
    app.state.workflow_registry = workflow_registry
    app.state.workflow_runtime = workflow_runtime
    app.state.path_policy = path_policy

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 清理 app.state，避免污染其他测试
    for attr in ("services", "agent_registry", "tool_registry", "skill_registry",
                 "config", "market_service", "workflow_registry", "workflow_runtime",
                 "path_policy"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
