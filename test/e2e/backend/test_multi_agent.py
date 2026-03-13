"""E2E: 多 Agent 流程（需要真实后端运行）"""
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
class TestMultiAgent:
    @pytest.mark.asyncio
    async def test_create_session_with_agent(self):
        """创建绑定特定 Agent 的会话"""
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "type": "create_session",
                "payload": {"agent_id": "default"},
            }))
            r = json.loads(await ws.recv())
            assert r["type"] == "session_created"

    @pytest.mark.asyncio
    async def test_list_agents(self):
        """列出可用 Agent"""
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_agents", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "agents_list"
            agents = r["payload"]["agents"]
            assert any(a["id"] == "default" for a in agents)
