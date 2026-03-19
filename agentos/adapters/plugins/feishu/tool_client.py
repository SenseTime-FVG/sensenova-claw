"""飞书工具请求辅助：封装 tenant_access_token、JSON 请求和文件上传。"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx


class FeishuToolError(RuntimeError):
    """飞书工具调用错误。"""


class FeishuToolClient:
    """基于已初始化的飞书 Channel client 发起 API 调用。"""

    def __init__(self, feishu_channel: Any):
        self._channel = feishu_channel

    async def _get_token(self) -> str:
        client = self._channel._client
        if not client:
            raise FeishuToolError("Feishu client not initialized")
        return await asyncio.to_thread(
            lambda: client._token_manager.get_tenant_access_token()
        )

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(
                method=method,
                url=f"https://open.feishu.cn{path}",
                headers=headers,
                params=params,
                json=body,
            )
        return self._parse_json_response(response)

    async def request_multipart(
        self,
        path: str,
        *,
        data: dict[str, Any],
        file_bytes: bytes,
        file_name: str,
        file_field: str = "file",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
        }
        mime = content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        files = {
            file_field: (file_name, file_bytes, mime),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"https://open.feishu.cn{path}",
                headers=headers,
                data={k: self._encode_form_value(v) for k, v in data.items() if v is not None},
                files=files,
            )
        return self._parse_json_response(response)

    async def download(self, url: str, *, max_bytes: int = 30 * 1024 * 1024) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        content = response.content
        if len(content) > max_bytes:
            raise FeishuToolError(f"File too large: {len(content)} bytes > {max_bytes} bytes")
        filename = url.rstrip("/").split("/")[-1] or "download.bin"
        return content, filename

    @staticmethod
    def read_local_file(file_path: str, *, max_bytes: int = 30 * 1024 * 1024) -> tuple[bytes, str]:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FeishuToolError(f"File not found: {path}")
        content = path.read_bytes()
        if len(content) > max_bytes:
            raise FeishuToolError(f"File too large: {len(content)} bytes > {max_bytes} bytes")
        return content, path.name

    @staticmethod
    def _encode_form_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _parse_json_response(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        data = response.json()
        if data.get("code") not in (None, 0):
            raise FeishuToolError(data.get("msg") or f"Feishu API error: {data.get('code')}")
        return data
