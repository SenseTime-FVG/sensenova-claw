"""C01: CommandDispatcher 命令分派 + Tab 补全

使用真实 MockCLIApp（tests/helpers 中的纯 Python 实现），无 mock。
"""
import sys
import os

# 注入 tests/ 目录到 sys.path，以便 import helpers（测试辅助模块）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import MockCLIApp
from agentos.app.cli.commands import CommandDispatcher, get_completions


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

    async def test_session_current(self):
        app = MockCLIApp()
        app.current_session_id = "s1"
        d = CommandDispatcher(app)
        assert await d.dispatch("/session current") is None

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

    # ── /session 命令 ──────────────────────────

    async def test_session_list(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/session list")
        assert any(m.get("type") == "list_sessions" for m in app._sent)

    async def test_session_bare(self):
        """裸 /session 等同于 /session list"""
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/session")
        assert any(m.get("type") == "list_sessions" for m in app._sent)

    async def test_session_switch_no_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/session switch")
        # 不应崩溃

    async def test_session_switch_with_arg(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/session switch s123")
        assert app.current_session_id == "s123"

    # ── /agent 命令 ──────────────────────────

    async def test_agent_list(self):
        """裸 /agent 等同于 /agent list"""
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/agent")
        assert any(m.get("type") == "list_agents" for m in app._sent)

    async def test_agent_list_explicit(self):
        app = MockCLIApp()
        d = CommandDispatcher(app)
        await d.dispatch("/agent list")
        assert any(m.get("type") == "list_agents" for m in app._sent)

    async def test_agent_create(self):
        app = MockCLIApp()
        app._http_responses["POST /api/agents"] = {"id": "helper", "model": "gpt-4o"}
        d = CommandDispatcher(app)
        await d.dispatch("/agent create helper 助手Agent")

    async def test_agent_delete(self):
        app = MockCLIApp()
        app._http_responses["DELETE /api/agents/helper"] = {"status": "deleted"}
        d = CommandDispatcher(app)
        await d.dispatch("/agent delete helper")

    async def test_agent_info(self):
        app = MockCLIApp()
        app._http_responses["GET /api/agents/default"] = {
            "id": "default", "name": "Default", "description": "",
            "provider": "openai", "model": "gpt-4o-mini",
            "temperature": 0.2, "maxTokens": None,
            "toolCount": 5, "skillCount": 3, "sessionCount": 2,
            "tools": [], "skills": [],
        }
        d = CommandDispatcher(app)
        await d.dispatch("/agent info default")

    async def test_agent_switch(self):
        app = MockCLIApp()
        app._http_responses["GET /api/agents/helper"] = {"id": "helper"}
        d = CommandDispatcher(app)
        await d.dispatch("/agent switch helper")
        assert app.current_agent_id == "helper"
        assert app.current_session_id == "mock_sess"

    # ── /tool 命令 ──────────────────────────

    async def test_tool_list(self):
        app = MockCLIApp()
        app._http_responses["GET /api/tools"] = [
            {"name": "bash_command", "enabled": True, "riskLevel": "high", "description": "执行命令"},
        ]
        d = CommandDispatcher(app)
        await d.dispatch("/tool list")

    async def test_tool_bare(self):
        """裸 /tool 等同于 /tool list"""
        app = MockCLIApp()
        app._http_responses["GET /api/tools"] = []
        d = CommandDispatcher(app)
        await d.dispatch("/tool")

    async def test_tool_enable(self):
        app = MockCLIApp()
        app._http_responses["PUT /api/tools/bash_command/enabled"] = {"name": "bash_command", "enabled": True}
        d = CommandDispatcher(app)
        await d.dispatch("/tool enable bash_command")

    async def test_tool_disable(self):
        app = MockCLIApp()
        app._http_responses["PUT /api/tools/bash_command/enabled"] = {"name": "bash_command", "enabled": False}
        d = CommandDispatcher(app)
        await d.dispatch("/tool disable bash_command")

    # ── /skill 命令 ──────────────────────────

    async def test_skill_list(self):
        app = MockCLIApp()
        app._http_responses["GET /api/skills"] = [
            {"name": "pdf_to_markdown", "enabled": True, "category": "builtin", "description": "PDF转MD"},
        ]
        d = CommandDispatcher(app)
        await d.dispatch("/skill list")

    async def test_skill_bare(self):
        """裸 /skill 等同于 /skill list"""
        app = MockCLIApp()
        app._http_responses["GET /api/skills"] = []
        d = CommandDispatcher(app)
        await d.dispatch("/skill")

    async def test_skill_search(self):
        app = MockCLIApp()
        app._http_responses["GET /api/skills/search?q=pdf"] = {
            "local_results": [{"name": "pdf_to_markdown", "description": "PDF转MD"}],
            "remote_results": [],
        }
        d = CommandDispatcher(app)
        await d.dispatch("/skill search pdf")


class TestTabCompletion:
    """测试 get_completions 补全逻辑"""

    def test_empty_returns_all(self):
        result = get_completions("")
        assert "/session" in result
        assert "/agent" in result
        assert "/quit" in result

    def test_slash_returns_all(self):
        result = get_completions("/")
        assert "/session" in result

    def test_partial_top_command(self):
        result = get_completions("/se")
        assert "/session" in result
        assert "/quit" not in result

    def test_exact_top_command(self):
        result = get_completions("/session")
        assert result == ["/session"]

    def test_session_subcommands(self):
        result = get_completions("/session ")
        assert "list" in result
        assert "switch" in result

    def test_session_partial_sub(self):
        result = get_completions("/session sw")
        assert result == ["switch"]

    def test_agent_subcommands(self):
        result = get_completions("/agent ")
        assert "list" in result
        assert "create" in result
        assert "switch" in result

    def test_tool_subcommands(self):
        result = get_completions("/tool ")
        assert "list" in result
        assert "enable" in result

    def test_skill_subcommands(self):
        result = get_completions("/skill ")
        assert "list" in result
        assert "search" in result

    def test_debug_subcommands(self):
        result = get_completions("/debug ")
        assert "on" in result
        assert "off" in result

    def test_no_match(self):
        result = get_completions("/zzz")
        assert result == []
