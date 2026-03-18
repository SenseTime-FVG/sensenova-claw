import pytest

from agentos.capabilities.tools.ask_user_tool import AskUserTool


@pytest.mark.asyncio
async def test_ask_user_tool_valid_params():
    tool = AskUserTool()
    result = await tool.execute(question="选择环境？", options=["dev", "prod"])

    assert result["_ask_user"] is True
    assert result["question"] == "选择环境？"
    assert result["options"] == ["dev", "prod"]
    assert result["multi_select"] is False


@pytest.mark.asyncio
async def test_ask_user_tool_multi_select_requires_options():
    tool = AskUserTool()
    result = await tool.execute(question="选择？", multi_select=True)

    assert result["success"] is False
    assert "多选模式必须提供 options" in result["error"]


@pytest.mark.asyncio
async def test_ask_user_tool_returns_marker():
    tool = AskUserTool()
    result = await tool.execute(question="确认？", options=["是", "否"])

    assert "_ask_user" in result
    assert result["_ask_user"] is True
