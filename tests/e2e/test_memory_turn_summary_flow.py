from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import pytest

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.capabilities.memory.config import MemoryConfig
from sensenova_claw.capabilities.memory.manager import MemoryManager
from sensenova_claw.kernel.events.types import AGENT_STEP_COMPLETED
from sensenova_claw.platform.config.config import config
from tests.e2e.run_e2e import run_single_turn, setup_services, teardown_services


@pytest.mark.asyncio
async def test_completed_turn_appends_summary_to_memory_file(tmp_path: Path) -> None:
    """完整 turn 结束后，应异步写入摘要记忆文件。"""
    original_config = copy.deepcopy(config.data)
    config.data["system"]["sensenova_claw_home"] = str(tmp_path / ".sensenova-claw")
    svc = await setup_services(tmp_path, provider="mock", model=None)

    try:
        workspace = tmp_path / "workspace"
        memory_manager = MemoryManager(
            workspace_dir=str(workspace),
            config=MemoryConfig(enabled=True),
            db_path=tmp_path / "memory_index.db",
            llm_factory=LLMFactory(),
        )
        svc["agent_runtime"].memory_manager = memory_manager

        events, _elapsed = await run_single_turn(
            svc,
            "请记住我偏好 Python，并在后续回答里沿用这个偏好。",
            timeout=10,
        )

        memory_path = workspace / "MEMORY.md"
        for _ in range(20):
            if memory_path.exists():
                break
            await asyncio.sleep(0.05)
    finally:
        await teardown_services(svc)
        config.data = original_config

    event_types = [event.type for event in events]
    assert AGENT_STEP_COMPLETED in event_types

    assert memory_path.exists()
    content = memory_path.read_text(encoding="utf-8")
    assert "请总结以下对话" in content
    assert "请记住我偏好 Python" in content
