"""CLIApp 单元测试"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.app.cli.app import CLIApp


class AsyncIterList:
    """将列表包装为 async iterable，模拟 async for raw in ws"""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture
def app():
    """创建一个基本的 CLIApp 实例，mock 外部依赖"""
    with patch("agentos.app.cli.app.CommandDispatcher"), \
         patch("agentos.app.cli.app.DisplayEngine"), \
         patch("agentos.app.cli.app.Console"):
        return CLIApp(host="localhost", port=8000)


@pytest.fixture
def app_with_options():
    """创建带有完整选项的 CLIApp 实例"""
    with patch("agentos.app.cli.app.CommandDispatcher"), \
         patch("agentos.app.cli.app.DisplayEngine"), \
         patch("agentos.app.cli.app.Console"):
        return CLIApp(
            host="127.0.0.1",
            port=9000,
            agent_id="test-agent",
            session_id="session-123",
            debug=True,
            execute="hello",
        )


class TestCLIAppInit:
    """初始化参数测试"""

    def test_default_init(self, app):
        """默认参数初始化"""
        assert app.host == "localhost"
        assert app.port == 8000
        assert app.initial_agent_id is None
        assert app.initial_session_id is None
        assert app.debug is False
        assert app.execute is None
        assert app.current_agent_id == "default"
        assert app.ws is None
        assert app._last_response == ""

    def test_custom_init(self, app_with_options):
        """自定义参数初始化"""
        assert app_with_options.host == "127.0.0.1"
        assert app_with_options.port == 9000
        assert app_with_options.initial_agent_id == "test-agent"
        assert app_with_options.initial_session_id == "session-123"
        assert app_with_options.debug is True
        assert app_with_options.execute == "hello"
        assert app_with_options.current_agent_id == "test-agent"


class TestSend:
    """_send 方法测试"""

    async def test_send_json(self, app):
        """发送 JSON 消息到 WebSocket"""
        app.ws = AsyncMock()
        msg = {"type": "test", "payload": {"key": "value"}}
        await app._send(msg)
        app.ws.send.assert_called_once_with(json.dumps(msg))


class TestCreateSession:
    """_create_session 方法测试"""

    async def test_create_session_default(self, app):
        """使用默认 agent_id 创建会话"""
        app.ws = AsyncMock()
        app.ws.recv = AsyncMock(return_value=json.dumps({"session_id": "new-session"}))
        result = await app._create_session()
        assert result == "new-session"
        assert app.current_session_id == "new-session"
        assert app.current_agent_id == "default"

    async def test_create_session_custom_agent(self, app):
        """使用自定义 agent_id 创建会话"""
        app.ws = AsyncMock()
        app.ws.recv = AsyncMock(return_value=json.dumps({"session_id": "s-456"}))
        result = await app._create_session("my-agent")
        assert result == "s-456"
        assert app.current_agent_id == "my-agent"


class TestLoadSession:
    """_load_session 方法测试"""

    async def test_load_existing_session(self, app):
        """加载已有会话"""
        app.ws = AsyncMock()
        app.ws.recv = AsyncMock(return_value=json.dumps({"ok": True}))
        await app._load_session("existing-session")
        assert app.current_session_id == "existing-session"


class TestSendUserInput:
    """_send_user_input 方法测试"""

    async def test_send_user_input(self, app):
        """发送用户输入消息"""
        app.ws = AsyncMock()
        app.current_session_id = "session-1"
        await app._send_user_input("你好")
        sent = json.loads(app.ws.send.call_args[0][0])
        assert sent["type"] == "user_input"
        assert sent["session_id"] == "session-1"
        assert sent["payload"]["content"] == "你好"


class TestSendConfirmationResponse:
    """_send_confirmation_response 方法测试"""

    async def test_send_approved(self, app):
        """发送批准的确认响应"""
        app.ws = AsyncMock()
        app.current_session_id = "s-1"
        data = {"payload": {"tool_call_id": "tc-123"}}
        await app._send_confirmation_response(data, True)
        sent = json.loads(app.ws.send.call_args[0][0])
        assert sent["type"] == "tool_confirmation_response"
        assert sent["payload"]["tool_call_id"] == "tc-123"
        assert sent["payload"]["approved"] is True

    async def test_send_rejected(self, app):
        """发送拒绝的确认响应"""
        app.ws = AsyncMock()
        app.current_session_id = "s-1"
        data = {"payload": {"tool_call_id": "tc-456"}}
        await app._send_confirmation_response(data, False)
        sent = json.loads(app.ws.send.call_args[0][0])
        assert sent["payload"]["approved"] is False


class TestReceiveLoop:
    """_receive_loop 消息分发测试"""

    async def test_turn_completed(self, app):
        """收到 turn_completed 事件"""
        msg = {"type": "turn_completed", "payload": {"final_response": "回答内容"}}
        app.ws = AsyncIterList([json.dumps(msg)])
        app.display = MagicMock()
        await app._receive_loop()
        assert app._last_response == "回答内容"
        app.display.show_response.assert_called_once_with("回答内容")
        assert app._waiting.is_set()

    async def test_error_event(self, app):
        """收到 error 事件"""
        msg = {"type": "error", "payload": {"message": "something wrong"}}
        app.ws = AsyncIterList([json.dumps(msg)])
        app.display = MagicMock()
        await app._receive_loop()
        app.display.show_error.assert_called_once_with(msg)
        assert app._waiting.is_set()

    async def test_tool_confirmation_requested(self, app):
        """收到 tool_confirmation_requested 事件"""
        msg = {"type": "tool_confirmation_requested", "payload": {"tool_call_id": "tc-1"}}
        app.ws = AsyncIterList([json.dumps(msg)])
        app.display = MagicMock()
        await app._receive_loop()
        assert not app._confirm_queue.empty()
        assert app._waiting.is_set()

    async def test_other_event(self, app):
        """收到其他事件，交给 display.handle_event"""
        msg = {"type": "agent.step_started", "payload": {}}
        app.ws = AsyncIterList([json.dumps(msg)])
        app.display = MagicMock()
        await app._receive_loop()
        app.display.handle_event.assert_called_once_with(msg)

    async def test_debug_mode(self, app):
        """debug 模式下显示调试信息"""
        app.debug = True
        msg = {"type": "turn_completed", "payload": {"final_response": ""}}
        app.ws = AsyncIterList([json.dumps(msg)])
        app.display = MagicMock()
        await app._receive_loop()
        app.display.show_debug.assert_called_once_with(msg)


class TestRunExecuteMode:
    """_run_execute_mode 脚本模式测试"""

    async def test_execute_success(self, app):
        """脚本模式正常执行"""
        app.execute = "测试命令"
        app.ws = AsyncMock()
        app.current_session_id = "s-1"
        app._last_response = "执行结果"

        async def fake_wait():
            pass

        app._wait_for_turn = AsyncMock(side_effect=fake_wait)
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write = MagicMock()
            result = await app._run_execute_mode()
        assert result == 0

    async def test_execute_timeout(self, app):
        """脚本模式超时"""
        app.execute = "slow-command"
        app.ws = AsyncMock()
        app.current_session_id = "s-1"
        app._wait_for_turn = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.write = MagicMock()
            # wait_for 会抛 TimeoutError，需要 mock asyncio.wait_for
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await app._run_execute_mode()
        assert result == 2


class TestWaitForTurn:
    """_wait_for_turn 方法测试"""

    async def test_simple_wait(self, app):
        """没有确认请求时直接等待完成"""
        # 模拟 _waiting 立即被设置
        async def set_waiting():
            await asyncio.sleep(0.01)
            app._waiting.set()

        asyncio.create_task(set_waiting())
        await asyncio.wait_for(app._wait_for_turn(), timeout=1.0)

    async def test_execute_mode_auto_reject(self, app):
        """脚本模式下自动拒绝确认请求"""
        app.execute = "some command"
        app.ws = AsyncMock()
        app.current_session_id = "s-1"

        confirm_data = {"payload": {"tool_call_id": "tc-1"}}
        await app._confirm_queue.put(confirm_data)

        async def set_then_clear():
            await asyncio.sleep(0.01)
            app._waiting.set()
            await asyncio.sleep(0.01)
            # 第二轮设置：确认处理完后再完成
            app._waiting.set()

        asyncio.create_task(set_then_clear())
        await asyncio.wait_for(app._wait_for_turn(), timeout=1.0)
        # 验证发送了拒绝
        sent = json.loads(app.ws.send.call_args[0][0])
        assert sent["payload"]["approved"] is False
