"""session persistence 单元测试

测试 messages 表、sessions 表迁移、消息存取、会话清理。
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from sensenova_claw.adapters.storage.repository import Repository


@pytest_asyncio.fixture
async def repo(tmp_path):
    """创建临时数据库的 Repository"""
    db_path = str(tmp_path / "test.db")
    r = Repository(db_path=db_path)
    await r.init()
    return r


@pytest.mark.asyncio
async def test_messages_table_creation(repo):
    """验证 messages 表已创建"""
    conn = repo._conn()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None


@pytest.mark.asyncio
async def test_sessions_table_migration(repo):
    """验证 sessions 表新增列"""
    conn = repo._conn()
    cursor = conn.execute("PRAGMA table_info(sessions)")
    cols = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "channel" in cols
    assert "model" in cols
    assert "message_count" in cols


@pytest.mark.asyncio
async def test_save_and_get_messages(repo):
    """消息存取往返测试"""
    session_id = "sess_test_001"
    turn_id = "turn_test_001"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "hello")

    # 保存 user 消息
    await repo.save_message(session_id, turn_id, role="user", content="hello")
    # 保存 assistant 消息
    await repo.save_message(session_id, turn_id, role="assistant", content="hi there")
    # 保存带 tool_calls 的 assistant 消息
    import json
    tool_calls_json = json.dumps([{"id": "tc_1", "name": "bash_command", "arguments": {"command": "ls"}}])
    await repo.save_message(session_id, turn_id, role="assistant", content="", tool_calls=tool_calls_json)
    # 保存 tool 消息
    await repo.save_message(session_id, turn_id, role="tool", content="file1.txt", tool_call_id="tc_1", tool_name="bash_command")

    messages = await repo.get_session_messages(session_id)
    assert len(messages) == 4

    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"

    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "hi there"

    assert messages[2]["role"] == "assistant"
    assert "tool_calls" in messages[2]
    assert messages[2]["tool_calls"][0]["id"] == "tc_1"

    assert messages[3]["role"] == "tool"
    assert messages[3]["content"] == "file1.txt"
    assert messages[3]["tool_call_id"] == "tc_1"
    assert messages[3]["name"] == "bash_command"


@pytest.mark.asyncio
async def test_update_session_info(repo):
    """测试更新会话的 channel 和 model"""
    session_id = "sess_test_002"
    await repo.create_session(session_id)
    await repo.update_session_info(session_id, channel="websocket", model="gpt-4o")

    conn = repo._conn()
    row = conn.execute("SELECT channel, model FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    assert row[0] == "websocket"
    assert row[1] == "gpt-4o"


@pytest.mark.asyncio
async def test_increment_message_count(repo):
    """测试递增消息计数"""
    session_id = "sess_test_003"
    await repo.create_session(session_id)
    await repo.increment_message_count(session_id)
    await repo.increment_message_count(session_id)

    conn = repo._conn()
    row = conn.execute("SELECT message_count FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    assert row[0] == 2


@pytest.mark.asyncio
async def test_delete_session_cascade(repo):
    """级联删除会话及关联数据"""
    session_id = "sess_cascade"
    turn_id = "turn_cascade"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "test")
    await repo.save_message(session_id, turn_id, role="user", content="test")

    await repo.delete_session_cascade(session_id)

    conn = repo._conn()
    assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", (session_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)).fetchone()[0] == 0
    conn.close()


@pytest.mark.asyncio
async def test_prune_sessions(repo):
    """清理超期会话"""
    # 创建一个 "旧" 会话（手动修改 last_active）
    old_session = "sess_old"
    await repo.create_session(old_session)
    conn = repo._conn()
    old_time = time.time() - 31 * 86400  # 31 天前
    conn.execute("UPDATE sessions SET last_active = ? WHERE session_id = ?", (old_time, old_session))
    conn.commit()
    conn.close()
    repo._local.conn = None  # 关闭后清除缓存，使下次 _conn() 重建连接

    # 创建一个新会话
    new_session = "sess_new"
    await repo.create_session(new_session)

    pruned = await repo.prune_sessions(max_age_days=30)
    assert pruned == 1

    sessions = await repo.list_sessions()
    session_ids = [s["session_id"] for s in sessions]
    assert old_session not in session_ids
    assert new_session in session_ids


@pytest.mark.asyncio
async def test_cap_sessions(repo):
    """限制会话总数"""
    for i in range(5):
        await repo.create_session(f"sess_cap_{i}")

    capped = await repo.cap_sessions(max_count=3)
    assert capped == 2

    sessions = await repo.list_sessions()
    assert len(sessions) == 3


@pytest.mark.asyncio
async def test_load_session_history_from_state_store(repo):
    """测试 SessionStateStore.load_session_history 从 DB 加载"""
    from sensenova_claw.kernel.runtime.state import SessionStateStore

    session_id = "sess_history"
    turn_id = "turn_history"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "hello")
    await repo.save_message(session_id, turn_id, role="user", content="hello")
    await repo.save_message(session_id, turn_id, role="assistant", content="hi")

    store = SessionStateStore()
    # 第一次加载：从 DB
    history = await store.load_session_history(session_id, repo)
    assert len(history) == 2
    assert history[0]["role"] == "user"

    # 第二次加载：从内存缓存
    history2 = await store.load_session_history(session_id, repo)
    assert history2 is history  # 同一个对象引用


@pytest.mark.asyncio
async def test_log_event_not_blocking_event_loop(repo):
    """验证 log_event 在线程池中执行，不阻塞 event loop"""
    import threading
    from sensenova_claw.kernel.events.envelope import EventEnvelope

    session_id = "sess_thread_test"
    turn_id = "turn_thread_test"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "test")

    # 记录 _sync_log_event 实际执行时所在的线程
    execution_threads: list[int] = []
    original_sync = repo._sync_log_event

    def patched_sync(event):
        execution_threads.append(threading.get_ident())
        return original_sync(event)

    repo._sync_log_event = patched_sync

    event = EventEnvelope(
        type="test.event",
        session_id=session_id,
        turn_id=turn_id,
        payload={"msg": "hello"},
        source="test",
    )
    await repo.log_event(event)

    # 验证 _sync_log_event 在非主线程中执行
    assert len(execution_threads) == 1
    assert execution_threads[0] != threading.main_thread().ident, \
        "log_event 的同步实现应在线程池中执行，而非 event loop 主线程"


@pytest.mark.asyncio
async def test_concurrent_log_events_complete_correctly(repo):
    """验证并发 log_event 不丢失数据"""
    import asyncio
    from sensenova_claw.kernel.events.envelope import EventEnvelope

    session_id = "sess_concurrent"
    turn_id = "turn_concurrent"
    await repo.create_session(session_id)
    await repo.create_turn(turn_id, session_id, "test")

    # 并发写入 10 个事件
    events = [
        EventEnvelope(
            type=f"test.event.{i}",
            session_id=session_id,
            turn_id=turn_id,
            payload={"index": i},
            source="test",
        )
        for i in range(10)
    ]
    await asyncio.gather(*[repo.log_event(e) for e in events])

    # 验证全部写入
    stored = await repo.get_session_events(session_id)
    assert len(stored) == 10
