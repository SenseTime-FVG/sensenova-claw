"""CreateAgentTool 编排工具单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from agentos.capabilities.tools.orchestration import CreateAgentTool
from agentos.capabilities.tools.base import ToolRiskLevel


@pytest.fixture
def tool():
    return CreateAgentTool()


@pytest.fixture
def mock_registry():
    """创建 mock AgentRegistry"""
    registry = MagicMock()
    registry.get.return_value = None  # 默认不存在
    return registry


@pytest.fixture
def default_agent():
    """创建一个 mock 默认 Agent 配置"""
    agent = MagicMock()
    agent.provider = "openai"
    agent.model = "gpt-4o"
    agent.temperature = 0.5
    return agent


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

    async def test_empty_id(self, tool, mock_registry):
        """id 为空时返回错误"""
        result = await tool.execute(id="", name="Test", _agent_registry=mock_registry)
        assert result["success"] is False
        assert "id" in result["error"]

    async def test_empty_name(self, tool, mock_registry):
        """name 为空时返回错误"""
        result = await tool.execute(id="test", name="", _agent_registry=mock_registry)
        assert result["success"] is False
        assert "name" in result["error"]

    async def test_whitespace_only_id(self, tool, mock_registry):
        """id 只有空格时返回错误"""
        result = await tool.execute(id="   ", name="Test", _agent_registry=mock_registry)
        assert result["success"] is False

    async def test_duplicate_agent(self, tool, mock_registry):
        """Agent 已存在时返回错误"""
        mock_registry.get.side_effect = lambda x: MagicMock() if x == "existing" else None
        result = await tool.execute(
            id="existing", name="Test", _agent_registry=mock_registry
        )
        assert result["success"] is False
        assert "已存在" in result["error"]


class TestExecuteSuccess:
    """成功创建 Agent 测试"""

    async def test_create_minimal(self, tool, mock_registry):
        """最小参数创建 Agent"""
        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            mock_agent = MagicMock()
            MockConfig.create.return_value = mock_agent

            result = await tool.execute(
                id="new-agent",
                name="New Agent",
                _agent_registry=mock_registry,
            )

        assert result["success"] is True
        assert result["agent_id"] == "new-agent"
        assert result["name"] == "New Agent"
        mock_registry.register.assert_called_once_with(mock_agent)
        mock_registry.save.assert_called_once_with(mock_agent)

    async def test_inherit_from_default(self, tool, mock_registry, default_agent):
        """未指定 provider/model/temperature 时从 default Agent 继承"""
        # get("new-agent") 返回 None，get("default") 返回 default_agent
        mock_registry.get.side_effect = lambda x: default_agent if x == "default" else None

        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            MockConfig.create.return_value = MagicMock()

            result = await tool.execute(
                id="new-agent",
                name="New Agent",
                _agent_registry=mock_registry,
            )

        assert result["success"] is True
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"

        # 验证 AgentConfig.create 被调用时的 temperature 继承自 default
        call_kwargs = MockConfig.create.call_args[1]
        assert call_kwargs["temperature"] == 0.5

    async def test_custom_params_override_default(self, tool, mock_registry, default_agent):
        """显式指定 provider/model 时覆盖默认值"""
        mock_registry.get.side_effect = lambda x: default_agent if x == "default" else None

        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            MockConfig.create.return_value = MagicMock()

            result = await tool.execute(
                id="custom",
                name="Custom Agent",
                provider="anthropic",
                model="claude-3-haiku",
                temperature=0.8,
                _agent_registry=mock_registry,
            )

        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-3-haiku"

    async def test_no_default_agent_fallback(self, tool, mock_registry):
        """没有 default Agent 时使用硬编码默认值"""
        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            MockConfig.create.return_value = MagicMock()

            result = await tool.execute(
                id="agent1",
                name="Agent 1",
                _agent_registry=mock_registry,
            )

        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"

    async def test_tools_and_delegation(self, tool, mock_registry):
        """传递 tools 和 can_delegate_to 列表"""
        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            MockConfig.create.return_value = MagicMock()

            await tool.execute(
                id="agent2",
                name="Agent 2",
                tools=["bash_command", "read_file"],
                can_delegate_to=["agent1"],
                _agent_registry=mock_registry,
            )

        call_kwargs = MockConfig.create.call_args[1]
        assert call_kwargs["tools"] == ["bash_command", "read_file"]
        assert call_kwargs["can_delegate_to"] == ["agent1"]

    async def test_strips_internal_kwargs(self, tool, mock_registry):
        """内部参数 (_path_policy, _session_id) 被正确移除"""
        with patch("agentos.capabilities.agents.config.AgentConfig") as MockConfig:
            MockConfig.create.return_value = MagicMock()

            result = await tool.execute(
                id="agent3",
                name="Agent 3",
                _agent_registry=mock_registry,
                _path_policy=MagicMock(),
                _session_id="s-123",
            )

        assert result["success"] is True
