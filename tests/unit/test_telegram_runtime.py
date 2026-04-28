"""Telegram runtime 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

telegram_mod = pytest.importorskip("telegram", reason="python-telegram-bot not installed")
from telegram import Update
from telegram.error import Conflict
from unittest.mock import AsyncMock, patch

from sensenova_claw.adapters.plugins.telegram.config import TelegramConfig
from sensenova_claw.adapters.plugins.telegram.runtime import TelegramRuntime, _SSL_CONTEXT


class TestPolling:
    def test_runtime_builds_bot_with_certifi_requests(self):
        request_kwargs: list[dict] = []
        get_updates_request_kwargs: list[dict] = []

        def _fake_httpx_request(**kwargs):
            if not request_kwargs:
                request_kwargs.append(kwargs)
                return "request"
            get_updates_request_kwargs.append(kwargs)
            return "get_updates_request"

        with (
            patch("sensenova_claw.adapters.plugins.telegram.runtime.HTTPXRequest", side_effect=_fake_httpx_request),
            patch("sensenova_claw.adapters.plugins.telegram.runtime.Bot") as bot_cls,
        ):
            TelegramRuntime(
                config=TelegramConfig(enabled=True, bot_token="123:abc", polling_timeout_seconds=1),
            )

        bot_cls.assert_called_once_with(
            token="123:abc",
            request="request",
            get_updates_request="get_updates_request",
        )
        assert request_kwargs[0]["httpx_kwargs"]["verify"] is _SSL_CONTEXT
        assert get_updates_request_kwargs[0]["httpx_kwargs"]["verify"] is _SSL_CONTEXT

    @pytest.mark.asyncio
    async def test_handle_update_dispatches_text_message(self):
        dispatched: list[dict] = []
        runtime = TelegramRuntime(
            config=TelegramConfig(enabled=True, bot_token="123:abc", polling_timeout_seconds=1),
        )
        async def collect(message):
            dispatched.append(message)

        runtime.set_message_handler(collect)
        runtime.set_bot_username("sensenova_claw_bot")

        update = Update.de_json(
            {
                "update_id": 100,
                "message": {
                    "message_id": 10,
                    "text": "@sensenova_claw_bot hi",
                    "chat": {"id": -100123, "type": "supergroup"},
                    "from": {
                        "id": 1001,
                        "username": "alice",
                        "is_bot": False,
                        "first_name": "Alice",
                    },
                    "entities": [
                        {"type": "mention", "offset": 0, "length": 19}
                    ],
                    "message_thread_id": 777,
                    "date": 1710000000,
                },
            },
            runtime._bot,
        )

        await runtime.handle_update(update)

        assert dispatched
        assert dispatched[0].text == "@sensenova_claw_bot hi"
        assert dispatched[0].chat_id == "-100123"
        assert dispatched[0].message_thread_id == 777
        assert dispatched[0].mentioned_bot is True

    @pytest.mark.asyncio
    async def test_poll_loop_stops_on_conflict(self):
        runtime = TelegramRuntime(
            config=TelegramConfig(enabled=True, bot_token="123:abc", polling_timeout_seconds=1),
        )

        with (
            patch.object(
                type(runtime._bot),
                "get_updates",
                AsyncMock(
                    side_effect=[
                        Conflict("terminated by other getUpdates request"),
                        asyncio.CancelledError(),
                    ]
                ),
            ),
            patch("sensenova_claw.adapters.plugins.telegram.runtime.asyncio.sleep", AsyncMock()) as sleep_mock,
        ):
            await runtime._poll_loop()

        assert runtime._sensenova_claw_status["status"] == "failed"
        assert "other getUpdates request" in runtime._sensenova_claw_status["error"]
        sleep_mock.assert_not_awaited()


class TestSendText:
    @pytest.mark.asyncio
    async def test_send_text_passes_reply_and_thread_params(self):
        runtime = TelegramRuntime(
            config=TelegramConfig(enabled=True, bot_token="123:abc"),
        )
        calls: list[dict] = []

        async def fake_send_message(**kwargs):
            calls.append(kwargs)
            return type("FakeMessage", (), {"message_id": 88})()

        with patch.object(type(runtime._bot), "send_message", AsyncMock(side_effect=fake_send_message)):
            result = await runtime.send_text(
                "-100123",
                "hello world",
                reply_to_message_id=10,
                message_thread_id=777,
            )

        assert result["success"] is True
        assert result["message_id"] == "88"
        assert calls[0]["chat_id"] == "-100123"
        assert calls[0]["text"] == "hello world"
        assert calls[0]["reply_to_message_id"] == 10
        assert calls[0]["message_thread_id"] == 777


class TestWebhook:
    @pytest.mark.asyncio
    async def test_handle_update_ignores_non_text_message(self):
        dispatched: list[dict] = []
        runtime = TelegramRuntime(config=TelegramConfig(enabled=True, bot_token="123:abc"))
        async def collect(message):
            dispatched.append(message)

        runtime.set_message_handler(collect)
        runtime.set_bot_username("sensenova_claw_bot")

        update = Update.de_json(
            {
                "update_id": 100,
                "message": {
                    "message_id": 10,
                    "chat": {"id": 1001, "type": "private"},
                    "from": {
                        "id": 1001,
                        "username": "alice",
                        "is_bot": False,
                        "first_name": "Alice",
                    },
                    "photo": [
                        {
                            "file_id": "abc",
                            "file_unique_id": "uq-1",
                            "width": 10,
                            "height": 10,
                        }
                    ],
                    "date": 1710000000,
                },
            }
            ,
            runtime._bot,
        )
        await runtime.handle_update(update)

        assert dispatched == []
