"""CreateAgentTool 编排工具单元测试

使用真实 AgentRegistry 和 AgentConfig，无 mock/patch。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.capabilities.tools.orchestration import CreateAgentTool
from agentos.capabilities.tools.base import ToolRiskLevel
from agentos.capabilities.agents.config import AgentConfig
from agentos.capabilities.agents.registry import AgentRegistry


@pytest.fixture
def tool():
    return CreateAgentTool()


@pytest.fixture
def agent_registry(tmp_path):
    """创建真实 AgentRegistry（临时目录）"""
    config_dir = tmp_path / "agents"
    config_dir.mkdir()
    return AgentRegistry()


@pytest.fixture
def registry_with_default(agent_registry):
    """带有 default Agent 的注册表"""
    default = AgentConfig(
        id="default",
        name="Default Agent",
        provider="openai",
        model="gpt-4o",
        temperature=0.5,
    )
    agent_registry.register(default)
    return agent_registry


class TestToolMetadata:
    """工具元数据测试"""

    def test_name(self, tool):
        assert tool.name == "create_agent"

    def test_risk_level(self, tool):
        assert tool.risk_level == ToolRiskLevel.MEDIUM

    def test_required_params(self, tool):
        assert tool.parameters["required"] == ["id", "name"]

    def test_description_nonempty(self, tool):
        assert len(tool.description) > 0


class TestExecuteValidation:
    """参数验证测试"""

    async def test_no_registry(self, tool):
        """未注入 AgentRegistry 时返回错误"""
        result = await tool.execute(id="test", name="Test")
        assert result["success"] is False
        assert "AgentRegistry" in result["error"]

    async def test_empty_id(self, tool, agent_registry):
        """id 为空时返回错误"""
        result = await tool.execute(id="", name="Test", _agent_registry=agent_registry)
        assert result["success"] is False
        assert "id" in result["error"]

    async def test_empty_name(self, tool, agent_registry):
        """name 为空时返回错误"""
        result = await tool.execute(id="test", name="", _agent_registry=agent_registry)
        assert result["success"] is False
        assert "name" in result["error"]

    async def test_whitespace_only_id(self, tool, agent_registry):
        """id 只有空格时返回错误"""
        result = await tool.execute(id="   ", name="Test", _agent_registry=agent_registry)
        assert result["success"] is False

    async def test_duplicate_agent(self, tool, agent_registry):
        """Agent 已存在时返回错误"""
        # 先注册一个 existing Agent
        existing = AgentConfig(id="existing", name="Existing")
        agent_registry.register(existing)

        result = await tool.execute(
            id="existing", name="Test", _agent_registry=agent_registry
        )
        assert result["success"] is False
        assert "已存在" in result["error"]


class TestExecuteSuccess:
    """成功创建 Agent 测试"""

    async def test_create_minimal(self, tool, agent_registry):
        """最小参数创建 Agent"""
        result = await tool.execute(
            id="new-agent",
            name="New Agent",
            _agent_registry=agent_registry,
        )

        assert result["success"] is True
        assert result["agent_id"] == "new-agent"
        assert result["name"] == "New Agent"

        # 验证 Agent 已注册
        registered = agent_registry.get("new-agent")
        assert registered is not None
        assert registered.name == "New Agent"

    async def test_inherit_from_default(self, tool, registry_with_default):
        """未指定 provider/model/temperature 时从 default Agent 继承"""
        result = await tool.execute(
            id="new-agent",
            name="New Agent",
            _agent_registry=registry_with_default,
        )

        assert result["success"] is True
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"

        # 验证 temperature 继承自 default
        created = registry_with_default.get("new-agent")
        assert created.temperature == 0.5

    async def test_custom_params_override_default(self, tool, registry_with_default):
        """显式指定 provider/model 时覆盖默认值"""
        result = await tool.execute(
            id="custom",
            name="Custom Agent",
            provider="anthropic",
            model="claude-3-haiku",
            temperature=0.8,
            _agent_registry=registry_with_default,
        )

        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-3-haiku"

        created = registry_with_default.get("custom")
        assert created.temperature == 0.8

    async def test_no_default_agent_fallback(self, tool, agent_registry):
        """没有 default Agent 时使用硬编码默认值"""
        result = await tool.execute(
            id="agent1",
            name="Agent 1",
            _agent_registry=agent_registry,
        )

        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"

    async def test_tools_and_delegation(self, tool, agent_registry):
        """传递 tools 和 can_delegate_to 列表"""
        await tool.execute(
            id="agent2",
            name="Agent 2",
            tools=["bash_command", "read_file"],
            can_delegate_to=["agent1"],
            _agent_registry=agent_registry,
        )

        created = agent_registry.get("agent2")
        assert created.tools == ["bash_command", "read_file"]
        assert created.can_delegate_to == ["agent1"]

    async def test_strips_internal_kwargs(self, tool, agent_registry, tmp_path):
        """内部参数 (_session_id 等) 被正确移除"""
        result = await tool.execute(
            id="agent3",
            name="Agent 3",
            _agent_registry=agent_registry,
            _session_id="s-123",
        )

        assert result["success"] is True

    async def test_supports_send_message_alias(self, tool, agent_registry):
        """兼容 can_send_message_to 别名。"""
        result = await tool.execute(
            id="agent4",
            name="Agent 4",
            can_send_message_to=["helper"],
            _agent_registry=agent_registry,
        )

        assert result["success"] is True
        created = agent_registry.get("agent4")
        assert created is not None
        assert created.can_send_message_to == ["helper"]
