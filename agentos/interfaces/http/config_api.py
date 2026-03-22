"""
Config API - 按 section 读写 config.yml 中的 llm / agent / plugins
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agentos.interfaces.http.config_store import load_raw_config, persist_path_updates, persist_section_updates
from agentos.platform.config.llm_presets import check_llm_configured, LLM_PROVIDER_CATEGORIES
from agentos.platform.secrets.migration import migrate_plaintext_secrets
from agentos.platform.secrets.refs import is_secret_ref
from agentos.platform.secrets.registry import is_secret_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

EDITABLE_SECTIONS = ("llm", "agent", "plugins")


class SectionsUpdateBody(BaseModel):
    llm: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    plugins: dict[str, Any] | None = None


class ListModelsBody(BaseModel):
    api_key: str
    base_url: str = ""
    provider: str = "openai"  # 'openai' | 'anthropic' | 'gemini' | 任意 OpenAI 兼容 provider key


class TestLLMBody(BaseModel):
    provider: str       # 'openai' | 'anthropic' | 'gemini'
    api_key: str
    base_url: str = ""
    model_id: str


class ProviderUpdateBody(BaseModel):
    name: str | None = None
    api_key: str | None = None
    base_url: str = ""
    timeout: int = 60
    max_retries: int = 3


class ModelUpdateBody(BaseModel):
    name: str | None = None
    provider: str
    model_id: str
    timeout: int = 60
    max_output_tokens: int = 8192


@router.get("/secret")
async def get_secret_value(path: str, request: Request):
    """按路径读取敏感配置的真实值，仅允许注册过的 secret path。"""
    if not path:
        raise HTTPException(400, "缺少 path")
    if not is_secret_path(path):
        raise HTTPException(400, f"不允许读取非敏感路径: {path}")

    cfg = request.app.state.config
    return {"path": path, "value": cfg.get(path, "") or ""}


@router.post("/migrate-secrets")
async def migrate_secrets(request: Request):
    """将 config.yml 中的明文敏感字段迁移到 secret store。"""
    secret_store = getattr(request.app.state, "secret_store", None)
    if secret_store is None:
        raise HTTPException(500, "secret store 未初始化")
    try:
        return migrate_plaintext_secrets(request.app.state.config, secret_store=secret_store)
    except Exception as exc:
        raise HTTPException(500, f"迁移 secret 失败: {exc}")


@router.get("/sections")
async def get_config_sections(request: Request):
    """返回 llm / agent / plugins 三个 section 的当前值"""
    cfg = request.app.state.config
    raw_config = load_raw_config(cfg)
    result: dict[str, Any] = {}
    for key in EDITABLE_SECTIONS:
        result[key] = _sanitize_section(
            path=key,
            resolved=deepcopy(cfg.data.get(key, {})),
            raw=deepcopy(raw_config.get(key, {})),
        )
    return result


@router.put("/sections")
async def update_config_sections(body: SectionsUpdateBody, request: Request):
    """更新指定 section 并持久化到 config.yml，同时热更新运行时配置"""
    cfg = request.app.state.config

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "未提供任何更新内容")

    logger.debug("Config sections update request: %s", updates)
    flattened_updates = _flatten_updates(updates)
    logger.debug("Config sections flattened updates: %s", flattened_updates)

    try:
        data = persist_path_updates(
            cfg,
            flattened_updates,
            secret_store=getattr(request.app.state, "secret_store", None),
        )
    except Exception as e:
        raise HTTPException(500, f"写入配置文件失败: {e}")

    logger.info("Config sections updated and reloaded: %s", list(updates.keys()))

    # 返回更新后的 sections
    result: dict[str, Any] = {}
    raw_config = load_raw_config(cfg)
    for key in EDITABLE_SECTIONS:
        result[key] = _sanitize_section(
            path=key,
            resolved=deepcopy(data.get(key, {})),
            raw=deepcopy(raw_config.get(key, {})),
        )
    return {"status": "saved", "sections": result}


@router.put("/llm/providers/{provider_name}")
async def update_llm_provider(provider_name: str, body: ProviderUpdateBody, request: Request):
    cfg = request.app.state.config
    secret_store = getattr(request.app.state, "secret_store", None)
    raw_config = load_raw_config(cfg)
    llm_section = deepcopy(raw_config.get("llm", {}))
    providers = deepcopy(llm_section.get("providers", {}))
    models = deepcopy(llm_section.get("models", {}))

    if provider_name not in providers:
        raise HTTPException(404, f"Provider 不存在: {provider_name}")

    next_name = (body.name or provider_name).strip().lower()
    if not next_name:
        raise HTTPException(400, "Provider 名称不能为空")
    if next_name != provider_name and next_name in providers:
        raise HTTPException(400, f"Provider 已存在: {next_name}")

    existing = providers.pop(provider_name)
    provider_payload = {
        "base_url": body.base_url,
        "timeout": body.timeout,
        "max_retries": body.max_retries,
    }
    providers[next_name] = provider_payload
    llm_section["providers"] = providers

    if next_name != provider_name:
        for model in models.values():
            if isinstance(model, dict) and model.get("provider") == provider_name:
                model["provider"] = next_name
        llm_section["models"] = models

    if body.api_key is not None:
        api_key_path = f"llm.providers.{next_name}.api_key"
        try:
            persist_path_updates(
                cfg,
                {api_key_path: body.api_key},
                secret_store=secret_store,
            )
        except Exception as exc:
            raise HTTPException(500, f"写入配置文件失败: {exc}")
        raw_config = load_raw_config(cfg)
        llm_section = deepcopy(raw_config.get("llm", {}))
        providers = deepcopy(llm_section.get("providers", {}))
        providers[next_name] = {
            **providers.get(next_name, {}),
            **provider_payload,
        }
        llm_section["providers"] = providers
    else:
        current_raw = existing if isinstance(existing, dict) else {}
        if "api_key" in current_raw:
            provider_payload["api_key"] = current_raw["api_key"]
            providers[next_name] = provider_payload
            llm_section["providers"] = providers

    try:
        data = persist_section_updates(cfg, {"llm": llm_section})
    except Exception as exc:
        raise HTTPException(500, f"写入配置文件失败: {exc}")

    return {"status": "saved", "provider": _sanitize_section(
        path=f"llm.providers.{next_name}",
        resolved=deepcopy(data.get("llm", {}).get("providers", {}).get(next_name, {})),
        raw=deepcopy(load_raw_config(cfg).get("llm", {}).get("providers", {}).get(next_name, {})),
    )}


@router.put("/llm/models/{model_name}")
async def update_llm_model(model_name: str, body: ModelUpdateBody, request: Request):
    cfg = request.app.state.config
    raw_config = load_raw_config(cfg)
    llm_section = deepcopy(raw_config.get("llm", {}))
    models = deepcopy(llm_section.get("models", {}))

    if model_name not in models:
        raise HTTPException(404, f"Model 不存在: {model_name}")

    next_name = (body.name or model_name).strip()
    if not next_name:
        raise HTTPException(400, "Model 名称不能为空")
    if next_name != model_name and next_name in models:
        raise HTTPException(400, f"Model 已存在: {next_name}")

    models.pop(model_name)
    models[next_name] = {
        "provider": body.provider,
        "model_id": body.model_id,
        "timeout": body.timeout,
        "max_output_tokens": body.max_output_tokens,
    }
    llm_section["models"] = models
    if llm_section.get("default_model") == model_name:
        llm_section["default_model"] = next_name

    try:
        data = persist_section_updates(cfg, {"llm": llm_section})
    except Exception as exc:
        raise HTTPException(500, f"写入配置文件失败: {exc}")

    return {"status": "saved", "model": _sanitize_section(
        path=f"llm.models.{next_name}",
        resolved=deepcopy(data.get("llm", {}).get("models", {}).get(next_name, {})),
        raw=deepcopy(load_raw_config(cfg).get("llm", {}).get("models", {}).get(next_name, {})),
    )}


def _flatten_updates(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_updates(value, path))
        else:
            result[path] = value
    return result


def _sanitize_section(path: str, resolved: Any, raw: Any) -> Any:
    if is_secret_path(path):
        return {
            "configured": bool(resolved),
            "masked_value": _mask_secret(resolved),
            "source": _detect_secret_source(raw),
        }
    if isinstance(resolved, dict):
        raw_dict = raw if isinstance(raw, dict) else {}
        return {
            key: _sanitize_section(
                path=f"{path}.{key}",
                resolved=value,
                raw=raw_dict.get(key),
            )
            for key, value in resolved.items()
        }
    if isinstance(resolved, list):
        return resolved
    return resolved


def _mask_secret(secret: Any) -> str | None:
    if not isinstance(secret, str) or not secret:
        return None
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def _detect_secret_source(raw_value: Any) -> str:
    if not raw_value:
        return "empty"
    if isinstance(raw_value, str) and is_secret_ref(raw_value):
        return "secret"
    if isinstance(raw_value, str) and raw_value.startswith("${") and raw_value.endswith("}"):
        return "env"
    return "plain"


@router.get("/llm-status")
async def get_llm_status(request: Request):
    """检测当前配置中是否至少有一个 LLM 提供商已配置有效 API key"""
    cfg = request.app.state.config
    is_configured, providers = check_llm_configured(cfg.data)
    return {"configured": is_configured, "providers": providers}


@router.get("/llm-presets")
async def get_llm_presets():
    """返回所有 LLM 提供商预设分类列表，供前端展示使用"""
    return {"categories": LLM_PROVIDER_CATEGORIES}


@router.post("/list-models")
async def list_models(body: ListModelsBody):
    """通过 OpenAI 兼容的 GET /models 接口获取可用模型列表"""
    try:
        logger.debug("List models request: provider=%s base_url=%s", body.provider, body.base_url)
        if body.provider == "anthropic":
            models = await _list_models_anthropic(body.api_key, body.base_url)
        else:
            models = await _list_models_openai(body.api_key, body.base_url)
        return {"success": True, "models": models}
    except Exception as e:
        logger.warning("List models failed: %s", e)
        return {"success": False, "error": str(e), "models": []}


async def _list_models_openai(api_key: str, base_url: str) -> list[dict]:
    """通过 OpenAI SDK 的 models.list() 获取模型列表"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.models.list()
    models = []
    for model in response.data:
        models.append({"id": model.id, "owned_by": getattr(model, "owned_by", "")})
    models.sort(key=lambda m: m["id"])
    return models


