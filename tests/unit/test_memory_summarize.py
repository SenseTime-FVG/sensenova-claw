"""对话总结记忆单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentos.capabilities.memory.config import MemoryConfig
from agentos.capabilities.memory.manager import MemoryManager, _SUMMARIZE_SYSTEM_PROMPT


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def mock_llm_factory():
    factory = MagicMock()
    provider = MagicMock()
    provider.call = AsyncMock(
        return_value={"content": "需求：实现登录功能。状态：已完成基础验证码校验。"}
    )
    factory.get_provider.return_value = provider
    return factory


@pytest.fixture
def manager(workspace, tmp_path, mock_llm_factory):
    cfg = MemoryConfig(enabled=True, bootstrap_max_chars=8000)
    db_path = tmp_path / "test_memory.db"
    return MemoryManager(
        workspace_dir=str(workspace),
        config=cfg,
        db_path=db_path,
        llm_factory=mock_llm_factory,
    )


@pytest.fixture
def manager_no_llm(workspace, tmp_path):
    cfg = MemoryConfig(enabled=True)
    db_path = tmp_path / "test_memory.db"
    return MemoryManager(
        workspace_dir=str(workspace),
        config=cfg,
        db_path=db_path,
        llm_factory=None,
    )


class TestExtractConversation:
    def test_extract_user_and_assistant_messages(self, manager):
        messages = [
            {"role": "system", "content": "你是 AI 助手"},
            {"role": "user", "content": "帮我实现登录功能"},
            {"role": "assistant", "content": "好的，我来处理"},
            {"role": "tool", "content": "工具输出"},
            {"role": "assistant", "content": "已经补上验证码逻辑"},
        ]

        result = manager._extract_conversation(messages)

        assert "用户: 帮我实现登录功能" in result
        assert "助手: 好的，我来处理" in result
        assert "助手: 已经补上验证码逻辑" in result
        assert "你是 AI 助手" not in result
        assert "工具输出" not in result


class TestSummarizeTurn:
    @pytest.mark.asyncio
    async def test_summarize_turn_creates_memory_file(self, manager, workspace):
        messages = [
            {"role": "user", "content": "帮我实现登录功能"},
            {"role": "assistant", "content": "好的，已经完成基础验证码校验"},
        ]

        await manager.summarize_turn(messages)

        memory_path = workspace / "MEMORY.md"
        assert memory_path.exists()
        content = memory_path.read_text(encoding="utf-8")
        assert "需求：实现登录功能" in content
        assert "---" in content

    @pytest.mark.asyncio
    async def test_summarize_turn_writes_agent_memory_file(self, manager, workspace):
        messages = [
            {"role": "user", "content": "继续处理 planner 的任务"},
            {"role": "assistant", "content": "已完成接口整理"},
        ]

        await manager.summarize_turn(messages, agent_id="planner")

        memory_path = workspace / "memory" / "planner.md"
        assert memory_path.exists()
        content = memory_path.read_text(encoding="utf-8")
        assert "需求：实现登录功能" in content

    @pytest.mark.asyncio
    async def test_summarize_turn_appends_instead_of_overwrite(self, manager, workspace):
        messages = [
            {"role": "user", "content": "第一轮对话"},
            {"role": "assistant", "content": "第一轮回复"},
        ]

        await manager.summarize_turn(messages)
        await manager.summarize_turn(messages)

        content = (workspace / "MEMORY.md").read_text(encoding="utf-8")
        assert content.count("---") == 2

    @pytest.mark.asyncio
    async def test_summarize_turn_skips_without_llm_factory(self, manager_no_llm, workspace):
        messages = [
            {"role": "user", "content": "测试"},
            {"role": "assistant", "content": "回复"},
        ]

        await manager_no_llm.summarize_turn(messages)

        assert not (workspace / "MEMORY.md").exists()

    @pytest.mark.asyncio
    async def test_summarize_turn_skips_empty_conversation(self, manager, workspace):
        await manager.summarize_turn([{"role": "system", "content": "系统提示"}])

        assert not (workspace / "MEMORY.md").exists()

    @pytest.mark.asyncio
    async def test_summarize_turn_skips_empty_summary(self, manager, workspace, mock_llm_factory):
        mock_llm_factory.get_provider.return_value.call = AsyncMock(return_value={"content": ""})

        await manager.summarize_turn(
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好"},
            ]
        )

        assert not (workspace / "MEMORY.md").exists()

    @pytest.mark.asyncio
    async def test_summarize_turn_passes_provider_and_model(self, manager, mock_llm_factory):
        await manager.summarize_turn(
            [
                {"role": "user", "content": "测试"},
                {"role": "assistant", "content": "回复"},
            ],
            provider="openai",
            model="gpt-4o-mini",
        )

        mock_llm_factory.get_provider.assert_called_with("openai")
        call_args = mock_llm_factory.get_provider.return_value.call.call_args
        assert call_args.kwargs["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_summarize_turn_uses_expected_prompt(self, manager, mock_llm_factory):
        await manager.summarize_turn(
            [
                {"role": "user", "content": "帮我写代码"},
                {"role": "assistant", "content": "好的"},
            ]
        )

        call_args = mock_llm_factory.get_provider.return_value.call.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == _SUMMARIZE_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "帮我写代码" in messages[1]["content"]
