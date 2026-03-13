"""市场适配器抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.skills.models import SearchResult, SkillDetail, UpdateInfo


class MarketAdapter(ABC):
    """统一的市场适配器接口"""

    @property
    def supports_search(self) -> bool:
        """该来源是否支持搜索"""
        return True

    @property
    def supports_browse(self) -> bool:
        """该来源是否支持浏览（无需搜索关键词列出 skills）"""
        return False

    async def browse(self, page: int = 1, page_size: int = 20) -> SearchResult:
        """浏览/列出 skills（不需要搜索关键词）。
        默认使用空查询搜索作为回退。"""
        return await self.search("", page, page_size)

    @abstractmethod
    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """搜索 skill，返回分页结果"""

    @abstractmethod
    async def get_detail(self, skill_id: str) -> SkillDetail:
        """获取 skill 详情"""

    @abstractmethod
    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """下载并解压 skill 到目标目录，返回 skill 路径"""

    @abstractmethod
    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        """检查是否有新版本"""
