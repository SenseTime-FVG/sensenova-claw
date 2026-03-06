#!/usr/bin/env python
"""简化的TUI实现 - 用于测试"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import websockets
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, RichLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleTUIApp(App):
    """简化的TUI应用"""

    CSS = """
    Screen { background: $surface; }
    #chat-log { height: 1fr; border: solid $primary; margin: 1; }
    #input-container { height: auto; margin: 0 1; }
    Input { width: 100%; }
    """

    def __init__(self, ws_url: str):
        super().__init__()
        self.ws_url = ws_url
        self.ws = None
        self.session_id = None
        self.chat_log = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            RichLog(id="chat-log", wrap=True, markup=True),
            Vertical(Input(placeholder="输入你的问题...", id="user-input"), id="input-container"),
        )
        yield Footer()

    async def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", RichLog)
        self.chat_log.write("[bold cyan]AgentOS TUI[/bold cyan]")
        self.chat_log.write(f"正在连接到 {self.ws_url}...")
        logger.info(f"TUI mounted, connecting to {self.ws_url}")

        # 启动WebSocket连接
        asyncio.create_task(self.connect_websocket())

    async def connect_websocket(self) -> None:
        """连接到Gateway"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.chat_log.write("[green]✓ 已连接到 Gateway[/green]")

            # 创建会话
            await self.ws.send(json.dumps({"type": "create_session", "payload": {}, "timestamp": asyncio.get_event_loop().time()}))

            # 接收消息（在当前任务中持续运行）
            await self.receive_messages()

        except Exception as e:
            self.chat_log.write(f"[red]✗ 连接失败: {e}[/red]")
            logger.error(f"Connection error: {e}", exc_info=True)

    async def receive_messages(self) -> None:
        """接收WebSocket消息"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                logger.info(f"Received message: {data.get('type')}")
                self.handle_message(data)
        except Exception as e:
            logger.error(f"Receive error: {e}", exc_info=True)
            if self.chat_log:
                self.chat_log.write(f"[red]✗ 接收消息失败: {e}[/red]")

    def handle_message(self, data: dict) -> None:
        """处理消息"""
        msg_type = data.get("type", "")
        payload = data.get("payload", {})
        timestamp = datetime.now().strftime("%H:%M:%S")

        if msg_type == "session_created":
            self.session_id = data.get("session_id")
            self.chat_log.write(f"[green]✓ 会话已创建: {self.session_id}[/green]")
            self.chat_log.write("输入你的问题开始对话...")

        elif msg_type == "tool_execution":
            tool_name = payload.get("tool_name", "")
            self.chat_log.write(f"[yellow][{timestamp}] 🔧 Tool: {tool_name} 执行中...[/yellow]")

        elif msg_type == "tool_result":
            tool_name = payload.get("tool_name", "")
            self.chat_log.write(f"[yellow][{timestamp}] ✓ Tool: {tool_name} 完成[/yellow]")

        elif msg_type == "turn_completed":
            response = payload.get("content", "") or payload.get("final_response", "")
            if response:
                self.chat_log.write(f"[bold blue][{timestamp}] Assistant:[/bold blue] {response}")

        elif msg_type == "error":
            error_msg = payload.get("message", "Unknown error")
            self.chat_log.write(f"[bold red][{timestamp}] Error:[/bold red] {error_msg}")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入"""
        content = event.value.strip()
        if not content or not self.ws or not self.session_id:
            return

        event.input.value = ""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_log.write(f"[bold green][{timestamp}] User:[/bold green] {content}")

        await self.ws.send(json.dumps({
            "type": "user_input",
            "session_id": self.session_id,
            "payload": {"content": content, "attachments": [], "context_files": []},
            "timestamp": asyncio.get_event_loop().time()
        }))


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="AgentOS TUI Client (Simple)")
    parser.add_argument("--port", type=int, default=8000, help="Gateway port")
    parser.add_argument("--host", type=str, default="localhost", help="Gateway host")
    args = parser.parse_args()

    ws_url = f"ws://{args.host}:{args.port}/ws"
    app = SimpleTUIApp(ws_url)
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
