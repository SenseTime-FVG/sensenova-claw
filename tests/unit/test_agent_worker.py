"""AgentSessionWorker 单元测试 — 使用真实组件，无 mock"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PublicEventBus, PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_COMPLETED,
    AGENT_MESSAGE_FAILED,
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.state import SessionStateStore, TurnState
from sensenova_claw.kernel.runtime.workers.agent_worker import AgentSessionWorker
from sensenova_claw.platform.config.config import config


# ── 真实 AgentRuntime 替身 ────────────────────────────────


class _SimpleAgentRuntime:
    """持有真实的 repo、state_store、context_builder、tool_registry"""

    def __init__(self, repo, state_store, context_builder, tool_registry, memory_manager=None):
        self.repo = repo
        self.state_store = state_store
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.jsonl_writer = None
        self.context_compressor = None


class _SendMessageTool(Tool):
    name = "send_message"
    description = "向其他 Agent 发送消息"
    parameters = {"type": "object", "properties": {}}


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def public_bus():
    return PublicEventBus()


@pytest.fixture
def private_bus(public_bus):
    return PrivateEventBus("s1", public_bus)


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "test.db"))
    await r.init()
    return r


@pytest.fixture
def state_store():
    return SessionStateStore()


@pytest.fixture
def tool_registry():
    return ToolRegistry()


@pytest.fixture
def context_builder():
    return ContextBuilder()


@pytest.fixture
def runtime(repo, state_store, context_builder, tool_registry):
    return _SimpleAgentRuntime(repo, state_store, context_builder, tool_registry)


@pytest.fixture
def fake_memory_manager():
    class _FakeMemoryManager:
        def __init__(self):
            self.load_memory_md = AsyncMock(return_value="记忆上下文")
            self.summarize_turn = AsyncMock()

    return _FakeMemoryManager()


async def _collect_from_bus(public_bus, target_type=None, count=None, timeout=5.0):
    """从公共总线收集事件，直到出现目标类型或收集足够数量"""
    collected = []
    done = asyncio.Event()

    async def collector():
        async for evt in public_bus.subscribe():
            collected.append(evt)
            if target_type and evt.type == target_type:
                done.set()
                break
            if count and len(collected) >= count:
                done.set()
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.01)  # 等待订阅完成
    return collected, done, task


# ── 配置读取辅助测试 ─────────────────────────────────────


class TestConfigHelpers:
    """配置读取辅助方法测试"""

    def test_get_provider_from_agent_config(self, private_bus, runtime):
        # 显式固定 config，避免受本机 ~/.sensenova-claw/config.yml 覆盖影响。
        original = copy.deepcopy(config.data)
        try:
            config.data["llm"]["models"]["claude-sonnet"] = {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-6",
            }
            agent_cfg = AgentConfig(id="test", name="test", model="claude-sonnet")
            worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
            assert worker._get_provider() == "anthropic"
        finally:
            config.data = original

    def test_get_provider_fallback_to_global(self, private_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=None)
        provider = worker._get_provider()
        assert isinstance(provider, str)

    def test_get_model_from_agent_config(self, private_bus, runtime):
        # model key "claude-opus" → model_id 应为 "claude-opus-4-6"
        agent_cfg = AgentConfig(id="test", name="test", model="claude-opus")
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        assert worker._get_model() == "claude-opus-4-6"

    def test_get_temperature_from_agent_config(self, private_bus, runtime):
        agent_cfg = AgentConfig(id="test", name="test", temperature=0.8)
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        assert worker._get_temperature() == 0.8

    def test_get_temperature_fallback(self, private_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=None)
        temp = worker._get_temperature()
        assert isinstance(temp, (int, float))

    def test_get_model_key_fallback_to_llm_default_model(self, private_bus, runtime):
        original = copy.deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=None)
            assert worker._get_model() == "mock-agent-v1"
            assert worker._get_provider() == "mock"
        finally:
            config.data = original

    def test_get_filtered_tools_no_config(self, private_bus, runtime):
        """无 agent_config 时返回全部工具"""
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=None)
        tools = worker._get_filtered_tools()
        assert len(tools) > 0

    def test_get_filtered_tools_with_filter(self, private_bus, runtime):
        """配置了 tools 列表后只保留指定工具"""
        agent_cfg = AgentConfig(id="test", name="test", tools=["bash_command"])
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        tools = worker._get_filtered_tools()
        names = {t["name"] for t in tools}
        assert "bash_command" in names

    def test_get_filtered_tools_keeps_mcp_tools_when_tools_are_explicit(self, private_bus, runtime, monkeypatch):
        """agent.tools 只过滤内置工具，不应误过滤 MCP 工具。"""
        monkeypatch.setattr(
            runtime.tool_registry,
            "as_llm_tools",
            lambda **kwargs: [
                {"name": "bash_command", "description": "bash", "parameters": {}},
                {"name": "read_file", "description": "read", "parameters": {}},
                {"name": "mcp__browsermcp__browser_snapshot", "description": "snapshot", "parameters": {}},
            ],
        )
        agent_cfg = AgentConfig(
            id="test",
            name="test",
            tools=["bash_command"],
            mcp_servers=["browsermcp"],
            mcp_tools=["browsermcp/browser_snapshot"],
        )
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        tools = worker._get_filtered_tools()
        names = {t["name"] for t in tools}
        assert "bash_command" in names
        assert "mcp__browsermcp__browser_snapshot" in names
        assert "read_file" not in names

    def test_get_filtered_tools_hides_send_message_when_delegation_disabled(self, private_bus, runtime):
        """禁用委托后，不应再向 LLM 暴露 send_message。"""
        runtime.tool_registry.register(_SendMessageTool())
        agent_cfg = AgentConfig(id="test", name="test", can_delegate_to=None)
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        tools = worker._get_filtered_tools()
        names = {t["name"] for t in tools}
        assert "send_message" not in names

    def test_get_filtered_tools_honors_disabled_tool_preferences(self, private_bus, runtime, tmp_path):
        """Agent 工具偏好禁用后，不应再向 LLM 暴露该工具。"""
        runtime.context_builder.sensenova_claw_home = str(tmp_path)
        (tmp_path / ".agent_preferences.json").write_text(
            '{"agent_tools": {"test": {"bash_command": false}}}',
            encoding="utf-8",
        )
        agent_cfg = AgentConfig(id="test", name="test")
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        tools = worker._get_filtered_tools()
        names = {t["name"] for t in tools}
        assert "bash_command" not in names


# ── 事件路由测试 ──────────────────────────────────────────


class TestHandleRouting:
    async def test_ignores_unknown_event(self, private_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        await worker._handle(EventEnvelope(type="unknown", session_id="s1"))

    async def test_agent_message_completed_triggers_follow_up(self, private_bus, public_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)

        event = EventEnvelope(
            type=AGENT_MESSAGE_COMPLETED,
            session_id="s1",
            payload={"agent_id": "helper", "result": "异步结果"},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        published_types = [e.type for e in collected]
        assert AGENT_STEP_STARTED in published_types
        assert LLM_CALL_REQUESTED in published_types

    async def test_agent_message_failed_triggers_follow_up(self, private_bus, public_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)

        event = EventEnvelope(
            type=AGENT_MESSAGE_FAILED,
            session_id="s1",
            payload={"agent_id": "helper", "error": "出错了"},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        published_types = [e.type for e in collected]
        assert AGENT_STEP_STARTED in published_types
        assert LLM_CALL_REQUESTED in published_types

    async def test_cancel_request_marks_turn_cancelled(self, private_bus, public_bus, runtime, repo, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="hi")
        state_store.set_turn("s1", TurnState(turn_id="t1", user_input="hi", messages=[]))

        collected, done, task = await _collect_from_bus(public_bus, target_type=ERROR_RAISED)
        await worker._handle(
            EventEnvelope(
                type=USER_TURN_CANCEL_REQUESTED,
                session_id="s1",
                payload={"reason": "user_stop"},
            )
        )
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert state_store.is_turn_cancelled("s1", "t1") is True
        turns = await repo.get_session_turns("s1")
        assert turns[0]["status"] == "cancelled"
        assert collected[-1].payload["error_type"] == "TurnCancelled"


# ── USER_INPUT 处理测试 ──────────────────────────────────


class TestHandleUserInput:
    async def test_user_input_triggers_llm_request(self, private_bus, public_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, count=2)

        event = EventEnvelope(
            type=USER_INPUT, session_id="s1", turn_id="t1",
            payload={"content": "你好"},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        published_types = [e.type for e in collected]
        assert AGENT_STEP_STARTED in published_types
        assert LLM_CALL_REQUESTED in published_types

    async def test_user_input_sets_turn_state(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        event = EventEnvelope(
            type=USER_INPUT, session_id="s1", turn_id="t1",
            payload={"content": "test"},
        )
        await worker._handle(event)

        state = state_store.get_turn("s1", "t1")
        assert state is not None
        assert isinstance(state, TurnState)
        assert state.user_input == "test"

    async def test_user_input_loads_agent_memory(self, private_bus, repo, state_store, context_builder, tool_registry, fake_memory_manager):
        runtime = _SimpleAgentRuntime(
            repo,
            state_store,
            context_builder,
            tool_registry,
            memory_manager=fake_memory_manager,
        )
        agent_cfg = AgentConfig(id="planner", name="planner")
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)

        event = EventEnvelope(
            type=USER_INPUT, session_id="s1", turn_id="t1",
            payload={"content": "加载记忆"},
        )
        await worker._handle(event)

        fake_memory_manager.load_memory_md.assert_awaited_once_with(agent_id="planner")


# ── LLM_CALL_RESULT 处理测试 ─────────────────────────────


class TestHandleLLMResult:
    async def test_appends_assistant_message(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "你好", "tool_calls": []}},
        )
        await worker._handle(event)
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "assistant"
        assert state.messages[0]["content"] == "你好"

    async def test_appends_tool_calls_to_message(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)

        tc = [{"id": "tc1", "name": "bash_command", "arguments": {}}]
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "", "tool_calls": tc}},
        )
        await worker._handle(event)
        assert state.messages[0]["tool_calls"] == tc

    async def test_skips_when_no_turn_id(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id=None,
            payload={"response": {"content": "x"}},
        )
        await worker._handle(event)
        assert state_store.get_turn("s1", "t1") is None

    async def test_skips_when_state_not_found(self, private_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="nonexistent",
            payload={"response": {"content": "x"}},
        )
        await worker._handle(event)

    async def test_ignores_llm_result_for_cancelled_turn(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)
        state_store.mark_turn_cancelled("s1", "t1")

        await worker._handle(
            EventEnvelope(
                type=LLM_CALL_RESULT,
                session_id="s1",
                turn_id="t1",
                payload={"response": {"content": "不会写入", "tool_calls": []}},
            )
        )
        assert state.messages == []


# ── LLM_CALL_COMPLETED 处理测试 ──────────────────────────


class TestHandleLLMCompleted:
    async def test_no_tool_calls_ends_turn(self, private_bus, public_bus, runtime, state_store, repo):
        """没有工具调用时应发布 AGENT_STEP_COMPLETED"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="hi")

        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "你好！"},
            ],
        )
        state.history_offset = 1
        state_store.set_turn("s1", state)

        collected, done, task = await _collect_from_bus(public_bus, target_type=AGENT_STEP_COMPLETED)

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert any(e.type == AGENT_STEP_COMPLETED for e in collected)

    async def test_with_tool_calls_triggers_tool_requests(self, private_bus, public_bus, runtime, state_store):
        """有工具调用时应发布 TOOL_CALL_REQUESTED"""
        worker = AgentSessionWorker("s1", private_bus, runtime)
        tc = [{"id": "tc1", "name": "bash_command", "arguments": {"cmd": "ls"}}]
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[{"role": "assistant", "content": "", "tool_calls": tc}],
        )
        state_store.set_turn("s1", state)

        collected, done, task = await _collect_from_bus(public_bus, target_type=TOOL_CALL_REQUESTED)

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert any(e.type == TOOL_CALL_REQUESTED for e in collected)
        assert state.pending_tool_calls == {"tc1"}

    async def test_skips_when_no_assistant_message(self, private_bus, runtime, state_store):
        """没有 assistant 消息时不崩溃"""
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[
            {"role": "user", "content": "hi"},
        ])
        state_store.set_turn("s1", state)

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        await worker._handle(event)

    async def test_no_tool_calls_triggers_memory_summary(self, private_bus, public_bus, repo, state_store, context_builder, tool_registry, fake_memory_manager, monkeypatch):
        original = copy.deepcopy(config.data)
        config.data["llm"]["models"]["claude-sonnet"] = {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
        }
        runtime = _SimpleAgentRuntime(
            repo,
            state_store,
            context_builder,
            tool_registry,
            memory_manager=fake_memory_manager,
        )
        agent_cfg = AgentConfig(id="planner", name="planner", model="claude-sonnet")
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)

        await repo.create_session("s1", meta={"agent_id": "planner"})
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="hi")

        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "你好！"},
            ],
        )
        state.history_offset = 1
        state_store.set_turn("s1", state)

        created_tasks = []
        original_create_task = asyncio.create_task

        def capture_task(coro):
            task = original_create_task(coro)
            created_tasks.append(task)
            return task

        monkeypatch.setattr(
            "sensenova_claw.kernel.runtime.workers.agent_worker.asyncio.create_task",
            capture_task,
        )

        collected, done, task = await _collect_from_bus(public_bus, target_type=AGENT_STEP_COMPLETED)

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        try:
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()
            await asyncio.gather(*created_tasks)

            assert any(evt.type == AGENT_STEP_COMPLETED for evt in collected)
            fake_memory_manager.summarize_turn.assert_awaited_once_with(
                state.messages,
                provider="anthropic",
                model="claude-sonnet-4-6",
                agent_id="planner",
            )
        finally:
            config.data = original

    def test_get_provider_prefers_agent_provider_for_direct_model_id(self, private_bus, runtime):
        agent_cfg = AgentConfig(id="test", name="test", model="gpt-4o-mini")
        agent_cfg.provider = "openai"
        worker = AgentSessionWorker("s1", private_bus, runtime, agent_config=agent_cfg)
        assert worker._get_provider() == "openai"
        assert worker._get_model() == "gpt-4o-mini"


