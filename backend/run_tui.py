#!/usr/bin/env python
"""TUI Channel 启动脚本"""
from __future__ import annotations

import argparse
import asyncio

from app.gateway.channels.tui_channel import TUIChannel


async def main():
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
    channel = TUIChannel(ws_url)
    await channel.start()


if __name__ == "__main__":
    asyncio.run(main())
