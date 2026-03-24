#!/usr/bin/env python
"""Sensenova-Claw CLI 入口"""

import argparse
import asyncio
import sys

from sensenova_claw.app.cli.app import CLIApp


def main() -> int:
    parser = argparse.ArgumentParser(description="Sensenova-Claw CLI")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--agent", default=None, help="Agent ID")
    parser.add_argument("--session", default=None, help="恢复指定 session")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("-e", "--execute", default=None, help="执行单条消息后退出")
    args = parser.parse_args()

    app = CLIApp(
        host=args.host,
        port=args.port,
        agent_id=args.agent,
        session_id=args.session,
        debug=args.debug,
        execute=args.execute,
    )
    return asyncio.run(app.run())


if __name__ == "__main__":
    sys.exit(main())
