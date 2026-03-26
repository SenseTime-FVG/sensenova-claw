"""Skill 市场管理核心服务"""
from __future__ import annotations

import asyncio
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.skills.models import SearchResult, SkillDetail, UpdateInfo
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.adapters.skill_sources.base import MarketAdapter
from sensenova_claw.adapters.skill_sources.clawhub import ClawHubAdapter
from sensenova_claw.adapters.skill_sources.anthropic_market import AnthropicAdapter
from sensenova_claw.adapters.skill_sources.git_adapter import GitAdapter

logger = logging.getLogger(__name__)


class SkillMarketService:
    def __init__(
        self,
        skills_dir: Path,
        skill_registry: SkillRegistry,
        config: dict[str, Any],
    ):
        self._skills_dir = skills_dir
        self._registry = skill_registry
        self._config = config
        self._locks: dict[str, asyncio.Lock] = {}
        self._running_tasks: set[asyncio.Task] = set()
        self._shutting_down = False

        self._adapters: dict[str, MarketAdapter] = {
            "clawhub": ClawHubAdapter(
                api_base=config.get("skills", {}).get("clawhub_api_base", "https://clawhub.ai/api/v1"),
            ),
            "anthropic": AnthropicAdapter(
                api_base=config.get("skills", {}).get("anthropic_market_api_base", "https://marketplace.claude.com/api/v1"),
            ),
            "git": GitAdapter(),
        }

    def _get_lock(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    def _get_adapter(self, source: str) -> MarketAdapter:
        adapter = self._adapters.get(source)
        if not adapter:
            raise ValueError(f"未知来源: {source}")
        return adapter

    def _check_shutting_down(self) -> None:
        """检查是否正在关闭，若是则抛出 CancelledError"""
        if self._shutting_down:
            raise asyncio.CancelledError("服务正在关闭")

    async def shutdown(self) -> None:
        """取消所有正在进行的安装/更新任务"""
        self._shutting_down = True
        if self._running_tasks:
            logger.info("正在取消 %d 个进行中的 skill 操作...", len(self._running_tasks))
            for task in self._running_tasks:
                task.cancel()
            # 等待所有任务完成取消，不抛出异常
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
            self._running_tasks.clear()
        logger.info("SkillMarketService 已关闭")

    async def browse(self, source: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """浏览市场 skills（无需搜索关键词）"""
        adapter = self._get_adapter(source)
        return await adapter.browse(page, page_size)

    async def search(self, source: str, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        adapter = self._get_adapter(source)
        return await adapter.search(query, page, page_size)

    async def get_detail(self, source: str, skill_id: str) -> SkillDetail:
        # 本地 skill 直接从 registry 读取，不走 market adapter
        if source in ("local", "builtin"):
            return self._get_local_detail(skill_id)

        adapter = self._get_adapter(source)
        detail = await adapter.get_detail(skill_id)
        detail.installed = self._registry.get(detail.name) is not None
        return detail

    def _get_local_detail(self, skill_id: str) -> SkillDetail:
        """从 SkillRegistry 构造本地 skill 详情"""
        skill = self._registry.get(skill_id)
        if not skill:
            discovered = self._registry.discover_all_skills(self._config)
            skill = next((item for item in discovered if item.name == skill_id), None)
        if not skill:
            raise ValueError(f"本地 Skill 未找到: {skill_id}")

        # 读取 SKILL.md 内容作为预览
        skill_md = skill.path / "SKILL.md"
        preview = ""
        if skill_md.exists():
            preview = skill_md.read_text(encoding="utf-8")

        # 列出 skill 目录下的文件
        files: list[str] = []
        if skill.path.exists():
            files = [
                str(f.relative_to(skill.path))
                for f in skill.path.rglob("*")
                if f.is_file() and f.name != ".install.json"
            ]

        return SkillDetail(
            id=skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            skill_md_preview=preview,
            files=files,
            installed=True,
        )

    async def install(self, source: str, skill_id: str, repo_url: str | None = None) -> dict:
        self._check_shutting_down()
        actual_id = repo_url if source == "git" else skill_id
        if not actual_id:
            return {"ok": False, "error": "缺少 skill_id 或 repo_url", "code": "INSTALL_FAILED"}

        # 追踪当前任务，以便关闭时取消
        current_task = asyncio.current_task()
        if current_task:
            self._running_tasks.add(current_task)

        lock = self._get_lock(actual_id)
        try:
            async with lock:
                try:
                    adapter = self._get_adapter(source)
                    self._skills_dir.mkdir(parents=True, exist_ok=True)
                    skill_path = await adapter.download(actual_id, self._skills_dir)

                    skill_md = skill_path / "SKILL.md"
                    if not skill_md.exists():
                        shutil.rmtree(skill_path, ignore_errors=True)
                        return {"ok": False, "error": "下载的内容不包含有效 SKILL.md", "code": "INVALID_SKILL"}

                    parsed = self._registry.parse_skill(skill_md)
                    if not parsed:
                        shutil.rmtree(skill_path, ignore_errors=True)
                        return {"ok": False, "error": "SKILL.md 格式无效", "code": "INVALID_SKILL"}

                    if self._registry.get(parsed.name):
                        shutil.rmtree(skill_path, ignore_errors=True)
                        return {"ok": False, "error": f"Skill '{parsed.name}' already installed", "code": "NAME_CONFLICT"}

                    install_info = {
                        "source": source,
                        "source_id": skill_id or "",
                        "version": parsed.version or "0.0.0",
                        "installed_at": datetime.now(timezone.utc).isoformat(),
                        "repo_url": repo_url,
                        "checksum": "",
                    }
                    (skill_path / ".install.json").write_text(
                        json.dumps(install_info, ensure_ascii=False, indent=2), encoding="utf-8",
                    )

                    self._registry.register(parsed)
                    logger.info("Skill '%s' 安装成功 (source=%s)", parsed.name, source)
                    return {"ok": True, "skill_name": parsed.name}

                except asyncio.CancelledError:
                    logger.info("安装 skill '%s' 被取消", actual_id)
                    return {"ok": False, "error": "操作已取消（服务关闭）", "code": "CANCELLED"}
                except FileExistsError:
                    return {"ok": False, "error": "Skill 目录已存在", "code": "NAME_CONFLICT"}
                except Exception as e:
                    logger.error("安装 skill 失败: %s", e, exc_info=True)
                    return {"ok": False, "error": str(e), "code": "INSTALL_FAILED"}
        finally:
            if current_task:
                self._running_tasks.discard(current_task)

    async def uninstall(self, skill_name: str) -> dict:
        lock = self._get_lock(skill_name)
        async with lock:
            skill = self._registry.get(skill_name)
            if not skill:
                return {"ok": False, "error": f"Skill '{skill_name}' not found", "code": "NOT_FOUND"}

            if skill.source == "local":
                return {"ok": False, "error": "Cannot uninstall local skill", "code": "PERMISSION_DENIED"}

            if skill.path.exists():
                shutil.rmtree(skill.path)

            self._registry.unregister(skill_name)
            logger.info("Skill '%s' 已卸载", skill_name)
            return {"ok": True}

    async def check_updates(self) -> list[dict]:
        self._check_shutting_down()
        updates = []
        for skill in self._registry.get_all():
            if self._shutting_down:
                break
            info = skill.install_info
            if not info:
                continue
            source = info.get("source")
            source_id = info.get("source_id")
            version = info.get("version")
            if not source or not source_id or not version:
                continue
            try:
                adapter = self._get_adapter(source)
                update = await adapter.check_update(source_id, version)
                if update:
                    updates.append({
                        "skill_name": skill.name,
                        "current_version": update.current_version,
                        "latest_version": update.latest_version,
                    })
            except Exception:
                logger.warning("检查 %s 更新失败", skill.name, exc_info=True)
        return updates

    async def update(self, skill_name: str) -> dict:
        self._check_shutting_down()

        # 追踪当前任务，以便关闭时取消
        current_task = asyncio.current_task()
        if current_task:
            self._running_tasks.add(current_task)

        lock = self._get_lock(skill_name)
        try:
            async with lock:
                skill = self._registry.get(skill_name)
                if not skill:
                    return {"ok": False, "error": f"Skill '{skill_name}' not found", "code": "NOT_FOUND"}

                info = skill.install_info
                if not info:
                    return {"ok": False, "error": "Local skill cannot be updated", "code": "PERMISSION_DENIED"}

                old_version = info.get("version", "unknown")
                source = info["source"]
                source_id = info["source_id"]

                try:
                    adapter = self._get_adapter(source)
                    backup_path = skill.path.with_suffix(".bak")
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    skill.path.rename(backup_path)

                    try:
                        new_path = await adapter.download(source_id, self._skills_dir)
                        new_version = old_version
                        try:
                            detail = await adapter.get_detail(source_id)
                            new_version = detail.version or new_version
                        except Exception:
                            pass

                        install_info = {
                            **info,
                            "version": new_version,
                            "installed_at": datetime.now(timezone.utc).isoformat(),
                        }
                        (new_path / ".install.json").write_text(
                            json.dumps(install_info, ensure_ascii=False, indent=2), encoding="utf-8",
                        )

                        self._registry.reload_skill(skill_name, self._config)
                        shutil.rmtree(backup_path, ignore_errors=True)
                        return {"ok": True, "old_version": old_version, "new_version": new_version}

                    except Exception:
                        if backup_path.exists():
                            new_path_maybe = self._skills_dir / source_id
                            if new_path_maybe.exists():
                                shutil.rmtree(new_path_maybe, ignore_errors=True)
                            backup_path.rename(skill.path)
                        raise

                except asyncio.CancelledError:
                    logger.info("更新 skill '%s' 被取消", skill_name)
                    return {"ok": False, "error": "操作已取消（服务关闭）", "code": "CANCELLED"}
                except Exception as e:
                    logger.error("更新 skill '%s' 失败: %s", skill_name, e, exc_info=True)
                    return {"ok": False, "error": str(e), "code": "INSTALL_FAILED"}
        finally:
            if current_task:
                self._running_tasks.discard(current_task)
