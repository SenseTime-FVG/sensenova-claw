"""邮件工具单元测试"""

from email.message import EmailMessage
from unittest.mock import patch

import pytest

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


def test_list_emails_selects_folder_before_search():
    """列邮件前必须先 select 文件夹，否则 IMAP 仍停留在 AUTH 状态。"""
    tool = ListEmailsTool()
    calls = []

    header = EmailMessage()
    header["Subject"] = "Test subject"
    header["From"] = "sender@example.com"
    header["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"

    class FakeIMAP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            calls.append(("login", username, password))
            return "OK", [b"logged in"]

        def select(self, folder):
            calls.append(("select", folder))
            return "OK", [b"1"]

        def search(self, charset, criteria):
            calls.append(("search", charset, criteria))
            return "OK", [b"1"]

        def fetch(self, num, query):
            calls.append(("fetch", num, query))
            return "OK", [(b"1 (RFC822.HEADER {0})", header.as_bytes())]

    with patch("sensenova_claw.capabilities.tools.email.imaplib.IMAP4_SSL", return_value=FakeIMAP()):
        emails = tool._fetch_emails(
            "imap.test.com",
            993,
            "user@test.com",
            "secret",
            "INBOX",
            10,
            False,
            None,
            None,
            None,
        )

    assert emails == [
        {
            "id": "1",
            "from": "sender@example.com",
            "subject": "Test subject",
            "date": "Mon, 01 Jan 2024 00:00:00 +0000",
        }
    ]
    assert [name for name, *_ in calls] == ["login", "select", "search", "fetch"]


def test_list_emails_sends_imap_id_for_163_before_select():
    """163 邮箱要求在 select 前发送 IMAP ID。"""
    tool = ListEmailsTool()
    calls = []

    header = EmailMessage()
    header["Subject"] = "Test subject"
    header["From"] = "sender@example.com"
    header["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"

    class FakeIMAP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            calls.append(("login", username, password))
            return "OK", [b"logged in"]

        def _simple_command(self, name, *args):
            calls.append(("command", name, *args))
            return "OK", [b"ID completed"]

        def select(self, folder):
            calls.append(("select", folder))
            return "OK", [b"1"]

        def search(self, charset, criteria):
            calls.append(("search", charset, criteria))
            return "OK", [b"1"]

        def fetch(self, num, query):
            calls.append(("fetch", num, query))
            return "OK", [(b"1 (RFC822.HEADER {0})", header.as_bytes())]

    with patch("sensenova_claw.capabilities.tools.email.imaplib.IMAP4_SSL", return_value=FakeIMAP()):
        tool._fetch_emails(
            "imap.163.com",
            993,
            "user@163.com",
            "secret",
            "INBOX",
            10,
            False,
            None,
            None,
            None,
        )

    assert [name for name, *_ in calls] == ["login", "command", "select", "search", "fetch"]
    assert calls[1][1] == "ID"
    assert "support-email" in calls[1][2]


def test_list_emails_does_not_send_imap_id_for_other_hosts():
    """非 163 邮箱保持原状，不发送 IMAP ID。"""
    tool = ListEmailsTool()
    calls = []

    header = EmailMessage()
    header["Subject"] = "Test subject"
    header["From"] = "sender@example.com"
    header["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"

    class FakeIMAP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            calls.append(("login", username, password))
            return "OK", [b"logged in"]

        def _simple_command(self, name, *args):
            calls.append(("command", name, *args))
            return "OK", [b"ID completed"]

        def select(self, folder):
            calls.append(("select", folder))
            return "OK", [b"1"]

        def search(self, charset, criteria):
            calls.append(("search", charset, criteria))
            return "OK", [b"1"]

        def fetch(self, num, query):
            calls.append(("fetch", num, query))
            return "OK", [(b"1 (RFC822.HEADER {0})", header.as_bytes())]

    with patch("sensenova_claw.capabilities.tools.email.imaplib.IMAP4_SSL", return_value=FakeIMAP()):
        tool._fetch_emails(
            "imap.qq.com",
            993,
            "user@qq.com",
            "secret",
            "INBOX",
            10,
            False,
            None,
            None,
            None,
        )

    assert [name for name, *_ in calls] == ["login", "select", "search", "fetch"]


def test_list_emails_empty_folder_falls_back_to_inbox():
    """空 folder 不应传给 IMAP；应回退到默认 INBOX。"""
    tool = ListEmailsTool()
    selected_folders = []

    header = EmailMessage()
    header["Subject"] = "Test subject"
    header["From"] = "sender@example.com"
    header["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"

    class FakeIMAP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            return "OK", [b"logged in"]

        def select(self, folder):
            selected_folders.append(folder)
            return "OK", [b"1"]

        def search(self, charset, criteria):
            return "OK", [b"1"]

        def fetch(self, num, query):
            return "OK", [(b"1 (RFC822.HEADER {0})", header.as_bytes())]

    with patch("sensenova_claw.capabilities.tools.email.imaplib.IMAP4_SSL", return_value=FakeIMAP()):
        tool._fetch_emails(
            "imap.test.com",
            993,
            "user@test.com",
            "secret",
            "",
            10,
            False,
            None,
            None,
            None,
        )

    assert selected_folders == ["INBOX"]


def test_list_emails_raises_clear_error_when_select_fails():
    """select 失败时应直接报出文件夹错误，避免误导成 SEARCH/AUTH。"""
    tool = ListEmailsTool()

    class FakeIMAP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            return "OK", [b"logged in"]

        def select(self, folder):
            return "NO", [b"Mailbox does not exist"]

    with patch("sensenova_claw.capabilities.tools.email.imaplib.IMAP4_SSL", return_value=FakeIMAP()):
        with pytest.raises(ValueError, match="选择邮箱文件夹失败"):
            tool._fetch_emails(
                "imap.test.com",
                993,
                "user@test.com",
                "secret",
                "INBOX",
                10,
                False,
                None,
                None,
                None,
            )


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
