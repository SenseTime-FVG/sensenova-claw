"""MarketAdapter 基类单元测试"""
import pytest
from unittest.mock import AsyncMock

from agentos.adapters.skill_sources.base import MarketAdapter
from agentos.capabilities.skills.models import SearchResult, SkillDetail, UpdateInfo
from pathlib import Path


class DummyAdapter(MarketAdapter):
    """用于测试基类默认行为的最小实现"""

    def __init__(self):
        self.search_called_with = None

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        self.search_called_with = (query, page, page_size)
        return SearchResult(source="dummy", total=0, page=page, page_size=page_size, items=[])

    async def get_detail(self, skill_id: str) -> SkillDetail:
        return SkillDetail(id=skill_id, name="test", description="", skill_md_preview="", files=[], installed=False)

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        return target_dir / skill_id

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        return None


class TestMarketAdapterBase:
    """测试基类默认属性和方法"""

    def test_supports_search_默认返回true(self):
        adapter = DummyAdapter()
        assert adapter.supports_search is True

    def test_supports_browse_默认返回false(self):
        adapter = DummyAdapter()
        assert adapter.supports_browse is False

    async def test_browse_默认回退到search(self):
        """browse 默认实现应调用 search("")"""
        adapter = DummyAdapter()
        result = await adapter.browse(page=2, page_size=10)
        assert adapter.search_called_with == ("", 2, 10)
        assert result.source == "dummy"

    async def test_browse_使用默认参数(self):
        adapter = DummyAdapter()
        await adapter.browse()
        assert adapter.search_called_with == ("", 1, 20)

    def test_不能直接实例化基类(self):
        """MarketAdapter 是 ABC，不可直接实例化"""
        with pytest.raises(TypeError):
            MarketAdapter()
