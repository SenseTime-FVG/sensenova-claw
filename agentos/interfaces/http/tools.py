"""
Tools API - 从真实 ToolRegistry 读取已注册工具，并提供 API key 管理能力。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agentos.platform.secrets.refs import is_secret_ref

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])

TOOL_API_KEY_SPECS: dict[str, dict[str, Any]] = {
    "serper_search": {
        "config_path": "tools.serper_search.api_key",
        "docs_url": "https://serper.dev/",
        "description": "Google search via Serper API",
        "setup_guide": [
            "1. 打开 https://serper.dev/ ，点击 Sign up / Get started，使用邮箱或 Google 账号完成注册并登录。",
            "2. 登录后进入 Dashboard，在页面中找到 API Key 区域；Serper 会在控制台里直接展示可复制的 key。",
            "3. 点击复制按钮获取 API Key。Serper 官方提供免费试用额度，通常可以先不绑信用卡就完成测试。",
            "4. 把复制出的 API Key 粘贴到这里，点击 Validate 验证；验证通过后，再保存到当前工具配置中。",
        ],
        "example_format": "<serper-api-key>",
    },
    "brave_search": {
        "config_path": "tools.brave_search.api_key",
        "docs_url": "https://api-dashboard.search.brave.com/app/documentation/web-search/get-started",
        "description": "Web search via Brave Search API",
        "setup_guide": [
            "1. 打开 Brave Search API 文档页 https://api-dashboard.search.brave.com/app/documentation/web-search/get-started ，点击 Log in 注册或登录控制台。",
            "2. 登录后进入 dashboard，在 Subscriptions 中选择并订阅一个 Web Search plan；没有订阅时不会生成可用 token。",
            "3. 打开订阅后的应用或凭据页面，复制请求头里要用的 X-Subscription-Token。",
            "4. 把这个 token 粘贴到这里，点击 Validate 验证；验证通过后保存即可。",
        ],
        "example_format": "<brave-x-subscription-token>",
    },
    "baidu_search": {
        "config_path": "tools.baidu_search.api_key",
        "docs_url": "https://cloud.baidu.com/doc/qianfan-docs/s/qm8qxemze",
        "description": "Web search via Baidu AppBuilder AI Search",
        "setup_guide": [
            "1. 登录百度智能云后，打开千帆开发者中心文档中的“快速开始”页，进入控制台-安全认证-API Key。",
            "2. 点击“创建 API Key”，并在“添加权限”里勾选你要调用的千帆 / AppBuilder / AI 搜索相关能力。",
            "3. 创建完成后复制该 API Key；百度接口调用时需要按 Bearer 方式使用，所以这里保存的就是 Bearer 后面的那段 key。",
            "4. 把复制出的 key 粘贴到这里，点击 Validate 验证；若后续还要调用应用对话接口，再在百度控制台中额外准备 app_id。",
        ],
        "example_format": "bce-v3/ALTAK-.../...",
    },
    "tavily_search": {
        "config_path": "tools.tavily_search.api_key",
        "docs_url": "https://docs.tavily.com/documentation/quickstart",
        "description": "Web search via Tavily Search API",
        "setup_guide": [
            "1. 打开 https://tavily.com/ 并完成登录，首次使用会进入 Tavily dashboard。",
            "2. 在 Dashboard 或 API Keys 区域找到系统分配给你的 key，并点击复制。",
            "3. Tavily 请求使用 Authorization: Bearer <api_key>，所以这里需要填写的就是 Bearer 后面的实际 key。",
            "4. 把 key 粘贴到这里后点击 Validate 验证，验证通过后保存。",
        ],
        "example_format": "tvly-...",
    },
}


def _prefs_path(request: Request) -> Path:
    home = Path(getattr(request.app.state, "agentos_home", "") or str(Path.home() / ".agentos"))
    return home / ".agent_preferences.json"


def _load_prefs(request: Request) -> dict:
    p = _prefs_path(request)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_prefs(request: Request, prefs: dict) -> None:
    p = _prefs_path(request)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def _api_key_status(request) -> dict[str, dict[str, Any]]:
    """获取工具 API key 状态"""
    cfg = request.app.state.config
    config_manager = request.app.state.config_manager
    raw_config = config_manager._load_raw_yaml()
    result: dict[str, dict[str, Any]] = {}
    for tool_name, spec in TOOL_API_KEY_SPECS.items():
        value = cfg.get(spec["config_path"], "")
        raw_value = _read_raw_value(raw_config, spec["config_path"])
        result[tool_name] = {
            "configured": bool(value),
            "masked_key": _mask_secret(value),
            "source": _detect_secret_source(raw_value),
            "docs_url": spec["docs_url"],
            "description": spec["description"],
            "setup_guide": spec["setup_guide"],
            "example_format": spec["example_format"],
        }
    return result


def _read_raw_value(raw_config: dict[str, Any], dotted_path: str) -> Any:
    current: Any = raw_config
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _detect_secret_source(raw_value: Any) -> str:
    if not raw_value:
        return "empty"
    if isinstance(raw_value, str) and is_secret_ref(raw_value):
        return "secret"
    if isinstance(raw_value, str) and raw_value.startswith("${") and raw_value.endswith("}"):
        return "env"
    return "plain"


async def _validate_serper(api_key: str) -> tuple[bool, str]:
    payload = {"q": "test", "gl": "us", "hl": "en", "page": 1}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post("https://google.serper.dev/search", headers=headers, json=payload)
    if resp.is_success:
        return True, "Serper API key is valid."
    return False, f"Serper validation failed with status {resp.status_code}."


async def _validate_brave(api_key: str) -> tuple[bool, str]:
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    params = {"q": "test", "count": 1}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
    if resp.is_success:
        return True, "Brave Search API key is valid."
    return False, f"Brave validation failed with status {resp.status_code}."


async def _validate_baidu(api_key: str) -> tuple[bool, str]:
    headers = {
        "X-Appbuilder-Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": "test"}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": 1}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            headers=headers,
            json=payload,
        )
    if not resp.is_success:
        return False, f"Baidu validation failed with status {resp.status_code}."
    data = resp.json()
    if data.get("code"):
        return False, str(data.get("message", "Baidu validation failed."))
    return True, "Baidu AppBuilder API key is valid."


async def _validate_tavily(api_key: str) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"query": "test", "topic": "general", "search_depth": "basic", "max_results": 1}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post("https://api.tavily.com/search", headers=headers, json=payload)
    if resp.is_success:
        return True, "Tavily API key is valid."
    return False, f"Tavily validation failed with status {resp.status_code}."


VALIDATORS = {
    "serper_search": _validate_serper,
    "brave_search": _validate_brave,
    "baidu_search": _validate_baidu,
    "tavily_search": _validate_tavily,
}


class EnablePayload(BaseModel):
    enabled: bool


class ApiKeyValidatePayload(BaseModel):
    api_key: str | None = None


@router.get("")
async def list_tools(request: Request):
    """获取所有已注册的工具。"""
    tool_registry = request.app.state.tool_registry
    cfg = request.app.state.config
    prefs = _load_prefs(request)
    tool_prefs = prefs.get("tools", {})

    tools = []
    for name, tool in tool_registry._tools.items():
        enabled = tool_prefs.get(name, True)
        api_key_spec = TOOL_API_KEY_SPECS.get(name)
        tools.append({
            "id": f"tool-{name}",
            "name": name,
            "description": tool.description or "",
            "category": "builtin",
            "version": "1.0.0",
            "enabled": enabled,
            "riskLevel": tool.risk_level.value if hasattr(tool.risk_level, "value") else "low",
            "parameters": tool.parameters or {},
            "requiresApiKey": api_key_spec is not None,
            "apiKeyConfigured": bool(api_key_spec and cfg.get(api_key_spec["config_path"], "")),
        })
    return tools


@router.put("/{tool_name}/enabled")
async def toggle_tool(tool_name: str, body: EnablePayload, request: Request):
    """启用/禁用工具。"""
    tool_registry = request.app.state.tool_registry
    tool = tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(404, f"Tool 不存在: {tool_name}")

    prefs = _load_prefs(request)
    if "tools" not in prefs:
        prefs["tools"] = {}
    prefs["tools"][tool_name] = body.enabled
    _save_prefs(request, prefs)

    logger.info("Tool %s %s", tool_name, "enabled" if body.enabled else "disabled")
    return {"name": tool_name, "enabled": body.enabled}


@router.get("/api-keys")
async def get_tool_api_keys(request: Request):
    """返回工具 API key 状态与配置指南。"""
    return _api_key_status(request)


@router.put("/api-keys")
async def update_tool_api_keys(body: dict[str, str | None], request: Request):
    """批量保存工具 API key。"""
    if not body:
        raise HTTPException(400, "No API key updates provided")

    path_updates: dict[str, Any] = {}
    for tool_name, api_key in body.items():
        spec = TOOL_API_KEY_SPECS.get(tool_name)
        if not spec:
            raise HTTPException(404, f"Tool API key config not found: {tool_name}")
        path_updates[spec["config_path"]] = api_key or ""

    # Convert flat path_updates to nested dict for ConfigManager
    tools_nested: dict[str, Any] = {}
    for path, value in path_updates.items():
        keys = path.split(".")
        sub_path = keys[1:]  # Remove "tools." prefix
        current = tools_nested
        for k in sub_path[:-1]:
            current = current.setdefault(k, {})
        current[sub_path[-1]] = value

    config_manager = request.app.state.config_manager
    try:
        await config_manager.update("tools", tools_nested)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save API keys: {exc}")

    logger.info("Updated tool API keys: %s", list(body.keys()))
    return {"status": "saved", "api_keys": _api_key_status(request)}


@router.post("/api-keys/{tool_name}/validate")
async def validate_tool_api_key(tool_name: str, body: ApiKeyValidatePayload, request: Request):
    """对工具 API key 做轻量校验。"""
    spec = TOOL_API_KEY_SPECS.get(tool_name)
    if not spec:
        raise HTTPException(404, f"Tool API key config not found: {tool_name}")

    api_key = body.api_key or request.app.state.config.get(spec["config_path"], "")
    if not api_key:
        return {"valid": False, "message": "API key is empty."}

    validator = VALIDATORS.get(tool_name)
    if not validator:
        return {"valid": True, "message": "No validator available for this tool."}

    try:
        valid, message = await validator(api_key)
    except httpx.HTTPError as exc:
        return {"valid": False, "message": f"Validation request failed: {exc}"}
    except Exception as exc:
        logger.exception("Tool API key validation failed: %s", tool_name)
        return {"valid": False, "message": f"Validation failed: {exc}"}

    return {"valid": valid, "message": message}
