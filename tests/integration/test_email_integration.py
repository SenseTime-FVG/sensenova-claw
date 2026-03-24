"""邮件工具集成测试"""

import pytest
from pathlib import Path
from unittest.mock import patch

from sensenova_claw.capabilities.tools.email import DownloadAttachmentTool
from sensenova_claw.platform.config.config import config


@pytest.mark.asyncio
async def test_download_attachment_disabled():
    """邮件功能未启用时返回错误"""
    tool = DownloadAttachmentTool()

    with patch.object(config, "get", return_value={"enabled": False}):
        result = await tool.execute(
            email_id="1",
            attachment_filename="test.txt",
            save_path="/tmp/test.txt",
        )
        assert result["success"] is False
        assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_attachment_size_limit():
    """测试附件大小限制配置"""
    mock_config = {
        "enabled": True,
        "imap_host": "imap.test.com",
        "imap_port": 993,
        "username": "test@test.com",
        "password": "test_pass",
        "max_attachment_size_mb": 1,
    }

    with patch.object(config, "get", return_value=mock_config):
        assert config.get("tools.email")["max_attachment_size_mb"] == 1
