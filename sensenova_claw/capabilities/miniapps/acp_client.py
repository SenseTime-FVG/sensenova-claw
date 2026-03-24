from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class ACPClientError(RuntimeError):
    """ACP 客户端错误。"""


class ACPClient:
    """最小可用的 ACP stdio 客户端。

    目标是对接 Claude Code / Codex 一类通过 ACP 暴露能力的代码 Agent。
    当前实现基于逐行 JSON-RPC over stdio，覆盖：
    - initialize
    - session/new
    - session/prompt
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        startup_timeout_seconds: float = 20.0,
        request_timeout_seconds: float = 180.0,
    ) -> None:
        self._command = command
        self._args = list(args or [])
        self._env = dict(env or {})
        self._cwd = cwd
        self._startup_timeout_seconds = startup_timeout_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._notify_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None

    async def __aenter__(self) -> "ACPClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._proc is not None:
            return

        env = os.environ.copy()
        env.update(self._env)
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        logger.info("ACP process started: %s %s", self._command, " ".join(self._args))

    async def close(self) -> None:
        proc = self._proc
        self._proc = None

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        for future in self._pending.values():
            if not future.done():
                future.set_exception(ACPClientError("ACP process closed"))
        self._pending.clear()

        if not proc:
            return

        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
            try:
                await proc.stdin.wait_closed()
            except Exception:
                pass

        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    async def initialize(self) -> dict[str, Any]:
        return await self.call(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {
                    "name": "Sensenova-Claw MiniApp Builder",
                    "version": "0.1.0",
                },
                "clientCapabilities": {
                    "fsRead": True,
                    "fsWrite": True,
                    "promptCapabilities": {
                        "audio": False,
                        "image": False,
                        "embeddedContext": False,
                    },
                    "sessionCapabilities": {},
                },
            },
            timeout_seconds=self._startup_timeout_seconds,
        )

    async def new_session(self, cwd: str) -> str:
        result = await self.call(
            "session/new",
            {
                "cwd": cwd,
                "mcpServers": [],
            },
            timeout_seconds=self._startup_timeout_seconds,
        )
        session_id = str((result or {}).get("sessionId", "")).strip()
        if not session_id:
            raise ACPClientError("ACP session/new 返回缺少 sessionId")
        return session_id

    async def prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        on_notification: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> dict[str, Any]:
        self._notify_callback = on_notification
        try:
            result = await self.call(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": prompt}],
                },
                timeout_seconds=self._request_timeout_seconds,
            )
            return result or {}
        finally:
            self._notify_callback = None

    async def call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        if self._proc is None or self._proc.stdin is None:
            raise ACPClientError("ACP process is not started")

        self._request_id += 1
        request_id = self._request_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        raw = json.dumps(payload, ensure_ascii=False) + "\n"
        self._proc.stdin.write(raw.encode("utf-8"))
        await self._proc.stdin.drain()
        logger.debug("ACP request sent: %s", payload)

        try:
            return await asyncio.wait_for(
                future,
                timeout=float(timeout_seconds if timeout_seconds is not None else self._request_timeout_seconds),
            )
        except asyncio.TimeoutError as exc:
            raise ACPClientError(f"ACP request timeout: {method}") from exc
        finally:
            self._pending.pop(request_id, None)

    async def _reader_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout

        while True:
            line = await stdout.readline()
            if not line:
                break

            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Ignore invalid ACP line: %s", text)
                continue

            logger.debug("ACP message received: %s", message)
            if "id" in message:
                request_id = int(message["id"])
                future = self._pending.get(request_id)
                if not future or future.done():
                    continue
                if "error" in message and message["error"] is not None:
                    error = message["error"]
                    future.set_exception(ACPClientError(str(error)))
                else:
                    future.set_result(message.get("result"))
                continue

            if "method" in message:
                callback = self._notify_callback
                if callback is None:
                    continue
                try:
                    maybe_awaitable = callback(message)
                    if asyncio.iscoroutine(maybe_awaitable):
                        await maybe_awaitable
                except Exception:
                    logger.warning("ACP notification callback failed", exc_info=True)
