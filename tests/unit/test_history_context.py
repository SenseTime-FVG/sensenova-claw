"""多轮对话上下文传递测试

验证:
1. 同 session 第2轮包含第1轮的 user/assistant 消息
2. history 不会包含重复的 system prompt
3. 服务重启后可从 SQLite 恢复历史
"""

from __future__ import annotations

import pytest

from agentos.adapters.storage.repository import Repository
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.state import SessionStateStore, TurnState


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    r = Repository(db_path=db_path)
    await r.init()
    return r


@pytest.fixture
def store():
    return SessionStateStore()


@pytest.fixture
def builder():
    return ContextBuilder()


# ---------- 核心: history_offset 阻止 system prompt 泄漏到历史 ----------

@pytest.mark.asyncio
async def test_history_offset_prevents_system_prompt_in_history(builder, store, repo):
    """append_to_history 只追加新消息，不追加 system prompt 和旧历史"""
    session_id = "sess_test"

    # 第1轮：无历史
    history = await store.load_session_history(session_id, repo)
    assert history == []

    messages_t1 = builder.build_messages("hello", history)
    state_t1 = TurnState(turn_id="t1", user_input="hello", messages=messages_t1)
    state_t1.history_offset = 1 + len(history)  # = 1 (跳过 system)

    # 模拟 LLM 返回
    state_t1.messages.append({"role": "assistant", "content": "hi there"})

    # 只追加新消息
    new_msgs = state_t1.messages[state_t1.history_offset:]
    store.append_to_history(session_id, new_msgs)

    saved_history = store.get_session_history(session_id)
    # 历史中应该只有 user + assistant，不含 system prompt
    assert len(saved_history) == 2
    assert saved_history[0]["role"] == "user"
    assert saved_history[1]["role"] == "assistant"
    assert saved_history[1]["content"] == "hi there"

    # 第2轮：历史应被包含
    history_t2 = store.get_session_history(session_id)
    messages_t2 = builder.build_messages("what is 1+1?", history_t2)

    # 验证第2轮消息结构: [system, user1, assistant1, user2]
    assert messages_t2[0]["role"] == "system"
    assert messages_t2[1]["role"] == "user"
    assert "hello" in messages_t2[1]["content"]
    assert messages_t2[2]["role"] == "assistant"
    assert messages_t2[2]["content"] == "hi there"
    assert messages_t2[3]["role"] == "user"
    assert "1+1" in messages_t2[3]["content"]
    # 只有一个 system prompt
    system_count = sum(1 for m in messages_t2 if m["role"] == "system")
    assert system_count == 1


@pytest.mark.asyncio
async def test_three_turns_no_exponential_growth(builder, store, repo):
    """3轮对话后，历史中不应出现重复消息"""
    session_id = "sess_3turns"

    for turn_idx, user_input in enumerate(["hello", "how are you", "bye"], 1):
        history = await store.load_session_history(session_id, repo)
        messages = builder.build_messages(user_input, history)
        state = TurnState(
            turn_id=f"t{turn_idx}",
            user_input=user_input,
            messages=messages,
        )
        state.history_offset = 1 + len(history)

        # 模拟 LLM 返回
        state.messages.append({"role": "assistant", "content": f"reply_{turn_idx}"})
        new_msgs = state.messages[state.history_offset:]
        store.append_to_history(session_id, new_msgs)

    final_history = store.get_session_history(session_id)
    # 3轮 × 2条消息(user + assistant) = 6条
    assert len(final_history) == 6

    roles = [m["role"] for m in final_history]
    assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]


# ---------- SQLite 持久化与恢复 ----------

@pytest.mark.asyncio
async def test_history_persisted_to_sqlite_and_restored(builder, repo):
    """消息持久化到 SQLite 后，新的 StateStore 可以恢复历史"""
    import json

    session_id = "sess_persist"
    turn_id = "turn_persist"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "hello")

    # 模拟 agent_worker 持久化消息
    new_messages = [
        {"role": "user", "content": "[2026-03-11] hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    for msg in new_messages:
        role = msg.get("role", "")
        tool_calls_json = None
        if msg.get("tool_calls"):
            tool_calls_json = json.dumps(msg["tool_calls"], ensure_ascii=False)
        await repo.save_message(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            content=msg.get("content"),
            tool_calls=tool_calls_json,
            tool_call_id=msg.get("tool_call_id"),
            tool_name=msg.get("name"),
        )

    # 模拟服务重启: 创建全新的 StateStore
    fresh_store = SessionStateStore()
    history = await fresh_store.load_session_history(session_id, repo)

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "[2026-03-11] hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hi there"

    # 第2轮可以正常构建上下文
    messages_t2 = builder.build_messages("what is 1+1?", history)
    system_count = sum(1 for m in messages_t2 if m["role"] == "system")
    assert system_count == 1
    assert len(messages_t2) == 4  # system + user1 + assistant1 + user2


@pytest.mark.asyncio
async def test_tool_calls_in_history(builder, store, repo):
    """包含工具调用的轮次，历史中应保留 assistant(tool_calls) + tool 消息"""
    session_id = "sess_tools"

    history = await store.load_session_history(session_id, repo)
    messages = builder.build_messages("search for Python", history)
    state = TurnState(turn_id="t1", user_input="search for Python", messages=messages)
    state.history_offset = 1 + len(history)

    # LLM 返回 tool_calls
    state.messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "tc_1", "name": "serper_search", "arguments": {"q": "Python"}}],
    })
    # tool 返回
    state.messages.append({
        "role": "tool",
        "name": "serper_search",
        "content": '{"results": []}',
        "tool_call_id": "tc_1",
    })
    # 第二轮 LLM 返回最终结果
    state.messages.append({"role": "assistant", "content": "搜索结果如下..."})

    new_msgs = state.messages[state.history_offset:]
    store.append_to_history(session_id, new_msgs)

    saved = store.get_session_history(session_id)
    # user + assistant(tool_calls) + tool + assistant(final) = 4
    assert len(saved) == 4
    assert saved[0]["role"] == "user"
    assert saved[1]["role"] == "assistant"
    assert "tool_calls" in saved[1]
    assert saved[2]["role"] == "tool"
    assert saved[3]["role"] == "assistant"
    assert saved[3]["content"] == "搜索结果如下..."
