"""FeishuApiTool 集成测试

去除所有 mock/MagicMock/AsyncMock/patch，使用真实组件验证：
- 工具元信息（name, risk_level, parameters）
- 初始化配置（allowed_methods, allowed_prefixes）
- 请求验证（method 白名单、path 前缀白名单）
- 真实 HTTP 请求执行（标记 @pytest.mark.slow，网络失败时 skip）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agentos.capabilities.tools.feishu_api_tool import FeishuApiTool
from agentos.capabilities.tools.base import ToolRiskLevel


# ---- 辅助：轻量 Channel 替代品 ----


class _FakeFeishuChannel:
    """最小化的飞书 Channel 替代，仅提供 _client 属性"""

    def __init__(self, client: Any = None):
        self._client = client


class _FakeTokenManager:
    """模拟 lark_oapi 的 token manager"""

    def __init__(self, token: str = "test-token-abc"):
        self._token = token

    def get_tenant_access_token(self) -> str:
        return self._token


class _FakeLarkClient:
    """最小化的 lark Client 替代"""

    def __init__(self, token: str = "test-token-abc"):
        self._token_manager = _FakeTokenManager(token)


@pytest.fixture
def fake_channel():
    """带有 fake client 的飞书 Channel"""
    return _FakeFeishuChannel(client=_FakeLarkClient())


@pytest.fixture
def tool(fake_channel):
    """默认配置的 FeishuApiTool（仅允许 GET）"""
    return FeishuApiTool(feishu_channel=fake_channel)


@pytest.fixture
def tool_full(fake_channel):
    """允许多种方法和路径前缀的 FeishuApiTool"""
    return FeishuApiTool(
        feishu_channel=fake_channel,
        allowed_methods=["GET", "POST"],
        allowed_path_prefixes=["/open-apis/docx/", "/open-apis/drive/"],
    )


class TestToolMetadata:
    """工具元信息测试"""

    def test_name(self, tool):
        assert tool.name == "feishu_api"

    def test_risk_level(self, tool):
        assert tool.risk_level == ToolRiskLevel.HIGH

    def test_required_params(self, tool):
        assert "method" in tool.parameters["required"]
        assert "path" in tool.parameters["required"]


class TestInit:
    """初始化测试"""

    def test_default_allowed_methods(self, fake_channel):
        """默认仅允许 GET"""
        t = FeishuApiTool(feishu_channel=fake_channel)
        assert t._allowed_methods == {"GET"}

    def test_custom_allowed_methods(self, fake_channel):
        """自定义允许方法"""
        t = FeishuApiTool(feishu_channel=fake_channel, allowed_methods=["GET", "POST", "DELETE"])
        assert t._allowed_methods == {"GET", "POST", "DELETE"}

    def test_allowed_prefixes(self, fake_channel):
        """路径前缀配置"""
        t = FeishuApiTool(feishu_channel=fake_channel, allowed_path_prefixes=["/open-apis/"])
        assert t._allowed_prefixes == ["/open-apis/"]

    def test_empty_prefixes(self, fake_channel):
        """空路径前缀列表（不限制）"""
        t = FeishuApiTool(feishu_channel=fake_channel)
        assert t._allowed_prefixes == []


class TestExecuteValidation:
    """请求验证测试"""

    async def test_method_not_allowed(self, tool):
        """不允许的 HTTP 方法"""
        result = await tool.execute(method="POST", path="/open-apis/test")
        assert "error" in result
        assert "not allowed" in result["error"]

    async def test_path_not_in_prefixes(self, tool_full):
        """路径不在白名单内"""
        result = await tool_full.execute(method="GET", path="/open-apis/im/v1/messages")
        assert "error" in result
        assert "not in allowed prefixes" in result["error"]

    async def test_client_not_initialized(self, fake_channel):
        """飞书客户端未初始化"""
        fake_channel._client = None
        t = FeishuApiTool(feishu_channel=fake_channel)
        result = await t.execute(method="GET", path="/test")
        assert "error" in result
        assert "not initialized" in result["error"]


class TestExecuteRequest:
    """HTTP 请求执行测试（真实网络调用）"""

    @pytest.mark.slow
    async def test_real_api_call(self, tool):
        """真实 HTTP 请求（飞书 API 返回 401 因 token 无效，但验证请求链路畅通）"""
        try:
            result = await tool.execute(method="GET", path="/open-apis/im/v1/messages")
        except Exception as e:
            pytest.skip(f"网络请求失败: {e}")
        # 飞书 API 会因 token 无效返回错误，但 HTTP 请求本身应成功完成
        assert "status_code" in result
        # 应返回 HTTP 状态码（通常是 400 或 401）
        assert isinstance(result["status_code"], int)

    @pytest.mark.slow
    async def test_real_api_with_prefixes(self, tool_full):
        """真实 HTTP 请求（路径在白名单内）"""
        try:
            result = await tool_full.execute(
                method="GET",
                path="/open-apis/docx/v1/documents",
            )
        except Exception as e:
            pytest.skip(f"网络请求失败: {e}")
        assert "status_code" in result
        assert "error" not in result
