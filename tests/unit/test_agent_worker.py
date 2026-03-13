"""AgentSessionWorker 单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
)
from agentos.kernel.runtime.state import TurnState
from agentos.kernel.runtime.workers.agent_worker import AgentSessionWorker


def _make_worker(agent_config=None):
    """构建 AgentSessionWorker 并 mock 所有外部依赖"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    runtime = MagicMock()
    runtime.repo = AsyncMock()
    runtime.state_store = MagicMock()
    runtime.state_store.is_first_turn.return_value = False
    runtime.state_store.load_session_history = AsyncMock(return_value=[])
    runtime.context_builder = MagicMock()
    runtime.context_builder.build_messages.return_value = [
        {"role": "system", "content": "你是AI助手"},
        {"role": "user", "content": "hello"},
    ]
    runtime.context_builder.append_tool_result.side_effect = lambda msgs, **kw: msgs + [
        {"role": "tool", "content": str(kw.get("result", "")), "tool_call_id": kw.get("tool_call_id")}
    ]
    runtime.tool_registry = MagicMock()
    runtime.tool_registry.as_llm_tools.return_value = [
        {"name": "bash_command"}, {"name": "read_file"}, {"name": "delegate"}
    ]
    runtime.memory_manager = None
    worker = AgentSessionWorker("s1", bus, runtime, agent_config=agent_config)
    return worker, bus, runtime


class TestConfigHelpers:
    """配置读取辅助方法测试"""

    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    def test_get_provider_from_agent_config(self, mock_config):
        agent_cfg = MagicMock()
        agent_cfg.provider = "anthropic"
        worker, _, _ = _make_worker(agent_config=agent_cfg)
        assert worker._get_provider() == "anthropic"

    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    def test_get_provider_fallback_to_global(self, mock_config):
        mock_config.get.return_value = "openai"
        worker, _, _ = _make_worker(agent_config=None)
        assert worker._get_provider() == "openai"

    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    def test_get_model_from_agent_config(self, mock_config):
        agent_cfg = MagicMock()
        agent_cfg.model = "claude-3"
        worker, _, _ = _make_worker(agent_config=agent_cfg)
        assert worker._get_model() == "claude-3"

    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    def test_get_temperature_from_agent_config(self, mock_config):
        agent_cfg = MagicMock()
        agent_cfg.temperature = 0.8
        worker, _, _ = _make_worker(agent_config=agent_cfg)
        assert worker._get_temperature() == 0.8

    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    def test_get_temperature_fallback(self, mock_config):
        mock_config.get.return_value = 0.3
        worker, _, _ = _make_worker(agent_config=None)
        assert worker._get_temperature() == 0.3

    def test_get_filtered_tools_no_config(self):
        """无 agent_config 时返回全部工具"""
        worker, _, runtime = _make_worker(agent_config=None)
        tools = worker._get_filtered_tools()
        assert len(tools) == 3

    def test_get_filtered_tools_with_filter(self):
        """配置了 tools 列表后只保留指定工具 + delegate"""
        agent_cfg = MagicMock()
        agent_cfg.tools = ["bash_command"]
        worker, _, runtime = _make_worker(agent_config=agent_cfg)
        tools = worker._get_filtered_tools()
        names = {t["name"] for t in tools}
        assert "bash_command" in names
        assert "delegate" in names  # 始终保留
        assert "read_file" not in names


class TestHandleRouting:
    """_handle 事件路由测试"""

    @pytest.mark.asyncio
    async def test_ignores_unknown_event(self):
        worker, bus, _ = _make_worker()
        await worker._handle(EventEnvelope(type="unknown", session_id="s1"))
        bus.publish.assert_not_called()


