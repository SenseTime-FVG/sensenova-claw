from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import shutil
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

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


@dataclass
class PreviewServerHandle:
    slug: str
    port: int
    process: asyncio.subprocess.Process
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None


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
        self._preview_server_lock = asyncio.Lock()
        self._preview_servers: dict[str, PreviewServerHandle] = {}

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

    async def shutdown(self) -> None:
        async with self._preview_server_lock:
            handles = list(self._preview_servers.values())
            self._preview_servers.clear()
        for handle in handles:
            await self._stop_preview_server(handle)

    async def ensure_preview_server(self, page_id: str) -> dict[str, Any]:
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"custom page not found: {page_id}")

        slug = str(page.get("slug") or "")
        async with self._preview_server_lock:
            handle = self._preview_servers.get(slug)
            if handle and handle.process.returncode is None:
                return {
                    "slug": slug,
                    "port": handle.port,
                    "base_url": f"http://127.0.0.1:{handle.port}",
                }

            if handle:
                await self._stop_preview_server(handle)
                self._preview_servers.pop(slug, None)

            new_handle = await self._start_preview_server(page)
            self._preview_servers[slug] = new_handle
            return {
                "slug": slug,
                "port": new_handle.port,
                "base_url": f"http://127.0.0.1:{new_handle.port}",
            }

    async def _drop_preview_server(self, slug: str) -> None:
        if not slug:
            return
        async with self._preview_server_lock:
            handle = self._preview_servers.pop(slug, None)
        if handle is not None:
            await self._stop_preview_server(handle)

    async def _start_preview_server(self, page: dict[str, Any]) -> PreviewServerHandle:
        workspace_dir = self._workspace_abs_dir(page)
        server_path = workspace_dir / "server.py"
        if not server_path.exists():
            raise FileNotFoundError(f"workspace server entry not found: {server_path}")

        port = _pick_free_port()
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(server_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            cwd=str(workspace_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        handle = PreviewServerHandle(
            slug=str(page.get("slug") or ""),
            port=port,
            process=proc,
            stdout_task=asyncio.create_task(self._stream_preview_server_logs(str(page.get("slug") or ""), proc.stdout, "stdout")),
            stderr_task=asyncio.create_task(self._stream_preview_server_logs(str(page.get("slug") or ""), proc.stderr, "stderr")),
        )
        await self._wait_preview_server_ready(handle)
        logger.info("Mini-app preview server started: slug=%s port=%s", handle.slug, handle.port)
        return handle

    async def _stop_preview_server(self, handle: PreviewServerHandle) -> None:
        for task in (handle.stdout_task, handle.stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        proc = handle.process
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        logger.info("Mini-app preview server stopped: slug=%s port=%s", handle.slug, handle.port)

    async def _wait_preview_server_ready(self, handle: PreviewServerHandle) -> None:
        url = f"http://127.0.0.1:{handle.port}/health"
        async with httpx.AsyncClient(timeout=1.0) as client:
            for _ in range(40):
                if handle.process.returncode is not None:
                    raise RuntimeError(
                        f"workspace preview server exited early: slug={handle.slug} returncode={handle.process.returncode}"
                    )
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
        raise RuntimeError(f"workspace preview server start timeout: slug={handle.slug}")

    async def _stream_preview_server_logs(
        self,
        slug: str,
        stream: asyncio.StreamReader | None,
        channel: str,
    ) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.debug("Mini-app preview server [%s][%s]: %s", slug, channel, text)

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
                "preview_mode": "server",
                "workspace_root": self._workspace_rel_dir(effective_agent_id, slug),
                "app_dir": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app",
                "server_entry_file_path": f"{self._workspace_rel_dir(effective_agent_id, slug)}/server.py",
                "entry_file_path": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app/index.html",
                "bridge_script_path": f"{self._workspace_rel_dir(effective_agent_id, slug)}/app/sensenova_claw-bridge.js",
                "server_start_command": sys.executable,
                "server_start_args": ["server.py"],
                "background_refresh_policy": "optional_cron",
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
                    "preview_mode",
                    "build_status",
                    "build_summary",
                    "latest_run_id",
                    "last_interaction_session_id",
                    "preserved_license_files",
                    "entry_file_path",
                    "server_entry_file_path",
                    "server_start_command",
                    "server_start_args",
                    "background_refresh_policy",
                }
                for key, value in updates.items():
                    if key in mutable_keys and value is not None:
                        page[key] = value
                page["updated_at"] = int(time.time() * 1000)
                self.save_pages(pages)
                return page
        return None

    async def delete_page(self, page_id: str, *, delete_workspace: bool = False) -> bool:
        async with self._lock:
            pages = self.load_pages()
            deleted_page = next(
                (page for page in pages if page.get("id") == page_id or page.get("slug") == page_id),
                None,
            )
            new_pages = [
                page
                for page in pages
                if page.get("id") != page_id and page.get("slug") != page_id
            ]
            if len(new_pages) == len(pages):
                return False
            self.save_pages(new_pages)
        if deleted_page:
            await self._drop_preview_server(str(deleted_page.get("slug") or ""))
            self._delete_dedicated_agent(deleted_page)
            if delete_workspace:
                self._delete_workspace_dir(deleted_page)
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
        refresh_mode: str = "none",
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

        normalized_refresh_mode = _normalize_refresh_mode(refresh_mode)
        interaction_message = message.strip() or self._build_interaction_message(
            page,
            action,
            payload,
            refresh_mode=normalized_refresh_mode,
        )
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
                "refresh_mode": normalized_refresh_mode,
            },
        )

        return {
            "ok": True,
            "session_id": session_id,
            "turn_id": turn_id,
            "refresh_mode": normalized_refresh_mode,
            "should_refresh_workspace": normalized_refresh_mode == "immediate",
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
        refresh_mode: str = "none",
    ) -> dict[str, Any]:
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"custom page not found: {page_id}")

        normalized_target = _normalize_action_target(target)
        normalized_refresh_mode = _normalize_refresh_mode(refresh_mode)
        if normalized_target == "agent":
            result = await self.dispatch_interaction(
                page_id,
                action=action,
                payload=payload,
                message=message,
                session_id=session_id,
                refresh_mode=normalized_refresh_mode,
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
                "refresh_mode": normalized_refresh_mode,
            },
        )
        return {
            "ok": True,
            "target": normalized_target,
            "session_id": "",
            "turn_id": "",
            "logged_at": ts,
            "refresh_mode": normalized_refresh_mode,
            "should_refresh_workspace": normalized_refresh_mode == "immediate",
        }

    def _workspace_rel_dir(self, agent_id: str, slug: str) -> str:
        return f"{agent_id}/miniapps/{slug}"

    def _workspace_abs_dir(self, page: dict[str, Any]) -> Path:
        return self.sensenova_claw_home / "workdir" / str(page["workspace_root"])

    def _delete_dedicated_agent(self, page: dict[str, Any]) -> None:
        if not bool(page.get("create_dedicated_agent", False)):
            return
        agent_id = str(page.get("agent_id") or "").strip()
        if not agent_id:
            return
        self.agent_registry.delete(agent_id)
        prompt_path = self.sensenova_claw_home / "agents" / agent_id / "SYSTEM_PROMPT.md"
        if prompt_path.exists():
            prompt_path.unlink()

    def _delete_workspace_dir(self, page: dict[str, Any]) -> None:
        workspace_root = str(page.get("workspace_root") or "").strip()
        if not workspace_root:
            return

        workdir_root = (self.sensenova_claw_home / "workdir").resolve()
        workspace_dir = (workdir_root / workspace_root).resolve()
        try:
            workspace_dir.relative_to(workdir_root)
        except ValueError as exc:
            raise ValueError(f"unsafe workspace path: {workspace_root}") from exc

        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

    def _app_abs_dir(self, page: dict[str, Any]) -> Path:
        return self.sensenova_claw_home / "workdir" / str(page["app_dir"])

    def _interaction_log_path(self, page: dict[str, Any]) -> Path:
        return self._workspace_abs_dir(page) / "interaction_log.jsonl"

    def _ensure_workspace_structure(self, page: dict[str, Any]) -> None:
        workspace_dir = self._workspace_abs_dir(page)
        app_dir = self._app_abs_dir(page)
        (workspace_dir / "logs").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "data").mkdir(parents=True, exist_ok=True)
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
            "preview_mode": page.get("preview_mode", "server"),
            "entry_file_path": page["entry_file_path"],
            "server_entry_file_path": page.get("server_entry_file_path", ""),
            "server_start_command": page.get("server_start_command", sys.executable),
            "server_start_args": page.get("server_start_args", ["server.py"]),
            "background_refresh_policy": page.get("background_refresh_policy", "optional_cron"),
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
        workspace_dir = self._workspace_abs_dir(page)
        app_dir = self._app_abs_dir(page)
        self._write_bridge_script(page)
        (workspace_dir / "server.py").write_text(_standalone_workspace_server_py(), encoding="utf-8")
        state_path = workspace_dir / "data" / "workspace_state.json"
        if not state_path.exists():
            state_path.write_text(
                json.dumps(_default_workspace_state(page), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
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

        workdir = str(self._workspace_abs_dir(page).resolve())
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
            "- 你的工作目录就是该 mini-app 的 workspace 根目录，前端页面在 app/，服务端入口在 server.py，持久化数据在 data/\n"
            "- 当用户通过页面按钮、表单或课程结果触发交互时，系统会把事件整理成结构化消息发给你\n"
            "- 先把工作区设计成自包含的 client-server 系统：大多数交互优先由浏览器本地逻辑或 workspace 自己的服务端接口完成，只有最后兜底才把消息发给 Agent\n"
            "- 普通问答、笔记沉淀、答题记录和状态保存，不应默认触发整个工作区刷新；只有显式要求时才做即时刷新\n"
            "- 需要继续澄清需求时，优先使用 ask_user\n"
            "- 需要调整页面时，优先同时考虑 app/ 前端与 server.py 服务端的数据结构和接口，而不是只改单页 UI\n"
            "- 若工作区需要补充下一批内容，优先做成后台/夜间 refresh、可选 cron 或队列式预生成，避免打断当前用户会话\n"
            f"{license_lines}\n"
            "- 任何复用现有项目的场景，都不要删除授权与归因文件\n"
            "- 如果页面里要把交互发送回宿主页面，请使用 window.SensenovaClawMiniApp.emit(action, payload, options)，并明确 options.refreshMode"
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
                    "build_summary": "workspace 已生成并接入独立 Web server，可直接预览；普通问答不会默认触发刷新",
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

        template_kind = "generic-workspace-server"
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
        workspace_dir = self._workspace_abs_dir(page)
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
            cwd=str(workspace_dir),
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
            session_id = await client.new_session(str(workspace_dir))
            self._log_run(page, run_id, f"ACP session created: {session_id}")
            build_prompt = self._build_acp_prompt(page, prompt)
            result = await client.prompt(session_id, build_prompt, on_notification=on_notification)
            self._log_run(page, run_id, f"ACP prompt 完成: {json.dumps(result, ensure_ascii=False)}")

    def _build_acp_prompt(self, page: dict[str, Any], prompt: str) -> str:
        return (
            f"请在当前 workspace 中构建 mini-app《{page['name']}》。\n"
            f"需求描述：{page.get('description', '')}\n"
            f"用户最新要求：{prompt}\n"
            f"模板建议：{json.dumps(page.get('templates', []), ensure_ascii=False)}\n"
            "当前目录约定：\n"
            "- app/ 存放前端页面与静态资源\n"
            "- server.py 是 workspace 自带的服务端入口\n"
            "- data/ 用于保存持久化状态、待汇总问答、进度与预生成内容\n"
            "强制要求：\n"
            "1. 生成的是自包含 client-server 工作区，而不是只依赖宿主页面的单页静态壳。\n"
            "2. 保留并继续使用 server.py 这类独立服务端入口；前端应优先通过自己的服务端接口读写状态。\n"
            "3. 用户的大部分交互应在页面本地逻辑或 workspace 服务端内完成，只有最后兜底的求助、复杂问答或人工升级才发送给 Agent。\n"
            "4. 不是所有发给 Agent 的消息都会触发 workspace refresh。普通问答、笔记记录、答题状态上报等默认不触发即时刷新。\n"
            "5. 若需要补充下一批内容，优先设计后台/夜间 refresh、队列预生成或可选 cron 任务，避免打断当前用户会话。\n"
            "6. 用户再次打开 workspace 时，应尽量已经看到准备好的内容，而不是先等待一次长时间刷新。\n"
            "7. 若需要把交互发送给宿主系统，请使用 window.SensenovaClawMiniApp.emit(action, payload, options)，并通过 options.refreshMode 明确标注 none/background/immediate。\n"
            "8. 若复用了现有项目，请保留 LICENSE/NOTICE/ATTRIBUTIONS 文件。\n"
            "9. 最终保证 workspace 可通过自己的 Web server 提供页面和 API，而不只是依赖静态文件服务器。"
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
        *,
        refresh_mode: str,
    ) -> str:
        return (
            f"【MiniApp 交互事件】\n"
            f"- 页面: {page.get('name')} ({page.get('slug')})\n"
            f"- 动作: {action}\n"
            f"- refresh_mode: {refresh_mode}\n"
            f"- 载荷: {json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "请根据当前页面状态与用户操作继续推进任务。"
            "优先把普通问答、记录、状态沉淀视为不打断工作区的轻量交互。"
            "只有当 refresh_mode=immediate，或者你明确认为必须更新预生成内容时，才把它视为需要立即刷新工作区。"
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


def _normalize_refresh_mode(refresh_mode: str) -> str:
    value = str(refresh_mode or "").strip().lower()
    if value in {"none", "background", "immediate"}:
        return value
    return "none"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


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
        <p>正在初始化自带 Web 服务的 workspace。页面数据、预生成内容和后台 refresh 队列会由 workspace 自己的 server 负责。</p>
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
fetch("./api/workspace-state").catch(function(error) {{
  console.warn("Workspace server is not ready yet", error);
}});
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
      var meta = Object.assign({{}}, nextOptions.meta || {{}});
      if (nextOptions.refreshMode) {{
        meta.refreshMode = nextOptions.refreshMode;
      }}
      return post("interaction", action, payload, nextOptions.target || "", meta);
    }},
    emitTo: function(target, action, payload, options) {{
      var nextOptions = options || {{}};
      var meta = Object.assign({{}}, nextOptions.meta || {{}});
      if (nextOptions.refreshMode) {{
        meta.refreshMode = nextOptions.refreshMode;
      }}
      return post("interaction", action, payload, target || "", meta);
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


def _default_workspace_state(page: dict[str, Any]) -> dict[str, Any]:
    templates = _normalize_templates(page)
    prepared_units = []
    source_items = templates or [
        {"title": "今日任务 1", "desc": "完成一轮自检并记录关键结论。"},
        {"title": "今日任务 2", "desc": "处理一个需要状态保存的交互流程。"},
        {"title": "今日任务 3", "desc": "确认哪些问题必须升级给 Agent，哪些应在本地或服务端解决。"},
    ]
    for index, item in enumerate(source_items[:6], start=1):
        prepared_units.append(
            {
                "id": f"unit_{index}",
                "title": str(item.get("title") or f"预置单元 {index}"),
                "desc": str(item.get("desc") or "完成后会记录到服务端状态中。"),
                "status": "ready",
                "score": None,
            }
        )

    return {
        "workspace_name": page.get("name") or "Mini-App Workspace",
        "workspace_slug": page.get("slug") or "",
        "prepared_units": prepared_units,
        "pending_agent_items": 0,
        "saved_notes": [],
        "qa_history": [],
        "activity_log": [
            {
                "ts": int(time.time() * 1000),
                "type": "system",
                "message": "workspace 已初始化，优先使用本地逻辑与服务端接口处理交互。",
            }
        ],
        "refresh": {
            "queued": False,
            "mode": "nightly_cron",
            "reason": "",
            "last_materialized_at": int(time.time() * 1000),
            "recommended_window": "00:00",
        },
    }


def _standalone_workspace_server_py() -> str:
    return """from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "workspace_state.json"
INBOX_PATH = DATA_DIR / "agent_inbox.jsonl"


def _default_state() -> dict:
    return {
        "workspace_name": ROOT.name,
        "workspace_slug": ROOT.name,
        "prepared_units": [],
        "pending_agent_items": 0,
        "saved_notes": [],
        "qa_history": [],
        "activity_log": [],
        "refresh": {
            "queued": False,
            "mode": "nightly_cron",
            "reason": "",
            "last_materialized_at": int(time.time() * 1000),
            "recommended_window": "00:00",
        },
    }


def load_state() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        state = _default_state()
        save_state(state)
        return state
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = _default_state()
        save_state(state)
        return state


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_inbox(record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with INBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\\n")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:
        print("[workspace-server]", format % args, flush=True)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _send_json(self, payload: dict, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"ok": True, "ts": int(time.time() * 1000)})
            return
        if path == "/api/workspace-state":
            self._send_json(load_state())
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        state = load_state()
        payload = self._read_json()
        now = int(time.time() * 1000)

        if path == "/api/units/complete":
            unit_id = str(payload.get("unit_id") or "")
            answer = str(payload.get("answer") or "").strip()
            score = payload.get("score")
            for item in state.get("prepared_units", []):
                if str(item.get("id")) != unit_id:
                    continue
                item["status"] = "completed"
                item["answered_at"] = now
                if answer:
                    item["last_answer"] = answer
                item["score"] = score
                break
            remaining = [item for item in state.get("prepared_units", []) if item.get("status") != "completed"]
            if not remaining:
                refresh = state.setdefault("refresh", {})
                refresh["queued"] = True
                refresh["mode"] = "nightly_cron"
                refresh["reason"] = "prepared_units_exhausted"
            state.setdefault("activity_log", []).insert(0, {
                "ts": now,
                "type": "unit_completed",
                "message": f"完成单元: {unit_id}",
            })
            save_state(state)
            self._send_json({
                "ok": True,
                "state": state,
                "should_refresh_workspace": False,
            })
            return

        if path == "/api/agent-inbox":
            record = {
                "ts": now,
                "kind": str(payload.get("kind") or "note"),
                "content": payload,
            }
            append_inbox(record)
            state["pending_agent_items"] = int(state.get("pending_agent_items") or 0) + 1
            if record["kind"] == "note":
                state.setdefault("saved_notes", []).insert(0, {
                    "ts": now,
                    "text": str(payload.get("text") or "").strip(),
                })
            if record["kind"] == "qa":
                state.setdefault("qa_history", []).insert(0, {
                    "ts": now,
                    "question": str(payload.get("question") or "").strip(),
                })
            state.setdefault("activity_log", []).insert(0, {
                "ts": now,
                "type": "agent_inbox",
                "message": f"记录到 Agent inbox: {record['kind']}",
            })
            save_state(state)
            self._send_json({
                "ok": True,
                "state": state,
                "should_refresh_workspace": False,
            })
            return

        if path == "/api/workspace-events":
            event_type = str(payload.get("event_type") or "workspace_event")
            state.setdefault("activity_log", []).insert(0, {
                "ts": now,
                "type": event_type,
                "message": str(payload.get("message") or "记录一条工作区事件"),
            })
            save_state(state)
            self._send_json({
                "ok": True,
                "state": state,
                "should_refresh_workspace": False,
            })
            return

        if path == "/api/refresh-requests":
            refresh = state.setdefault("refresh", {})
            refresh["queued"] = True
            refresh["mode"] = str(payload.get("mode") or "background")
            refresh["reason"] = str(payload.get("reason") or "manual_request")
            state.setdefault("activity_log", []).insert(0, {
                "ts": now,
                "type": "refresh_request",
                "message": f"已排入后台 refresh: {refresh['reason']}",
            })
            save_state(state)
            self._send_json({
                "ok": True,
                "state": state,
                "should_refresh_workspace": False,
            })
            return

        self._send_json({"ok": False, "detail": f"unknown path: {path}"}, status=HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini-app workspace server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    APP_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        save_state(_default_state())

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[workspace-server] listening on http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
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

.composer {
  width: 100%;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  padding: 14px;
  resize: vertical;
  min-height: 120px;
  background: #fff;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.meta-pill {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #115e59;
  font-size: 12px;
  font-weight: 700;
}

.empty-state {
  padding: 18px;
  border-radius: 18px;
  background: #f8fafc;
  color: #475569;
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
          <div class="hero-kicker">Standalone Workspace Server</div>
          <h1 class="hero-title">{page['name']}</h1>
          <p class="hero-desc">{page.get('description') or '一个自带服务端、尽量少打断用户的工作区。绝大多数交互在本地和 workspace server 内完成，Agent 只处理最后兜底的问题。'}</p>
          <div class="meta-row">
            <span class="meta-pill">大多数交互: 本地 / Server</span>
            <span class="meta-pill">Agent 问答: 不默认刷新工作区</span>
            <span class="meta-pill">补充内容: 后台 / 夜间 refresh</span>
          </div>
          <div class="hero-actions">
            <button class="btn btn-primary" id="save-server-btn">保存当前状态</button>
            <button class="btn btn-secondary" id="queue-refresh-btn">排入夜间补充</button>
          </div>
        </div>

        <aside class="card stats-card">
          <div class="hero-kicker">服务端状态</div>
          <div class="stats-grid">
            <div class="stat"><span>预置单元</span><strong id="card-count">0</strong></div>
            <div class="stat"><span>已完成</span><strong id="interaction-count">0</strong></div>
            <div class="stat"><span>待汇总 Agent 项</span><strong id="pending-agent-count">0</strong></div>
            <div class="stat"><span>补货窗口</span><strong id="last-sync">--</strong></div>
          </div>
        </aside>
      </section>

      <section class="section-grid">
        <section class="card section-card">
          <div class="hero-kicker">已准备单元</div>
          <div class="list" id="task-list"></div>
        </section>

        <section class="card section-card">
          <div class="hero-kicker">问题与笔记</div>
          <textarea id="freeform-input" class="composer" placeholder="大部分内容先记到 workspace server；只有确实需要时，再点按钮向 Agent 提问"></textarea>
          <div class="hero-actions">
            <button class="btn btn-secondary" id="save-note-btn">仅记录到服务端</button>
            <button class="btn btn-primary" id="ask-agent-btn">最后兜底，询问 Agent</button>
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
    script = """let workspaceState = null;
const actionRouting = {
  defaultTarget: "server",
  routes: {
    unit_completed: "server",
    save_workspace_snapshot: "server",
    workspace_refresh_requested: "server",
    workspace_agent_question: "agent",
  },
};

function emitLog(text) {
  const host = document.getElementById("event-log");
  const item = document.createElement("div");
  item.className = "event-pill";
  item.textContent = text;
  host.prepend(item);
}

async function requestJson(path, options) {
  const response = await fetch(path, Object.assign({
    headers: {
      "Content-Type": "application/json",
    },
  }, options || {}));
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function completedUnits() {
  if (!workspaceState) return 0;
  return (workspaceState.prepared_units || []).filter((item) => item.status === "completed").length;
}

function syncStats() {
  const preparedUnits = (workspaceState && workspaceState.prepared_units) || [];
  document.getElementById("card-count").textContent = String(preparedUnits.length);
  document.getElementById("interaction-count").textContent = String(completedUnits());
  document.getElementById("pending-agent-count").textContent = String((workspaceState && workspaceState.pending_agent_items) || 0);
  document.getElementById("last-sync").textContent = ((workspaceState && workspaceState.refresh) || {}).recommended_window || "--";
}

function renderTasks() {
  const host = document.getElementById("task-list");
  const items = (workspaceState && workspaceState.prepared_units) || [];
  host.innerHTML = "";
  if (items.length === 0) {
    host.innerHTML = '<div class="empty-state">当前没有预生成内容，建议由后台 refresh 补充下一批单元。</div>';
    return;
  }
  items.forEach((item) => {
    const node = document.createElement("div");
    node.className = "list-item";
    const statusLabel = item.status === "completed" ? "已完成" : "待完成";
    node.innerHTML = `
      <h3>${item.title}</h3>
      <p>${item.desc || ""}</p>
      <div class="meta-row">
        <span class="meta-pill">${statusLabel}</span>
      </div>
      <div class="hero-actions">
        <button class="btn btn-secondary" data-complete-id="${item.id}" ${item.status === "completed" ? "disabled" : ""}>完成并记录</button>
      </div>
    `;
    host.appendChild(node);
  });
}

function renderActivityLog() {
  const host = document.getElementById("event-log");
  const items = (workspaceState && workspaceState.activity_log) || [];
  host.innerHTML = "";
  items.slice(0, 8).forEach((item) => {
    const node = document.createElement("div");
    node.className = "event-pill";
    node.textContent = item.message || item.type || "workspace event";
    host.appendChild(node);
  });
}

function syncState(nextState) {
  workspaceState = nextState;
  syncStats();
  renderTasks();
  renderActivityLog();
  if (window.SensenovaClawMiniApp && window.SensenovaClawMiniApp.updateState) {
    window.SensenovaClawMiniApp.updateState({
      prepared_unit_count: (workspaceState.prepared_units || []).length,
      completed_unit_count: completedUnits(),
      refresh_queued: !!((workspaceState.refresh || {}).queued),
    });
  }
}

async function loadState() {
  const data = await requestJson("./api/workspace-state");
  syncState(data);
}

document.getElementById("task-list").addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.dataset.completeId) return;
  const data = await requestJson("./api/units/complete", {
    method: "POST",
    body: JSON.stringify({
      unit_id: target.dataset.completeId,
      answer: "用户已在 workspace 内完成此单元",
      score: 1,
    }),
  });
  syncState(data.state || workspaceState);
  emitLog(`[Server] unit_completed -> ${target.dataset.completeId}`);
  if (window.SensenovaClawMiniApp && workspaceState && workspaceState.refresh && workspaceState.refresh.queued) {
    window.SensenovaClawMiniApp.emitTo("server", "workspace_refresh_requested", {
      page: "__PAGE_SLUG__",
      reason: workspaceState.refresh.reason || "prepared_units_exhausted",
    }, {
      refreshMode: "background",
    });
  }
});

document.getElementById("save-server-btn").addEventListener("click", async () => {
  const data = await requestJson("./api/workspace-events", {
    method: "POST",
    body: JSON.stringify({
      event_type: "workspace_snapshot",
      message: "用户在 workspace 内保存了一次当前状态",
    }),
  });
  syncState(data.state || workspaceState);
  if (window.SensenovaClawMiniApp) {
    window.SensenovaClawMiniApp.emitTo("server", "save_workspace_snapshot", {
      page: "__PAGE_SLUG__",
      summary: "用户在 workspace 内保存了当前状态",
    }, {
      refreshMode: "none",
    });
  }
  emitLog("[Server] save_workspace_snapshot");
});

document.getElementById("queue-refresh-btn").addEventListener("click", async () => {
  const data = await requestJson("./api/refresh-requests", {
    method: "POST",
    body: JSON.stringify({
      reason: "manual_background_refresh",
      mode: "background",
    }),
  });
  syncState(data.state || workspaceState);
  if (window.SensenovaClawMiniApp) {
    window.SensenovaClawMiniApp.emitTo("server", "workspace_refresh_requested", {
      page: "__PAGE_SLUG__",
      reason: "manual_background_refresh",
    }, {
      refreshMode: "background",
    });
  }
  emitLog("[Background] 已排入后台补充");
});

document.getElementById("save-note-btn").addEventListener("click", async () => {
  const text = document.getElementById("freeform-input").value.trim();
  if (!text) {
    emitLog("请先输入需要记录的笔记");
    return;
  }
  const data = await requestJson("./api/agent-inbox", {
    method: "POST",
    body: JSON.stringify({
      kind: "note",
      text: text,
    }),
  });
  syncState(data.state || workspaceState);
  document.getElementById("freeform-input").value = "";
  emitLog("[Server] 已记录到待汇总笔记");
});

document.getElementById("ask-agent-btn").addEventListener("click", async () => {
  const text = document.getElementById("freeform-input").value.trim();
  if (!text) {
    emitLog("请先输入你想让 Agent 回答的问题");
    return;
  }
  const data = await requestJson("./api/agent-inbox", {
    method: "POST",
    body: JSON.stringify({
      kind: "qa",
      question: text,
    }),
  });
  syncState(data.state || workspaceState);
  if (window.SensenovaClawMiniApp) {
    window.SensenovaClawMiniApp.emitTo("agent", "workspace_agent_question", {
      page: "__PAGE_SLUG__",
      question: text,
      note: "回答问题即可，不要默认刷新整个 workspace。",
    }, {
      refreshMode: "none",
      meta: {
        channel: "qa",
      },
    });
  }
  document.getElementById("freeform-input").value = "";
  emitLog("[Agent] 已发送兜底问题，不触发即时刷新");
});

if (window.SensenovaClawMiniApp && window.SensenovaClawMiniApp.configureActionRouting) {
  window.SensenovaClawMiniApp.configureActionRouting(actionRouting);
}

loadState().then(function() {
  emitLog("Workspace server 已连接，优先在本地与服务端内完成交互。");
}).catch(function(error) {
  emitLog(`Workspace server 尚未就绪: ${error instanceof Error ? error.message : error}`);
});

"""
    return script.replace("__PAGE_SLUG__", str(page.get("slug") or ""))


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
