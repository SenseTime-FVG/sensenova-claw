from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.platform.config.workspace import ensure_agent_workspace

from .acp_client import ACPClient, ACPClientError

logger = logging.getLogger(__name__)

LICENSE_FILENAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.txt",
    "NOTICE",
    "NOTICE.txt",
)


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or f"page-{uuid.uuid4().hex[:6]}"


class MiniAppService:
    """管理 custom page / mini-app 的元数据、工作区和生成任务。"""

    def __init__(
        self,
        *,
        sensenova_claw_home: str | Path,
        config: Any,
        agent_registry: Any,
        gateway: Any | None = None,
    ) -> None:
        self.sensenova_claw_home = Path(sensenova_claw_home).expanduser().resolve()
        self.config = config
        self.agent_registry = agent_registry
        self.gateway = gateway
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def storage_path(self) -> Path:
        return self.sensenova_claw_home / "custom_pages.json"

    @property
    def runs_dir(self) -> Path:
        return self.sensenova_claw_home / "custom_pages_runs"

    def load_pages(self) -> list[dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取 custom_pages.json 失败", exc_info=True)
            return []
        return data if isinstance(data, list) else []

    def save_pages(self, pages: list[dict[str, Any]]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(pages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        for page in self.load_pages():
            if page.get("id") == page_id or page.get("slug") == page_id:
                return page
        return None

    async def restore_dedicated_agents(self) -> None:
        for page in self.load_pages():
            try:
                await self._ensure_agent(page, refresh_existing=False)
            except Exception:
                logger.warning("恢复 mini-app agent 失败: %s", page.get("slug"), exc_info=True)

    async def create_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            pages = self.load_pages()
            slug = payload.get("slug", "").strip() or slugify(str(payload.get("name", "")))
            if any(p.get("slug") == slug for p in pages):
                slug = f"{slug}-{uuid.uuid4().hex[:4]}"

            requested_agent_id = str(payload.get("agent_id") or "default").strip() or "default"
            if self.agent_registry.get(requested_agent_id) is None:
                requested_agent_id = "default"
            create_dedicated_agent = bool(payload.get("create_dedicated_agent", True))
            effective_agent_id = (
                f"miniapp-{slug}-agent" if create_dedicated_agent else requested_agent_id
            )
            now = int(time.time() * 1000)

            page: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "slug": slug,
                "name": str(payload.get("name", "")).strip(),
                "description": str(payload.get("description", "")).strip(),
                "icon": str(payload.get("icon") or "Sparkles"),
                "agent_id": effective_agent_id,
                "base_agent_id": requested_agent_id,
                "create_dedicated_agent": create_dedicated_agent,
                "system_prompt": str(payload.get("system_prompt", "")).strip(),
                "templates": list(payload.get("templates") or []),
                "type": "miniapp",
                "workspace_mode": str(payload.get("workspace_mode") or "scratch"),
                "source_project_path": str(payload.get("source_project_path") or "").strip(),
                "builder_type": str(payload.get("builder_type") or "builtin"),
                "generation_prompt": str(
                    payload.get("generation_prompt")
                    or payload.get("description")
                    or payload.get("name")
                    or ""
                ).strip(),
                "workspace_root": self._workspace_rel_dir(effective_agent_id, slug),
                "app_dir": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app",
                "entry_file_path": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app/index.html",
                "bridge_script_path": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app/sensenova_claw-bridge.js",
                "preserved_license_files": [],
                "build_status": "pending",
                "build_summary": "",
                "latest_run_id": "",
                "last_interaction_session_id": "",
                "created_at": now,
                "updated_at": now,
            }

            await self._ensure_agent(page, refresh_existing=True)
            self._ensure_workspace_structure(page)
            self._write_placeholder_app(page)
            self._write_workspace_manifest(page)
            pages.append(page)
            self.save_pages(pages)

        run = await self.trigger_generation(
            page["slug"],
            prompt=page["generation_prompt"],
            requested_by="create_page",
        )
        page = self.get_page(page["slug"]) or page
        page["latest_run"] = run
        return page

    async def update_page(self, page_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            pages = self.load_pages()
            for page in pages:
                if page.get("id") != page_id and page.get("slug") != page_id:
                    continue
                mutable_keys = {
                    "name",
                    "description",
                    "icon",
                    "system_prompt",
                    "templates",
                    "workspace_mode",
                    "source_project_path",
                    "builder_type",
                    "generation_prompt",
                    "build_status",
                    "build_summary",
                    "latest_run_id",
                    "last_interaction_session_id",
                    "preserved_license_files",
                    "entry_file_path",
                }
                for key, value in updates.items():
                    if key in mutable_keys and value is not None:
                        page[key] = value
                page["updated_at"] = int(time.time() * 1000)
                self.save_pages(pages)
                return page
        return None

    async def delete_page(self, page_id: str) -> bool:
        async with self._lock:
            pages = self.load_pages()
            new_pages = [
                page
                for page in pages
                if page.get("id") != page_id and page.get("slug") != page_id
            ]
            if len(new_pages) == len(pages):
                return False
            self.save_pages(new_pages)
            return True

    def list_runs(self, page_id: str) -> list[dict[str, Any]]:
        page = self.get_page(page_id)
        if not page:
            return []
        path = self.runs_dir / f"{page['slug']}.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取 mini-app run 失败: %s", path, exc_info=True)
            return []
        runs = data if isinstance(data, list) else []
        return sorted(runs, key=lambda item: item.get("started_at_ms", 0), reverse=True)

    async def trigger_generation(
        self,
        page_id: str,
        *,
        prompt: str,
        requested_by: str,
    ) -> dict[str, Any]:
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"custom page not found: {page_id}")

        run = {
            "id": f"run_{uuid.uuid4().hex[:12]}",
            "builder_type": page.get("builder_type", "builtin"),
            "status": "queued",
            "prompt": prompt,
            "requested_by": requested_by,
            "started_at_ms": int(time.time() * 1000),
            "ended_at_ms": None,
            "logs": [],
        }
        self._append_run(page, run)
        await self.update_page(
            page["slug"],
            {
                "build_status": "queued",
                "build_summary": "已创建生成任务",
                "latest_run_id": run["id"],
            },
        )

        builder_type = str(page.get("builder_type") or "builtin")
        if builder_type == "acp":
            task = asyncio.create_task(self._run_generation(page["slug"], run["id"], prompt))
            self._tasks[run["id"]] = task
        else:
            await self._run_generation(page["slug"], run["id"], prompt)

        refreshed = next(
            (item for item in self.list_runs(page["slug"]) if item.get("id") == run["id"]),
            run,
        )
        return refreshed

    async def dispatch_interaction(
        self,
        page_id: str,
        *,
        action: str,
        payload: dict[str, Any],
        message: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"custom page not found: {page_id}")
        if self.gateway is None:
            raise RuntimeError("gateway unavailable")

        session_id = session_id.strip() or str(page.get("last_interaction_session_id") or "").strip()
        if not session_id:
            created = await self.gateway.create_session(
                agent_id=str(page.get("agent_id") or "default"),
                meta={
                    "title": f"{page.get('name', 'MiniApp')} 交互会话",
                    "agent_id": str(page.get("agent_id") or "default"),
                    "source": "miniapp",
                    "custom_page_slug": page.get("slug"),
                },
            )
            session_id = str(created["session_id"])
        await self.update_page(page["slug"], {"last_interaction_session_id": session_id})

        interaction_message = message.strip() or self._build_interaction_message(page, action, payload)
        turn_id = await self.gateway.send_user_input(
            session_id=session_id,
            content=interaction_message,
            source="custom_page_interaction",
        )

        self._append_action_log(
            page,
            {
                "ts": int(time.time() * 1000),
                "target": "agent",
                "action": action,
                "payload": payload,
                "session_id": session_id,
                "turn_id": turn_id,
            },
        )

        return {
            "ok": True,
            "session_id": session_id,
            "turn_id": turn_id,
        }

    async def dispatch_action(
        self,
        page_id: str,
        *,
        action: str,
        payload: dict[str, Any],
        target: str,
        message: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"custom page not found: {page_id}")

        normalized_target = _normalize_action_target(target)
        if normalized_target == "agent":
            result = await self.dispatch_interaction(
                page_id,
                action=action,
                payload=payload,
                message=message,
                session_id=session_id,
            )
            return {
                **result,
                "target": "agent",
            }

        ts = int(time.time() * 1000)
        self._append_action_log(
            page,
            {
                "ts": ts,
                "target": normalized_target,
                "action": action,
                "payload": payload,
                "message": message.strip(),
                "session_id": "",
                "turn_id": "",
            },
        )
        return {
            "ok": True,
            "target": normalized_target,
            "session_id": "",
            "turn_id": "",
            "logged_at": ts,
        }

    def _workspace_rel_dir(self, agent_id: str, slug: str) -> str:
        return f"{agent_id}/miniapps/{slug}"

    def _workspace_abs_dir(self, page: dict[str, Any]) -> Path:
        return self.sensenova_claw_home / "workdir" / str(page["workspace_root"])

    def _app_abs_dir(self, page: dict[str, Any]) -> Path:
        return self.sensenova_claw_home / "workdir" / str(page["app_dir"])

    def _interaction_log_path(self, page: dict[str, Any]) -> Path:
        return self._workspace_abs_dir(page) / "interaction_log.jsonl"

    def _ensure_workspace_structure(self, page: dict[str, Any]) -> None:
        workspace_dir = self._workspace_abs_dir(page)
        app_dir = self._app_abs_dir(page)
        (workspace_dir / "logs").mkdir(parents=True, exist_ok=True)
        app_dir.mkdir(parents=True, exist_ok=True)

    def _write_workspace_manifest(self, page: dict[str, Any]) -> None:
        manifest = {
            "id": page["id"],
            "slug": page["slug"],
            "name": page["name"],
            "description": page["description"],
            "agent_id": page["agent_id"],
            "workspace_mode": page["workspace_mode"],
            "builder_type": page["builder_type"],
            "entry_file_path": page["entry_file_path"],
            "bridge_script_path": page["bridge_script_path"],
            "templates": page.get("templates", []),
            "preserved_license_files": page.get("preserved_license_files", []),
        }
        manifest_path = self._workspace_abs_dir(page) / "miniapp.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_placeholder_app(self, page: dict[str, Any]) -> None:
        app_dir = self._app_abs_dir(page)
        self._write_bridge_script(page)
        (app_dir / "styles.css").write_text(_placeholder_css(), encoding="utf-8")
        (app_dir / "app.js").write_text(_placeholder_js(page["name"]), encoding="utf-8")
        (app_dir / "index.html").write_text(_placeholder_html(page["name"]), encoding="utf-8")

    async def _ensure_agent(self, page: dict[str, Any], *, refresh_existing: bool) -> None:
        agent_id = str(page.get("agent_id") or "default").strip() or "default"
        base_agent_id = str(page.get("base_agent_id") or "default").strip() or "default"
        create_dedicated = bool(page.get("create_dedicated_agent", False))

        await ensure_agent_workspace(str(self.sensenova_claw_home), agent_id)
        if not create_dedicated:
            if self.agent_registry.get(agent_id) is None:
                fallback = self.agent_registry.get("default")
                if fallback is None:
                    return
                self.agent_registry.register(fallback)
            return

        if self.agent_registry.get(agent_id) is not None and not refresh_existing:
            return

        base_agent = self.agent_registry.get(base_agent_id) or self.agent_registry.get("default")
        if base_agent is None:
            raise RuntimeError("default agent not found")

        workdir = str(self._app_abs_dir(page).resolve())
        system_prompt = self._build_agent_system_prompt(page, base_agent.system_prompt)
        dedicated = AgentConfig.create(
            id=agent_id,
            name=f"{page['name']} Workspace Agent",
            description=f"负责 mini-app《{page['name']}》的构建、维护与交互响应",
            model=base_agent.model,
            temperature=base_agent.temperature,
            max_tokens=base_agent.max_tokens,
            extra_body=dict(base_agent.extra_body),
            system_prompt=system_prompt,
            tools=list(base_agent.tools),
            skills=list(base_agent.skills),
            workdir=workdir,
            can_delegate_to=list(base_agent.can_delegate_to),
            max_delegation_depth=base_agent.max_delegation_depth,
            max_pingpong_turns=base_agent.max_pingpong_turns,
        )
        self.agent_registry.register(dedicated)

        prompt_path = self.sensenova_claw_home / "agents" / agent_id / "SYSTEM_PROMPT.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(system_prompt, encoding="utf-8")

    def _build_agent_system_prompt(self, page: dict[str, Any], base_prompt: str) -> str:
        license_lines = "\n".join(
            f"- 保留并尊重授权文件: {item}" for item in page.get("preserved_license_files", [])
        )
        if not license_lines:
            license_lines = "- 如果工作区存在 LICENSE/NOTICE/ATTRIBUTIONS，请保留它们"
        return (
            f"{base_prompt.strip()}\n\n"
            "## Mini-App Workspace 额外职责\n"
            f"- 你负责维护 mini-app《{page['name']}》\n"
            f"- 当前 mini-app slug: {page['slug']}\n"
            f"- 当前 mini-app 描述: {page.get('description', '')}\n"
            "- 你的工作目录就是该 mini-app 的 app 目录，默认直接在这里读写前端文件\n"
            "- 当用户通过页面按钮、表单或课程结果触发交互时，系统会把事件整理成结构化消息发给你\n"
            "- 需要继续澄清需求时，优先使用 ask_user\n"
            "- 需要调整页面时，直接修改当前工作目录中的 HTML/CSS/JS 文件\n"
            f"{license_lines}\n"
            "- 任何复用现有项目的场景，都不要删除授权与归因文件\n"
            "- 如果页面里要把交互发送回宿主页面，请使用 window.SensenovaClawMiniApp.emit(action, payload)"
        ).strip()

    def _append_run(self, page: dict[str, Any], run: dict[str, Any]) -> None:
        path = self.runs_dir
        path.mkdir(parents=True, exist_ok=True)
        run_file = path / f"{page['slug']}.json"
        runs = self.list_runs(page["slug"])
        runs.append(run)
        run_file.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_run(
        self,
        page: dict[str, Any],
        run_id: str,
        updater: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any] | None:
        run_file = self.runs_dir / f"{page['slug']}.json"
        runs = self.list_runs(page["slug"])
        updated_run = None
        for run in runs:
            if run.get("id") != run_id:
                continue
            updater(run)
            updated_run = run
            break
        run_file.parent.mkdir(parents=True, exist_ok=True)
        run_file.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        return updated_run

    def _log_run(self, page: dict[str, Any], run_id: str, message: str, *, level: str = "info") -> None:
        def updater(run: dict[str, Any]) -> None:
            run.setdefault("logs", []).append(
                {
                    "ts": int(time.time() * 1000),
                    "level": level,
                    "message": message,
                }
            )

        self._update_run(page, run_id, updater)

    async def _run_generation(self, page_id: str, run_id: str, prompt: str) -> None:
        page = self.get_page(page_id)
        if not page:
            return

        try:
            self._log_run(page, run_id, "开始生成 mini-app")
            await self.update_page(page["slug"], {"build_status": "running", "build_summary": "正在生成 mini-app..."})
            builder_type = str(page.get("builder_type") or "builtin")
            if builder_type == "acp":
                await self._run_acp_generation(page, run_id, prompt)
            else:
                await self._run_builtin_generation(page, run_id, prompt)

            self._update_run(
                page,
                run_id,
                lambda run: run.update(
                    {
                        "status": "completed",
                        "ended_at_ms": int(time.time() * 1000),
                    }
                ),
            )
            await self.update_page(
                page["slug"],
                {
                    "build_status": "ready",
                    "build_summary": "mini-app 已生成，可直接预览并继续让 Agent 迭代",
                    "latest_run_id": run_id,
                },
            )
        except Exception as exc:
            logger.warning("mini-app generation failed: %s", page.get("slug"), exc_info=True)
            self._log_run(page, run_id, f"生成失败: {exc}", level="error")
            self._update_run(
                page,
                run_id,
                lambda run: run.update(
                    {
                        "status": "failed",
                        "ended_at_ms": int(time.time() * 1000),
                        "error": str(exc),
                    }
                ),
            )
            await self.update_page(
                page["slug"],
                {
                    "build_status": "failed",
                    "build_summary": f"生成失败: {exc}",
                    "latest_run_id": run_id,
                },
            )
        finally:
            self._write_workspace_manifest(self.get_page(page_id) or page)
            self._tasks.pop(run_id, None)

    async def _run_builtin_generation(self, page: dict[str, Any], run_id: str, prompt: str) -> None:
        app_dir = self._app_abs_dir(page)
        self._write_bridge_script(page)

        if page.get("workspace_mode") == "reuse" and page.get("source_project_path"):
            self._log_run(page, run_id, "复用现有项目并保留 LICENSE")
            entry_path, licenses = self._copy_source_project(page)
            if entry_path:
                self._inject_bridge_script(entry_path)
                await self.update_page(
                    page["slug"],
                    {
                        "entry_file_path": self._to_workdir_rel(entry_path),
                        "preserved_license_files": licenses,
                    },
                )
                self._log_run(page, run_id, f"已复用项目入口: {self._to_workdir_rel(entry_path)}")
                return
            self._log_run(page, run_id, "未找到可直接打开的入口，改为生成包装页面")

        template_kind = "generic-workspace"
        self._log_run(page, run_id, f"使用内置模板: {template_kind}")
        (app_dir / "styles.css").write_text(_builtin_styles_css(), encoding="utf-8")
        (app_dir / "app.js").write_text(_generic_workspace_js(page), encoding="utf-8")
        (app_dir / "index.html").write_text(_generic_workspace_html(page), encoding="utf-8")

    async def _run_acp_generation(self, page: dict[str, Any], run_id: str, prompt: str) -> None:
        acp_cfg = self._get_acp_config()
        command = str(acp_cfg.get("command") or "").strip()
        if not command:
            raise ACPClientError("miniapps.acp.command 未配置")

        args = list(acp_cfg.get("args") or [])
        env = {str(k): str(v) for k, v in dict(acp_cfg.get("env") or {}).items()}
        startup_timeout = float(acp_cfg.get("startup_timeout_seconds", 20))
        request_timeout = float(acp_cfg.get("request_timeout_seconds", 180))
        app_dir = self._app_abs_dir(page)
        self._write_bridge_script(page)

        async def on_notification(message: dict[str, Any]) -> None:
            method = str(message.get("method") or "")
            params = message.get("params") or {}
            if method == "session/update":
                update = (params or {}).get("update") or {}
                self._log_run(page, run_id, _format_acp_update_log_message(update))
            else:
                self._log_run(page, run_id, f"ACP notification: {method}")

        async with ACPClient(
            command,
            args,
            env=env,
            cwd=str(app_dir),
            startup_timeout_seconds=startup_timeout,
            request_timeout_seconds=request_timeout,
        ) as client:
            self._log_run(page, run_id, "ACP initialize")
            init_result = await client.initialize()
            self._log_run(
                page,
                run_id,
                f"ACP agent 已就绪: {((init_result or {}).get('agentInfo') or {}).get('name', 'unknown')}",
            )
            session_id = await client.new_session(str(app_dir))
            self._log_run(page, run_id, f"ACP session created: {session_id}")
            build_prompt = self._build_acp_prompt(page, prompt)
            result = await client.prompt(session_id, build_prompt, on_notification=on_notification)
            self._log_run(page, run_id, f"ACP prompt 完成: {json.dumps(result, ensure_ascii=False)}")

    def _build_acp_prompt(self, page: dict[str, Any], prompt: str) -> str:
        return (
            f"请在当前工作目录中构建 mini-app《{page['name']}》。\n"
            f"需求描述：{page.get('description', '')}\n"
            f"用户最新要求：{prompt}\n"
            f"模板建议：{json.dumps(page.get('templates', []), ensure_ascii=False)}\n"
            "要求：\n"
            "1. 输出一个可直接打开的前端页面，默认入口为 index.html。\n"
            "2. 若需要把页面交互发送给宿主系统，请使用 window.SensenovaClawMiniApp.emit(action, payload)。\n"
            "3. 若复用了现有项目，请保留 LICENSE/NOTICE/ATTRIBUTIONS 文件。\n"
            "4. 若需要拆分文件，可创建 styles.css、app.js 等辅助文件。\n"
            "5. 生成完成后请保证页面可直接在静态文件服务器中运行。"
        )

    def _get_acp_config(self) -> dict[str, Any]:
        if hasattr(self.config, "get"):
            return dict(self.config.get("miniapps.acp", {}) or {})
        if isinstance(self.config, dict):
            return dict((self.config.get("miniapps") or {}).get("acp") or {})
        return {}

    def _copy_source_project(self, page: dict[str, Any]) -> tuple[Path | None, list[str]]:
        source = Path(str(page.get("source_project_path") or "")).expanduser()
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(f"source project path not found: {source}")

        app_dir = self._app_abs_dir(page)
        for child in app_dir.iterdir():
            if child.name.startswith("."):
                continue
            if child.name in {"index.html", "app.js", "styles.css", "sensenova_claw-bridge.js"}:
                child.unlink(missing_ok=True)
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        ignore = shutil.ignore_patterns(".git", "node_modules", ".next", "dist", "build", "__pycache__")
        for entry in source.iterdir():
            if entry.name in {".git", "node_modules", ".next", "dist", "build", "__pycache__"}:
                continue
            target = app_dir / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target, dirs_exist_ok=True, ignore=ignore)
            else:
                shutil.copy2(entry, target)

        licenses: list[str] = []
        source_licenses_dir = app_dir / "source_licenses"
        source_licenses_dir.mkdir(parents=True, exist_ok=True)
        for name in LICENSE_FILENAMES:
            candidate = source / name
            if not candidate.exists():
                continue
            shutil.copy2(candidate, source_licenses_dir / candidate.name)
            licenses.append(f"{self._to_workdir_rel(source_licenses_dir / candidate.name)}")

        (app_dir / "ATTRIBUTIONS.md").write_text(
            _build_attributions_markdown(source=source, licenses=licenses),
            encoding="utf-8",
        )

        entry = self._find_entry_file(app_dir)
        if entry is None:
            (app_dir / "index.html").write_text(_reuse_wrapper_html(page, source), encoding="utf-8")
            entry = app_dir / "index.html"
        return entry, licenses

    def _find_entry_file(self, app_dir: Path) -> Path | None:
        candidates = [
            app_dir / "index.html",
            app_dir / "public" / "index.html",
            app_dir / "dist" / "index.html",
            app_dir / "build" / "index.html",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _inject_bridge_script(self, entry_path: Path) -> None:
        try:
            content = entry_path.read_text(encoding="utf-8")
        except Exception:
            return
        if "sensenova_claw-bridge.js" in content:
            return
        if "</body>" in content:
            content = content.replace(
                "</body>",
                '  <script src="./sensenova_claw-bridge.js"></script>\n</body>',
            )
        else:
            content += '\n<script src="./sensenova_claw-bridge.js"></script>\n'
        entry_path.write_text(content, encoding="utf-8")

    def _write_bridge_script(self, page: dict[str, Any]) -> None:
        bridge_path = self._app_abs_dir(page) / "sensenova_claw-bridge.js"
        bridge_path.write_text(_bridge_js(page["slug"]), encoding="utf-8")

    def _to_workdir_rel(self, path: Path) -> str:
        return str(path.resolve().relative_to((self.sensenova_claw_home / "workdir").resolve())).replace("\\", "/")

    def _build_interaction_message(
        self,
        page: dict[str, Any],
        action: str,
        payload: dict[str, Any],
    ) -> str:
        return (
            f"【MiniApp 交互事件】\n"
            f"- 页面: {page.get('name')} ({page.get('slug')})\n"
            f"- 动作: {action}\n"
            f"- 载荷: {json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "请根据当前页面状态与用户操作继续推进任务。"
            "如果需要改页面，请直接修改当前工作目录中的文件；如果需要澄清需求，请使用 ask_user。"
        )

    def _append_action_log(self, page: dict[str, Any], record: dict[str, Any]) -> None:
        path = self._interaction_log_path(page)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

def _build_attributions_markdown(source: Path, licenses: list[str]) -> str:
    license_lines = "\n".join(f"- {item}" for item in licenses) if licenses else "- 未检测到 LICENSE/NOTICE 文件"
    return (
        "# 项目复用归因\n\n"
        f"- 复用来源路径: `{source}`\n"
        "- 该 mini-app 由 Sensenova-Claw 在保留授权文件的前提下复制到当前工作区。\n"
        "- 请在继续修改时保留原授权与归因信息。\n\n"
        "## 已保留的授权文件\n"
        f"{license_lines}\n"
    )


def _extract_acp_update_text(update: dict[str, Any]) -> str:
    content = update.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if "title" in update:
        return str(update.get("title"))
    if "description" in update:
        return str(update.get("description"))
    return json.dumps(update, ensure_ascii=False)


def _format_acp_update_log_message(update: dict[str, Any]) -> str:
    label = str(update.get("sessionUpdate") or "update").strip() or "update"
    status = str(update.get("status") or "").strip()
    text = _extract_acp_update_text(update)
    if status:
        return f"ACP {label} [{status}]: {text}"
    return f"ACP {label}: {text}"


def _normalize_action_target(target: str) -> str:
    value = str(target or "").strip().lower()
    if value in {"local", "server", "agent"}:
        return value
    return "agent"


def _placeholder_html(name: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{name}</title>
    <link rel="stylesheet" href="./styles.css" />
  </head>
  <body>
    <main class="placeholder-shell">
      <div class="placeholder-card">
        <span class="eyebrow">Sensenova-Claw Mini-App</span>
        <h1>{name}</h1>
        <p>正在初始化工作区与页面资源，请稍候刷新。</p>
        <div class="pulse-bar"><span></span></div>
      </div>
    </main>
    <script src="./sensenova_claw-bridge.js"></script>
    <script src="./app.js"></script>
  </body>
</html>
"""


def _placeholder_css() -> str:
    return """body {
  margin: 0;
  font-family: "Helvetica Neue", Arial, sans-serif;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.25), transparent 35%),
    radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.22), transparent 32%),
    #08111a;
  color: #f8fafc;
}

