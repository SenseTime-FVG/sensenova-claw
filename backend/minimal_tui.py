#!/usr/bin/env python
"""最小化TUI测试 - 只显示连接状态"""
from __future__ import annotations

import asyncio
import json
import logging

import websockets
from textual.app import App, ComposeResult
from textual.widgets import RichLog

logging.basicConfig(level=logging.DEBUG, filename='/tmp/tui_debug.log')
logger = logging.getLogger(__name__)


class MinimalTUI(App):
    def compose(self) -> ComposeResult:
        yield RichLog(id="log")

    async def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("TUI Started")
        logger.info("TUI Started")

        # 测试WebSocket连接
        try:
            log.write("Connecting to ws://localhost:8000/ws...")
            logger.info("Connecting...")

            ws = await websockets.connect("ws://localhost:8000/ws")
            log.write("✓ Connected!")
            logger.info("Connected!")

            # 创建会话
            await ws.send(json.dumps({"type": "create_session", "payload": {}, "timestamp": 0}))
            log.write("Session request sent")
            logger.info("Session request sent")

            # 接收一条消息
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            log.write(f"Received: {data.get('type')}")
            logger.info(f"Received: {data}")

            if data.get("type") == "session_created":
                session_id = data.get("session_id")
                log.write(f"✓ Session created: {session_id}")
                logger.info(f"Session created: {session_id}")

            # 保持连接
            log.write("Connection established. Press Ctrl+C to exit.")

            async for message in ws:
                data = json.loads(message)
                log.write(f"Message: {data.get('type')}")
                logger.info(f"Message: {data}")

        except Exception as e:
            log.write(f"✗ Error: {e}")
            logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    app = MinimalTUI()
    app.run()
