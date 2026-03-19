"""邮件收发工具集

使用 Python 标准库 SMTP/IMAP 协议实现邮件自动化能力。
"""

import asyncio
import email
import imaplib
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header
from pathlib import Path
from typing import Any

from agentos.capabilities.tools.base import Tool, ToolRiskLevel
from agentos.platform.config.config import config


def _decode_email_header(header: str) -> str:
    """解码邮件头部（RFC 2047 编码）"""
    if not header:
        return ""
    decoded = decode_header(header)
    parts = []
    for content, charset in decoded:
        if isinstance(content, bytes):
            parts.append(content.decode(charset or "utf-8", errors="ignore"))
        else:
            parts.append(content)
    return "".join(parts)


def _sanitize_imap_string(value: str) -> str:
    """转义 IMAP 搜索字符串中的双引号，防止注入"""
    return value.replace('"', '\\"')


def _convert_date_to_imap(date_str: str) -> str:
    """将 YYYY-MM-DD 格式转为 IMAP 要求的 DD-Mon-YYYY 格式

    Raises:
        ValueError: 日期格式不符合 YYYY-MM-DD
    """
    dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
    return dt.strftime("%d-%b-%Y")


class SendEmailTool(Tool):
    name = "send_email"
    description = "发送邮件，支持纯文本/HTML、抄送、附件"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "收件人邮箱地址，多个收件人用逗号分隔"},
            "subject": {"type": "string", "description": "邮件主题"},
            "body": {"type": "string", "description": "邮件正文"},
            "cc": {"type": "string", "description": "抄送地址，多个用逗号分隔（可选）"},
            "html": {"type": "boolean", "description": "是否为 HTML 格式（默认 false）"},
            "attachments": {"type": "array", "items": {"type": "string"}, "description": "附件文件路径列表（可选）"},
        },
        "required": ["to", "subject", "body"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        smtp_host = email_config.get("smtp_host")
        smtp_port = email_config.get("smtp_port", 587)
        username = email_config.get("username")
        password = email_config.get("password")

        if not all([smtp_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        to = kwargs["to"]
        subject = kwargs["subject"]
        body = kwargs["body"]
        cc = kwargs.get("cc", "")
        is_html = kwargs.get("html", False)
        attachments = kwargs.get("attachments", [])

        try:
            msg = MIMEMultipart()
            msg["From"] = username
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

            for filepath in attachments:
                path = Path(filepath)
                if not path.exists():
                    return {"success": False, "error": f"附件不存在: {filepath}"}

                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={path.name}")
                    msg.attach(part)

            await asyncio.to_thread(self._send_smtp, smtp_host, smtp_port, username, password, msg, to, cc)
            return {"success": True, "output": f"邮件已发送至 {to}" + (f" (抄送: {cc})" if cc else "")}

        except Exception as e:
            return {"success": False, "error": f"发送邮件失败: {str(e)}"}

    def _send_smtp(self, host, port, username, password, msg, to, cc):
        recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            recipients.extend([addr.strip() for addr in cc.split(",")])

        # 根据端口选择连接方式：465 用 SMTP_SSL，其他用 SMTP + STARTTLS
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(username, password)
                server.sendmail(username, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(username, recipients, msg.as_string())


class ListEmailsTool(Tool):
    name = "list_emails"
    description = "列出邮件，支持过滤"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "邮箱文件夹（默认 INBOX）"},
            "limit": {"type": "integer", "description": "返回数量（默认 10）"},
            "unread_only": {"type": "boolean", "description": "仅未读邮件（默认 false）"},
            "from_email": {"type": "string", "description": "发件人过滤（可选）"},
            "subject_contains": {"type": "string", "description": "主题包含关键词（可选）"},
            "since_date": {"type": "string", "description": "起始日期 YYYY-MM-DD（可选）"},
        },
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> Any:
        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        imap_host = email_config.get("imap_host")
        imap_port = email_config.get("imap_port", 993)
        username = email_config.get("username")
        password = email_config.get("password")

        if not all([imap_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        folder = kwargs.get("folder", "INBOX")
        limit = kwargs.get("limit", 10)
        unread_only = kwargs.get("unread_only", False)
        from_email = kwargs.get("from_email")
        subject_contains = kwargs.get("subject_contains")
        since_date = kwargs.get("since_date")

        try:
            emails = await asyncio.to_thread(
                self._fetch_emails, imap_host, imap_port, username, password,
                folder, limit, unread_only, from_email, subject_contains, since_date
            )
            return {"success": True, "output": json.dumps(emails, ensure_ascii=False)}
        except Exception as e:
            return {"success": False, "error": f"列出邮件失败: {str(e)}"}

    def _fetch_emails(self, host, port, username, password, folder, limit, unread_only, from_email, subject_contains, since_date):
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(folder)

            criteria = []
            if unread_only:
                criteria.append("UNSEEN")
            if from_email:
                criteria.append(f'FROM "{_sanitize_imap_string(from_email)}"')
            if subject_contains:
                criteria.append(f'SUBJECT "{_sanitize_imap_string(subject_contains)}"')
            if since_date:
                criteria.append(f'SINCE {_convert_date_to_imap(since_date)}')

            search_str = " ".join(criteria) if criteria else "ALL"
            _, message_numbers = mail.search(None, search_str)

            emails = []
            for num in message_numbers[0].split()[-limit:]:
                _, msg_data = mail.fetch(num, "(RFC822.HEADER)")
                msg = email.message_from_bytes(msg_data[0][1])

                subject = _decode_email_header(msg.get("Subject", ""))
                from_addr = _decode_email_header(msg.get("From", ""))
                date = msg.get("Date", "")

                emails.append({"id": num.decode(), "from": from_addr, "subject": subject, "date": date})

            return emails[::-1]


class ReadEmailTool(Tool):
    name = "read_email"
    description = "读取完整邮件内容和附件列表"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "邮件 ID"},
            "folder": {"type": "string", "description": "邮箱文件夹（默认 INBOX）"},
            "mark_as_read": {"type": "boolean", "description": "是否标记为已读（默认 false）"},
        },
        "required": ["email_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        imap_host = email_config.get("imap_host")
        imap_port = email_config.get("imap_port", 993)
        username = email_config.get("username")
        password = email_config.get("password")

        if not all([imap_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        email_id = kwargs["email_id"]
        folder = kwargs.get("folder", "INBOX")
        mark_as_read = kwargs.get("mark_as_read", False)

        try:
            email_data = await asyncio.to_thread(
                self._read_email, imap_host, imap_port, username, password, folder, email_id, mark_as_read
            )
            return {"success": True, "output": json.dumps(email_data, ensure_ascii=False)}
        except Exception as e:
            return {"success": False, "error": f"读取邮件失败: {str(e)}"}

    def _read_email(self, host, port, username, password, folder, email_id, mark_as_read):
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(folder)

            _, msg_data = mail.fetch(email_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = _decode_email_header(msg.get("Subject", ""))
            from_addr = _decode_email_header(msg.get("From", ""))
            to_addr = _decode_email_header(msg.get("To", ""))
            date = msg.get("Date", "")

            body = ""
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    disposition = str(part.get("Content-Disposition", ""))

                    if "attachment" in disposition:
                        filename = part.get_filename()
                        if filename:
                            attachments.append(_decode_email_header(filename))
                    elif content_type == "text/plain" and not body:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    elif content_type == "text/html" and not body:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            if mark_as_read:
                mail.store(email_id, "+FLAGS", "\\Seen")

            return {"id": email_id, "from": from_addr, "to": to_addr, "subject": subject, "date": date, "body": body, "attachments": attachments}


class DownloadAttachmentTool(Tool):
    name = "download_attachment"
    description = "下载邮件附件到本地"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "邮件 ID"},
            "attachment_filename": {"type": "string", "description": "附件文件名"},
            "save_path": {"type": "string", "description": "保存路径"},
            "folder": {"type": "string", "description": "邮箱文件夹（默认 INBOX）"},
        },
        "required": ["email_id", "attachment_filename", "save_path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        kwargs.pop("_path_policy", None)

        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        save_path = kwargs["save_path"]

        imap_host = email_config.get("imap_host")
        imap_port = email_config.get("imap_port", 993)
        username = email_config.get("username")
        password = email_config.get("password")
        max_size_mb = email_config.get("max_attachment_size_mb", 10)

        if not all([imap_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        email_id = kwargs["email_id"]
        attachment_filename = kwargs["attachment_filename"]
        folder = kwargs.get("folder", "INBOX")

        try:
            await asyncio.to_thread(
                self._download_attachment, imap_host, imap_port, username, password,
                folder, email_id, attachment_filename, Path(save_path), max_size_mb
            )
            return {"success": True, "output": f"附件已保存至 {save_path}"}
        except Exception as e:
            return {"success": False, "error": f"下载附件失败: {str(e)}"}

    def _download_attachment(self, host, port, username, password, folder, email_id, filename, save_path, max_size_mb):
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(folder)

            _, msg_data = mail.fetch(email_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue

                part_filename = part.get_filename()
                if part_filename and _decode_email_header(part_filename) == filename:
                    payload = part.get_payload(decode=True)

                    size_mb = len(payload) / (1024 * 1024)
                    if size_mb > max_size_mb:
                        raise ValueError(f"附件大小 {size_mb:.1f}MB 超过限制 {max_size_mb}MB")

                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(payload)
                    return

            raise ValueError(f"未找到附件: {filename}")


class MarkEmailTool(Tool):
    name = "mark_email"
    description = "标记邮件状态（已读/未读/删除）"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "邮件 ID"},
            "action": {"type": "string", "enum": ["read", "unread", "delete"], "description": "操作类型"},
            "folder": {"type": "string", "description": "邮箱文件夹（默认 INBOX）"},
        },
        "required": ["email_id", "action"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        imap_host = email_config.get("imap_host")
        imap_port = email_config.get("imap_port", 993)
        username = email_config.get("username")
        password = email_config.get("password")

        if not all([imap_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        email_id = kwargs["email_id"]
        action = kwargs["action"]
        folder = kwargs.get("folder", "INBOX")

        try:
            await asyncio.to_thread(self._mark_email, imap_host, imap_port, username, password, folder, email_id, action)
            action_text = {"read": "已读", "unread": "未读", "delete": "删除"}
            return {"success": True, "output": f"邮件已标记为{action_text[action]}"}
        except Exception as e:
            return {"success": False, "error": f"标记邮件失败: {str(e)}"}

    def _mark_email(self, host, port, username, password, folder, email_id, action):
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(folder)

            if action == "read":
                mail.store(email_id, "+FLAGS", "\\Seen")
            elif action == "unread":
                mail.store(email_id, "-FLAGS", "\\Seen")
            elif action == "delete":
                mail.store(email_id, "+FLAGS", "\\Deleted")
                mail.expunge()


class SearchEmailsTool(Tool):
    name = "search_emails"
    description = "搜索邮件"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "folder": {"type": "string", "description": "邮箱文件夹（默认 INBOX）"},
            "since_date": {"type": "string", "description": "起始日期 YYYY-MM-DD（可选）"},
            "limit": {"type": "integer", "description": "返回数量（默认 20）"},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        email_config = config.get("tools.email", {})
        if not email_config.get("enabled"):
            return {"success": False, "error": "邮件功能未启用"}

        imap_host = email_config.get("imap_host")
        imap_port = email_config.get("imap_port", 993)
        username = email_config.get("username")
        password = email_config.get("password")

        if not all([imap_host, username, password]):
            return {"success": False, "error": "邮件配置不完整"}

        query = kwargs["query"]
        folder = kwargs.get("folder", "INBOX")
        since_date = kwargs.get("since_date")
        limit = kwargs.get("limit", 20)

        try:
            emails = await asyncio.to_thread(
                self._search_emails, imap_host, imap_port, username, password, folder, query, since_date, limit
            )
            return {"success": True, "output": json.dumps(emails, ensure_ascii=False)}
        except Exception as e:
            return {"success": False, "error": f"搜索邮件失败: {str(e)}"}

    def _search_emails(self, host, port, username, password, folder, query, since_date, limit):
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(folder)

            criteria = [f'TEXT "{_sanitize_imap_string(query)}"']
            if since_date:
                criteria.append(f'SINCE {_convert_date_to_imap(since_date)}')

            search_str = " ".join(criteria)
            _, message_numbers = mail.search(None, search_str)

            emails = []
            for num in message_numbers[0].split()[-limit:]:
                _, msg_data = mail.fetch(num, "(RFC822.HEADER)")
                msg = email.message_from_bytes(msg_data[0][1])

                subject = _decode_email_header(msg.get("Subject", ""))
                from_addr = _decode_email_header(msg.get("From", ""))
                date = msg.get("Date", "")

                emails.append({"id": num.decode(), "from": from_addr, "subject": subject, "date": date})

            return emails[::-1]
