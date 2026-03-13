"""ClawHubAdapter 单元测试"""
import io
import zipfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import httpx

from agentos.adapters.skill_sources.clawhub import ClawHubAdapter, MAX_RETRIES


def _make_response(status_code=200, json_data=None, content=b"", headers=None):
    """构造 mock httpx.Response"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    try:
        resp.text = content.decode("utf-8") if isinstance(content, bytes) and json_data is None else ""
    except UnicodeDecodeError:
        resp.text = ""
    resp.headers = httpx.Headers(headers or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _make_zip(files: dict[str, str]) -> bytes:
    """创建内存 zip，files 为 {路径: 内容}"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestClawHubAdapterProperties:
    def test_supports_browse(self):
        adapter = ClawHubAdapter()
        assert adapter.supports_browse is True

    def test_supports_search(self):
        adapter = ClawHubAdapter()
        assert adapter.supports_search is True

    def test_自定义api_base(self):
        adapter = ClawHubAdapter(api_base="https://custom.api/v1/")
        assert adapter._api_base == "https://custom.api/v1"


class TestClawHubSearch:
    async def test_search_解析结果(self):
        """搜索返回 results 列表，正确映射字段"""
        mock_json = {
            "results": [
                {
                    "slug": "my-skill",
                    "displayName": "My Skill",
                    "summary": "描述",
                    "version": "1.0.0",
                    "updatedAt": "2025-01-01",
                },
            ]
        }
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data=mock_json)
            result = await adapter.search("test", page=1, page_size=10)

        assert result.source == "clawhub"
        assert result.total == 1
        assert len(result.items) == 1
        item = result.items[0]
        assert item.id == "my-skill"
        assert item.name == "My Skill"
        assert item.description == "描述"
        assert item.version == "1.0.0"

    async def test_search_空结果(self):
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data={"results": []})
            result = await adapter.search("nothing")
        assert result.total == 0
        assert result.items == []


class TestClawHubBrowse:
    async def test_browse_列表格式(self):
        """browse 返回列表格式的 JSON"""
        mock_json = [
            {"slug": "s1", "displayName": "S1", "summary": "desc1", "owner": {"handle": "alice"}},
        ]
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data=mock_json)
            # 使 json() 返回列表
            mock_req.return_value.json.return_value = mock_json
            result = await adapter.browse(page=1, page_size=5)

        assert result.source == "clawhub"
        assert len(result.items) == 1
        assert result.items[0].author == "alice"

    async def test_browse_dict格式带skills键(self):
        mock_json = {
            "skills": [
                {"slug": "s2", "name": "S2", "description": "d2"},
            ],
            "total": 100,
        }
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data=mock_json)
            result = await adapter.browse()
        assert result.total == 100
        assert len(result.items) == 1

    async def test_browse_失败回退到search(self):
        """browse 出错时回退到 search("tool")"""
        adapter = ClawHubAdapter()
        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "skills" in url and call_count == 1:
                raise httpx.HTTPError("fail")
            return _make_response(json_data={"results": []})

        with patch.object(adapter, "_request", side_effect=mock_request):
            result = await adapter.browse()
        assert result.source == "clawhub"


class TestClawHubGetDetail:
    async def test_get_detail_正常返回(self):
        mock_json = {
            "skill": {"displayName": "Cool Skill", "summary": "很酷的技能"},
            "latestVersion": {"version": "2.0.0"},
            "owner": {"handle": "bob", "displayName": "Bob"},
        }
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            # 第一个调用返回详情，第二个返回 SKILL.md
            skill_md_resp = _make_response(content=b"# Skill Content")
            skill_md_resp.text = "# Skill Content"
            mock_req.side_effect = [
                _make_response(json_data=mock_json),
                skill_md_resp,
            ]
            detail = await adapter.get_detail("cool-skill")

        assert detail.id == "cool-skill"
        assert detail.name == "Cool Skill"
        assert detail.version == "2.0.0"
        assert detail.author == "bob"
        assert detail.skill_md_preview == "# Skill Content"

    async def test_get_detail_skill_md获取失败(self):
        """SKILL.md 获取失败不应影响整体"""
        mock_json = {
            "skill": {"displayName": "X"},
            "latestVersion": {},
            "owner": {},
        }
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                _make_response(json_data=mock_json),
                httpx.HTTPError("not found"),
            ]
            detail = await adapter.get_detail("x-skill")
        assert detail.skill_md_preview == ""