.placeholder-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.placeholder-card {
  width: min(560px, 100%);
  padding: 28px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(6, 11, 18, 0.84);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}

.eyebrow {
  display: inline-block;
  margin-bottom: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.16);
  color: #7dd3fc;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.pulse-bar {
  margin-top: 20px;
  height: 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.pulse-bar span {
  display: block;
  width: 36%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #38bdf8, #34d399);
  animation: placeholder-slide 1.6s infinite ease-in-out;
}

@keyframes placeholder-slide {
  from { transform: translateX(-120%); }
  to { transform: translateX(320%); }
}
"""


def _placeholder_js(name: str) -> str:
    return f"""console.log("Mini-app placeholder ready: {name}");
"""


def _bridge_js(slug: str) -> str:
    return f"""(function () {{
  function post(kind, action, payload, target, meta) {{
    if (window.parent === window) return false;
    window.parent.postMessage({{
      source: "sensenova_claw-miniapp",
      slug: "{slug}",
      kind: kind,
      action: action || "",
      payload: payload || {{}},
      target: target || "",
      meta: meta || {{}},
    }}, "*");
    return true;
  }}

  window.SensenovaClawMiniApp = {{
    emit: function(action, payload, options) {{
      var nextOptions = options || {{}};
      return post("interaction", action, payload, nextOptions.target || "", nextOptions.meta || {{}});
    }},
    emitTo: function(target, action, payload, options) {{
      var nextOptions = options || {{}};
      return post("interaction", action, payload, target || "", nextOptions.meta || {{}});
    }},
    configureActionRouting: function(config) {{
      var nextConfig = config || {{}};
      return post("config", "", {{}}, "", {{
        defaultTarget: nextConfig.defaultTarget || "",
        routes: nextConfig.routes || {{}},
      }});
    }},
    updateState: function(payload) {{
      return post("state", "", payload, "", {{}});
    }},
    log: function(payload) {{
      return post("log", "", payload, "", {{}});
    }},
  }};
}})();
"""


def _builtin_styles_css() -> str:
    return """body {
  margin: 0;
  font-family: "Helvetica Neue", Arial, sans-serif;
  color: #0f172a;
  background:
    linear-gradient(135deg, rgba(15, 118, 110, 0.16), transparent 36%),
    linear-gradient(225deg, rgba(14, 165, 233, 0.14), transparent 42%),
    #f4f7fb;
}

