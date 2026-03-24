"""WhatsApp sidecar bridge client。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from .models import WhatsAppInboundMessage

logger = logging.getLogger(__name__)

MessageHandler = Callable[[WhatsAppInboundMessage], Awaitable[None]]
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class WhatsAppBridgeClient(Protocol):
    """WhatsApp bridge 协议。"""

    def set_message_handler(self, handler: MessageHandler) -> None:
        """注册入站消息回调。"""
        ...

    async def start(self) -> None:
        """启动 bridge。"""
        ...

    async def stop(self) -> None:
        """停止 bridge。"""
        ...

    async def send_text(self, target: str, text: str) -> dict:
        """向指定 JID 发送文本。"""
        ...


class SidecarBridgeClient:
    """基于本地 sidecar 子进程的 WhatsApp bridge client。"""

    def __init__(
        self,
        *,
        command: str,
        entry: str,
        auth_dir: str,
        typing_indicator: str = "composing",
        startup_timeout_seconds: float = 30,
        send_timeout_seconds: float = 15,
        env: dict[str, str] | None = None,
    ):
        self._command = command
        self._entry = entry
        self._auth_dir = str(Path(auth_dir).expanduser())
        self._typing_indicator = typing_indicator
        self._startup_timeout_seconds = startup_timeout_seconds
        self._send_timeout_seconds = send_timeout_seconds
        self._extra_env = env or {}

        self._message_handler: MessageHandler | None = None
        self._event_handler: EventHandler | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    def set_event_handler(self, handler: EventHandler) -> None:
        self._event_handler = handler

    async def start(self) -> None:
        if self._proc and self._proc.returncode is None:
            return

        Path(self._auth_dir).mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(self._extra_env)

        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            self._entry,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

        await self._request(
            "start",
            {
                "authDir": self._auth_dir,
                "typingIndicator": self._typing_indicator,
            },
            timeout=self._startup_timeout_seconds,
        )

    async def stop(self) -> None:
        if not self._proc:
            return

        if self._proc.returncode is None:
            try:
                await self._request("stop", {}, timeout=min(2.0, self._send_timeout_seconds))
            except Exception:
                logger.debug("WhatsApp sidecar stop request failed", exc_info=True)

        if self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()

        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._proc = None
        self._reader_task = None

    async def send_text(self, target: str, text: str) -> dict:
        return await self._request(
            "send_text",
            {"target": target, "text": text},
            timeout=self._send_timeout_seconds,
        )

    async def get_status(self) -> dict:
        return await self._request("status", {}, timeout=self._send_timeout_seconds)

    async def logout(self) -> dict:
        return await self._request("logout", {}, timeout=self._send_timeout_seconds)

    async def _request(self, command_type: str, payload: dict[str, Any], timeout: float) -> dict:
        if not self._proc or self._proc.returncode is not None or not self._proc.stdin:
            raise RuntimeError("WhatsApp sidecar is not running")

        async with self._lock:
            command_id = f"cmd_{uuid.uuid4().hex[:12]}"
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending[command_id] = future

            command = {"id": command_id, "type": command_type, "payload": payload}
            self._proc.stdin.write((json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._proc.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"WhatsApp sidecar command timed out: {command_type}") from None
        finally:
            self._pending.pop(command_id, None)

    async def _read_stdout(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid WhatsApp sidecar JSON: %s", raw)
                continue
            await self._handle_event(event)

    async def _read_stderr(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None

        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            logger.debug("WhatsApp sidecar stderr: %s", line.decode("utf-8", errors="replace").rstrip())

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")
        if event_type == "response":
            command_id = event.get("id", "")
            future = self._pending.get(command_id)
            if future and not future.done():
                future.set_result(event.get("payload", {}))
            return

        if self._event_handler:
            self._dispatch_handler(
                self._event_handler(event),
                handler_name="event_handler",
                event_type=event_type,
            )

        if event_type == "message" and self._message_handler:
            payload = event.get("payload", {})
            self._dispatch_handler(
                self._message_handler(
                WhatsAppInboundMessage(
                    text=payload.get("text", ""),
                    chat_jid=payload.get("chat_jid", ""),
                    chat_type=payload.get("chat_type", "p2p"),
                    sender_jid=payload.get("sender_jid", ""),
                    message_id=payload.get("message_id", ""),
                    push_name=payload.get("push_name"),
                )
                ),
                handler_name="message_handler",
                event_type=event_type,
            )

    def _dispatch_handler(
        self,
        coro: Awaitable[None],
        *,
        handler_name: str,
        event_type: str,
    ) -> None:
        task = asyncio.create_task(coro)
        task.add_done_callback(
            lambda finished: self._log_handler_result(
                finished,
                handler_name=handler_name,
                event_type=event_type,
            )
        )

    @staticmethod
    def _log_handler_result(
        task: asyncio.Task[None],
        *,
        handler_name: str,
        event_type: str,
    ) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning(
                "WhatsApp bridge %s cancelled: event_type=%s",
                handler_name,
                event_type,
            )
        except Exception:
            logger.exception(
                "WhatsApp bridge %s failed: event_type=%s",
                handler_name,
                event_type,
            )


class LocalBridgeStub:
    """默认 bridge 存根。

    当前仓库先完成 channel 接入与测试闭环，真实 WhatsApp Web runtime 后续替换到这里。
    """

    def __init__(self, auth_dir: str):
        self._auth_dir = Path(auth_dir).expanduser() if auth_dir else None
        self._handler: MessageHandler | None = None

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._auth_dir:
            self._auth_dir.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "WhatsApp bridge stub started. 目前未接入真实 WhatsApp Web runtime，仅支持测试注入。 auth_dir=%s",
            self._auth_dir,
        )

    async def stop(self) -> None:
        logger.info("WhatsApp bridge stub stopped")

    async def send_text(self, target: str, text: str) -> dict:
        logger.warning(
            "WhatsApp bridge stub cannot send message yet. target=%s text=%s",
            target,
            text[:100],
        )
        return {
            "success": False,
            "error": "WhatsApp bridge runtime is not configured",
            "target": target,
        }
