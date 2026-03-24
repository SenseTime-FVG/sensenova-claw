import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from sensenova_claw.capabilities.tools.base import ToolRiskLevel
from sensenova_claw.capabilities.tools.proactive_tools import (
    CreateProactiveJobTool,
    ListProactiveJobsTool,
    ManageProactiveJobTool,
)


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt.add_job = AsyncMock()
    rt.remove_job = AsyncMock()
    rt.set_job_enabled = AsyncMock()
    rt.list_jobs = MagicMock(return_value=[])
    return rt


def test_create_tool_properties():
    tool = CreateProactiveJobTool(runtime=MagicMock())
    assert tool.name == "create_proactive_job"
    assert tool.risk_level == ToolRiskLevel.HIGH


def test_list_tool_properties():
    tool = ListProactiveJobsTool(runtime=MagicMock())
    assert tool.name == "list_proactive_jobs"
    assert tool.risk_level == ToolRiskLevel.LOW


def test_manage_tool_properties():
    tool = ManageProactiveJobTool(runtime=MagicMock())
    assert tool.name == "manage_proactive_job"
    assert tool.risk_level == ToolRiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_create_job_via_tool(mock_runtime):
    tool = CreateProactiveJobTool(runtime=mock_runtime)
    result = await tool.execute(
        name="每日邮件摘要",
        trigger={"kind": "time", "cron": "0 9 * * *"},
        task={"prompt": "整理邮件"},
        delivery={"channels": ["web"]},
    )
    mock_runtime.add_job.assert_called_once()
    assert "成功" in result or "created" in result.lower() or "每日邮件摘要" in result


@pytest.mark.asyncio
async def test_list_jobs_via_tool(mock_runtime):
    tool = ListProactiveJobsTool(runtime=mock_runtime)
    result = await tool.execute()
    mock_runtime.list_jobs.assert_called_once()


@pytest.mark.asyncio
async def test_manage_disable_job(mock_runtime):
    tool = ManageProactiveJobTool(runtime=mock_runtime)
    result = await tool.execute(job_id="pj-1", action="disable")
    mock_runtime.set_job_enabled.assert_called_once_with("pj-1", False)


@pytest.mark.asyncio
async def test_manage_delete_job(mock_runtime):
    tool = ManageProactiveJobTool(runtime=mock_runtime)
    result = await tool.execute(job_id="pj-1", action="delete")
    mock_runtime.remove_job.assert_called_once_with("pj-1")
