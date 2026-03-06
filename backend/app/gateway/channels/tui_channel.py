from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime

import websockets
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, RichLog

logger = logging.getLogger(__name__)


class TUIChannel:
    """TUI Channel 作为 WebSocket 客户端连接到 Gateway"""

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._session_id: str | None = None
        self._app: TUIApp | None = None
        self._running = False

    async def start(self) -> None:
        """启动 TUI 并连接到 Gateway"""
        self._running = True
        self._app = TUIApp(self)

        # 先启动TUI应用（在后台），然后启动WebSocket连接
        async def run_both():
            # 启动WebSocket连接
            ws_task = asyncio.create_task(self._connect_websocket())
            # 启动TUI应用（这会阻塞直到退出）
            await self._app.run_async()
            # TUI退出后，停止WebSocket
            self._running = False
            ws_task.cancel()

        await run_both()
        logger.info("TUIChannel started")

    async def stop(self) -> None:
        """停止 TUI"""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._app:
            self._app.exit()
        logger.info("TUIChannel stopped")

    async def _connect_websocket(self) -> None:
        """连接到 Gateway WebSocket"""
        while self._running:
            try:
                if self._app and self._app.chat_log:
                    self._app.call_from_thread(self._app.chat_log.write, f"正在连接到 {self._ws_url}...")

                async with websockets.connect(self._ws_url) as websocket:
                    self._ws = websocket
                    logger.info(f"Connected to Gateway at {self._ws_url}")

                    if self._app and self._app.chat_log:
                        self._app.call_from_thread(self._app.chat_log.write, "[green]✓ 已连接到 Gateway[/green]")

                    # 创建会话
                    await self._create_session()

                    # 接收消息
                    async for message in websocket:
                        data = json.loads(message)
                        await self._handle_message(data)

            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                if self._app and self._app.chat_log:
                    self._app.call_from_thread(self._app.chat_log.write, f"[red]✗ 连接失败: {e}[/red]")
                await asyncio.sleep(2)  # 重连延迟

    async def _create_session(self) -> None:
        """创建新会话"""
        if not self._ws:
            return

        await self._ws.send(json.dumps({
            "type": "create_session",
            "payload": {},
            "timestamp": asyncio.get_event_loop().time()
        }))

    async def _handle_message(self, data: dict) -> None:
        """处理来自 Gateway 的消息"""
        msg_type = data.get("type")

        if msg_type == "session_created":
            self._session_id = data.get("session_id")
            if self._app:
                self._app.call_from_thread(self._app.set_session_id, self._session_id)
            logger.info(f"Session created: {self._session_id}")
        else:
            # 将所有其他消息传递给TUI应用处理
            if self._app:
                self._app.call_from_thread(self._app.handle_event, data)

    async def send_user_input(self, content: str) -> None:
        """发送用户输入"""
        if not self._ws or not self._session_id:
            return

        await self._ws.send(json.dumps({
            "type": "user_input",
            "session_id": self._session_id,
            "payload": {
                "content": content,
                "attachments": [],
                "context_files": []
            },
            "timestamp": asyncio.get_event_loop().time()
        }))


class TUIApp(App):
    """Textual TUI 应用"""

    CSS = """
    Screen {
        background: $surface;
    }

    #chat-log {
        height: 1fr;
        border: solid $primary;
        margin: 1;
    }

    #input-container {
        height: auto;
        margin: 0 1;
    }

    Input {
        width: 100%;
    }
    """

    def __init__(self, channel: TUIChannel):
        super().__init__()
        self.channel = channel
        self.chat_log: RichLog | None = None
        self.session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            RichLog(id="chat-log", wrap=True, markup=True),
            Vertical(
                Input(placeholder="输入你的问题...", id="user-input"),
                id="input-container",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", RichLog)
        self.chat_log.write("[bold cyan]AgentOS TUI[/bold cyan]")
        self.chat_log.write("正在连接到 Gateway...")

    def set_session_id(self, session_id: str) -> None:
        """设置会话ID"""
        self.session_id = session_id
        if self.chat_log:
            self.chat_log.write(f"[green]已连接，会话ID: {session_id}[/green]")
            self.chat_log.write("输入你的问题开始对话...")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入"""
        content = event.value.strip()
        if not content:
            return

        event.input.value = ""

        if self.chat_log:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.chat_log.write(f"[bold green][{timestamp}] User:[/bold green] {content}")

        await self.channel.send_user_input(content)

    def handle_event(self, data: dict) -> None:
        """处理来自 Gateway 的事件"""
        if not self.chat_log:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_type = data.get("type", "")
        payload = data.get("payload", {})

        if msg_type == "tool_execution":
            tool_name = payload.get("tool_name", "")
            self.chat_log.write(f"[yellow][{timestamp}] Tool:[/yellow] {tool_name} 执行中...")

        elif msg_type == "tool_result":
            tool_name = payload.get("tool_name", "")
            success = payload.get("success", True)
            status = "完成" if success else "失败"
            self.chat_log.write(f"[yellow][{timestamp}] Tool:[/yellow] {tool_name} {status}")

        elif msg_type == "turn_completed":
            response = payload.get("content", "") or payload.get("final_response", "")
            if response:
                self.chat_log.write(f"[bold blue][{timestamp}] Assistant:[/bold blue] {response}")

        elif msg_type == "error":
            error_msg = payload.get("message", "Unknown error")
            self.chat_log.write(f"[bold red][{timestamp}] Error:[/bold red] {error_msg}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgentOS TUI Client")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Gateway WebSocket port (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Gateway host (default: localhost)"
    )
    args = parser.parse_args()

    ws_url = f"ws://{args.host}:{args.port}/ws"

    async def main():
        channel = TUIChannel(ws_url)
        await channel.start()

    asyncio.run(main())
