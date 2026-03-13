"""Anthropic Plugin Marketplace 适配器"""
from __future__ import annotations

import zipfile
import tempfile
import logging
from pathlib import Path

import httpx

from agentos.capabilities.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

ANTHROPIC_MARKET_API_BASE = "https://marketplace.claude.com/api/v1"


class AnthropicAdapter(MarketAdapter):
    def __init__(self, api_base: str = ANTHROPIC_MARKET_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    @property
    def supports_browse(self) -> bool:
        return True

    async def browse(self, page: int = 1, page_size: int = 20) -> SearchResult:
        """浏览 Anthropic 市场中的 featured/popular plugins"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._api_base}/plugins",
                    params={"page": page, "per_page": page_size, "sort": "popular"},
                )
                resp.raise_for_status()
                data = resp.json()

            items = [
                SkillSearchItem(
                    id=p.get("id", ""),
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    author=p.get("author", {}).get("name") if isinstance(p.get("author"), dict) else p.get("author"),
                    version=p.get("version"),
                    downloads=p.get("installs"),
                    source="anthropic",
                    updated_at=p.get("updatedAt") or p.get("updated_at"),
                )
                for p in data.get("plugins", data if isinstance(data, list) else [])
            ]
            return SearchResult(
                source="anthropic",
                total=data.get("total", len(items)) if isinstance(data, dict) else len(items),
                page=page,
                page_size=page_size,
                items=items,
            )
        except Exception as e:
            logger.warning("Anthropic browse 失败，回退到搜索: %s", e)
            return await self.search("assistant", page, page_size)

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/plugins/search",
                params={"q": query, "page": page, "per_page": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

        items = [
            SkillSearchItem(
                id=p.get("id", ""),
                name=p.get("name", ""),
                description=p.get("description", ""),
                author=p.get("author", {}).get("name"),
                version=p.get("version"),
                downloads=p.get("installs"),
                source="anthropic",
                updated_at=p.get("updatedAt") or p.get("updated_at"),
            )
            for p in data.get("plugins", [])
        ]
        return SearchResult(
            source="anthropic",
            total=data.get("total", len(items)),
            page=page,
            page_size=page_size,
            items=items,
        )

    async def get_detail(self, skill_id: str) -> SkillDetail:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/plugins/{skill_id}")
            resp.raise_for_status()
            data = resp.json()

        return SkillDetail(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            version=data.get("version"),
            author=data.get("author", {}).get("name"),
            skill_md_preview=data.get("skill_md", ""),
            files=data.get("files", []),
            installed=False,
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/plugins/{skill_id}/download")
            resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                # Zip Slip 防护
                resolved_target = target_dir.resolve()
                for member in zf.infolist():
                    dest = (target_dir / member.filename).resolve()
                    if not str(dest).startswith(str(resolved_target) + "/"):
                        raise ValueError(f"Zip Slip detected: {member.filename}")
                names = zf.namelist()

                # 情况1：zip 内有子目录且含 SKILL.md
                skill_dirs = [n for n in names if n.endswith("/SKILL.md")]
                if skill_dirs:
                    skill_root = skill_dirs[0].split("/SKILL.md")[0]
                    zf.extractall(target_dir)
                    return target_dir / skill_root

                # 情况2：有统一顶层目录
                top_dirs = {n.split("/")[0] for n in names if "/" in n}
                if len(top_dirs) == 1:
                    zf.extractall(target_dir)
                    return target_dir / top_dirs.pop()

                # 情况3：平铺文件（根目录直接含 SKILL.md 等），创建子目录
                skill_dir = target_dir / skill_id
                skill_dir.mkdir(parents=True, exist_ok=True)
                zf.extractall(skill_dir)
                return skill_dir
        finally:
            tmp_path.unlink(missing_ok=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api_base}/plugins/{skill_id}")
                resp.raise_for_status()
                data = resp.json()
            latest = data.get("version")
            if latest and latest != current_version:
                return UpdateInfo(
                    skill_id=skill_id,
                    current_version=current_version,
                    latest_version=latest,
                )
        except Exception:
            logger.warning("检查 Anthropic skill %s 更新失败", skill_id, exc_info=True)
        return None
