"""邮件工具集成测试"""

import pytest
from pathlib import Path
from unittest.mock import patch

from agentos.capabilities.tools.email import DownloadAttachmentTool
from agentos.platform.security.path_policy import PathPolicy, PathVerdict
from agentos.platform.config.config import config


@pytest.mark.asyncio
async def test_download_attachment_with_path_policy():
    """测试附件下载与 PathPolicy 集成"""
    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)

    policy = PathPolicy(workspace=workspace, granted_paths=[])
    tool = DownloadAttachmentTool()

    # 允许的路径（workspace 内）
    allowed_path = workspace / "test.txt"
    assert policy.check_write(str(allowed_path)) == PathVerdict.ALLOW

    # 不允许的路径
    forbidden_path = Path("/etc/passwd")
    assert policy.check_write(str(forbidden_path)) == PathVerdict.DENY

    # 测试工具拒绝不安全路径
    with patch.object(config, "get", return_value={"enabled": True}):
        result = await tool.execute(
            email_id="1",
            attachment_filename="test.txt",
            save_path=str(forbidden_path),
            _path_policy=policy
        )
        assert result["success"] is False
        assert "路径不允许" in result["error"]


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
