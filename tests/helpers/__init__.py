"""辅助函数"""
import asyncio
import json
from typing import Any


async def collect_ws_events(ws, timeout=30) -> list[dict]:
    events = []
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(raw)
            events.append(data)
            if data.get("type") in ("turn_completed", "error"):
                break
    except asyncio.TimeoutError:
        pass
    return events


class MockCLIApp:
    def __init__(self):
        self.debug = False
        self.current_session_id = None
        self.current_agent_id = "default"
        self.console = type("C", (), {"print": lambda *a, **k: None, "output": []})()
        self._sent = []

    async def _send(self, msg):
        self._sent.append(msg)

    async def _create_session(self, aid=None):
        self.current_session_id = "mock_sess"
        self.current_agent_id = aid or "default"
        return self.current_session_id

    async def _load_session(self, sid):
        self.current_session_id = sid

    async def _wait_for_turn(self):
        pass
