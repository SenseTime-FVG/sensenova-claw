"""C01: CommandDispatcher 命令分派

使用真实 MockCLIApp（tests/helpers 中的纯 Python 实现），无 mock。
"""
import sys
import os

# 注入 tests/ 目录到 sys.path，以便 import helpers（测试辅助模块）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import MockCLIApp
from agentos.app.cli.commands import CommandDispatcher


class TestCommandDispatcher:
    async def test_quit(self):
        d = CommandDispatcher(MockCLIApp())
        assert await d.dispatch("/quit") == "quit"

    async def test_help(self):
        d = CommandDispatcher(MockCLIApp())
        assert await d.dispatch("/help") is None

    async def test_slash_shows_help(self):
        d = CommandDispatcher(MockCLIApp())
        assert await d.dispatch("/") is None

    async def test_debug_toggle(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/debug on")
        assert app.debug is True
        await d.dispatch("/debug off")
        assert app.debug is False

    async def test_debug_status(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        assert await d.dispatch("/debug") is None

    async def test_current(self):
        app = MockCLIApp()
        app.current_session_id = "s1"
        d = CommandDispatcher(app)
        assert await d.dispatch("/current") is None

    async def test_unknown(self):
        d = CommandDispatcher(MockCLIApp())
        assert await d.dispatch("/xyz") is None

    async def test_new_session(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/new")
        assert app.current_session_id == "mock_sess"

    async def test_new_session_with_agent(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/new helper")
        assert app.current_agent_id == "helper"

    async def test_sessions_list(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/sessions")
        assert any(m.get("type") == "list_sessions" for m in app._sent)

    async def test_agents_list(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/agents")
        assert any(m.get("type") == "list_agents" for m in app._sent)

    async def test_switch_no_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/switch")
        # 不应崩溃

    async def test_switch_with_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/switch s123")
        assert app.current_session_id == "s123"
