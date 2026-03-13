"""C01: CommandDispatcher 命令分派"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import MockCLIApp
from agentos.app.cli.commands import CommandDispatcher


class TestCommandDispatcher:
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_quit(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/quit")) == "quit"

    def test_help(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/help")) is None

    def test_slash_shows_help(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/")) is None

    def test_debug_toggle(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/debug on"))
        assert app.debug is True
        self._run(d.dispatch("/debug off"))
        assert app.debug is False

    def test_debug_status(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        assert self._run(d.dispatch("/debug")) is None

    def test_current(self):
        app = MockCLIApp()
        app.current_session_id = "s1"
        d = CommandDispatcher(app)
        assert self._run(d.dispatch("/current")) is None

    def test_unknown(self):
        d = CommandDispatcher(MockCLIApp())
        assert self._run(d.dispatch("/xyz")) is None

    def test_new_session(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/new"))
        assert app.current_session_id == "mock_sess"

    def test_new_session_with_agent(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/new helper"))
        assert app.current_agent_id == "helper"

    def test_sessions_list(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/sessions"))
        assert any(m.get("type") == "list_sessions" for m in app._sent)

    def test_agents_list(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/agents"))
        assert any(m.get("type") == "list_agents" for m in app._sent)

    def test_switch_no_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/switch"))
        # 不应崩溃

    def test_switch_with_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/switch s123"))
        assert app.current_session_id == "s123"
