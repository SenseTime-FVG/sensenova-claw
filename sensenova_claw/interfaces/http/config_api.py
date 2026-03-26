"""
Config API - 按 section 读写 config.yml，管理 LLM provider/model
"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from sensenova_claw.capabilities.miniapps.acp_wizard import ACPWizardInstallError, ACPWizardService
from sensenova_claw.platform.config.llm_presets import check_llm_configured, LLM_PROVIDER_CATEGORIES
from sensenova_claw.platform.secrets.migration import migrate_plaintext_secrets
from sensenova_claw.platform.secrets.registry import is_secret_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


class ListModelsBody(BaseModel):
    api_key: str
    base_url: str = ""
    provider: str = "openai"  # 'openai' | 'anthropic' | 'gemini' | 任意 OpenAI 兼容 provider key


class TestLLMBody(BaseModel):
    provider: str       # 'openai' | 'anthropic' | 'gemini'
    api_key: str
    base_url: str = ""
    model_id: str
    max_tokens: int = 128000
    max_output_tokens: int = 16384


class ProviderUpdateBody(BaseModel):
    name: str | None = None
    source_type: str = "openai"
    api_key: str | None = None
    base_url: str = ""
    timeout: int = 60
    max_retries: int = 3


class ModelUpdateBody(BaseModel):
    name: str | None = None
    provider: str
    model_id: str
    timeout: int = 60
    max_tokens: int = 128000
    max_output_tokens: int = 16384


class DefaultModelUpdateBody(BaseModel):
    default_model: str = ""


class ACPWizardInstallBody(BaseModel):
    agent_id: str
    step_ids: list[str] = []


def _get_acp_wizard(request: Request) -> ACPWizardService:
    service = getattr(request.app.state, "acp_wizard_service", None)
    if service is not None:
        return service
    service = ACPWizardService(project_root=getattr(request.app.state, "project_root", None))
    request.app.state.acp_wizard_service = service
    return service


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
    """返回 llm / agent / plugins / miniapps 四个 section 的当前值"""
    config_manager = request.app.state.config_manager
    default_sections = ["llm", "agent", "plugins", "miniapps"]
    sections = config_manager.get_sections(default_sections)
    raw_config = config_manager._load_raw_yaml()
    raw_llm = raw_config.get("llm", {}) if isinstance(raw_config, dict) else {}
    raw_providers = raw_llm.get("providers", {}) if isinstance(raw_llm, dict) else {}
    explicit_provider_names = [
        name for name, value in raw_providers.items()
        if isinstance(name, str) and isinstance(value, dict)
    ]
    llm_section = sections.get("llm", {})
    if isinstance(llm_section, dict):
        llm_section["_meta"] = {
            "explicit_provider_names": explicit_provider_names,
        }
    return sections


@router.get("/acp/wizard")
async def get_acp_wizard(request: Request):
    cfg = request.app.state.config
    wizard = _get_acp_wizard(request)
    return wizard.inspect(current_config=cfg.get("miniapps.acp", {}) or {})


@router.post("/acp/wizard/install")
async def install_acp_agent(body: ACPWizardInstallBody, request: Request):
    cfg = request.app.state.config
    wizard = _get_acp_wizard(request)
    try:
        return await wizard.install(
            body.agent_id,
            step_ids=body.step_ids,
            current_config=cfg.get("miniapps.acp", {}) or {},
        )
    except ACPWizardInstallError as exc:
        raise HTTPException(400, str(exc))
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, f"ACP 安装超时: {exc}")


@router.put("/sections")
async def update_config_sections(body: dict[str, Any], request: Request):
    """更新指定 section 并持久化到 config.yml，同时热更新运行时配置"""
    if not body:
        raise HTTPException(400, "未提供任何更新内容")
    config_manager = request.app.state.config_manager
    try:
        results = {}
        for section, data in body.items():
            if isinstance(data, dict):
                results[section] = await config_manager.update(section, data)
        return {"status": "saved", "sections": results}
    except Exception as e:
        raise HTTPException(500, f"写入配置文件失败: {e}")


@router.put("/llm/providers/{provider_name}")
async def update_llm_provider(provider_name: str, body: ProviderUpdateBody, request: Request):
    """更新单个 LLM provider，支持改名并联动迁移 model 引用"""
    config_manager = request.app.state.config_manager
    raw_config = config_manager._load_raw_yaml()
    llm_section = deepcopy(raw_config.get("llm", {}))
    providers = deepcopy(llm_section.get("providers", {}))
    models = deepcopy(llm_section.get("models", {}))

    provider_exists = provider_name in providers
    next_name = (body.name or provider_name).strip().lower()
    if not next_name:
        raise HTTPException(400, "Provider 名称不能为空")
    if provider_exists and next_name != provider_name and next_name in providers:
        raise HTTPException(400, f"Provider 已存在: {next_name}")

    existing = providers.pop(provider_name, {})
    provider_payload: dict[str, Any] = {
        "source_type": body.source_type or (existing.get("source_type") if isinstance(existing, dict) else "openai"),
        "base_url": body.base_url,
        "timeout": body.timeout,
        "max_retries": body.max_retries,
    }
    if body.api_key is not None:
        provider_payload["api_key"] = body.api_key
    elif isinstance(existing, dict) and "api_key" in existing:
        provider_payload["api_key"] = existing["api_key"]

    providers[next_name] = provider_payload
    llm_section["providers"] = providers

    if provider_exists and next_name != provider_name:
        for model in models.values():
            if isinstance(model, dict) and model.get("provider") == provider_name:
                model["provider"] = next_name
    llm_section["models"] = models

    try:
        updated_llm = await config_manager.replace("llm", llm_section)
    except Exception as exc:
        raise HTTPException(500, f"写入配置文件失败: {exc}")

    return {
        "status": "saved",
        "provider": updated_llm.get("providers", {}).get(next_name, {}),
    }


@router.put("/llm/models/{model_name}")
async def update_llm_model(model_name: str, body: ModelUpdateBody, request: Request):
    """更新单个 LLM model，支持改名并联动 default_model"""
    config_manager = request.app.state.config_manager
    raw_config = config_manager._load_raw_yaml()
    llm_section = deepcopy(raw_config.get("llm", {}))
    models = deepcopy(llm_section.get("models", {}))

    model_exists = model_name in models
    next_name = (body.name or model_name).strip()
    if not next_name:
        raise HTTPException(400, "Model 名称不能为空")
    if model_exists and next_name != model_name and next_name in models:
        raise HTTPException(400, f"Model 已存在: {next_name}")

    models.pop(model_name, None)
    models[next_name] = {
        "provider": body.provider,
        "model_id": body.model_id,
        "timeout": body.timeout,
        "max_tokens": body.max_tokens,
        "max_output_tokens": body.max_output_tokens,
    }
    llm_section["models"] = models
    if model_exists and llm_section.get("default_model") == model_name:
        llm_section["default_model"] = next_name

    try:
        updated_llm = await config_manager.replace("llm", llm_section)
    except Exception as exc:
        raise HTTPException(500, f"写入配置文件失败: {exc}")

    return {
        "status": "saved",
        "model": updated_llm.get("models", {}).get(next_name, {}),
    }


@router.put("/llm/default-model")
async def update_llm_default_model(body: DefaultModelUpdateBody, request: Request):
    """更新默认模型，不修改 provider/model 其他配置。"""
    config_manager = request.app.state.config_manager
    raw_config = config_manager._load_raw_yaml()
    llm_section = deepcopy(raw_config.get("llm", {}))
    models = deepcopy(llm_section.get("models", {}))

    if body.default_model and body.default_model not in models:
        raise HTTPException(400, f"Model 不存在: {body.default_model}")

    llm_section["default_model"] = body.default_model

    try:
        updated_llm = await config_manager.replace("llm", llm_section)
    except Exception as exc:
        raise HTTPException(500, f"写入配置文件失败: {exc}")

    return {
        "status": "saved",
        "default_model": updated_llm.get("default_model", ""),
    }

@router.get("/llm-status")
async def get_llm_status(request: Request):
    """检测当前配置中是否至少有一个 LLM 提供商已配置有效 API key"""
    cfg = request.app.state.config
    is_configured, providers = check_llm_configured(
        cfg.data,
        secret_store=getattr(cfg, "_secret_store", None),
    )
    return {"configured": is_configured, "providers": providers}


@router.get("/llm-presets")
async def get_llm_presets():
    """返回所有 LLM 提供商预设分类列表，供前端展示使用"""
    return {"categories": LLM_PROVIDER_CATEGORIES}


@router.get("/required-check")
async def check_required_config(request: Request):
    """检查必配项状态：搜索工具（至少一个）、邮箱配置"""
    cfg = request.app.state.config

    # 搜索工具：serper / brave / baidu / tavily 至少配一个
    search_keys = [
        "tools.serper_search.api_key",
        "tools.brave_search.api_key",
        "tools.baidu_search.api_key",
        "tools.tavily_search.api_key",
    ]
    search_configured = any(
        bool(cfg.get(k, "")) and not str(cfg.get(k, "")).startswith("${")
        for k in search_keys
    )

    # 邮箱：enabled + smtp_host + username 都有值
    email_enabled = cfg.get("tools.email.enabled", False)
    email_smtp = cfg.get("tools.email.smtp_host", "")
    email_user = cfg.get("tools.email.username", "")
    email_configured = bool(email_enabled and email_smtp and email_user)

    return {
        "search_tool": {
            "configured": search_configured,
            "message": "搜索工具未配置（serper/brave/baidu/tavily 至少需要配置一个）",
        },
        "email": {
            "configured": email_configured,
            "message": "邮箱未配置（需要配置 SMTP/IMAP 信息）",
        },
    }


@router.post("/list-models")
async def list_models(body: ListModelsBody):
    """通过 OpenAI 兼容的 GET /models 接口获取可用模型列表"""
    try:
        logger.debug("List models request: provider=%s base_url=%s", body.provider, body.base_url)
        if body.provider in ("anthropic", "anthropic-compatible"):
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
        if provider in ("anthropic", "anthropic-compatible"):
            result = await _test_anthropic(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
                max_tokens=body.max_tokens,
                max_output_tokens=body.max_output_tokens,
            )
            return {"success": True, **result}
        if provider in ("gemini", "gemini-compatible"):
            result = await _test_gemini(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
                max_tokens=body.max_tokens,
                max_output_tokens=body.max_output_tokens,
            )
            return {"success": True, **result}
        if provider in ("openai", "openai-compatible"):
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
                max_tokens=body.max_tokens,
                max_output_tokens=body.max_output_tokens,
            )
            return {"success": True, **result}
        else:
            # 未知 provider 类型，尝试 OpenAI 兼容方式
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
                max_tokens=body.max_tokens,
                max_output_tokens=body.max_output_tokens,
            )
            return {"success": True, **result}
    except Exception as e:
        logger.warning("LLM test failed: %s", e)
        return {"success": False, "error": str(e)}


async def _test_openai_compatible(
    api_key: str,
    base_url: str,
    model_id: str,
    max_tokens: int,
    max_output_tokens: int,
) -> dict:
    """通过 OpenAI SDK 测试连通性"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        max_tokens=max_tokens,
        extra_body={"max_output_tokens": max_output_tokens},
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_anthropic(
    api_key: str,
    base_url: str,
    model_id: str,
    max_tokens: int,
    max_output_tokens: int,
) -> dict:
    """通过 Anthropic SDK 测试连通性"""
    _ = max_output_tokens
    import anthropic
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.messages.create(
        model=model_id,
        messages=[{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        max_tokens=max_tokens,
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_gemini(
    api_key: str,
    base_url: str,
    model_id: str,
    max_tokens: int,
    max_output_tokens: int,
) -> dict:
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
        messages=[{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        max_tokens=max_tokens,
        extra_body={"max_output_tokens": max_output_tokens},
    )
    return {"model": response.model, "message": "连接成功"}
