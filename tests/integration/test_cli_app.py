"""C02: CLIApp 会话管理（集成测试）"""
import asyncio
import sys
import os
import pytest

# 注入 tests/ 目录到 sys.path，以便 import helpers（测试辅助模块）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import MockCLIApp
from sensenova_claw.app.cli.commands import CommandDispatcher


class TestCLIApp:
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_create_session_default_agent(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/new"))
        assert app.current_session_id is not None
        assert app.current_agent_id == "default"

    def test_create_session_custom_agent(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/new research"))
        assert app.current_agent_id == "research"

    def test_switch_session(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        self._run(d.dispatch("/switch test_sess_123"))
        assert app.current_session_id == "test_sess_123"

    def test_history_sends_get_messages(self):
        app = MockCLIApp()
        app.current_session_id = "hist_s"
        d = CommandDispatcher(app)
        self._run(d.dispatch("/history"))
        assert any(m.get("type") == "get_messages" for m in app._sent)

    def test_cancel_sends_cancel_turn(self):
        app = MockCLIApp()
        app.current_session_id = "cancel_s"
        d = CommandDispatcher(app)
        self._run(d.dispatch("/cancel"))
        assert any(m.get("type") == "cancel_turn" for m in app._sent)

