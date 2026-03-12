"""ClawHub 市场适配器

API 文档: https://deepwiki.com/openclaw/clawhub/7-http-api-v1
基础 URL: https://clawhub.ai/api/v1
"""
from __future__ import annotations

import zipfile
import tempfile
import logging
from pathlib import Path

import httpx

from app.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

CLAWHUB_API_BASE = "https://clawhub.ai/api/v1"


class ClawHubAdapter(MarketAdapter):
    def __init__(self, api_base: str = CLAWHUB_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """搜索 skill

        ClawHub 搜索端点: GET /api/v1/search?q=<query>&limit=<n>&cursor=<cursor>
        返回格式: { "results": [ { slug, displayName, summary, score, version, updatedAt } ] }
        使用 OpenAI embedding 向量搜索，不是简单关键词匹配。
        ClawHub 使用 cursor 分页，这里做适配转换。
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/search",
                params={"q": query, "limit": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        items = [
            SkillSearchItem(
                id=s.get("slug", ""),
                name=s.get("displayName", s.get("slug", "")),
                description=s.get("summary", ""),
                author=None,  # 搜索结果不含 author
                version=s.get("version"),
                downloads=None,  # 搜索结果不含 downloads
                source="clawhub",
            )
            for s in results
        ]
        return SearchResult(
            source="clawhub",
            total=len(items),
            page=page,
            page_size=page_size,
            items=items,
        )

    async def get_detail(self, skill_id: str) -> SkillDetail:
        """获取 skill 详情

        ClawHub 详情端点: GET /api/v1/skills/{slug}
        返回格式: { skill: { slug, displayName, summary, tags, stats }, latestVersion: {...}, owner: {...} }
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/skills/{skill_id}")
            resp.raise_for_status()
            data = resp.json()

        skill = data.get("skill", {})
        latest = data.get("latestVersion", {})
        owner = data.get("owner", {})
        stats = skill.get("stats", {})

        # 获取 SKILL.md 预览（通过 file 端点）
        skill_md_preview = ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                file_resp = await client.get(
                    f"{self._api_base}/skills/{skill_id}/file",
                    params={"path": "SKILL.md"},
                )
                if file_resp.status_code == 200:
                    skill_md_preview = file_resp.text
        except Exception:
            logger.debug("获取 %s 的 SKILL.md 预览失败", skill_id)

        return SkillDetail(
            id=skill_id,
            name=skill.get("displayName", skill_id),
            description=skill.get("summary", ""),
            version=latest.get("version"),
            author=owner.get("handle") or owner.get("displayName"),
            skill_md_preview=skill_md_preview,
            files=[],  # 文件列表需要额外请求，暂不获取
            installed=False,
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """下载 skill zip

        ClawHub 下载端点: GET /api/v1/download?slug=<slug>&version=<v>
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/download",
                params={"slug": skill_id},
            )
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
        """检查更新：对比 latestVersion.version 与当前版本"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api_base}/skills/{skill_id}")
                resp.raise_for_status()
                data = resp.json()
            latest = data.get("latestVersion", {}).get("version")
            if latest and latest != current_version:
                return UpdateInfo(
                    skill_id=skill_id,
                    current_version=current_version,
                    latest_version=latest,
                )
        except Exception:
            logger.warning("检查 ClawHub skill %s 更新失败", skill_id, exc_info=True)
        return None
