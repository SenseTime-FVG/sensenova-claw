"""
LLM 预设配置模块单元测试
"""

import pytest
from agentos.platform.config.llm_presets import (
    LLM_PROVIDER_CATEGORIES,
    get_all_providers,
    get_provider,
    check_llm_configured,
)


class TestLLMProviderCategories:
    """测试 LLM_PROVIDER_CATEGORIES 数据结构"""

    def test_categories_exist(self):
        """确保三个分类都存在"""
        keys = [c["key"] for c in LLM_PROVIDER_CATEGORIES]
        assert "openai_compatible" in keys
        assert "anthropic" in keys
        assert "gemini" in keys

    def test_each_category_has_required_fields(self):
        """每个分类必须有 key、label、providers"""
        for category in LLM_PROVIDER_CATEGORIES:
            assert "key" in category
            assert "label" in category
            assert "providers" in category
            assert isinstance(category["providers"], list)
            assert len(category["providers"]) > 0

    def test_openai_compatible_providers(self):
        """openai_compatible 分类下应包含 6 个提供商（含自定义）"""
        category = next(c for c in LLM_PROVIDER_CATEGORIES if c["key"] == "openai_compatible")
        provider_keys = [p["key"] for p in category["providers"]]
        assert "openai" in provider_keys
        assert "qwen" in provider_keys
        assert "zhipu" in provider_keys
        assert "minimax" in provider_keys
        assert "deepseek" in provider_keys
        assert "custom_openai" in provider_keys
        assert len(category["providers"]) == 6

    def test_each_provider_has_required_fields(self):
        """每个提供商必须有 key、label、base_url、models"""
        for category in LLM_PROVIDER_CATEGORIES:
            for provider in category["providers"]:
                assert "key" in provider, f"provider 缺少 key: {provider}"
                assert "label" in provider, f"provider 缺少 label: {provider}"
                assert "base_url" in provider, f"provider 缺少 base_url: {provider}"
                assert "models" in provider, f"provider 缺少 models: {provider}"
                assert isinstance(provider["models"], list)

    def test_each_model_has_required_fields(self):
        """每个模型必须有 key 和 model_id"""
        for category in LLM_PROVIDER_CATEGORIES:
            for provider in category["providers"]:
                for model in provider["models"]:
                    assert "key" in model, f"model 缺少 key: {model}"
                    assert "model_id" in model, f"model 缺少 model_id: {model}"

    def test_default_base_urls(self):
        """检查各提供商的默认 base_url"""
        all_providers = get_all_providers()
        url_map = {p["key"]: p["base_url"] for p in all_providers}

        assert url_map["openai"] == "https://api.openai.com/v1"
        assert url_map["qwen"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert url_map["zhipu"] == "https://open.bigmodel.cn/api/paas/v4"
        assert url_map["minimax"] == "https://api.minimax.chat/v1"
        assert url_map["deepseek"] == "https://api.deepseek.com/v1"
        assert url_map["anthropic"] == "https://api.anthropic.com"
        assert url_map["gemini"] == "https://generativelanguage.googleapis.com"


class TestGetAllProviders:
    """测试 get_all_providers 函数"""

    def test_returns_flat_list(self):
        """返回值应是扁平列表"""
        providers = get_all_providers()
        assert isinstance(providers, list)

    def test_contains_all_providers(self):
        """扁平列表应包含所有提供商"""
        providers = get_all_providers()
        keys = [p["key"] for p in providers]
        expected_keys = ["openai", "qwen", "zhipu", "minimax", "deepseek", "custom_openai", "anthropic", "gemini"]
        for key in expected_keys:
            assert key in keys, f"缺少提供商: {key}"

    def test_total_provider_count(self):
        """总提供商数量应为 8"""
        providers = get_all_providers()
        assert len(providers) == 8

    def test_each_entry_has_category_info(self):
        """每个条目应附带 category_key 和 category_label"""
        providers = get_all_providers()
        for provider in providers:
            assert "category_key" in provider, f"缺少 category_key: {provider['key']}"
            assert "category_label" in provider, f"缺少 category_label: {provider['key']}"

    def test_openai_category_key(self):
        """OpenAI 提供商应属于 openai_compatible 分类"""
        providers = get_all_providers()
        openai = next(p for p in providers if p["key"] == "openai")
        assert openai["category_key"] == "openai_compatible"
        assert openai["category_label"] == "OpenAI 兼容"

    def test_anthropic_category_key(self):
        """Anthropic 提供商应属于 anthropic 分类"""
        providers = get_all_providers()
        anthropic = next(p for p in providers if p["key"] == "anthropic")
        assert anthropic["category_key"] == "anthropic"

    def test_gemini_category_key(self):
        """Gemini 提供商应属于 gemini 分类"""
        providers = get_all_providers()
        gemini = next(p for p in providers if p["key"] == "gemini")
        assert gemini["category_key"] == "gemini"

    def test_original_provider_data_preserved(self):
        """原始提供商字段（key、label、base_url、models）应被保留"""
        providers = get_all_providers()
        openai = next(p for p in providers if p["key"] == "openai")
        assert openai["label"] == "OpenAI"
        assert openai["base_url"] == "https://api.openai.com/v1"
        assert isinstance(openai["models"], list)


class TestGetProvider:
    """测试 get_provider 函数"""

    def test_found_existing_provider(self):
        """查找存在的提供商应返回完整信息"""
        provider = get_provider("openai")
        assert provider is not None
        assert provider["key"] == "openai"
        assert provider["label"] == "OpenAI"
        assert "base_url" in provider
        assert "models" in provider
        assert "category_key" in provider

    def test_found_deepseek(self):
        """查找 deepseek 提供商"""
        provider = get_provider("deepseek")
        assert provider is not None
        assert provider["key"] == "deepseek"
        assert provider["base_url"] == "https://api.deepseek.com/v1"

    def test_found_anthropic(self):
        """查找 anthropic 提供商"""
        provider = get_provider("anthropic")
        assert provider is not None
        assert provider["category_key"] == "anthropic"

    def test_not_found_returns_none(self):
        """查找不存在的提供商应返回 None"""
        result = get_provider("nonexistent_provider")
        assert result is None

    def test_not_found_mock(self):
        """mock 不在预设中，应返回 None"""
        result = get_provider("mock")
        assert result is None

    def test_not_found_empty_string(self):
        """空字符串 key 应返回 None"""
        result = get_provider("")
        assert result is None


class TestCheckLLMConfigured:
    """测试 check_llm_configured 函数"""

    def test_empty_config(self):
        """空配置应返回未配置"""
        is_configured, configured_keys = check_llm_configured({})
        assert is_configured is False
        assert configured_keys == []

    def test_no_providers_section(self):
        """llm 段缺少 providers 应返回未配置"""
        config = {"llm": {}}
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False

    def test_empty_api_key(self):
        """空 api_key 应视为未配置"""
        config = {
            "llm": {
                "providers": {
                    "openai": {"api_key": ""}
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False
        assert "openai" not in configured_keys

    def test_unresolved_env_var(self):
        """以 ${ 开头的 api_key（未解析环境变量）应视为未配置"""
        config = {
            "llm": {
                "providers": {
                    "openai": {"api_key": "${OPENAI_API_KEY}"}
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False
        assert "openai" not in configured_keys

    def test_real_api_key(self):
        """真实 api_key 应视为已配置"""
        config = {
            "llm": {
                "providers": {
                    "openai": {"api_key": "sk-real-api-key-12345"}
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is True
        assert "openai" in configured_keys

    def test_mock_provider_ignored(self):
        """mock 提供商应被忽略"""
        config = {
            "llm": {
                "providers": {
                    "mock": {"api_key": "any-key"}
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False
        assert "mock" not in configured_keys

    def test_multiple_providers_one_configured(self):
        """多个提供商中只有一个配置了真实 key"""
        config = {
            "llm": {
                "providers": {
                    "openai": {"api_key": "${OPENAI_API_KEY}"},
                    "deepseek": {"api_key": "sk-deepseek-real-key"},
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is True
        assert "deepseek" in configured_keys
        assert "openai" not in configured_keys

    def test_multiple_providers_all_configured(self):
        """多个提供商都配置了真实 key"""
        config = {
            "llm": {
                "providers": {
                    "openai": {"api_key": "sk-openai-key"},
                    "anthropic": {"api_key": "sk-ant-key"},
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is True
        assert "openai" in configured_keys
        assert "anthropic" in configured_keys
        assert len(configured_keys) == 2

    def test_unknown_provider_ignored(self):
        """不在预设中的提供商应被忽略"""
        config = {
            "llm": {
                "providers": {
                    "unknown_provider": {"api_key": "real-key-123"}
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False

    def test_non_dict_provider_config_ignored(self):
        """非 dict 类型的提供商配置应被忽略，不报错"""
        config = {
            "llm": {
                "providers": {
                    "openai": "invalid-config"
                }
            }
        }
        is_configured, configured_keys = check_llm_configured(config)
        assert is_configured is False

    def test_returns_tuple(self):
        """返回值应为 (bool, list) 元组"""
        result = check_llm_configured({})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)
