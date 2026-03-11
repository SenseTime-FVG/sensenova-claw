"""ClawHub 市场适配器"""
from __future__ import annotations

import zipfile
import tempfile
import logging
from pathlib import Path

import httpx

from app.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

CLAWHUB_API_BASE = "https://api.clawhub.ai/v1"


class ClawHubAdapter(MarketAdapter):
    def __init__(self, api_base: str = CLAWHUB_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/skills/search",
                params={"q": query, "page": page, "per_page": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

        items = [
            SkillSearchItem(
                id=s.get("slug", s.get("name", "")),
                name=s.get("name", ""),
                description=s.get("description", ""),
                author=s.get("author", {}).get("name"),
                version=s.get("version"),
                downloads=s.get("downloads"),
                source="clawhub",
            )
            for s in data.get("results", [])
        ]
        return SearchResult(
            source="clawhub",
            total=data.get("total", len(items)),
            page=page,
            page_size=page_size,
            items=items,
        )

    async def get_detail(self, skill_id: str) -> SkillDetail:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/skills/{skill_id}")
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
            resp = await client.get(f"{self._api_base}/skills/{skill_id}/download")
            resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".skill", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                top_dirs = {n.split("/")[0] for n in zf.namelist() if "/" in n}
                if len(top_dirs) == 1:
                    skill_name = top_dirs.pop()
                else:
                    skill_name = skill_id
                zf.extractall(target_dir)
            return target_dir / skill_name
        finally:
            tmp_path.unlink(missing_ok=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api_base}/skills/{skill_id}")
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
            logger.warning("检查 ClawHub skill %s 更新失败", skill_id, exc_info=True)
        return None
