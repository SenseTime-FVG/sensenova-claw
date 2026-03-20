"""飞书 Channel 实现：通过 WebSocket 长连接接收飞书消息，回复到飞书对话"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from agentos.adapters.channels.base import Channel
from agentos.adapters.plugins.feishu.text import chunk_text

if TYPE_CHECKING:
    from agentos.adapters.plugins.base import PluginApi
    from agentos.adapters.plugins.feishu.config import FeishuConfig

logger = logging.getLogger(__name__)


@dataclass
class FeishuSessionMeta:
    """飞书会话元数据，用于出站回复时查找 chat_id"""

    chat_id: str
    chat_type: str  # "p2p" | "group"
    last_message_id: str
    sender_id: str


@dataclass
class FeishuPendingQuestion:
    """飞书会话中的待回答 ask_user 问题。"""

    question_id: str
    question: str


class FeishuChannel(Channel):
    """
    飞书 Channel，基于 lark-oapi SDK 的 WebSocket 长连接模式。

    线程模型:
    - _handle_message_event: SDK 后台线程
    - _on_message_async / send_event: asyncio 线程
    - _chat_sessions / _session_meta: threading.Lock 保护
    """

    def __init__(self, config: FeishuConfig, plugin_api: PluginApi):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._client: lark.Client | None = None
        self._ws_client: lark.ws.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._agentos_status = {"status": "initialized", "error": None}

        # 正向: session_key("dm:<id>" / "group:<id>") → session_id
        self._chat_sessions: dict[str, str] = {}
        # 反向: session_id → FeishuSessionMeta（O(1) 查找 chat_id）
        self._session_meta: dict[str, FeishuSessionMeta] = {}
        self._pending_questions: dict[str, FeishuPendingQuestion] = {}
        self._lock = threading.Lock()

    def get_channel_id(self) -> str:
        return "feishu"

    def event_filter(self) -> set[str] | None:
        """此 Channel 关心的事件类型集合"""
        types = {AGENT_STEP_COMPLETED, ERROR_RAISED, CRON_DELIVERY_REQUESTED, USER_QUESTION_ASKED}
        if self._config.show_tool_progress:
            types.add(TOOL_CALL_STARTED)
        return types

    async def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._agentos_status = {"status": "connecting", "error": None}

        self._client = (
            lark.Client.builder()
            .app_id(self._config.app_id)
            .app_secret(self._config.app_secret)
            .log_level(
                lark.LogLevel.DEBUG
                if self._config.log_level == "DEBUG"
                else lark.LogLevel.INFO
            )
            .build()
        )

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self._config.app_id,
            self._config.app_secret,
            event_handler=event_handler,
            log_level=(
                lark.LogLevel.DEBUG
                if self._config.log_level == "DEBUG"
                else lark.LogLevel.INFO
            ),
        )

        # SDK 的 start() 内部调用 run_until_complete()，不能在已有 event loop 的线程池中运行。
        # 必须用独立线程 + 独立 event loop，避免与 uvicorn 主循环冲突。
        thread = threading.Thread(
            target=self._run_ws_in_thread, daemon=True, name="feishu-ws"
        )
        thread.start()
        self._agentos_status = {"status": "connected", "error": None}
        logger.info("FeishuChannel started (WebSocket mode)")

    def _run_ws_in_thread(self) -> None:
        """在独立线程中为 lark SDK 创建专用 event loop 并启动 WebSocket。

        lark_oapi SDK 在模块导入时将 asyncio event loop 缓存到模块级变量 `loop`，
        在 uvicorn 环境下该变量指向已在运行的主循环，导致 run_until_complete() 抛
        RuntimeError。这里需要将 SDK 的模块级 loop 替换为线程本地新建的循环。
        """
        thread_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(thread_loop)

        import lark_oapi.ws.client as _ws_mod
        _ws_mod.loop = thread_loop

        try:
            self._ws_client.start()
        except Exception as exc:
            self._agentos_status = {"status": "failed", "error": str(exc)}
            logger.exception("Feishu WebSocket thread crashed")
        finally:
            thread_loop.close()

    async def stop(self) -> None:
        self._agentos_status = {"status": "stopped", "error": None}
        logger.info("FeishuChannel stopped")

    # ---- 消息构建 ----

    def _build_content(self, text: str) -> tuple[str, str]:
        """根据 render_mode 构建消息内容，返回 (content_json, msg_type)"""
        if self._config.render_mode == "card":
            from agentos.adapters.plugins.feishu.card import build_markdown_card
            return build_markdown_card(text), "interactive"
        return json.dumps({"text": text}), "text"

    def _build_message_request(
        self, receive_id: str, receive_id_type: str, content: str, msg_type: str,
    ) -> CreateMessageRequest:
        """构建飞书消息发送请求"""
        return (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )

    # ---- 入站: 飞书 → AgentOS ----

    def _handle_message_event(self, data) -> None:
        """SDK 线程回调（P2ImMessageReceiveV1），跨线程调度到 asyncio"""
        try:
            msg = data.event.message
            sender = data.event.sender
            chat_id = msg.chat_id
            chat_type = msg.chat_type
            message_id = msg.message_id
            sender_id = sender.sender_id.open_id

            text = self._extract_text(msg.message_type, msg.content, chat_type, msg)
            if text is None:
                return
            if not self._should_respond(chat_type, sender_id, msg):
                return

            logger.info(
                "Feishu message: chat=%s sender=%s text=%s",
                chat_id,
                sender_id,
                text[:100],
            )

            if not self._loop or self._loop.is_closed():
                logger.warning("Feishu event loop unavailable, drop inbound message: chat=%s", chat_id)
                return

            future = asyncio.run_coroutine_threadsafe(
                self._on_message_async(
                    text, chat_id, chat_type, message_id, sender_id
                ),
                self._loop,
            )
            future.add_done_callback(self._log_inbound_dispatch_result)
        except Exception:
            logger.exception("Failed to handle Feishu message event")

    @staticmethod
    def _log_inbound_dispatch_result(
        future: concurrent.futures.Future[None],
    ) -> None:
        """记录跨线程投递后的异步异常，避免静默吞掉入站消息处理失败。"""
        try:
            future.result()
        except concurrent.futures.CancelledError:
            logger.warning("Feishu inbound dispatch cancelled")
        except Exception:
            logger.exception("Feishu inbound dispatch failed")

    async def _on_message_async(
        self, text: str, chat_id: str, chat_type: str, message_id: str, sender_id: str
    ) -> None:
        """asyncio 线程：session 管理 → bind → 发布事件"""
        session_key = (
            f"dm:{sender_id}" if chat_type == "p2p" else f"group:{chat_id}"
        )

        with self._lock:
            session_id = self._chat_sessions.get(session_key)
            if not session_id:
                session_id = f"feishu_{uuid.uuid4().hex[:12]}"
                self._chat_sessions[session_key] = session_id
            self._session_meta[session_id] = FeishuSessionMeta(
                chat_id=chat_id,
                chat_type=chat_type,
                last_message_id=message_id,
                sender_id=sender_id,
            )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "feishu")

        pending_question = self._pending_questions.pop(session_id, None)
        if pending_question is not None:
            await gateway.publish_from_channel(
                EventEnvelope(
                    type=USER_QUESTION_ANSWERED,
                    session_id=session_id,
                    turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                    source="feishu",
                    payload={
                        "question_id": pending_question.question_id,
                        "answer": text,
                        "cancelled": False,
                    },
                )
            )
            return

        await gateway.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                source="feishu",
                payload={
                    "content": text,
                    "attachments": [],
                    "context_files": [],
                },
            )
        )

    def _extract_text(
        self, msg_type: str, content_str: str, chat_type: str, msg
    ) -> str | None:
        """从飞书消息中提取文本内容"""
        if msg_type == "text":
            content = json.loads(content_str)
            text = content.get("text", "").strip()
            # 群聊中去除 @bot 的 mention 标记
            if chat_type == "group" and msg.mentions:
                for mention in msg.mentions:
                    text = text.replace(mention.key, "").strip()
            return text if text else None
        if msg_type == "image":
            return "[用户发送了一张图片]"
        if msg_type == "file":
            content = json.loads(content_str)
            return f"[用户发送了文件: {content.get('file_name', 'unknown')}]"
        logger.debug("Unsupported Feishu message type: %s", msg_type)
        return None

    def _should_respond(self, chat_type: str, sender_id: str, msg) -> bool:
        """判断是否应该响应该消息"""
        if chat_type == "p2p":
            if self._config.dm_policy == "allowlist":
                return sender_id in self._config.allowlist
            return True
        if chat_type == "group":
            if self._config.group_policy == "disabled":
                return False
            if self._config.group_policy == "mention":
                return bool(msg.mentions)
            return True
        return False

    # ---- 出站: AgentOS → 飞书 ----

    async def send_event(self, event: EventEnvelope) -> None:
        """接收 Gateway 分发的事件，发送到飞书"""
        if event.type == AGENT_STEP_COMPLETED:
            text = event.payload.get("result", {}).get(
                "content", ""
            ) or event.payload.get("final_response", "")
            if text:
                await self._send_reply(event.session_id, text)
        elif event.type == CRON_DELIVERY_REQUESTED:
            text = event.payload.get("text", "")
            if text:
                to = event.payload.get("to")
                await self._deliver_cron_text(text, to)
        elif event.type == ERROR_RAISED:
            error_msg = event.payload.get("error_message", "处理失败")
            await self._send_reply(event.session_id, f"⚠️ 错误: {error_msg}")
        elif event.type == USER_QUESTION_ASKED:
            question = event.payload.get("question", "")
            if question:
                self._pending_questions[event.session_id] = FeishuPendingQuestion(
                    question_id=str(event.payload.get("question_id", "")).strip(),
                    question=question,
                )
                await self._send_reply(event.session_id, question)
        elif event.type == TOOL_CALL_STARTED:
            tool_name = event.payload.get("tool_name", "")
            if tool_name:
                await self._send_reply(event.session_id, f"⏳ 正在执行 {tool_name}...")

    async def _deliver_cron_text(self, text: str, to: str | None = None) -> None:
        """投递 cron 文本：指定 to 则发到该目标，否则广播到所有已知 sessions"""
        if to:
            await self.send_outbound(target=to, text=text)
            return
        with self._lock:
            session_ids = list(self._session_meta.keys())
        if not session_ids:
            logger.warning("Cron delivery: no active feishu sessions to deliver to")
            return
        for sid in session_ids:
            await self._send_reply(sid, text)

    async def _send_reply(self, session_id: str, text: str) -> None:
        """通过飞书消息 API 发送回复（支持分片）"""
        if not self._client:
            return

        with self._lock:
            meta = self._session_meta.get(session_id)
        if not meta:
            logger.warning("No feishu meta for session %s", session_id)
            return

        # 截断过长消息
        if len(text) > 20000:
            text = text[:20000] + "\n\n... (内容过长，已截断)"

        try:
            for chunk in chunk_text(text, limit=4000):
                content, msg_type = self._build_content(chunk)
                request = self._build_message_request(
                    meta.chat_id, "chat_id", content, msg_type,
                )
                response = await asyncio.to_thread(
                    self._client.im.v1.message.create, request
                )
                if not response.success():
                    logger.error(
                        "Feishu send failed: code=%s msg=%s",
                        response.code,
                        response.msg,
                    )
                    break
        except Exception:
            logger.exception("Failed to send Feishu message")

    # ---- 主动出站: send_outbound（满足 OutboundCapable 结构化类型） ----

    async def send_outbound(self, target: str, text: str, msg_type: str = "card") -> dict:
        """向指定目标发送消息。返回 {success, message_id, ...}"""
        if not self._client:
            return {"success": False, "error": "Client not initialized"}

        if target.startswith("user:"):
            receive_id, receive_id_type = target[5:], "open_id"
        else:
            receive_id, receive_id_type = target, "chat_id"

        last_result: dict = {}
        for chunk in chunk_text(text, limit=4000):
            content, actual_msg_type = self._build_content(chunk)
            request = self._build_message_request(
                receive_id, receive_id_type, content, actual_msg_type,
            )
            response = await asyncio.to_thread(
                self._client.im.v1.message.create, request,
            )
            if not response.success():
                return {"success": False, "code": response.code, "msg": response.msg}
            last_result = {"success": True, "message_id": response.data.message_id}

        return last_result