.miniapp-shell {
  min-height: 100vh;
  padding: 24px;
}

.hero {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
}

.card {
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 20px 70px rgba(15, 23, 42, 0.08);
}

.hero-main {
  padding: 28px;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.1);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  margin: 16px 0 12px;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.05;
}

.hero-desc {
  max-width: 58ch;
  color: #475569;
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
}

.btn {
  appearance: none;
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 120ms ease, box-shadow 120ms ease, opacity 120ms ease;
}

.btn:hover {
  transform: translateY(-1px);
}

.btn-primary {
  background: linear-gradient(135deg, #0f766e, #0ea5e9);
  color: #fff;
  box-shadow: 0 12px 30px rgba(14, 165, 233, 0.24);
}

.btn-secondary {
  background: #e2e8f0;
  color: #0f172a;
}

.stats-card {
  padding: 24px;
  display: grid;
  gap: 14px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat {
  padding: 14px;
  border-radius: 18px;
  background: #f8fafc;
}

.stat strong {
  display: block;
  font-size: 24px;
}

.section-grid {
  display: grid;
  gap: 18px;
  margin-top: 18px;
  grid-template-columns: 1.3fr 1fr;
}

.section-card {
  padding: 22px;
}

.list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.list-item {
  padding: 16px;
  border-radius: 18px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.list-item h3 {
  margin: 0 0 6px;
}

.event-log {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.event-pill {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(15, 118, 110, 0.08);
  color: #115e59;
  font-size: 13px;
}

.quiz-shell {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.option-grid {
  display: grid;
  gap: 10px;
}

.option {
  width: 100%;
  text-align: left;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #fff;
  cursor: pointer;
}

.option.selected {
  border-color: #0ea5e9;
  background: rgba(14, 165, 233, 0.08);
}

.result-banner {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(16, 185, 129, 0.12);
  color: #166534;
  font-weight: 600;
}

@media (max-width: 960px) {
  .hero,
  .section-grid {
    grid-template-columns: 1fr;
  }
}
"""

def _generic_workspace_html(page: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{page['name']}</title>
    <link rel="stylesheet" href="./styles.css" />
  </head>
  <body>
    <main class="miniapp-shell">
      <section class="hero">
        <div class="card hero-main">
          <div class="hero-kicker">Workspace App</div>
          <h1 class="hero-title">{page['name']}</h1>
          <p class="hero-desc">{page.get('description') or '一个可以和专属 Agent 协同工作的工作区页面。'}</p>
          <div class="hero-actions">
            <button class="btn btn-primary" id="save-server-btn">保存当前状态</button>
            <button class="btn btn-secondary" id="refine-page-btn">请求 Agent 优化</button>
          </div>
        </div>

        <aside class="card stats-card">
          <div class="hero-kicker">工作台状态</div>
          <div class="stats-grid">
            <div class="stat"><span>模块</span><strong id="card-count">0</strong></div>
            <div class="stat"><span>互动</span><strong id="interaction-count">0</strong></div>
            <div class="stat"><span>模板</span><strong id="template-count">0</strong></div>
            <div class="stat"><span>最近同步</span><strong id="last-sync">--</strong></div>
          </div>
        </aside>
      </section>

      <section class="section-grid">
        <section class="card section-card">
          <div class="hero-kicker">任务卡片</div>
          <div class="list" id="task-list"></div>
        </section>

        <section class="card section-card">
          <div class="hero-kicker">自由输入</div>
          <textarea id="freeform-input" rows="9" style="width: 100%; border-radius: 18px; border: 1px solid rgba(15, 23, 42, 0.1); padding: 14px; resize: vertical;" placeholder="在这里写你想让 Agent 继续处理的内容"></textarea>
          <div class="hero-actions">
            <button class="btn btn-primary" id="submit-note-btn">提交给 Agent</button>
          </div>
        </section>
      </section>

      <section class="card section-card" style="margin-top: 18px;">
        <div class="hero-kicker">页面事件</div>
        <div class="event-log" id="event-log"></div>
      </section>
    </main>

    <script src="./sensenova_claw-bridge.js"></script>
    <script src="./app.js"></script>
  </body>
</html>
"""


def _generic_workspace_js(page: dict[str, Any]) -> str:
    templates = json.dumps(_normalize_templates(page), ensure_ascii=False)
    return f"""const templates = {templates};
let interactionCount = 0;
const actionRouting = {{
  defaultTarget: "agent",
  routes: {{
    task_card_selected: "local",
    save_workspace_snapshot: "server",
    request_page_refine: "agent",
    freeform_note_submitted: "agent",
  }},
}};

function emitLog(text) {{
  const host = document.getElementById("event-log");
  const item = document.createElement("div");
  item.className = "event-pill";
  item.textContent = text;
  host.prepend(item);
}}

function notifyAgent(action, payload) {{
  interactionCount += 1;
  document.getElementById("interaction-count").textContent = String(interactionCount);
  document.getElementById("last-sync").textContent = new Date().toLocaleTimeString("zh-CN");
  if (window.SensenovaClawMiniApp) {{
    window.SensenovaClawMiniApp.emit(action, payload);
  }}
  emitLog(`[Agent] ${{action}} -> ${{JSON.stringify(payload)}}`);
}}

function emitWorkspaceAction(action, payload, targetLabel) {{
  interactionCount += 1;
  document.getElementById("interaction-count").textContent = String(interactionCount);
  document.getElementById("last-sync").textContent = new Date().toLocaleTimeString("zh-CN");
  if (window.SensenovaClawMiniApp) {{
    window.SensenovaClawMiniApp.emit(action, payload);
  }}
  emitLog(`[${{targetLabel}}] ${{action}} -> ${{JSON.stringify(payload)}}`);
}}

function renderTasks() {{
  const host = document.getElementById("task-list");
  const items = templates.length > 0 ? templates : [
    {{ title: "整理需求", desc: "把当前工作流拆成清晰的步骤和交付物。" }},
    {{ title: "快速试验", desc: "先做最小可运行版本，再逐步增强。" }},
    {{ title: "继续迭代", desc: "把页面事件和 Agent 响应串起来。" }},
  ];
  document.getElementById("card-count").textContent = String(items.length);
  document.getElementById("template-count").textContent = String(items.length);
  host.innerHTML = "";
  items.forEach((item) => {{
    const node = document.createElement("div");
    node.className = "list-item";
    node.innerHTML = `<h3>${{item.title}}</h3><p>${{item.desc || ""}}</p><button class="btn btn-secondary" data-title="${{item.title}}">执行这个动作</button>`;
    host.appendChild(node);
  }});
}}

document.getElementById("task-list").addEventListener("click", (event) => {{
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.dataset.title) return;
  emitWorkspaceAction("task_card_selected", {{
    page: "{page['slug']}",
    title: target.dataset.title,
  }}, "Local");
}});

document.getElementById("save-server-btn").addEventListener("click", () => {{
  emitWorkspaceAction("save_workspace_snapshot", {{
    page: "{page['slug']}",
    summary: "用户在页面上保存了当前工作区状态",
  }}, "Server");
}});

document.getElementById("refine-page-btn").addEventListener("click", () => {{
  emitWorkspaceAction("request_page_refine", {{
    page: "{page['slug']}",
    request: "请根据当前使用体验优化页面布局和交互",
  }}, "Agent");
}});

document.getElementById("submit-note-btn").addEventListener("click", () => {{
  const text = document.getElementById("freeform-input").value.trim();
  if (!text) {{
    emitLog("请先输入一些内容");
    return;
  }}
  emitWorkspaceAction("freeform_note_submitted", {{
    page: "{page['slug']}",
    note: text,
  }}, "Agent");
}});

if (window.SensenovaClawMiniApp && window.SensenovaClawMiniApp.configureActionRouting) {{
  window.SensenovaClawMiniApp.configureActionRouting(actionRouting);
}}

renderTasks();
emitLog("Workspace app 已初始化。");
"""


def _reuse_wrapper_html(page: dict[str, Any], source: Path) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{page['name']}</title>
    <link rel="stylesheet" href="./styles.css" />
  </head>
  <body>
    <main class="miniapp-shell">
      <section class="card hero-main">
        <div class="hero-kicker">Reused Project</div>
        <h1 class="hero-title">{page['name']}</h1>
        <p class="hero-desc">已复制现有项目：{source}</p>
        <p class="hero-desc">该项目未检测到可直接作为入口的 index.html，因此当前显示包装页。你可以让专属 Agent 继续调整目录并生成真正的入口页面。</p>
        <div class="hero-actions">
          <button class="btn btn-primary" onclick="window.SensenovaClawMiniApp && window.SensenovaClawMiniApp.emit('request_project_adaptation', {{ source: '{source}' }})">让 Agent 继续接入这个项目</button>
        </div>
      </section>
    </main>
    <script src="./sensenova_claw-bridge.js"></script>
  </body>
</html>
"""


def _normalize_templates(page: dict[str, Any]) -> list[dict[str, str]]:
    items = []
    for item in list(page.get("templates") or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "desc": str(item.get("desc") or "").strip(),
            }
        )
    return items
