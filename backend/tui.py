#!/usr/bin/env python
"""AgentOS TUI - 最终版本"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import websockets
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, RichLog

logging.basicConfig(level=logging.DEBUG, filename='/tmp/tui.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AgentOSTUI(App):
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

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            RichLog(id="chat-log", wrap=True, markup=True),
            Vertical(Input(placeholder="输入你的问题...", id="user-input"), id="input-container"),
        )
        yield Footer()

    async def on_mount(self) -> None:
        logger.info("on_mount called")
        log = self.query_one("#chat-log", RichLog)
        log.write("[bold cyan]AgentOS TUI[/bold cyan]")
        log.write(f"正在连接到 {self.ws_url}...")
        logger.info(f"Starting connection to {self.ws_url}")
        asyncio.create_task(self._connect())

    async def _connect(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        try:
            logger.info("Connecting to WebSocket...")
            self.ws = await websockets.connect(self.ws_url)
            logger.info("Connected successfully")
            log.write("[green]✓ 已连接到 Gateway[/green]")

            logger.info("Sending create_session")
            await self.ws.send(json.dumps({"type": "create_session", "payload": {}, "timestamp": 0}))
            logger.info("Starting receive loop")
            await self._receive_loop()
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            log.write(f"[red]✗ 连接失败: {e}[/red]")

    async def _receive_loop(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        logger.info("Receive loop started")
        async for msg in self.ws:
            logger.info(f"Received message: {msg[:100]}")
            data = json.loads(msg)
            ts = datetime.now().strftime("%H:%M:%S")
            msg_type = data.get("type")
            payload = data.get("payload", {})
            logger.info(f"Message type: {msg_type}")

            if msg_type == "session_created":
                self.session_id = data.get("session_id")
                logger.info(f"Session created: {self.session_id}")
                log.write(f"[green]✓ 会话: {self.session_id}[/green]")
                log.write("输入你的问题开始对话...")
            elif msg_type == "tool_execution":
                logger.info(f"Tool execution: {payload.get('tool_name')}")
                log.write(f"[yellow][{ts}] 🔧 {payload.get('tool_name')} 执行中...[/yellow]")
            elif msg_type == "tool_result":
                logger.info(f"Tool result: {payload.get('tool_name')}")
                log.write(f"[yellow][{ts}] ✓ {payload.get('tool_name')} 完成[/yellow]")
            elif msg_type == "turn_completed":
                resp = payload.get("content") or payload.get("final_response", "")
                logger.info(f"Turn completed: {resp[:50]}")
                if resp:
                    log.write(f"[bold blue][{ts}] Assistant:[/bold blue] {resp}")
            elif msg_type == "error":
                logger.error(f"Error message: {payload.get('message')}")
                log.write(f"[red][{ts}] Error: {payload.get('message')}[/red]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.ws or not self.session_id or not event.value.strip():
            return
        log = self.query_one("#chat-log", RichLog)
        ts = datetime.now().strftime("%H:%M:%S")
        log.write(f"[bold green][{ts}] User:[/bold green] {event.value}")
        await self.ws.send(json.dumps({
            "type": "user_input",
            "session_id": self.session_id,
            "payload": {"content": event.value, "attachments": [], "context_files": []},
            "timestamp": 0
        }))
        event.input.value = ""


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="localhost")
    args = parser.parse_args()
    app = AgentOSTUI(f"ws://{args.host}:{args.port}/ws")
    app.run()
