"""Discord runtime 单元测试。"""

from __future__ import annotations

import asyncio
import types

import pytest

from sensenova_claw.adapters.plugins.discord.config import DiscordConfig
from sensenova_claw.adapters.plugins.discord.runtime import DiscordRuntime, build_discord_intents, format_discord_runtime_error


class _FakeIntents:
    def __init__(self):
        self.message_content = False
        self.guilds = False
        self.messages = False
        self.members = False

    @classmethod
    def default(cls):
        return cls()


def test_build_discord_intents_does_not_request_members_privilege():
    intents = build_discord_intents(type("DiscordModule", (), {"Intents": _FakeIntents}))
    assert intents.message_content is True
    assert intents.guilds is True
    assert intents.messages is True
    assert intents.members is False


def test_format_discord_runtime_error_for_privileged_intents():
    class PrivilegedIntentsRequired(Exception):
        pass

    error = format_discord_runtime_error(
        PrivilegedIntentsRequired("Shard ID None is requesting privileged intents")
    )
    assert "Privileged Intents" in error
    assert "Message Content Intent" in error


def test_format_discord_runtime_error_falls_back_to_exception_text():
    error = format_discord_runtime_error(RuntimeError("gateway closed"))
    assert error == "gateway closed"


def test_runtime_initial_status_is_idle():
    runtime = DiscordRuntime(DiscordConfig(enabled=True, bot_token="token"))
    assert runtime._sensenova_claw_status["status"] == "idle"


@pytest.mark.asyncio
async def test_runtime_start_returns_after_launching_connect_task(monkeypatch):
    events: list[str] = []

    class _FakeClient:
        def __init__(self, *, intents):
            self.intents = intents
            self.user = types.SimpleNamespace(id="bot-1")
            self.close_called = False

        async def login(self, token: str) -> None:
            events.append(f"login:{token}")

        async def connect(self, *, reconnect: bool = True) -> None:
            events.append(f"connect:{reconnect}")
            await asyncio.sleep(60)

        async def close(self) -> None:
            self.close_called = True
            events.append("close")

    class _FakeDiscordModule:
        Intents = _FakeIntents
        Client = _FakeClient
        Thread = type("Thread", (), {})
        DMChannel = type("DMChannel", (), {})

    monkeypatch.setattr("sensenova_claw.adapters.plugins.discord.runtime.importlib.import_module", lambda _: _FakeDiscordModule)

    runtime = DiscordRuntime(DiscordConfig(enabled=True, bot_token="token"))
    await runtime.start()

    assert events == ["login:token"]
    assert runtime._sensenova_claw_status["status"] == "connecting"
    assert runtime._connect_task is not None
    assert runtime._connect_task.done() is False

    await runtime.stop()
    assert "close" in events


@pytest.mark.asyncio
async def test_send_text_converts_message_reference_to_partial_message():
    sent_calls: list[dict] = []

    class _FakeChannel:
        def get_partial_message(self, message_id: int):
            return {"partial_message_id": message_id}

        async def send(self, text: str, **kwargs):
            sent_calls.append({"text": text, "kwargs": kwargs})
            return types.SimpleNamespace(id=98765)

    class _FakeClient:
        def __init__(self):
            self.channel = _FakeChannel()

        def get_channel(self, channel_id: int):
            assert channel_id == 12345
            return self.channel

    runtime = DiscordRuntime(DiscordConfig(enabled=True, bot_token="token"))
    runtime._client = _FakeClient()

    result = await runtime.send_text("12345", "hello", message_reference="67890")

    assert result["message_id"] == "98765"
    assert sent_calls == [
        {
            "text": "hello",
            "kwargs": {"reference": {"partial_message_id": 67890}},
        }
    ]
