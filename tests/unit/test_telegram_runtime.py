"""Telegram runtime 单元测试。"""

from __future__ import annotations

import pytest

telegram_mod = pytest.importorskip("telegram", reason="python-telegram-bot not installed")
from telegram import Update
from unittest.mock import AsyncMock, patch

from sensenova_claw.adapters.plugins.telegram.config import TelegramConfig
from sensenova_claw.adapters.plugins.telegram.runtime import TelegramRuntime


class TestPolling:
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
                        {"type": "mention", "offset": 0, "length": 12}
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