class TestHandleUserInput:
    """USER_INPUT 处理测试"""

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_user_input_triggers_llm_request(self, mock_config):
        mock_config.get.side_effect = lambda key, default=None: {
            "agent.provider": "mock",
            "agent.default_model": "gpt-4o",
            "agent.default_temperature": 0.2,
            "system.workspace_dir": "/tmp/ws",
        }.get(key, default)
        worker, bus, runtime = _make_worker()
        event = EventEnvelope(
            type=USER_INPUT,
            session_id="s1",
            turn_id="t1",
            payload={"content": "你好"},
        )
        await worker._handle(event)

        # 应该创建 session、更新活跃度、创建 turn
        runtime.repo.create_session.assert_called_once()
        runtime.repo.update_session_activity.assert_called_once()
        runtime.repo.create_turn.assert_called_once()

        # 应该发布 AGENT_STEP_STARTED 和 LLM_CALL_REQUESTED
        published_types = [call[0][0].type for call in bus.publish.call_args_list]
        assert AGENT_STEP_STARTED in published_types
        assert LLM_CALL_REQUESTED in published_types

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_user_input_sets_turn_state(self, mock_config):
        mock_config.get.side_effect = lambda key, default=None: default
        worker, bus, runtime = _make_worker()
        event = EventEnvelope(
            type=USER_INPUT, session_id="s1", turn_id="t1",
            payload={"content": "test"},
        )
        await worker._handle(event)
        runtime.state_store.set_turn.assert_called_once()
        state = runtime.state_store.set_turn.call_args[0][1]
        assert isinstance(state, TurnState)
        assert state.user_input == "test"


class TestHandleLLMResult:
    """LLM_CALL_RESULT 处理测试"""

    @pytest.mark.asyncio
    async def test_appends_assistant_message(self):
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        runtime.state_store.get_turn.return_value = state

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "你好", "tool_calls": []}},
        )
        await worker._handle(event)
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "assistant"
        assert state.messages[0]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_appends_tool_calls_to_message(self):
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        runtime.state_store.get_turn.return_value = state
        tc = [{"id": "tc1", "name": "bash_command", "arguments": {}}]
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "", "tool_calls": tc}},
        )
        await worker._handle(event)
        assert state.messages[0]["tool_calls"] == tc

    @pytest.mark.asyncio
    async def test_skips_when_no_turn_id(self):
        worker, bus, runtime = _make_worker()
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id=None,
            payload={"response": {"content": "x"}},
        )
        await worker._handle(event)
        runtime.state_store.get_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_state_not_found(self):
        worker, bus, runtime = _make_worker()
        runtime.state_store.get_turn.return_value = None
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "x"}},
        )
        await worker._handle(event)
        # 不抛异常即可


class TestHandleLLMCompleted:
    """LLM_CALL_COMPLETED 处理测试"""

    @pytest.mark.asyncio
    async def test_no_tool_calls_ends_turn(self):
        """没有工具调用时，应该发布 AGENT_STEP_COMPLETED"""
        worker, bus, runtime = _make_worker()
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "你好！"},
            ],
        )
        state.history_offset = 1
        runtime.state_store.get_turn.return_value = state

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1",
            payload={},
        )
        await worker._handle(event)

        # 应该保存结果
        runtime.repo.complete_turn.assert_called_once()
        # 应该发布 AGENT_STEP_COMPLETED
        published = [c[0][0] for c in bus.publish.call_args_list]
        assert any(e.type == AGENT_STEP_COMPLETED for e in published)

    @pytest.mark.asyncio
    async def test_with_tool_calls_triggers_tool_requests(self):
        """有工具调用时，应该发布 TOOL_CALL_REQUESTED"""
        worker, bus, runtime = _make_worker()
        tc = [{"id": "tc1", "name": "bash_command", "arguments": {"cmd": "ls"}}]
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[
                {"role": "assistant", "content": "", "tool_calls": tc},
            ],
        )
        runtime.state_store.get_turn.return_value = state

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1",
            payload={},
        )
        await worker._handle(event)

        published = [c[0][0] for c in bus.publish.call_args_list]
        assert any(e.type == TOOL_CALL_REQUESTED for e in published)
        assert state.pending_tool_calls == {"tc1"}

    @pytest.mark.asyncio
    async def test_skips_when_no_assistant_message(self):
        """没有 assistant 消息时不崩溃"""
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[
            {"role": "user", "content": "hi"},
        ])
        runtime.state_store.get_turn.return_value = state
        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        await worker._handle(event)
        bus.publish.assert_not_called()


