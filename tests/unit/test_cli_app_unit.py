"""CLIApp 单元测试

CLI 测试中需要 WebSocket 连接的测试标记为 skip。
不使用 mock/patch，仅测试可独立验证的逻辑。
"""
from __future__ import annotations

import asyncio
import json

import pytest


class TestCLIAppInit:
    """初始化参数测试"""

    def _make_app(self, **kwargs):
        """创建 CLIApp 实例，不连接 WebSocket"""
        from agentos.app.cli.app import CLIApp
        defaults = dict(host="localhost", port=8000)
        defaults.update(kwargs)
        return CLIApp(**defaults)

    def test_default_init(self):
        """默认参数初始化"""
        app = self._make_app()
        assert app.host == "localhost"
        assert app.port == 8000
        assert app.initial_agent_id is None
        assert app.initial_session_id is None
        assert app.debug is False
        assert app.execute is None
        assert app.current_agent_id == "default"
        assert app.ws is None
        assert app._last_response == ""

    def test_custom_init(self):
        """自定义参数初始化"""
        app = self._make_app(
            host="127.0.0.1",
            port=9000,
            agent_id="test-agent",
            session_id="session-123",
            debug=True,
            execute="hello",
        )
        assert app.host == "127.0.0.1"
        assert app.port == 9000
        assert app.initial_agent_id == "test-agent"
        assert app.initial_session_id == "session-123"
        assert app.debug is True
        assert app.execute == "hello"
        assert app.current_agent_id == "test-agent"


class TestReceiveLoopParsing:
    """测试 _receive_loop 中的消息解析逻辑（不依赖 WebSocket）"""

    def _make_app(self):
        from agentos.app.cli.app import CLIApp
        return CLIApp(host="localhost", port=8000)

    async def test_waiting_event_starts_unset(self):
        """_waiting 事件初始为未设置状态"""
        app = self._make_app()
        assert not app._waiting.is_set()

    async def test_confirm_queue_starts_empty(self):
        """确认队列初始为空"""
        app = self._make_app()
        assert app._confirm_queue.empty()

    async def test_confirm_queue_put_get(self):
        """确认队列可正常存取"""
        app = self._make_app()
        data = {"payload": {"tool_call_id": "tc-1"}}
        await app._confirm_queue.put(data)
        assert not app._confirm_queue.empty()
        got = await app._confirm_queue.get()
        assert got["payload"]["tool_call_id"] == "tc-1"


class TestWaitForTurn:
    """_wait_for_turn 方法测试"""

    def _make_app(self):
        from agentos.app.cli.app import CLIApp
        return CLIApp(host="localhost", port=8000)

    async def test_simple_wait(self):
        """没有确认请求时直接等待完成"""
        app = self._make_app()

        async def set_waiting():
            await asyncio.sleep(0.01)
            app._waiting.set()

        asyncio.create_task(set_waiting())
        await asyncio.wait_for(app._wait_for_turn(), timeout=1.0)


class TestSendAndSessionMethods:
    """_send / _create_session / _load_session / _send_user_input 等方法
    这些方法依赖真实 WebSocket 连接，标记 skip。
    """

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_send_json(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_create_session_default(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_create_session_custom_agent(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_load_existing_session(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_send_user_input(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_send_approved(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_send_rejected(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_receive_loop_turn_completed(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_receive_loop_error(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    async def test_execute_mode(self):
        pass
