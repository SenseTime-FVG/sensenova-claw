"""AnthropicAdapter 单元测试"""
import io
import zipfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import httpx

from agentos.adapters.skill_sources.anthropic_market import AnthropicAdapter


def _make_response(status_code=200, json_data=None, content=b"", headers=None):
    """构造 mock httpx.Response"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.headers = httpx.Headers(headers or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _mock_client(response):
    """创建一个 mock AsyncClient，所有 HTTP 方法返回同一响应"""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestAnthropicAdapterProperties:
    def test_supports_browse(self):
        assert AnthropicAdapter().supports_browse is True

    def test_supports_search(self):
        assert AnthropicAdapter().supports_search is True

    def test_自定义api_base尾部斜杠被去除(self):
        adapter = AnthropicAdapter(api_base="https://example.com/api/")
        assert adapter._api_base == "https://example.com/api"


class TestAnthropicSearch:
    async def test_search_正常解析(self):
        mock_json = {
            "plugins": [
                {
                    "id": "p1",
                    "name": "Plugin One",
                    "description": "desc1",
                    "author": {"name": "Alice"},
                    "version": "1.0",
                    "installs": 100,
                    "updatedAt": "2025-06-01",
                },
            ],
            "total": 42,
        }
        client = _mock_client(_make_response(json_data=mock_json))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().search("test", page=2, page_size=5)

        assert result.source == "anthropic"
        assert result.total == 42
        assert len(result.items) == 1
        item = result.items[0]
        assert item.id == "p1"
        assert item.name == "Plugin One"
        assert item.author == "Alice"
        assert item.downloads == 100

    async def test_search_空结果(self):
        client = _mock_client(_make_response(json_data={"plugins": [], "total": 0}))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().search("nothing")
        assert result.total == 0
        assert result.items == []


class TestAnthropicBrowse:
    async def test_browse_正常(self):
        mock_json = {
            "plugins": [
                {"id": "b1", "name": "Browse1", "description": "d", "author": {"name": "Bob"}, "version": "2.0"},
            ],
            "total": 50,
        }
        client = _mock_client(_make_response(json_data=mock_json))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().browse(page=1, page_size=10)
        assert result.source == "anthropic"
        assert result.total == 50

    async def test_browse_失败回退到search(self):
        """browse 失败时应回退调用 search("assistant")"""
        adapter = AnthropicAdapter()

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPError("browse fail")
            return _make_response(json_data={"plugins": [], "total": 0})

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await adapter.browse()
        assert result.source == "anthropic"


class TestAnthropicGetDetail:
    async def test_get_detail_正常(self):
        mock_json = {
            "name": "My Plugin",
            "description": "A plugin",
            "version": "3.0",
            "author": {"name": "Charlie"},
            "skill_md": "# Usage",
            "files": ["main.py", "SKILL.md"],
        }
        client = _mock_client(_make_response(json_data=mock_json))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            detail = await AnthropicAdapter().get_detail("my-plugin")

        assert detail.id == "my-plugin"
        assert detail.name == "My Plugin"
        assert detail.version == "3.0"
        assert detail.author == "Charlie"
        assert detail.skill_md_preview == "# Usage"
        assert detail.installed is False


class TestAnthropicDownload:
    async def test_download_有SKILL_md的子目录(self, tmp_path):
        """zip 内有 subdir/SKILL.md -> 返回 subdir"""
        zip_bytes = _make_zip({
            "my-plugin/SKILL.md": "# Skill",
            "my-plugin/code.py": "pass",
        })
        client = _mock_client(_make_response(content=zip_bytes))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().download("my-plugin", tmp_path)

        assert result == tmp_path / "my-plugin"
        assert (result / "SKILL.md").exists()

    async def test_download_统一顶层目录无SKILL_md(self, tmp_path):
        """zip 只有统一顶层目录但无 SKILL.md"""
        zip_bytes = _make_zip({
            "top-dir/main.py": "pass",
            "top-dir/config.yml": "x: 1",
        })
        client = _mock_client(_make_response(content=zip_bytes))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().download("some-plugin", tmp_path)

        assert result == tmp_path / "top-dir"

    async def test_download_平铺文件(self, tmp_path):
        """zip 内都是平铺文件 -> 创建 skill_id 子目录"""
        zip_bytes = _make_zip({
            "SKILL.md": "flat",
            "run.py": "pass",
        })
        client = _mock_client(_make_response(content=zip_bytes))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            result = await AnthropicAdapter().download("flat-plugin", tmp_path)

        assert result == tmp_path / "flat-plugin"
        assert (result / "SKILL.md").exists()

    async def test_download_zip_slip防护(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/shadow", "hacked")
        zip_bytes = buf.getvalue()

        client = _mock_client(_make_response(content=zip_bytes))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            with pytest.raises(ValueError, match="Zip Slip"):
                await AnthropicAdapter().download("evil", tmp_path)


class TestAnthropicCheckUpdate:
    async def test_有新版本(self):
        client = _mock_client(_make_response(json_data={"version": "2.0"}))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            info = await AnthropicAdapter().check_update("p1", "1.0")
        assert info is not None
        assert info.latest_version == "2.0"

    async def test_已是最新(self):
        client = _mock_client(_make_response(json_data={"version": "1.0"}))
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            info = await AnthropicAdapter().check_update("p1", "1.0")
        assert info is None

    async def test_异常返回none(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("agentos.adapters.skill_sources.anthropic_market.httpx.AsyncClient", return_value=client):
            info = await AnthropicAdapter().check_update("p1", "1.0")
        assert info is None