class TestHandleToolResult:
    """TOOL_CALL_RESULT 处理测试"""

    @pytest.mark.asyncio
    async def test_collects_result_and_triggers_next_llm(self):
        """单个工具完成后，无 pending 则触发下一轮 LLM"""
        worker, bus, runtime = _make_worker()
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[{"role": "assistant", "content": ""}],
            pending_tool_calls={"tc1"},
        )
        runtime.state_store.get_turn.return_value = state

        with patch("agentos.kernel.runtime.workers.agent_worker.config") as mc:
            mc.get.side_effect = lambda k, d=None: d
            event = EventEnvelope(
                type=TOOL_CALL_RESULT, session_id="s1", turn_id="t1",
                payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "output"},
            )
            await worker._handle(event)

        # pending 应该被清空
        assert len(state.pending_tool_calls) == 0
        # 应该发布 LLM_CALL_REQUESTED
        published_types = [c[0][0].type for c in bus.publish.call_args_list]
        assert LLM_CALL_REQUESTED in published_types

    @pytest.mark.asyncio
    async def test_waits_for_all_tools(self):
        """多个工具未全部完成时，不触发 LLM"""
        worker, bus, runtime = _make_worker()
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[],
            pending_tool_calls={"tc1", "tc2"},
        )
        runtime.state_store.get_turn.return_value = state

        event = EventEnvelope(
            type=TOOL_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "ok"},
        )
        await worker._handle(event)

        # 还有 tc2，不应该发布 LLM_CALL_REQUESTED
        bus.publish.assert_not_called()
        assert "tc2" in state.pending_tool_calls


class TestErrorHandling:
    """连续错误处理测试"""

    @pytest.mark.asyncio
    async def test_consecutive_errors_trigger_error_event(self):
        """连续错误达到阈值后发布 ERROR_RAISED"""
        worker, bus, runtime = _make_worker()
        runtime.state_store.get_turn.side_effect = RuntimeError("boom")

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "x"}},
        )
        # 执行 MAX_CONSECUTIVE_ERRORS 次
        for _ in range(AgentSessionWorker.MAX_CONSECUTIVE_ERRORS):
            await worker._handle(event)

        # 最后一次应该发布 ERROR_RAISED
        published = [c[0][0] for c in bus.publish.call_args_list]
        assert any(e.type == ERROR_RAISED for e in published)

    @pytest.mark.asyncio
    async def test_successful_handle_resets_error_count(self):
        """成功处理后重置连续错误计数"""
        worker, bus, _ = _make_worker()
        worker._consecutive_errors = 2
        # 处理一个不匹配的事件类型（不触发异常）
        event = EventEnvelope(type="unknown", session_id="s1")
        await worker._handle(event)
        assert worker._consecutive_errors == 0


class TestHandleUserInputWorkspace:
    """_handle_user_input 首轮 workspace 文件加载测试"""

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_first_turn_loads_workspace_files(self, mock_config):
        """is_first_turn=True 时应调用 load_workspace_files 并透传给 context_builder"""
        mock_config.get.side_effect = lambda key, default=None: {
            "agent.provider": "mock",
            "agent.default_model": "gpt-4o",
            "agent.default_temperature": 0.2,
            "system.workspace_dir": "/tmp/ws",
        }.get(key, default)

        worker, bus, runtime = _make_worker()
        # 模拟首轮
        runtime.state_store.is_first_turn.return_value = True
        runtime.state_store.mark_first_turn_done = MagicMock()

        fake_files = [{"filename": "README.md", "content": "# proj"}]

        # load_workspace_files 是在函数体内懒导入的，需要 patch 其原始模块路径
        with patch(
            "agentos.platform.config.workspace.load_workspace_files",
            new=AsyncMock(return_value=fake_files),
        ) as mock_load:
            event = EventEnvelope(
                type=USER_INPUT,
                session_id="s1",
                turn_id="t1",
                payload={"content": "你好"},
            )
            await worker._handle(event)

        # load_workspace_files 必须被调用，且路径来自 config
        mock_load.assert_called_once_with("/tmp/ws")
        # context_builder.build_messages 收到的 context_files 应为 fake_files
        call_kwargs = runtime.context_builder.build_messages.call_args
        assert call_kwargs.kwargs.get("context_files") == fake_files
        # 首轮标记应被写入
        runtime.state_store.mark_first_turn_done.assert_called_once_with("s1")

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_non_first_turn_skips_workspace_files(self, mock_config):
        """is_first_turn=False 时不加载 workspace 文件，context_files 为 None"""
        mock_config.get.side_effect = lambda key, default=None: default

        worker, bus, runtime = _make_worker()
        # 非首轮
        runtime.state_store.is_first_turn.return_value = False

        # load_workspace_files 是在函数体内懒导入的，需要 patch 其原始模块路径
        with patch(
            "agentos.platform.config.workspace.load_workspace_files",
            new=AsyncMock(),
        ) as mock_load:
            event = EventEnvelope(
                type=USER_INPUT,
                session_id="s1",
                turn_id="t1",
                payload={"content": "再次提问"},
            )
            await worker._handle(event)

        # 非首轮不应加载文件
        mock_load.assert_not_called()
        call_kwargs = runtime.context_builder.build_messages.call_args
        assert call_kwargs.kwargs.get("context_files") is None


