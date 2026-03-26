"""SkillMarketService 核心逻辑单测

对于 ClawHub/Anthropic adapter 保留 mock（无 API key），
其余逻辑使用真实组件 + 内存 adapter。
"""
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock  # 仅用于 ClawHub/Anthropic（唯一例外）

import pytest

from sensenova_claw.capabilities.skills.market_service import SkillMarketService
from sensenova_claw.capabilities.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.adapters.skill_sources.base import MarketAdapter


# ---------- 内存 MarketAdapter（真实子类，非 mock） ----------

class InMemoryAdapter(MarketAdapter):
    """用于测试的内存 MarketAdapter，无需网络调用"""

    def __init__(self):
        self._skills: dict[str, dict] = {}  # skill_id -> { name, description, content }

    def add_skill(self, skill_id: str, name: str, description: str = "Test", content: str = "Body"):
        """预置一个可供搜索/下载的 skill"""
        self._skills[skill_id] = {
            "name": name,
            "description": description,
            "content": content,
        }

    @property
    def supports_search(self) -> bool:
        return True

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        items = [
            SkillSearchItem(id=sid, name=info["name"], description=info["description"], source="memory")
            for sid, info in self._skills.items()
            if query.lower() in info["name"].lower() or query.lower() in info["description"].lower()
        ]
        return SearchResult(source="memory", total=len(items), page=page, page_size=page_size, items=items)

    async def get_detail(self, skill_id: str) -> SkillDetail:
        info = self._skills[skill_id]
        return SkillDetail(
            id=skill_id, name=info["name"], description=info["description"],
            skill_md_preview=f"---\nname: {info['name']}\n---\n{info['content']}",
            files=["SKILL.md"], installed=False,
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        info = self._skills[skill_id]
        skill_dir = target_dir / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        md_content = f"---\nname: {info['name']}\ndescription: {info['description']}\n---\n{info['content']}"
        (skill_dir / "SKILL.md").write_text(md_content, encoding="utf-8")
        return skill_dir

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        return None


# ---------- Fixtures ----------


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
def mem_adapter():
    """真实内存 adapter，预置一个 skill"""
    adapter = InMemoryAdapter()
    adapter.add_skill("test-skill", "test-skill", "Test description")
    return adapter


@pytest.fixture
def service(tmp_workspace, registry, mem_adapter):
    svc = SkillMarketService(
        skills_dir=tmp_workspace / "skills",
        skill_registry=registry,
        config={},
    )
    # 注入内存 adapter 替换默认的网络 adapter
    svc._adapters["memory"] = mem_adapter
    return svc


# ---------- 测试 ----------


@pytest.mark.asyncio
async def test_search(service):
    """搜索应返回预置的 skill"""
    result = await service.search("memory", "test")
    assert result.total == 1
    assert result.items[0].name == "test-skill"


@pytest.mark.asyncio
async def test_install_success(service, tmp_workspace):
    """安装 skill 应创建目录、写入 .install.json 并注册"""
    result = await service.install("memory", "test-skill")
    assert result["ok"] is True
    assert result["skill_name"] == "test-skill"

    install_json = tmp_workspace / "skills" / "test-skill" / ".install.json"
    assert install_json.exists()
    info = json.loads(install_json.read_text())
    assert info["source"] == "memory"
    assert service._registry.get("test-skill") is not None


@pytest.mark.asyncio
async def test_install_name_conflict(service, tmp_workspace):
    """已存在同名 skill 时安装应返回 NAME_CONFLICT"""
    # 先注册一个已存在的 skill
    existing = tmp_workspace / "skills" / "test-skill"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("---\nname: test-skill\ndescription: Old\n---\nOld body")
    service._registry.load_skills({})

    # 内存 adapter 预置一个 id 不同但 name 相同的 skill
    service._adapters["memory"].add_skill("test-skill-new", "test-skill", "New")

    result = await service.install("memory", "test-skill-new")
    assert result["ok"] is False
    assert result["code"] == "NAME_CONFLICT"


@pytest.mark.asyncio
async def test_uninstall_success(service, tmp_workspace):
    """卸载已安装的 skill 应删除目录并注销"""
    await service.install("memory", "test-skill")
    result = await service.uninstall("test-skill")
    assert result["ok"] is True
    assert not (tmp_workspace / "skills" / "test-skill").exists()
    assert service._registry.get("test-skill") is None


@pytest.mark.asyncio
async def test_uninstall_local_skill_denied(service, tmp_workspace):
    """卸载 local skill 应返回 PERMISSION_DENIED"""
    skill_dir = tmp_workspace / "skills" / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: local-skill\ndescription: Local\n---\nBody")
    service._registry.load_skills({})

    result = await service.uninstall("local-skill")
    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_get_local_detail_for_disabled_skill(service, registry, tmp_workspace):
    """禁用的本地 skill 仍应能在管理页读取详情"""
    skill_dir = tmp_workspace / "skills" / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: local-skill\ndescription: Local skill\n---\nLocal body",
        encoding="utf-8",
    )
    (skill_dir / "README.md").write_text("# Readme", encoding="utf-8")

    registry.load_skills({})
    registry.set_enabled("local-skill", False)

    detail = await service.get_detail("local", "local-skill")

    assert detail.name == "local-skill"
    assert detail.description == "Local skill"
    assert "Local body" in detail.skill_md_preview
    assert sorted(detail.files) == ["README.md", "SKILL.md"]
    assert detail.installed is True
