"""邮件工具单元测试"""

import pytest
from unittest.mock import patch

from sensenova_claw.capabilities.tools.email import (
    SendEmailTool,
    ListEmailsTool,
    ReadEmailTool,
    DownloadAttachmentTool,
    MarkEmailTool,
    SearchEmailsTool,
)
from sensenova_claw.capabilities.tools.base import ToolRiskLevel
from sensenova_claw.platform.config.config import config


@pytest.mark.asyncio
async def test_send_email_tool_schema():
    """测试发送邮件工具的 schema"""
    tool = SendEmailTool()
    assert tool.name == "send_email"
    assert tool.risk_level == ToolRiskLevel.MEDIUM
    assert "to" in tool.parameters["properties"]
    assert "subject" in tool.parameters["properties"]
    assert set(tool.parameters["required"]) == {"to", "subject", "body"}


@pytest.mark.asyncio
async def test_send_email_disabled():
    """测试邮件功能未启用时的错误"""
    with patch.object(config, "get", return_value={"enabled": False}):
        tool = SendEmailTool()
        result = await tool.execute(to="test@test.com", subject="Test", body="Test body")
        assert result["success"] is False
        assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_send_email_missing_config():
    """测试配置不完整时的错误"""
    with patch.object(config, "get", return_value={"enabled": True, "smtp_host": ""}):
        tool = SendEmailTool()
        result = await tool.execute(to="test@test.com", subject="Test", body="Test body")
        assert result["success"] is False
        assert "配置不完整" in result["error"]


@pytest.mark.asyncio
async def test_list_emails_tool_schema():
    """测试列出邮件工具的 schema"""
    tool = ListEmailsTool()
    assert tool.name == "list_emails"
    assert tool.risk_level == ToolRiskLevel.LOW
    assert "folder" in tool.parameters["properties"]
    assert tool.parameters["required"] == []


@pytest.mark.asyncio
async def test_read_email_tool_schema():
    """测试读取邮件工具的 schema"""
    tool = ReadEmailTool()
    assert tool.name == "read_email"
    assert tool.risk_level == ToolRiskLevel.LOW
    assert "email_id" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["email_id"]


@pytest.mark.asyncio
async def test_download_attachment_tool_schema():
    """测试下载附件工具的 schema"""
    tool = DownloadAttachmentTool()
    assert tool.name == "download_attachment"
    assert tool.risk_level == ToolRiskLevel.MEDIUM
    assert set(tool.parameters["required"]) == {"email_id", "attachment_filename", "save_path"}


@pytest.mark.asyncio
async def test_mark_email_tool_schema():
    """测试标记邮件工具的 schema"""
    tool = MarkEmailTool()
    assert tool.name == "mark_email"
    assert tool.risk_level == ToolRiskLevel.MEDIUM
    assert tool.parameters["properties"]["action"]["enum"] == ["read", "unread", "delete"]
    assert set(tool.parameters["required"]) == {"email_id", "action"}


@pytest.mark.asyncio
async def test_search_emails_tool_schema():
    """测试搜索邮件工具的 schema"""
    tool = SearchEmailsTool()
    assert tool.name == "search_emails"
    assert tool.risk_level == ToolRiskLevel.LOW
    assert "query" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["query"]
