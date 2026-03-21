"""Secret 引用解析单测。"""

import pytest

from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref, parse_secret_ref


def test_is_secret_ref_true_for_valid_placeholder():
    assert is_secret_ref("${secret:agentos/tools.serper_search.api_key}") is True


def test_is_secret_ref_false_for_env_placeholder():
    assert is_secret_ref("${OPENAI_API_KEY}") is False


def test_parse_secret_ref_returns_inner_ref():
    assert parse_secret_ref("${secret:agentos/llm.providers.openai.api_key}") == (
        "agentos/llm.providers.openai.api_key"
    )


def test_parse_secret_ref_rejects_invalid_value():
    with pytest.raises(ValueError, match="非法 secret 引用"):
        parse_secret_ref("${OPENAI_API_KEY}")


def test_build_secret_ref_wraps_ref():
    assert build_secret_ref("agentos/plugins.feishu.app_secret") == (
        "${secret:agentos/plugins.feishu.app_secret}"
    )