# ── TOOL_CALL_RESULT 处理测试 ─────────────────────────────


class TestHandleToolResult:
    async def test_collects_result_and_triggers_next_llm(self, private_bus, public_bus, runtime, state_store):
        """单个工具完成后触发下一轮 LLM"""
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[{"role": "assistant", "content": ""}],
            pending_tool_calls={"tc1"},
        )
        state_store.set_turn("s1", state)

        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)

        event = EventEnvelope(
            type=TOOL_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "output"},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert len(state.pending_tool_calls) == 0
        assert any(e.type == LLM_CALL_REQUESTED for e in collected)

    async def test_waits_for_all_tools(self, private_bus, runtime, state_store):
        """多个工具未全部完成时不触发 LLM"""
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(
            turn_id="t1", user_input="hi",
            messages=[],
            pending_tool_calls={"tc1", "tc2"},
        )
        state_store.set_turn("s1", state)

        event = EventEnvelope(
            type=TOOL_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "ok"},
        )
        await worker._handle(event)
        assert "tc2" in state.pending_tool_calls


# ── 连续错误处理测试 ──────────────────────────────────────


class TestErrorHandling:
    async def test_consecutive_errors_trigger_error_event(self, private_bus, public_bus, runtime, state_store):
        """连续错误达到阈值后发布 ERROR_RAISED"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, target_type=ERROR_RAISED)

        # 构造会导致异常的 payload: response 不是 dict
        bad_state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", bad_state)

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": "not_a_dict"},
        )
        for _ in range(AgentSessionWorker.MAX_CONSECUTIVE_ERRORS):
            await worker._handle(event)

        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert any(e.type == ERROR_RAISED for e in collected)

    async def test_successful_handle_resets_error_count(self, private_bus, runtime):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        worker._consecutive_errors = 2
        event = EventEnvelope(type="unknown", session_id="s1")
        await worker._handle(event)
        assert worker._consecutive_errors == 0


# ── LLM_CALL_RESULT 扩展字段透传测试 ─────────────────────


class TestHandleLLMResultExtraFields:
    async def test_reasoning_details_forwarded(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)

        reasoning = [{"type": "thinking", "thinking": "我在思考…"}]
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "回答", "tool_calls": [], "reasoning_details": reasoning}},
        )
        await worker._handle(event)
        assert state.messages[0]["reasoning_details"] == reasoning

    async def test_provider_specific_fields_forwarded(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)

        ps_fields = {"model_version": "gemini-2.0"}
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "回答", "tool_calls": [], "provider_specific_fields": ps_fields}},
        )
        await worker._handle(event)
        assert state.messages[0]["provider_specific_fields"] == ps_fields

    async def test_missing_extra_fields_not_set(self, private_bus, runtime, state_store):
        worker = AgentSessionWorker("s1", private_bus, runtime)
        state = TurnState(turn_id="t1", user_input="hi", messages=[])
        state_store.set_turn("s1", state)

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "普通回答", "tool_calls": []}},
        )
        await worker._handle(event)
        assert "reasoning_details" not in state.messages[0]
        assert "provider_specific_fields" not in state.messages[0]


# ── 增量持久化测试 ────────────────────────────────────


class TestIncrementalPersistence:
    """测试消息在各 handler 中增量保存到 SQLite"""

    async def test_llm_result_persists_assistant_message(self, private_bus, public_bus, runtime, state_store, repo):
        """_handle_llm_result 应立即保存 assistant 消息"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="你好")

        state = TurnState(
            turn_id="t1", user_input="你好",
            messages=[
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "你好"},
            ],
        )
        state.history_offset = 1
        state_store.set_turn("s1", state)

        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"response": {"content": "你好！", "tool_calls": []}},
        )
        await worker._handle(event)

        messages = await repo.get_session_messages("s1")
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "你好！"

    async def test_tool_result_persists_tool_message(self, private_bus, public_bus, runtime, state_store, repo):
        """_handle_tool_result 应立即保存 tool 消息"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="执行ls")

        state = TurnState(
            turn_id="t1", user_input="执行ls",
            messages=[
                {"role": "system", "content": "系统"},
                {"role": "user", "content": "执行ls"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "tc1", "name": "bash_command", "arguments": {"cmd": "ls"}}
                ]},
            ],
        )
        state.history_offset = 1
        state.pending_tool_calls = {"tc1"}
        state_store.set_turn("s1", state)

        # 等待 LLM_CALL_REQUESTED（工具结果收齐后触发下一轮 LLM）
        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)

        event = EventEnvelope(
            type=TOOL_CALL_RESULT, session_id="s1", turn_id="t1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "file1.py"},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        messages = await repo.get_session_messages("s1")
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["name"] == "bash_command"
        assert tool_msgs[0]["tool_call_id"] == "tc1"

    async def test_persist_message_skips_system_role(self, private_bus, public_bus, runtime, state_store, repo):
        """_persist_message 应跳过 system 角色"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="测试")

        await worker._persist_message("s1", "t1", {"role": "system", "content": "不应保存"})
        await worker._persist_message("s1", "t1", {"role": "user", "content": "测试"})
        await worker._persist_message("s1", "t1", {"role": "assistant", "content": "好的"})

        messages = await repo.get_session_messages("s1")
        roles_saved = [m["role"] for m in messages]
        assert "system" not in roles_saved
        assert len(messages) == 2

    async def test_llm_completed_does_not_duplicate_save(self, private_bus, public_bus, runtime, state_store, repo):
        """_handle_llm_completed 不应重复保存已增量保存的消息"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="你好")

        # 模拟已增量保存了 user + assistant 消息
        await repo.save_message("s1", "t1", "user", "你好")
        await repo.save_message("s1", "t1", "assistant", "你好！")

        state = TurnState(
            turn_id="t1", user_input="你好",
            messages=[
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ],
        )
        state.history_offset = 1
        state_store.set_turn("s1", state)

        collected, done, task = await _collect_from_bus(public_bus, target_type=AGENT_STEP_COMPLETED)

        event = EventEnvelope(
            type=LLM_CALL_COMPLETED, session_id="s1", turn_id="t1", payload={},
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        # 验证消息没有被重复保存（仍然只有 2 条）
        messages = await repo.get_session_messages("s1")
        assert len(messages) == 2

    async def test_cancelled_turn_keeps_user_message_in_runtime_history(
        self,
        private_bus,
        public_bus,
        runtime,
        state_store,
        repo,
    ):
        """取消当前轮次后，已进入上下文的用户消息仍应保留到后续轮次历史。"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="解释 DSA")
        await repo.save_message("s1", "t1", "user", "解释 DSA")

        cancelled_state = TurnState(
            turn_id="t1",
            user_input="解释 DSA",
            messages=[
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "解释 DSA"},
            ],
        )
        cancelled_state.history_offset = 1
        state_store.set_turn("s1", cancelled_state)

        cancel_event = EventEnvelope(
            type=USER_TURN_CANCEL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={"reason": "user_stop"},
        )
        await worker._handle(cancel_event)

        history = state_store.get_session_history("s1")
        assert history == [{"role": "user", "content": "解释 DSA"}]

        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)
        try:
            next_event = EventEnvelope(
                type=USER_INPUT,
                session_id="s1",
                turn_id="t2",
                payload={"content": "我刚才问了什么"},
            )
            await worker._handle(next_event)
            await asyncio.wait_for(done.wait(), timeout=5)
        finally:
            task.cancel()

        request_event = next(evt for evt in collected if evt.type == LLM_CALL_REQUESTED)
        request_messages = request_event.payload["messages"]
        user_contents = [
            msg.get("content", "")
            for msg in request_messages
            if msg.get("role") == "user"
        ]
        assert "解释 DSA" in user_contents
        assert any("我刚才问了什么" in content for content in user_contents)

    async def test_error_raised_keeps_user_message_in_runtime_history(
        self,
        private_bus,
        public_bus,
        runtime,
        state_store,
        repo,
    ):
        """纯 ERROR_RAISED 收尾时，已进入上下文的用户消息仍应保留到后续轮次历史。"""
        worker = AgentSessionWorker("s1", private_bus, runtime)

        await repo.create_session("s1")
        await repo.create_turn(turn_id="t1", session_id="s1", user_input="解释 DSA")
        await repo.save_message("s1", "t1", "user", "解释 DSA")

        failed_state = TurnState(
            turn_id="t1",
            user_input="解释 DSA",
            messages=[
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "解释 DSA"},
            ],
        )
        failed_state.history_offset = 1
        state_store.set_turn("s1", failed_state)

        error_event = EventEnvelope(
            type=ERROR_RAISED,
            session_id="s1",
            turn_id="t1",
            payload={"error_type": "WorkerCrash", "error_message": "boom"},
        )
        await worker._handle(error_event)

        history = state_store.get_session_history("s1")
        assert history == [{"role": "user", "content": "解释 DSA"}]

        collected, done, task = await _collect_from_bus(public_bus, target_type=LLM_CALL_REQUESTED)
        try:
            next_event = EventEnvelope(
                type=USER_INPUT,
                session_id="s1",
                turn_id="t2",
                payload={"content": "我刚才问了什么"},
            )
            await worker._handle(next_event)
            await asyncio.wait_for(done.wait(), timeout=5)
        finally:
            task.cancel()

        request_event = next(evt for evt in collected if evt.type == LLM_CALL_REQUESTED)
        request_messages = request_event.payload["messages"]
        user_contents = [
            msg.get("content", "")
            for msg in request_messages
            if msg.get("role") == "user"
        ]
        assert "解释 DSA" in user_contents
        assert any("我刚才问了什么" in content for content in user_contents)