class TestHandleUserInputMemory:
    """_handle_user_input 中 memory_manager 加载 MEMORY.md 测试"""

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_memory_manager_loads_memory_md(self, mock_config):
        """memory_manager 不为 None 时应调用 load_memory_md 并注入 memory_context"""
        mock_config.get.side_effect = lambda key, default=None: default

        worker, bus, runtime = _make_worker()
        # 注入 memory_manager
        memory_manager = MagicMock()
        memory_manager.load_memory_md = AsyncMock(return_value="# 记忆内容")
        runtime.memory_manager = memory_manager

        event = EventEnvelope(
            type=USER_INPUT,
            session_id="s1",
            turn_id="t1",
            payload={"content": "有记忆"},
        )
        await worker._handle(event)

        # load_memory_md 应被调用一次
        memory_manager.load_memory_md.assert_called_once()
        # context_builder.build_messages 收到的 memory_context 应为加载的内容
        call_kwargs = runtime.context_builder.build_messages.call_args
        assert call_kwargs.kwargs.get("memory_context") == "# 记忆内容"

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.agent_worker.config")
    async def test_no_memory_manager_passes_none(self, mock_config):
        """memory_manager 为 None 时 memory_context 传 None"""
        mock_config.get.side_effect = lambda key, default=None: default

        worker, bus, runtime = _make_worker()
        # 默认 memory_manager = None（_make_worker 已设置）
        assert runtime.memory_manager is None

        event = EventEnvelope(
            type=USER_INPUT,
            session_id="s1",
            turn_id="t1",
            payload={"content": "无记忆"},
        )
        await worker._handle(event)

        call_kwargs = runtime.context_builder.build_messages.call_args
        assert call_kwargs.kwargs.get("memory_context") is None


class TestHandleLLMResultExtraFields:
    """_handle_llm_result 中 reasoning_details / provider_specific_fields 透传测试"""

    @pytest.mark.asyncio
    async def test_reasoning_details_forwarded(self):
        """reasoning_details 存在时应透传到 assistant 消息"""
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        runtime.state_store.get_turn.return_value = state

        reasoning = [{"type": "thinking", "thinking": "我在思考…"}]
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={
                "response": {
                    "content": "回答",
                    "tool_calls": [],
                    "reasoning_details": reasoning,
                }
            },
        )
        await worker._handle(event)

        assert len(state.messages) == 1
        assert state.messages[0]["reasoning_details"] == reasoning

    @pytest.mark.asyncio
    async def test_provider_specific_fields_forwarded(self):
        """provider_specific_fields 存在时应透传到 assistant 消息"""
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        runtime.state_store.get_turn.return_value = state

        ps_fields = {"model_version": "gemini-2.0"}
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={
                "response": {
                    "content": "回答",
                    "tool_calls": [],
                    "provider_specific_fields": ps_fields,
                }
            },
        )
        await worker._handle(event)

        assert state.messages[0]["provider_specific_fields"] == ps_fields

    @pytest.mark.asyncio
    async def test_missing_extra_fields_not_set(self):
        """两个扩展字段均不存在时，assistant 消息中不应包含这两个键"""
        worker, bus, runtime = _make_worker()
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        runtime.state_store.get_turn.return_value = state

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "普通回答", "tool_calls": []}},
        )
        await worker._handle(event)

        assert "reasoning_details" not in state.messages[0]
        assert "provider_specific_fields" not in state.messages[0]


