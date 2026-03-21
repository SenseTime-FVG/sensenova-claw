"""
LLM 提供商预设配置模块

提供各主流 LLM 提供商的默认配置，供 CLI 和 Web 前端使用。
"""

from typing import Optional


# 每个模型的结构：{"key": str, "model_id": str}
# 每个提供商的结构：{"key": str, "label": str, "base_url": str, "models": list}
# 每个分类的结构：{"key": str, "label": str, "providers": list}

LLM_PROVIDER_CATEGORIES = [
    {
        "key": "openai_compatible",
        "label": "OpenAI 兼容",
        "providers": [
            {
                "key": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "models": [],
            },
            {
                "key": "qwen",
                "label": "通义千问(Qwen)",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": [],
            },
            {
                "key": "zhipu",
                "label": "智谱GLM(Zhipu)",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "models": [],
            },
            {
                "key": "minimax",
                "label": "MiniMax",
                "base_url": "https://api.minimax.chat/v1",
                "models": [],
            },
            {
                "key": "deepseek",
                "label": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "models": [],
            },
            {
                "key": "custom_openai",
                "label": "其他（自定义）",
                "base_url": "",
                "models": [],
            },
        ],
    },
    {
        "key": "anthropic",
        "label": "Anthropic (Claude)",
        "providers": [
            {
                "key": "anthropic",
                "label": "Anthropic",
                "base_url": "https://api.anthropic.com",
                "models": [],
            },
        ],
    },
    {
        "key": "gemini",
        "label": "Google Gemini",
        "providers": [
            {
                "key": "gemini",
                "label": "Google Gemini",
                "base_url": "https://generativelanguage.googleapis.com",
                "models": [],
            },
        ],
    },
]


def get_all_providers() -> list[dict]:
    """
    返回所有提供商的扁平列表，每个条目附带其所属分类信息。

    返回格式：
    [
        {
            "key": "openai",
            "label": "OpenAI",
            "base_url": "...",
            "models": [...],
            "category_key": "openai_compatible",
            "category_label": "OpenAI 兼容",
        },
        ...
    ]
    """
    result = []
    for category in LLM_PROVIDER_CATEGORIES:
        for provider in category["providers"]:
            result.append(
                {
                    **provider,
                    "category_key": category["key"],
                    "category_label": category["label"],
                }
            )
    return result


def get_provider(provider_key: str) -> Optional[dict]:
    """
    按 key 查找单个提供商，附带其分类信息。

    :param provider_key: 提供商 key，如 "openai"、"deepseek"
    :return: 提供商信息字典（含 category_key/category_label），未找到返回 None
    """
    for provider in get_all_providers():
        if provider["key"] == provider_key:
            return provider
    return None


def check_llm_configured(config_data: dict) -> tuple[bool, list[str]]:
    """
    检查配置中是否存在至少一个非 mock 的提供商并配置了真实 API key。

    有效的 API key 定义为：非空字符串，且不以 "${" 开头（未解析的环境变量占位符）。

    :param config_data: 配置字典，结构同 config.yml 加载后的 dict
    :return: (is_configured, configured_provider_keys)
        - is_configured: 是否已配置
        - configured_provider_keys: 已配置的提供商 key 列表
    """
    configured = []

    llm_section = config_data.get("llm", {})
    providers_section = llm_section.get("providers", {})

    # 遍历所有非 mock 提供商，检查 api_key 是否有效
    all_provider_keys = {p["key"] for p in get_all_providers()}

    for provider_key, provider_cfg in providers_section.items():
        # 跳过 mock 提供商
        if provider_key == "mock":
            continue
        # 只检查预设中已知的提供商
        if provider_key not in all_provider_keys:
            continue
        if not isinstance(provider_cfg, dict):
            continue

        api_key = provider_cfg.get("api_key", "")
        if not isinstance(api_key, str):
            continue

        # 有效 key：非空且不是未解析的环境变量占位符
        if api_key and not api_key.startswith("${"):
            configured.append(provider_key)

    return (len(configured) > 0, configured)
