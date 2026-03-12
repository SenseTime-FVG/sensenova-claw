"""FeishuApiTool：调用飞书开放平台 API（安全白名单限制）"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolRiskLevel


class FeishuApiTool(Tool):
    name = "feishu_api"
    description = (
        "调用飞书开放平台 API。"
        "method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)。"
        "path: API 路径 (如 /open-apis/docx/v1/documents)。"
        "body: 请求体 (JSON 对象)。params: URL 查询参数。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
            "path": {"type": "string", "description": "飞书 API 路径"},
            "body": {"type": "object", "description": "请求体"},
            "params": {"type": "object", "description": "URL 查询参数"},
        },
        "required": ["method", "path"],
    }
    risk_level = ToolRiskLevel.HIGH

    def __init__(
        self,
        feishu_channel: Any,
        allowed_methods: list[str] | None = None,
        allowed_path_prefixes: list[str] | None = None,
    ):
        self._channel = feishu_channel
        self._allowed_methods = set(allowed_methods or ["GET"])
        self._allowed_prefixes = allowed_path_prefixes or []

    async def execute(self, **kwargs: Any) -> Any:
        import asyncio

        import httpx

        method = kwargs.get("method", "GET")
        path = kwargs.get("path", "")

        if method not in self._allowed_methods:
            return {"error": f"Method {method} not allowed"}
        if self._allowed_prefixes and not any(path.startswith(p) for p in self._allowed_prefixes):
            return {"error": f"Path {path} not in allowed prefixes"}

        client = self._channel._client
        if not client:
            return {"error": "Feishu client not initialized"}

        token = await asyncio.to_thread(
            lambda: client._token_manager.get_tenant_access_token()
        )
        url = f"https://open.feishu.cn{path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers,
                json=kwargs.get("body"), params=kwargs.get("params"),
            )
        return {
            "status_code": resp.status_code,
            "data": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text[:5000],
        }
