"""邮件工具 E2E 测试

需要真实邮箱配置才能运行：
export EMAIL_USERNAME=test@gmail.com
export EMAIL_PASSWORD=your-app-password
"""

import pytest
import os
from pathlib import Path

from agentos.capabilities.tools.email import (
    SendEmailTool,
    ListEmailsTool,
    ReadEmailTool,
    DownloadAttachmentTool,
    MarkEmailTool,
    SearchEmailsTool,
)
from agentos.platform.config.config import config


# 检查是否配置了真实邮箱
EMAIL_CONFIGURED = bool(
    os.getenv("EMAIL_USERNAME") and os.getenv("EMAIL_PASSWORD")
)

pytestmark = pytest.mark.skipif(
    not EMAIL_CONFIGURED,
    reason="需要配置 EMAIL_USERNAME 和 EMAIL_PASSWORD 环境变量"
)


@pytest.mark.asyncio
async def test_send_email_e2e():
    """E2E: 发送邮件"""
    tool = SendEmailTool()

    result = await tool.execute(
        to=os.getenv("EMAIL_USERNAME"),  # 发给自己
        subject="AgentOS 测试邮件",
        body="这是一封自动化测试邮件，请忽略。"
    )

    assert result["success"], f"发送失败: {result.get('error')}"
    assert "已发送" in result["output"]


@pytest.mark.asyncio
async def test_list_emails_e2e():
    """E2E: 列出邮件"""
    tool = ListEmailsTool()

    result = await tool.execute(limit=5)

    assert result["success"], f"列出失败: {result.get('error')}"
    # 输出应该是邮件列表的 JSON 字符串
    assert result["output"]


@pytest.mark.asyncio
async def test_search_emails_e2e():
    """E2E: 搜索邮件"""
    tool = SearchEmailsTool()

    result = await tool.execute(
        query="AgentOS",
        limit=10
    )

    assert result["success"], f"搜索失败: {result.get('error')}"