class TestClawHubDownload:
    async def test_download_带顶层目录的zip(self, tmp_path):
        """zip 内文件都在同一顶层目录下"""
        zip_bytes = _make_zip({
            "my-skill/SKILL.md": "# skill",
            "my-skill/main.py": "print(1)",
        })
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(content=zip_bytes)
            mock_req.return_value.content = zip_bytes
            result = await adapter.download("my-skill", tmp_path)

        assert result == tmp_path / "my-skill"
        assert (result / "SKILL.md").exists()
        assert (result / "main.py").exists()

    async def test_download_平铺文件的zip(self, tmp_path):
        """zip 内文件没有统一顶层目录 -> 创建以 skill_id 命名的子目录"""
        zip_bytes = _make_zip({
            "SKILL.md": "# flat skill",
            "run.py": "pass",
        })
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(content=zip_bytes)
            mock_req.return_value.content = zip_bytes
            result = await adapter.download("flat-skill", tmp_path)

        assert result == tmp_path / "flat-skill"
        assert (result / "SKILL.md").exists()

    async def test_download_zip_slip_防护(self, tmp_path):
        """含路径穿越的 zip 应抛出 ValueError"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "hacked")
        zip_bytes = buf.getvalue()

        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(content=zip_bytes)
            mock_req.return_value.content = zip_bytes
            with pytest.raises(ValueError, match="Zip Slip"):
                await adapter.download("evil", tmp_path)


class TestClawHubCheckUpdate:
    async def test_check_update_有新版本(self):
        mock_json = {"latestVersion": {"version": "2.0.0"}}
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data=mock_json)
            info = await adapter.check_update("my-skill", "1.0.0")
        assert info is not None
        assert info.latest_version == "2.0.0"
        assert info.current_version == "1.0.0"

    async def test_check_update_已是最新(self):
        mock_json = {"latestVersion": {"version": "1.0.0"}}
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _make_response(json_data=mock_json)
            info = await adapter.check_update("my-skill", "1.0.0")
        assert info is None

    async def test_check_update_异常返回none(self):
        adapter = ClawHubAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.HTTPError("fail")
            info = await adapter.check_update("bad-skill", "1.0.0")
        assert info is None


class TestClawHubRetry:
    async def test_429重试成功(self):
        """遇到 429 后根据 Retry-After 重试"""
        adapter = ClawHubAdapter()
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = httpx.Headers({"Retry-After": "0"})

        resp_200 = _make_response(json_data={"results": []})

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=[resp_429, resp_200])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agentos.adapters.skill_sources.clawhub.httpx.AsyncClient", return_value=mock_client):
            with patch("agentos.adapters.skill_sources.clawhub.asyncio.sleep", new_callable=AsyncMock):
                result = await adapter._request("GET", "https://example.com/test")
        assert result.status_code == 200

    async def test_429超过最大重试次数抛异常(self):
        """连续 429 超过 MAX_RETRIES 次后 raise"""
        adapter = ClawHubAdapter()
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = httpx.Headers({"Retry-After": "0"})
        resp_429.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("429", request=MagicMock(), response=resp_429)
        )

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=resp_429)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agentos.adapters.skill_sources.clawhub.httpx.AsyncClient", return_value=mock_client):
            with patch("agentos.adapters.skill_sources.clawhub.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.HTTPStatusError):
                    await adapter._request("GET", "https://example.com/test")
