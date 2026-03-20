"""Secret 路径注册表单测。"""

from agentos.platform.secrets.registry import is_secret_path


def test_is_secret_path_matches_llm_provider_api_key():
    assert is_secret_path("llm.providers.openai.api_key") is True


def test_is_secret_path_matches_tool_api_key():
    assert is_secret_path("tools.serper_search.api_key") is True


def test_is_secret_path_matches_specific_plugin_secret():
    assert is_secret_path("plugins.feishu.app_secret") is True


def test_is_secret_path_rejects_non_secret_field():
    assert is_secret_path("plugins.feishu.enabled") is False
