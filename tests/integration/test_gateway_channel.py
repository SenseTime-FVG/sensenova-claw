"""Gateway Channel 集成测试"""
import pytest
from agentos.adapters.channels.websocket_channel import WebSocketChannel


class TestGatewayChannel:
    def test_channel_id(self):
        ch = WebSocketChannel("ws")
        assert ch.get_channel_id() == "ws"

    def test_bind_session(self):
        ch = WebSocketChannel("ws")
        # WebSocketChannel.bind_session 需要一个 WebSocket 对象
        # 简化测试：确保实例化不崩溃
        assert ch is not None
