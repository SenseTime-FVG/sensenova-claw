"""A07/A08/W05: WebSocket 协议测试

注意: 这些测试需要后端实际运行。
在 CI 中使用 skipif 标记跳过。
"""
import asyncio
import json
import pytest

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

WS_URL = "ws://localhost:8000/ws"


@pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets not installed")
@pytest.mark.skipif(True, reason="需要后端运行")
class TestWebSocketProtocol:
    @pytest.mark.asyncio
    async def test_create_session(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "create_session", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "session_created"
            assert "session_id" in r

    @pytest.mark.asyncio
    async def test_create_session_with_agent(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "type": "create_session",
                "payload": {"agent_id": "default"},
            }))
            r = json.loads(await ws.recv())
            assert r["type"] == "session_created"

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_sessions", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "sessions_list"

    @pytest.mark.asyncio
    async def test_list_agents(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_agents", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "agents_list"

    @pytest.mark.asyncio
    async def test_invalid_type(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "bad", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "error"