async def _list_models_anthropic(api_key: str, base_url: str) -> list[dict]:
    """通过 Anthropic SDK 获取模型列表"""
    import anthropic
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.models.list(limit=100)
    models = []
    for model in response.data:
        models.append({"id": model.id, "owned_by": "anthropic"})
    models.sort(key=lambda m: m["id"])
    return models


@router.post("/test-llm")
async def test_llm_connection(body: TestLLMBody):
    """用临时配置测试 LLM 连通性，发送一个简单请求验证 API key 和模型是否可用"""
    provider = body.provider
    try:
        if provider in ("openai", "anthropic", "gemini"):
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
            ) if provider == "openai" else (
                await _test_anthropic(
                    api_key=body.api_key,
                    base_url=body.base_url,
                    model_id=body.model_id,
                ) if provider == "anthropic" else
                await _test_gemini(
                    api_key=body.api_key,
                    base_url=body.base_url,
                    model_id=body.model_id,
                )
            )
            return {"success": True, **result}
        else:
            # 未知 provider 类型，尝试 OpenAI 兼容方式
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
            )
            return {"success": True, **result}
    except Exception as e:
        logger.warning("LLM test failed: %s", e)
        return {"success": False, "error": str(e)}


async def _test_openai_compatible(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 OpenAI SDK 测试连通性"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_anthropic(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 Anthropic SDK 测试连通性"""
    import anthropic
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.messages.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_gemini(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 OpenAI 兼容方式测试 Gemini"""
    from openai import AsyncOpenAI
    gemini_base = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=gemini_base,
        timeout=15,
    )
    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}
