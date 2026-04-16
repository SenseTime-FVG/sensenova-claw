"""DingTalk runtime：负责对接官方 dingtalk-stream SDK。"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import logging
import ssl
from typing import Any, Awaitable, Callable

import httpx
import websockets

from sensenova_claw.platform.security.ssl import CERTIFI_SSL_CONTEXT

from .config import DingtalkConfig
from .models import DingtalkInboundMessage

logger = logging.getLogger(__name__)

DingtalkMessageHandler = Callable[[DingtalkInboundMessage], Awaitable[None]]
_SSL_CONTEXT = CERTIFI_SSL_CONTEXT

_DINGTALK_API_BASE = "https://api.dingtalk.com"


class _CompatDingTalkStreamClient:
    """对官方 SDK 做最小兼容封装，补齐 CA 证书并修正异常日志。"""

    def __init__(self, sdk: Any, credential: Any, logger_: logging.Logger):
        self._client = sdk.DingTalkStreamClient(credential, logger=logger_)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    async def start(self) -> None:
        self.pre_start()

        while True:
            try:
                connection = self.open_connection()

                if not connection:
                    self.logger.error("open connection failed")
                    await asyncio.sleep(10)
                    continue
                self.logger.info("endpoint is %s", connection)

                uri = f'{connection["endpoint"]}?ticket={connection["ticket"]}'
                async with websockets.connect(uri, ssl=_SSL_CONTEXT) as websocket:
                    self.websocket = websocket
                    asyncio.create_task(self.keepalive(websocket))
                    async for raw_message in websocket:
                        json_message = json.loads(raw_message)
                        asyncio.create_task(self.background_task(json_message))
            except KeyboardInterrupt:
                break
            except (asyncio.exceptions.CancelledError, websockets.exceptions.ConnectionClosedError) as exc:
                self.logger.error("[start] network exception, error=%s", exc)
                await asyncio.sleep(10)
                continue
            except Exception as exc:
                await asyncio.sleep(3)
                self.logger.exception("unknown exception: %s", exc)
                continue


class DingtalkRuntime:
    """DingTalk Stream runtime 的最小实现。"""

    def __init__(self, config: DingtalkConfig):
        self._config = config
        self._message_handler: DingtalkMessageHandler | None = None
        self._client: Any | None = None
        self._sdk: Any | None = None
        self._client_task: asyncio.Task | None = None
        self._status: dict[str, str] = {"status": "idle"}
        self._sensenova_claw_status: dict[str, str] = {"status": "initialized", "error": ""}

    def set_message_handler(self, handler: DingtalkMessageHandler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        if not self._config.client_id or not self._config.client_secret:
            self._status = {"status": "failed", "error": "missing client credentials"}
            self._sensenova_claw_status = {"status": "failed", "error": "missing client credentials"}
            raise RuntimeError("DingTalk client_id/client_secret is required")

        try:
            sdk = importlib.import_module("dingtalk_stream")
        except ImportError as exc:
            self._status = {"status": "failed", "error": "dingtalk-stream not installed"}
            self._sensenova_claw_status = {"status": "failed", "error": "dingtalk-stream not installed"}
            raise ImportError("dingtalk-stream is required for DingtalkRuntime") from exc

        self._sdk = sdk
        credential = sdk.Credential(self._config.client_id, self._config.client_secret)
        self._client = _CompatDingTalkStreamClient(sdk=sdk, credential=credential, logger_=logger)
        self._client.register_callback_handler(
            sdk.ChatbotMessage.TOPIC,
            _DingtalkChatbotHandler(runtime=self, sdk=sdk),
        )
        self._status = {"status": "connecting"}
        self._sensenova_claw_status = {"status": "connecting", "error": ""}
        await self._validate_credentials()
        self._client_task = asyncio.create_task(self._client.start())
        self._status = {"status": "connected"}
        self._sensenova_claw_status = {"status": "connected", "error": ""}

    async def stop(self) -> None:
        if self._client_task is not None and not self._client_task.done():
            self._client_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._client_task
        self._client_task = None
        self._status = {"status": "stopped"}
        self._sensenova_claw_status = {"status": "stopped", "error": ""}

    async def send_text(self, target: str, text: str) -> dict[str, Any]:
        if target.startswith("webhook:"):
            webhook_url = target.removeprefix("webhook:").strip()
            if not webhook_url:
                raise ValueError("DingTalk webhook target cannot be empty")
            headers = {
                "Content-Type": "application/json",
                "Accept": "*/*",
            }
            payload = json.dumps(
                {
                    "msgtype": "text",
                    "text": {"content": text},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            async with httpx.AsyncClient(timeout=20.0, verify=_SSL_CONTEXT) as client:
                response = await client.post(
                    webhook_url,
                    headers=headers,
                    data=payload,
                )
            response.raise_for_status()
            return {"success": True, "message_id": ""}

        if self._client is None:
            raise RuntimeError("DingTalk runtime is not started")

        access_token = self._client.get_access_token()
        if not access_token:
            raise RuntimeError("failed to get dingtalk access token")

        payload = {
            "robotCode": self._config.client_id,
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False, separators=(",", ":")),
        }
        if target.startswith("user:"):
            payload["userIds"] = target.removeprefix("user:")
        elif target.startswith("conversation:"):
            payload["openConversationId"] = target.removeprefix("conversation:")
        else:
            raise ValueError("DingTalk outbound target must start with 'user:', 'conversation:' or 'webhook:'")

        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        }
        async with httpx.AsyncClient(timeout=20.0, verify=_SSL_CONTEXT) as client:
            response = await client.post(
                f"{_DINGTALK_API_BASE}/v1.0/robot/oToMessages/batchSend",
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        message_id = (
            str(body.get("processQueryKey") or "").strip()
            or str(body.get("messageId") or "").strip()
            or str(body.get("taskId") or "").strip()
        )
        return {"success": True, "message_id": message_id}

    async def _dispatch_message(self, incoming_message: DingtalkInboundMessage) -> None:
        if self._message_handler is not None:
            await self._message_handler(incoming_message)

    async def _validate_credentials(self) -> None:
        """启动前主动验证凭证，避免 SDK 后台无限重试时前端误显示已连接。"""
        if self._client is None:
            raise RuntimeError("DingTalk runtime is not started")

        token = await asyncio.to_thread(self._client.get_access_token)
        if not token:
            self._status = {"status": "failed", "error": "invalid client_id or client_secret"}
            self._sensenova_claw_status = {"status": "failed", "error": "invalid client_id or client_secret"}
            raise RuntimeError("invalid client_id or client_secret")

        connection = await asyncio.to_thread(self._client.open_connection)
        if not connection:
            self._status = {"status": "failed", "error": "failed to open dingtalk stream connection"}
            self._sensenova_claw_status = {"status": "failed", "error": "failed to open dingtalk stream connection"}
            raise RuntimeError("failed to open dingtalk stream connection")

    def _normalize_message(self, raw_message: Any) -> DingtalkInboundMessage | None:
        message_type = str(getattr(raw_message, "message_type", "") or "").strip().lower()
        if message_type != "text":
            return None

        text_content = getattr(getattr(raw_message, "text", None), "content", "") or ""
        text = text_content.strip()
        if not text:
            return None

        conversation_type = "p2p" if str(getattr(raw_message, "conversation_type", "")) == "1" else "group"
        return DingtalkInboundMessage(
            text=text,
            conversation_id=str(getattr(raw_message, "conversation_id", "") or ""),
            conversation_type=conversation_type,
            sender_id=str(getattr(raw_message, "sender_id", "") or ""),
            sender_staff_id=str(getattr(raw_message, "sender_staff_id", "") or ""),
            sender_nick=str(getattr(raw_message, "sender_nick", "") or ""),
            message_id=str(getattr(raw_message, "message_id", "") or ""),
            session_webhook=str(getattr(raw_message, "session_webhook", "") or ""),
            conversation_title=str(getattr(raw_message, "conversation_title", "") or "") or None,
            mentioned_bot=bool(getattr(raw_message, "is_in_at_list", False)),
            robot_code=str(getattr(raw_message, "robot_code", "") or "") or None,
        )


class _DingtalkChatbotHandler:
    """将官方 SDK 回调桥接为仓库内部标准消息。"""

    def __init__(self, runtime: DingtalkRuntime, sdk: Any):
        self._runtime = runtime
        self._sdk = sdk
        self.dingtalk_client = None

    def pre_start(self) -> None:
        """兼容官方 SDK CallbackHandler 接口。"""
        return

    async def process(self, callback: Any):
        raw_message = self._sdk.ChatbotMessage.from_dict(callback.data)
        incoming_message = self._runtime._normalize_message(raw_message)
        if incoming_message is not None:
            await self._runtime._dispatch_message(incoming_message)
        return self._sdk.AckMessage.STATUS_OK, "OK"

    async def raw_process(self, callback: Any):
        code, message = await self.process(callback)
        ack_message = self._sdk.AckMessage()
        ack_message.code = code
        ack_message.headers.message_id = callback.headers.message_id
        ack_message.headers.content_type = "application/json"
        ack_message.data = {"response": message}
        return ack_message
