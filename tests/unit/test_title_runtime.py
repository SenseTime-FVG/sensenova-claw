from __future__ import annotations

from types import SimpleNamespace

import pytest

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.runtime.title_runtime import TitleRuntime
from sensenova_claw.platform.config.config import config


class _RepoStub:
    def __init__(self):
        self.updated: list[tuple[str, str]] = []
        self._meta: dict[str, dict] = {}

    async def update_session_title(self, session_id: str, title: str) -> None:
        self.updated.append((session_id, title))

    async def get_session_meta(self, session_id: str) -> dict:
        return self._meta.get(session_id, {})


class _ProviderStub:
    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        return {"content": "千问标题", "tool_calls": [], "usage": {}, "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_title_runtime_uses_session_agent_model(monkeypatch):
    """标题生成应跟随当前 session 绑定的 agent 模型，而不是全局默认模型。"""
    old_llm = config.data.get("llm")
    config.data["llm"] = {
        "default_model": "mock",
        "models": {
            "mock": {"provider": "mock", "model_id": "mock-agent-v1"},
            "qwen-plus": {"provider": "qwen", "model_id": "qwen3.5-plus"},
        },
        "providers": old_llm.get("providers", {}) if isinstance(old_llm, dict) else {},
    }

    repo = _RepoStub()
    repo._meta["sess_qwen"] = {"agent_id": "qwen35"}
    agent_registry = AgentRegistry()
    agent_registry.register(
        AgentConfig.create(
            id="qwen35",
            name="Qwen Agent",
            model="qwen-plus",
        )
    )

    provider = _ProviderStub()
    runtime = TitleRuntime(bus=PublicEventBus(), repo=repo, agent_registry=agent_registry)
    runtime.llm_factory = SimpleNamespace(get_provider=lambda provider_name=None: provider)

    try:
        await runtime._generate_title("sess_qwen", "你好")
    finally:
        config.data["llm"] = old_llm

    assert repo.updated == [("sess_qwen", "千问标题")]
    assert provider.calls
    assert provider.calls[0]["model"] == "qwen3.5-plus"
