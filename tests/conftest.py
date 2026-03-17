"""全局 fixtures"""
import asyncio
import sys
import os
import shutil
import uuid
from pathlib import Path
from dataclasses import dataclass

import pytest
import pytest_asyncio
import yaml

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_gemini_config() -> dict | None:
    """从项目根目录 config.yml 读取 gemini provider 配置。

    返回 dict 包含 api_key / base_url / default_model，若无配置则返回 None。
    """
    config_path = _PROJECT_ROOT / "config.yml"
    if not config_path.exists():
        return None
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    gemini_cfg = data.get("llm_providers", {}).get("gemini", {})
    if not gemini_cfg.get("api_key"):
        return None
    return gemini_cfg


def skip_if_gemini_unavailable(provider_name: str):
    """若 provider_name 为 gemini 但 API key 不可用，则 skip。"""
    if provider_name != "gemini":
        return
    cfg = load_gemini_config()
    if cfg is None:
        pytest.skip("gemini API key 未配置，跳过真实 provider 测试")


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
def tmp_path():
    """在仓库内创建临时目录，绕开系统 Temp 目录权限问题。"""
    base = _PROJECT_ROOT / "pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
    """创建带有完整 app.state 的测试客户端（不启动 lifespan）"""
    from httpx import AsyncClient, ASGITransport
    from agentos.app.gateway.main import app
    from agentos.platform.config.config import Config
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.capabilities.tools.registry import ToolRegistry
    from agentos.capabilities.skills.registry import SkillRegistry
    from agentos.capabilities.skills.market_service import SkillMarketService
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

    # PathPolicy
    path_policy = PathPolicy(workspace=workspace_dir)

    # 真实 Services（只需 repo）
    @dataclass
    class Services:
        repo: Repository

    services = Services(repo=repo)

    # 真实 MarketService（无外部 API key，ClawHub/Anthropic 不可用但不影响测试）
    market_service = SkillMarketService(
        skills_dir=skills_dir,
        skill_registry=skill_registry,
        config=cfg.data,
    )

    # 挂载到 app.state
    app.state.services = services
    app.state.agent_registry = agent_registry
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.config = cfg
    app.state.market_service = market_service
    app.state.path_policy = path_policy

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 关闭 market_service
    await market_service.shutdown()

    # 清理 app.state，避免污染其他测试
    for attr in ("services", "agent_registry", "tool_registry", "skill_registry",
                 "config", "market_service", "path_policy"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
