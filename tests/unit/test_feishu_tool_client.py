"""飞书工具客户端单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from sensenova_claw.adapters.plugins.feishu.tool_client import FeishuToolClient, _SSL_CONTEXT


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
        "sensenova_claw.adapters.plugins.feishu.tool_client.TokenManager.get_self_tenant_token",
        _fake_get_self_tenant_token,
    )

    tool_client = FeishuToolClient(_FakeChannel(_FakeClientWithoutTokenManager()))

    token = await tool_client._get_token()

    assert token == "tenant_token_from_config"
    assert observed == {
        "app_id": "cli_app_id",
        "app_secret": "cli_app_secret",
    }


@pytest.mark.asyncio
async def test_request_json_uses_ssl_context():
    response = Mock()
    response.json.return_value = {"code": 0, "data": {"ok": True}}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.request.return_value = response

    with patch("sensenova_claw.adapters.plugins.feishu.tool_client.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        tool_client = FeishuToolClient(_FakeChannel(_FakeClientWithoutTokenManager()))
        tool_client._get_token = AsyncMock(return_value="tenant_token")
        await tool_client.request_json("GET", "/open-apis/test")

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT


@pytest.mark.asyncio
async def test_request_multipart_uses_ssl_context():
    response = Mock()
    response.json.return_value = {"code": 0, "data": {"ok": True}}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.feishu.tool_client.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        tool_client = FeishuToolClient(_FakeChannel(_FakeClientWithoutTokenManager()))
        tool_client._get_token = AsyncMock(return_value="tenant_token")
        await tool_client.request_multipart(
            "/open-apis/file",
            data={"file_type": "stream"},
            file_bytes=b"abc",
            file_name="a.txt",
        )

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT


@pytest.mark.asyncio
async def test_download_uses_ssl_context():
    response = Mock()
    response.content = b"abc"
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response

    with patch("sensenova_claw.adapters.plugins.feishu.tool_client.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        tool_client = FeishuToolClient(_FakeChannel(_FakeClientWithoutTokenManager()))
        await tool_client.download("https://example.com/demo.txt")

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT
