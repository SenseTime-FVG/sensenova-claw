"""E2E: 后端 Chat 流程（需要真实后端运行）"""
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
class TestChatFlow:
    @pytest.mark.asyncio
    async def test_full_chat_turn(self):
        """完整聊天流程: 创建会话 → 发消息 → 收响应"""
        async with websockets.connect(WS_URL) as ws:
            # 创建会话
            await ws.send(json.dumps({"type": "create_session", "payload": {}}))
            r = json.loads(await ws.recv())
            assert r["type"] == "session_created"
            session_id = r["session_id"]

            # 发送消息
            await ws.send(json.dumps({
                "type": "user_input",
                "session_id": session_id,
                "payload": {"content": "说 hello"},
            }))

            # 收集事件直到 step_completed
            events = []
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(raw)
                    events.append(data)
                    if data.get("type") in (
                        "agent.step_completed",
                        "error",
                    ):
                        break
            except asyncio.TimeoutError:
                pass

            # 应至少收到一些事件
            assert len(events) > 0
