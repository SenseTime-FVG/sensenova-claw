"""CLI ask_user 提示交互测试"""

from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.app.cli.app import CLIApp


@pytest.mark.asyncio
async def test_prompt_question_multi_select_single_index_returns_list(monkeypatch: pytest.MonkeyPatch):
    app = CLIApp(host="localhost", port=8000)
    data = {
        "payload": {
            "question": "请选择功能",
            "options": ["A", "B", "C"],
            "multi_select": True,
        }
    }

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr("builtins.input", lambda _: "1")

    answer, cancelled = await app._prompt_question(data)

    assert answer == ["A"]
    assert cancelled is False
