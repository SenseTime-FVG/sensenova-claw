"""飞书工具客户端单元测试。"""

from __future__ import annotations

import pytest

from agentos.adapters.plugins.feishu.tool_client import FeishuToolClient


class _FakeChannel:
    def __init__(self, client):
        self._client = client


class _FakeConfig:
    app_id = "cli_app_id"
    app_secret = "cli_app_secret"


class _FakeClientWithoutTokenManager:
    def __init__(self):
        self._config = _FakeConfig()


@pytest.mark.asyncio
async def test_get_token_uses_sdk_config_when_client_has_no_token_manager(monkeypatch: pytest.MonkeyPatch):
    observed: dict[str, str] = {}

    def _fake_get_self_tenant_token(config):
        observed["app_id"] = config.app_id
        observed["app_secret"] = config.app_secret
        return "tenant_token_from_config"

    monkeypatch.setattr(
        "agentos.adapters.plugins.feishu.tool_client.TokenManager.get_self_tenant_token",
        _fake_get_self_tenant_token,
    )

    tool_client = FeishuToolClient(_FakeChannel(_FakeClientWithoutTokenManager()))

    token = await tool_client._get_token()

    assert token == "tenant_token_from_config"
    assert observed == {
        "app_id": "cli_app_id",
        "app_secret": "cli_app_secret",
    }