class TestHandleLLMCompletedPersistence:
    """_handle_llm_completed 中持久化新消息到 SQLite 测试"""

    @pytest.mark.asyncio
    async def test_save_message_called_for_new_messages(self):
        """轮次结束时，应对 history_offset 之后每条非 system 消息调用 repo.save_message"""
        worker, bus, runtime = _make_worker()

        # 构造带 history_offset 的对话消息
        # index 0: system（旧历史的一部分，不应被保存）
        # index 1: user（旧历史），history_offset=2 表示新消息从 index 2 起
        # index 2: user（本轮新输入）
        # index 3: assistant（本轮新回复，无工具调用）
        state = TurnState(
            turn_id="t1",
            user_input="你好",
            messages=[
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "旧问题"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ],
        )
        state.history_offset = 2  # 新消息从 index 2 开始
        runtime.state_store.get_turn.return_value = state
        runtime.state_store.append_to_history = MagicMock()

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1",
            payload={},
        )
        await worker._handle(event)

        # history_offset=2 → 新消息 = index2(user) + index3(assistant)，共 2 条
        assert runtime.repo.save_message.call_count == 2
        # 验证每次调用的关键参数
        calls = runtime.repo.save_message.call_args_list
        roles_saved = [c.kwargs["role"] for c in calls]
        assert "user" in roles_saved
        assert "assistant" in roles_saved
        # session_id / turn_id 应正确透传
        for c in calls:
            assert c.kwargs["session_id"] == "s1"
            assert c.kwargs["turn_id"] == "t1"

    @pytest.mark.asyncio
    async def test_save_message_skips_system_role(self):
        """新消息中 role=system 的条目不应调用 repo.save_message"""
        worker, bus, runtime = _make_worker()

        # 故意在 history_offset 之后放一条 system 消息
        state = TurnState(
            turn_id="t1",
            user_input="测试",
            messages=[
                {"role": "system", "content": "注入提示"},
                {"role": "user", "content": "测试"},
                {"role": "system", "content": "不应保存"},   # system 不保存
                {"role": "assistant", "content": "好的"},
            ],
        )
        state.history_offset = 1  # 新消息从 index 1 开始（index 0 是旧历史 system）
        runtime.state_store.get_turn.return_value = state
        runtime.state_store.append_to_history = MagicMock()

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1",
            payload={},
        )
        await worker._handle(event)

        # index1(user) + index2(system，跳过) + index3(assistant) → 只保存 2 条
        assert runtime.repo.save_message.call_count == 2
        roles_saved = [c.kwargs["role"] for c in runtime.repo.save_message.call_args_list]
        assert "system" not in roles_saved

    @pytest.mark.asyncio
    async def test_save_message_with_tool_calls_json(self):
        """中间 assistant 消息含 tool_calls 时，应序列化为 JSON 字符串传给 save_message；
        最后一条 assistant 消息无 tool_calls，确保走到持久化路径"""
        worker, bus, runtime = _make_worker()

        tc = [{"id": "tc1", "name": "bash_command", "arguments": {"cmd": "ls"}}]
        # 消息布局：
        #   index 0: system（旧历史，不保存）
        #   index 1: user（新，本轮输入）             ← history_offset = 1
        #   index 2: assistant with tool_calls（新）
        #   index 3: tool result（新）
        #   index 4: assistant final（无 tool_calls，触发持久化）
        state = TurnState(
            turn_id="t1",
            user_input="执行ls",
            messages=[
                {"role": "system", "content": "系统"},
                {"role": "user", "content": "执行ls"},
                {"role": "assistant", "content": "", "tool_calls": tc},
                {"role": "tool", "content": "file1.py", "tool_call_id": "tc1", "name": "bash_command"},
                {"role": "assistant", "content": "执行完毕"},
            ],
        )
        state.history_offset = 1  # 新消息从 index 1 开始
        runtime.state_store.get_turn.return_value = state
        runtime.state_store.append_to_history = MagicMock()

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1",
            payload={},
        )
        await worker._handle(event)

        # 共 4 条新消息（跳过 system）：user, assistant(tool_calls), tool, assistant(final)
        assert runtime.repo.save_message.call_count == 4

        calls = runtime.repo.save_message.call_args_list
        assistant_with_tc_calls = [
            c for c in calls
            if c.kwargs["role"] == "assistant" and c.kwargs.get("tool_calls") is not None
        ]
        assert len(assistant_with_tc_calls) == 1
        # tool_calls 应为 JSON 字符串
        import json as _json
        parsed = _json.loads(assistant_with_tc_calls[0].kwargs["tool_calls"])
        assert parsed == tc
