"""ClawHub 市场适配器

API 文档: https://deepwiki.com/openclaw/clawhub/7-http-api-v1
基础 URL: https://clawhub.ai/api/v1

限流（匿名）: Read 120/min, Download 20/min
限流响应含 Retry-After 头，本适配器自动重试。
"""
from __future__ import annotations

import asyncio
import zipfile
import tempfile
import logging
from pathlib import Path

import httpx

from sensenova_claw.capabilities.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

CLAWHUB_API_BASE = "https://clawhub.ai/api/v1"
MAX_RETRIES = 3


class ClawHubAdapter(MarketAdapter):
    def __init__(self, api_base: str = CLAWHUB_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    @property
    def supports_browse(self) -> bool:
        return True

    async def _request(
        self, method: str, url: str, **kwargs
    ) -> httpx.Response:
        """带 429 重试的请求，遵守 Retry-After 头"""
        for attempt in range(MAX_RETRIES + 1):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, url, **kwargs)

            if resp.status_code != 429 or attempt == MAX_RETRIES:
                resp.raise_for_status()
                return resp

            # 读取 Retry-After（秒），默认等 5 秒
            retry_after = 5
            raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            if raw:
                try:
                    retry_after = int(raw)
                except ValueError:
                    pass
            # 限制最长等 30 秒
            retry_after = min(retry_after, 30)
            logger.info(
                "ClawHub 429 限流，%d 秒后重试 (attempt %d/%d): %s",
                retry_after, attempt + 1, MAX_RETRIES, url,
            )
            await asyncio.sleep(retry_after)

        # 不应到达，保险起见
        resp.raise_for_status()
        return resp  # type: ignore[return-value]

    async def browse(self, page: int = 1, page_size: int = 20) -> SearchResult:
        """浏览热门 skills，使用 /api/v1/skills 列表端点"""
        try:
            resp = await self._request(
                "GET",
                f"{self._api_base}/skills",
                params={"limit": page_size, "offset": (page - 1) * page_size},
            )
            data = resp.json()
            skills_list = data if isinstance(data, list) else data.get("skills", data.get("results", []))
            items = [
                SkillSearchItem(
                    id=s.get("slug", s.get("id", "")),
                    name=s.get("displayName", s.get("name", s.get("slug", ""))),
                    description=s.get("summary", s.get("description", "")),
                    author=s.get("owner", {}).get("handle") if isinstance(s.get("owner"), dict) else s.get("author"),
                    version=s.get("version"),
                    downloads=s.get("downloads"),
                    source="clawhub",
                    updated_at=s.get("updatedAt"),
                )
                for s in (skills_list if isinstance(skills_list, list) else [])
            ]
            return SearchResult(
                source="clawhub",
                total=data.get("total", len(items)) if isinstance(data, dict) else len(items),
                page=page,
                page_size=page_size,
                items=items,
            )
        except Exception as e:
            logger.warning("ClawHub browse 失败，回退到搜索: %s", e)
            return await self.search("tool", page, page_size)

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """搜索 skill

        ClawHub 搜索端点: GET /api/v1/search?q=<query>&limit=<n>
        返回格式: { "results": [ { slug, displayName, summary, score, version, updatedAt } ] }
        使用 OpenAI embedding 向量搜索。
        """
        resp = await self._request(
            "GET",
            f"{self._api_base}/search",
            params={"q": query, "limit": page_size},
        )
        data = resp.json()

        results = data.get("results", [])
        items = [
            SkillSearchItem(
                id=s.get("slug", ""),
                name=s.get("displayName", s.get("slug", "")),
                description=s.get("summary", ""),
                author=None,
                version=s.get("version"),
                downloads=None,
                source="clawhub",
                updated_at=s.get("updatedAt"),
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
        """
        resp = await self._request("GET", f"{self._api_base}/skills/{skill_id}")
        data = resp.json()

        skill = data.get("skill", {})
        latest = data.get("latestVersion", {})
        owner = data.get("owner", {})

        # 获取 SKILL.md 预览
        skill_md_preview = ""
        try:
            file_resp = await self._request(
                "GET",
                f"{self._api_base}/skills/{skill_id}/file",
                params={"path": "SKILL.md"},
            )
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
            files=[],
            installed=False,
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """下载 skill zip

        ClawHub 下载端点: GET /api/v1/download?slug=<slug>
        匿名限流 20 req/min，遇 429 自动重试。
        """
        resp = await self._request(
            "GET",
            f"{self._api_base}/download",
            params={"slug": skill_id},
        )

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                names = zf.namelist()

                # Zip Slip 防护
                resolved_target = target_dir.resolve()
                for member in zf.infolist():
                    dest = (target_dir / member.filename).resolve()
                    if not str(dest).startswith(str(resolved_target) + "/"):
                        raise ValueError(f"Zip Slip detected: {member.filename}")

                # 判断 zip 结构：有顶层目录 vs 平铺文件
                top_dirs = {n.split("/")[0] for n in names if "/" in n}
                has_top_dir = len(top_dirs) == 1 and all(
                    n.startswith(next(iter(top_dirs)) + "/") or n == next(iter(top_dirs))
                    for n in names
                )

                if has_top_dir:
                    # 有统一顶层目录，直接解压
                    skill_name = top_dirs.pop()
                    zf.extractall(target_dir)
                else:
                    # 平铺文件（ClawHub 常见），创建子目录后解压到其中
                    skill_name = skill_id
                    skill_dir = target_dir / skill_name
                    skill_dir.mkdir(parents=True, exist_ok=True)
                    zf.extractall(skill_dir)

            return target_dir / skill_name
        finally:
            tmp_path.unlink(missing_ok=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        """检查更新：对比 latestVersion.version 与当前版本"""
        try:
            resp = await self._request("GET", f"{self._api_base}/skills/{skill_id}")
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
