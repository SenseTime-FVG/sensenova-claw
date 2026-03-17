"""CLIApp 主类 + WebSocket 管理 + 主循环"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets
from rich.console import Console

from agentos.app.cli.commands import CommandDispatcher
from agentos.app.cli.display import DisplayEngine, read_user_input


class CLIApp:
    """AgentOS CLI 客户端"""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        debug: bool = False,
        execute: str | None = None,
    ):
        self.host = host
        self.port = port
        self.initial_agent_id = agent_id
        self.initial_session_id = session_id
        self.debug = debug
        self.execute = execute

        self.ws: websockets.WebSocketClientProtocol | None = None
        self.current_session_id: str | None = None
        self.current_agent_id: str = agent_id or "default"

        self._waiting = asyncio.Event()
        self._confirm_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._last_response: str = ""

        self.console = Console()
        self.dispatcher = CommandDispatcher(self)
        self.display = DisplayEngine(self)

    async def run(self) -> int:
        """主入口，返回退出码 0/1/2"""
        ws_url = f"ws://{self.host}:{self.port}/ws"
        self.console.print(f"[cyan]连接到 {ws_url}...[/cyan]")

        async with websockets.connect(ws_url) as ws:
            self.ws = ws
            if self.initial_session_id:
                await self._load_session(self.initial_session_id)
            else:
                await self._create_session(self.initial_agent_id)

            recv_task = asyncio.create_task(self._receive_loop())
            try:
                if self.execute:
                    return await self._run_execute_mode()
                return await self._run_interactive_mode()
            finally:
                recv_task.cancel()

    async def _receive_loop(self) -> None:
        """接收 WebSocket 消息的后台循环"""
        async for raw in self.ws:
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if self.debug:
                self.display.show_debug(data)

            if msg_type == "tool_confirmation_requested":
                await self._confirm_queue.put(data)
                self._waiting.set()
                continue

            if msg_type in ("turn_completed", "error"):
                if msg_type == "turn_completed":
                    self._last_response = data.get("payload", {}).get("final_response", "")
                    self.display.show_response(self._last_response)
                else:
                    self.display.show_error(data)
                self._waiting.set()
                continue

            self.display.handle_event(data)

    async def _wait_for_turn(self) -> None:
        """等待 turn 完成，期间处理确认请求"""
        while True:
            self._waiting.clear()
            await self._waiting.wait()

            while not self._confirm_queue.empty():
                confirm_data = await self._confirm_queue.get()
                if self.execute:
                    approved = False  # 脚本模式自动拒绝
                else:
                    approved = await self.display.prompt_confirmation(confirm_data)
                await self._send_confirmation_response(confirm_data, approved)
                continue

            if self._confirm_queue.empty():
                break

    async def _send(self, msg: dict) -> None:
        """发送 JSON 消息到 WebSocket"""
        await self.ws.send(json.dumps(msg))

    async def _create_session(self, agent_id: str | None = None) -> str:
        """创建新会话"""
        await self._send({
            "type": "create_session",
            "payload": {"agent_id": agent_id or "default"},
        })
        resp = json.loads(await self.ws.recv())
        self.current_session_id = resp.get("session_id")
        self.current_agent_id = agent_id or "default"
        return self.current_session_id

    async def _load_session(self, session_id: str) -> None:
        """加载已有会话"""
        await self._send({
            "type": "load_session",
            "payload": {"session_id": session_id},
        })
        await self.ws.recv()
        self.current_session_id = session_id

    async def _send_user_input(self, content: str) -> None:
        """发送用户输入"""
        await self._send({
            "type": "user_input",
            "session_id": self.current_session_id,
            "payload": {"content": content},
        })

    async def _send_confirmation_response(self, data: dict, approved: bool) -> None:
        """发送工具确认响应"""
        payload = data.get("payload", {})
        await self._send({
            "type": "tool_confirmation_response",
            "session_id": self.current_session_id,
            "payload": {
                "tool_call_id": payload.get("tool_call_id"),
                "approved": approved,
            },
        })

    async def _run_execute_mode(self) -> int:
        """脚本模式：执行单条消息后退出"""
        await self._send_user_input(self.execute)
        try:
            await asyncio.wait_for(self._wait_for_turn(), timeout=300)
        except asyncio.TimeoutError:
            sys.stderr.write("Error: timeout\n")
            return 2
        sys.stdout.write(self._last_response + "\n")
        return 0

    async def _run_interactive_mode(self) -> int:
        """交互模式：REPL 循环"""
        self.display.show_welcome()
        while True:
            try:
                raw = await asyncio.to_thread(read_user_input)
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]提示: 使用 /quit 退出[/dim]")
                continue

            text = raw.strip()
            if not text:
                continue

            if text.startswith("/"):
                action = await self.dispatcher.dispatch(text)
                if action == "quit":
                    return 0
                continue

            await self._send_user_input(text)
            await self._wait_for_turn()
