"""SkillMarketService 核心逻辑单测（使用 mock adapter）"""
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from agentos.capabilities.skills.market_service import SkillMarketService
from agentos.capabilities.skills.models import SearchResult, SkillSearchItem, SkillDetail
from agentos.capabilities.skills.registry import SkillRegistry


@pytest.fixture
def tmp_workspace(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return tmp_path


@pytest.fixture
def registry(tmp_workspace):
    state_file = tmp_workspace / "skills_state.json"
    return SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.supports_search = True
    adapter.search.return_value = SearchResult(
        source="mock", total=1, page=1, page_size=20,
        items=[SkillSearchItem(id="test-skill", name="test-skill", description="Test", source="mock")],
    )
    return adapter


@pytest.fixture
def service(tmp_workspace, registry, mock_adapter):
    svc = SkillMarketService(
        skills_dir=tmp_workspace / "skills",
        skill_registry=registry,
        config={},
    )
    svc._adapters["mock"] = mock_adapter
    return svc


@pytest.mark.asyncio
async def test_search(service, mock_adapter):
    result = await service.search("mock", "test")
    assert result.total == 1
    mock_adapter.search.assert_called_once()


@pytest.mark.asyncio
async def test_install_success(service, mock_adapter, tmp_workspace):
    async def fake_download(skill_id, target_dir):
        skill_dir = target_dir / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---\nBody")
        return skill_dir

    mock_adapter.download = AsyncMock(side_effect=fake_download)
    result = await service.install("mock", "test-skill")
    assert result["ok"] is True
    assert result["skill_name"] == "test-skill"
    install_json = tmp_workspace / "skills" / "test-skill" / ".install.json"
    assert install_json.exists()
    info = json.loads(install_json.read_text())
    assert info["source"] == "mock"
    assert service._registry.get("test-skill") is not None


@pytest.mark.asyncio
async def test_install_name_conflict(service, mock_adapter, tmp_workspace):
    # 先注册一个已存在的 skill
    existing = tmp_workspace / "skills" / "test-skill"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("---\nname: test-skill\ndescription: Old\n---\nOld body")
    service._registry.load_skills({})

    # mock download 返回一个新目录（模拟下载到临时名称）
    async def fake_download(skill_id, target_dir):
        skill_dir = target_dir / (skill_id + "-new")
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: New\n---\nNew body")
        return skill_dir

    mock_adapter.download = AsyncMock(side_effect=fake_download)

    result = await service.install("mock", "test-skill")
    assert result["ok"] is False
    assert result["code"] == "NAME_CONFLICT"


@pytest.mark.asyncio
async def test_uninstall_success(service, mock_adapter, tmp_workspace):
    async def fake_download(skill_id, target_dir):
        skill_dir = target_dir / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---\nBody")
        return skill_dir

    mock_adapter.download = AsyncMock(side_effect=fake_download)
    await service.install("mock", "test-skill")

    result = await service.uninstall("test-skill")
    assert result["ok"] is True
    assert not (tmp_workspace / "skills" / "test-skill").exists()
    assert service._registry.get("test-skill") is None


@pytest.mark.asyncio
async def test_uninstall_local_skill_denied(service, tmp_workspace):
    skill_dir = tmp_workspace / "skills" / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: local-skill\ndescription: Local\n---\nBody")
    service._registry.load_skills({})

    result = await service.uninstall("local-skill")
    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
