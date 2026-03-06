from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, RichLog

from app.events.envelope import EventEnvelope
from app.events.types import AGENT_STEP_COMPLETED, TOOL_CALL_COMPLETED, TOOL_CALL_REQUESTED, UI_USER_INPUT
from app.gateway.base import Channel
from app.gateway.gateway import Gateway

logger = logging.getLogger(__name__)


class TUIChannel(Channel):
    """TUI Channel 使用 Textual 实现命令行界面"""

    def __init__(self, gateway: Gateway, channel_id: str = "tui"):
        self._channel_id = channel_id
        self._gateway = gateway
        self._session_id: str | None = None
        self._app: TUIApp | None = None
        self._event_queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        """启动 TUI"""
        self._session_id = f"sess_{uuid.uuid4().hex[:12]}"
        self._gateway.bind_session(self._session_id, self._channel_id)

        self._app = TUIApp(self)
        asyncio.create_task(self._process_events())
        await self._app.run_async()
        logger.info(f"TUIChannel {self._channel_id} started")

    async def stop(self) -> None:
        """停止 TUI"""
        if self._app:
            self._app.exit()
        if self._session_id:
            self._gateway.unbind_session(self._session_id)
        logger.info(f"TUIChannel {self._channel_id} stopped")

    async def send_event(self, event: EventEnvelope) -> None:
        """接收来自 Gateway 的事件"""
        await self._event_queue.put(event)

    async def _process_events(self) -> None:
        """处理事件队列"""
        while True:
            event = await self._event_queue.get()
            if self._app:
                self._app.handle_event(event)

    async def send_user_input(self, content: str) -> None:
        """发送用户输入"""
        if not self._session_id:
            return

        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        event = EventEnvelope(
            type=UI_USER_INPUT,
            session_id=self._session_id,
            turn_id=turn_id,
            source="tui",
            payload={"content": content, "attachments": [], "context_files": []},
        )
        await self._gateway.publish_from_channel(event)


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

    def handle_event(self, event: EventEnvelope) -> None:
        """处理来自 Gateway 的事件"""
        if not self.chat_log:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        if event.type == TOOL_CALL_REQUESTED:
            tool_name = event.payload.get("tool_name", "")
            self.chat_log.write(f"[yellow][{timestamp}] Tool:[/yellow] {tool_name} 执行中...")

        elif event.type == TOOL_CALL_COMPLETED:
            tool_name = event.payload.get("tool_name", "")
            success = event.payload.get("success", False)
            status = "完成" if success else "失败"
            self.chat_log.write(f"[yellow][{timestamp}] Tool:[/yellow] {tool_name} {status}")

        elif event.type == AGENT_STEP_COMPLETED:
            response = event.payload.get("result", {}).get("content", "")
            if response:
                self.chat_log.write(f"[bold blue][{timestamp}] Assistant:[/bold blue] {response}")

        else:
            # 处理其他事件类型
            if event.payload.get("error"):
                error_msg = event.payload.get("error", "Unknown error")
                self.chat_log.write(f"[bold red][{timestamp}] Error:[/bold red] {error_msg}")
