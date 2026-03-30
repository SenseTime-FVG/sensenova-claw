from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sensenova_claw.capabilities.tools.builtin import FetchUrlTool
from sensenova_claw.platform.config.config import config


@pytest.fixture(autouse=True)
def restore_config():
    original = copy.deepcopy(config.data)
    yield
    config.data = original


def _make_async_client(response: MagicMock) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.request = AsyncMock(return_value=response)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=None)
    return manager, client


def _make_response(
    *,
    url: str,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    text: str = "",
    json_payload: object | None = None,
    content: bytes | None = None,
) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.url = httpx.URL(url)
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text
    response.content = content if content is not None else text.encode("utf-8")
    response.json = MagicMock(return_value=json_payload)
    return response


@pytest.mark.asyncio
async def test_fetch_url_rejects_non_http_scheme() -> None:
    response = _make_response(url="ftp://example.com/file.txt")
    manager, _client = _make_async_client(response)
    tool = FetchUrlTool()

    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        with pytest.raises(ValueError, match="http:// 或 https://"):
            await tool.execute(url="ftp://example.com/file.txt")


@pytest.mark.asyncio
async def test_fetch_url_rejects_invalid_format() -> None:
    response = _make_response(url="https://example.com")
    manager, _client = _make_async_client(response)
    tool = FetchUrlTool()

    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        with pytest.raises(ValueError, match="format"):
            await tool.execute(url="https://example.com", format="html")


@pytest.mark.asyncio
async def test_fetch_url_defaults_to_markdown_for_html() -> None:
    html = """
    <html>
      <body>
        <nav>Home Docs Pricing</nav>
        <article>
          <h1>Example Title</h1>
          <p>Hello <a href="https://example.com/docs">world</a>.</p>
          <ul><li>Alpha</li><li>Beta</li></ul>
        </article>
        <footer>Share this everywhere</footer>
      </body>
    </html>
    """
    response = _make_response(
        url="https://example.com/post",
        headers={"Content-Type": "text/html; charset=utf-8"},
        text=html,
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(url="https://example.com/post")

    assert result["url"] == "https://example.com/post"
    assert result["status_code"] == 200
    assert result["content_type"] == "text/html"
    assert result["format"] == "markdown"
    assert "Example Title" in result["content"]
    assert "[world](https://example.com/docs)" in result["content"]
    assert "Alpha" in result["content"]
    assert "Home Docs Pricing" not in result["content"]
    assert "<html>" not in result["content"]


@pytest.mark.asyncio
async def test_fetch_url_raises_for_non_2xx_html_response() -> None:
    html = """
    <html>
      <head><title>403 Forbidden</title></head>
      <body>
        <nav>Home Docs Pricing</nav>
        <main>
          <h1>403 Forbidden</h1>
          <p>Access denied by upstream service.</p>
          <footer>nginx</footer>
        </main>
      </body>
    </html>
    """
    response = _make_response(
        url="https://example.com/blocked",
        status_code=403,
        headers={"Content-Type": "text/html; charset=utf-8"},
        text=html,
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        with pytest.raises(ValueError, match="403"):
            await tool.execute(url="https://example.com/blocked")


@pytest.mark.asyncio
async def test_fetch_url_prefers_abstract_content_for_academic_html() -> None:
    html = """
    <html>
      <body>
        <header>
          <nav>Help Advanced Search Login</nav>
        </header>
        <main>
          <section class="paper-header">
            <h1>Assemble Your Crew: Automatic Multi-agent Communication Topology Design</h1>
            <p>Shiyuan Li, Yixin Liu</p>
          </section>
          <blockquote class="abstract mathjax">
            <span class="descriptor">Abstract:</span>
            <p>
              Multi-agent systems based on large language models have emerged as a powerful
              solution for complex problems. We propose ARG-Designer, a novel autoregressive
              model that jointly designs agent roles and communication topology.
            </p>
          </blockquote>
          <section class="metadata">
            <h2>Submission history</h2>
            <p>v1 submitted in July 2025.</p>
          </section>
          <section class="related">
            <h2>Related Papers</h2>
            <a href="/paper1">Paper 1</a>
            <a href="/paper2">Paper 2</a>
            <a href="/paper3">Paper 3</a>
            <a href="/paper4">Paper 4</a>
          </section>
        </main>
      </body>
    </html>
    """
    response = _make_response(
        url="https://example.com/paper",
        headers={"Content-Type": "text/html; charset=utf-8"},
        text=html,
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(url="https://example.com/paper")

    assert "Assemble Your Crew" in result["content"]
    assert "ARG-Designer" in result["content"]
    assert "Submission history" not in result["content"]
    assert "Related Papers" not in result["content"]
    assert "Help Advanced Search Login" not in result["content"]


@pytest.mark.asyncio
async def test_fetch_url_formats_json_as_pretty_text() -> None:
    payload = {"name": "agentos", "features": ["fetch", "markdown"]}
    response = _make_response(
        url="https://example.com/data.json",
        headers={"Content-Type": "application/json"},
        json_payload=payload,
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(url="https://example.com/data.json", format="text")

    assert result["content_type"] == "application/json"
    assert result["format"] == "text"
    assert result["content"] == json.dumps(payload, ensure_ascii=False, indent=2)


@pytest.mark.asyncio
async def test_fetch_url_returns_plain_text_for_text_response() -> None:
    response = _make_response(
        url="https://example.com/readme.txt",
        headers={"Content-Type": "text/plain; charset=utf-8"},
        text="line1\nline2\n",
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(url="https://example.com/readme.txt", format="text")

    assert result["content_type"] == "text/plain"
    assert result["content"] == "line1\nline2\n"


@pytest.mark.asyncio
async def test_fetch_url_downloads_non_text_content(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENSENOVA_CLAW_HOME", str(tmp_path))
    response = _make_response(
        url="https://example.com/report.pdf",
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="report.pdf"',
        },
        content=b"%PDF-1.4 fake",
    )
    manager, _client = _make_async_client(response)

    tool = FetchUrlTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(url="https://example.com/report.pdf", _session_id="session-1")

    assert result["content_type"] == "application/pdf"
    assert result["download_filename"] == "report.pdf"
    assert "已下载非文本内容" in result["content"]
    assert result["summary"]
    download_path = Path(result["download_path"])
    assert download_path.exists()
    assert download_path.read_bytes() == b"%PDF-1.4 fake"
