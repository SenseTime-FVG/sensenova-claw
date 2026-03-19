"""WhatsApp sidecar bridge client 单元测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agentos.adapters.plugins.whatsapp.bridge_client import SidecarBridgeClient
from agentos.adapters.plugins.whatsapp.models import WhatsAppInboundMessage


def _write_fake_sidecar(path: Path) -> None:
    path.write_text(
        """
import asyncio
import json
import os
import sys


async def main():
    async def emit(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n")
        sys.stdout.flush()

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        command = json.loads(line)
        if command["type"] == "start":
            if os.environ.get("FAKE_SIDECAR_MODE") == "timeout":
                continue
            await emit({"type": "response", "id": command["id"], "payload": {"success": True}})
            await emit({"type": "qr", "payload": {"text": "qr-text", "ascii": "##"}})
            await emit(
                {
                    "type": "message",
                    "payload": {
                        "text": "hello from sidecar",
                        "chat_jid": "15550000001@s.whatsapp.net",
                        "chat_type": "p2p",
                        "sender_jid": "15550000001@s.whatsapp.net",
                        "message_id": "wamid-sidecar-1",
                    },
                }
            )
            await emit(
                {
                    "type": "status",
                    "payload": {"state": "ready", "connected": True, "phone": "+15550000001"},
                }
            )
        elif command["type"] == "send_text":
            await emit({"type": "response", "id": command["id"], "payload": {"success": True, "echo": command["payload"]}})
        elif command["type"] == "status":
            await emit({"type": "response", "id": command["id"], "payload": {"success": True, "state": "ready"}})
        elif command["type"] == "logout":
            await emit({"type": "response", "id": command["id"], "payload": {"success": True}})
        elif command["type"] == "stop":
            await emit({"type": "response", "id": command["id"], "payload": {"success": True}})
            return


asyncio.run(main())
""".strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_client_reads_qr_and_message_events(tmp_path: Path) -> None:
    events: list[dict] = []
    messages: list[WhatsAppInboundMessage] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    async def on_message(message: WhatsAppInboundMessage) -> None:
        messages.append(message)

    sidecar = tmp_path / "fake_sidecar.py"
    _write_fake_sidecar(sidecar)

    client = SidecarBridgeClient(
        command="python3",
        entry=str(sidecar),
        auth_dir=str(tmp_path / "auth"),
        startup_timeout_seconds=2,
        send_timeout_seconds=2,
    )
    client.set_event_handler(on_event)
    client.set_message_handler(on_message)

    await client.start()
    await asyncio.sleep(0.2)
    await client.stop()

    assert any(event["type"] == "qr" for event in events)
    assert any(event["type"] == "status" for event in events)
    assert messages
    assert messages[0].text == "hello from sidecar"


@pytest.mark.asyncio
async def test_send_text_waits_for_response(tmp_path: Path) -> None:
    sidecar = tmp_path / "fake_sidecar.py"
    _write_fake_sidecar(sidecar)

    client = SidecarBridgeClient(
        command="python3",
        entry=str(sidecar),
        auth_dir=str(tmp_path / "auth"),
        startup_timeout_seconds=2,
        send_timeout_seconds=2,
    )

    await client.start()
    result = await client.send_text("15550000001@s.whatsapp.net", "hello")
    status = await client.get_status()
    await client.stop()

    assert result["success"] is True
    assert result["echo"]["target"] == "15550000001@s.whatsapp.net"
    assert status["state"] == "ready"


@pytest.mark.asyncio
async def test_start_times_out_when_sidecar_does_not_respond(tmp_path: Path) -> None:
    sidecar = tmp_path / "fake_sidecar.py"
    _write_fake_sidecar(sidecar)

    client = SidecarBridgeClient(
        command="python3",
        entry=str(sidecar),
        auth_dir=str(tmp_path / "auth"),
        startup_timeout_seconds=0.2,
        send_timeout_seconds=0.2,
        env={"FAKE_SIDECAR_MODE": "timeout"},
    )

    with pytest.raises(TimeoutError):
        await client.start()

    await client.stop()
