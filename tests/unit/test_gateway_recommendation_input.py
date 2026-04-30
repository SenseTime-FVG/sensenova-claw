from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sensenova_claw.interfaces.ws.gateway import Gateway


@pytest.mark.asyncio
async def test_send_user_input_preserves_recommendation_meta():
    publisher = MagicMock()
    publisher.publish = AsyncMock()

    gateway = Gateway(publisher=publisher, repo=MagicMock())

    await gateway.send_user_input(
        session_id="sess_source_001",
        content="请继续分析三个最强竞争对手",
        source="websocket",
        meta={
            "recommendation_id": "rec_1",
            "recommendation_source_session_id": "sess_source_001",
        },
    )

    publisher.publish.assert_awaited_once()
    event = publisher.publish.await_args.args[0]
    assert event.payload["meta"]["recommendation_id"] == "rec_1"
    assert event.payload["meta"]["recommendation_source_session_id"] == "sess_source_001"


@pytest.mark.asyncio
async def test_send_user_input_preserves_attachments():
    publisher = MagicMock()
    publisher.publish = AsyncMock()

    gateway = Gateway(publisher=publisher, repo=MagicMock())

    attachments = [
        {
            "kind": "image",
            "name": "screenshot.png",
            "path": "/tmp/screenshot.png",
            "mime_type": "image/png",
        }
    ]

    await gateway.send_user_input(
        session_id="sess_img_001",
        content="帮我看看这张图",
        source="websocket",
        attachments=attachments,
    )

    publisher.publish.assert_awaited_once()
    event = publisher.publish.await_args.args[0]
    assert event.payload["attachments"] == attachments
