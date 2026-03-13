"""FeishuApiTool 单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.capabilities.tools.feishu_api_tool import FeishuApiTool
from agentos.capabilities.tools.base import ToolRiskLevel


@pytest.fixture
def mock_channel():
    """模拟飞书 Channel"""
    channel = MagicMock()
    channel._client = MagicMock()
    channel._client._token_manager.get_tenant_access_token.return_value = "test-token-abc"
    return channel


@pytest.fixture
def tool(mock_channel):
    """默认配置的 FeishuApiTool（仅允许 GET）"""
    return FeishuApiTool(feishu_channel=mock_channel)


@pytest.fixture
def tool_full(mock_channel):
    """允许多种方法和路径前缀的 FeishuApiTool"""
    return FeishuApiTool(
        feishu_channel=mock_channel,
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

    def test_default_allowed_methods(self, mock_channel):
        """默认仅允许 GET"""
        t = FeishuApiTool(feishu_channel=mock_channel)
        assert t._allowed_methods == {"GET"}

    def test_custom_allowed_methods(self, mock_channel):
        """自定义允许方法"""
        t = FeishuApiTool(feishu_channel=mock_channel, allowed_methods=["GET", "POST", "DELETE"])
        assert t._allowed_methods == {"GET", "POST", "DELETE"}

    def test_allowed_prefixes(self, mock_channel):
        """路径前缀配置"""
        t = FeishuApiTool(feishu_channel=mock_channel, allowed_path_prefixes=["/open-apis/"])
        assert t._allowed_prefixes == ["/open-apis/"]

    def test_empty_prefixes(self, mock_channel):
        """空路径前缀列表（不限制）"""
        t = FeishuApiTool(feishu_channel=mock_channel)
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

    async def test_path_in_prefixes(self, tool_full):
        """路径在白名单内（不应报路径错误）"""
        # 需要 mock httpx 请求
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"data": "ok"}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await tool_full.execute(method="GET", path="/open-apis/docx/v1/documents")

        assert "error" not in result
        assert result["status_code"] == 200

    async def test_client_not_initialized(self, mock_channel):
        """飞书客户端未初始化"""
        mock_channel._client = None
        t = FeishuApiTool(feishu_channel=mock_channel)
        result = await t.execute(method="GET", path="/test")
        assert "error" in result
        assert "not initialized" in result["error"]


class TestExecuteRequest:
    """HTTP 请求执行测试"""

    async def test_json_response(self, tool_full, mock_channel):
        """JSON 响应正常解析"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json; charset=utf-8"}
        mock_resp.json.return_value = {"code": 0, "data": {"id": "doc-123"}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await tool_full.execute(
                method="POST",
                path="/open-apis/docx/v1/documents",
                body={"title": "test"},
            )

        assert result["status_code"] == 200
        assert result["data"]["code"] == 0

    async def test_text_response(self, tool_full, mock_channel):
        """非 JSON 响应返回截断文本"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = "<html>hello</html>"

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await tool_full.execute(
                method="GET",
                path="/open-apis/docx/v1/documents",
            )

        assert result["status_code"] == 200
        assert result["data"] == "<html>hello</html>"

    async def test_request_with_params(self, tool):
        """传递 URL 查询参数"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"items": []}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            # tool 默认无路径限制（_allowed_prefixes 为空列表），仅允许 GET
            result = await tool.execute(
                method="GET",
                path="/open-apis/test",
                params={"page_size": 10},
            )

        # 验证 params 被正确传递
        call_kwargs = mock_client_instance.request.call_args
        assert call_kwargs[1]["params"] == {"page_size": 10}

    async def test_correct_url_construction(self, tool):
        """URL 拼接正确"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            await tool.execute(method="GET", path="/open-apis/drive/v1/files")

        call_args = mock_client_instance.request.call_args
        assert call_args[0][1] == "https://open.feishu.cn/open-apis/drive/v1/files"

    async def test_auth_header(self, tool, mock_channel):
        """Authorization 头正确设置"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            await tool.execute(method="GET", path="/open-apis/test")

        call_kwargs = mock_client_instance.request.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-token-abc"
