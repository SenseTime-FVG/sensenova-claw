"""CLI 交互式 LLM 配置引导单元测试"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch

from agentos.app.cli.llm_setup import _write_config, run_llm_setup_sync
from agentos.platform.secrets.store import InMemorySecretStore


def test_write_config_creates_file(tmp_path):
    """测试 _write_config 在文件不存在时能正确创建文件并写入配置"""
    config_path = tmp_path / "config.yml"
    secret_store = InMemorySecretStore()
    _write_config(
        config_path=config_path,
        provider_key="qwen",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_key="qwen-plus",
        model_id="qwen-plus",
        category_key="openai_compatible",
        secret_store=secret_store,
    )
    assert config_path.exists()
    data = yaml.safe_load(config_path.read_text())
    # OpenAI 兼容提供商统一用 "openai" 作为存储键
    assert data["llm"]["providers"]["openai"]["api_key"] == "${secret:agentos/llm.providers.openai.api_key}"
    assert secret_store.get("agentos/llm.providers.openai.api_key") == "sk-test"
    assert data["llm"]["default_model"] == "qwen-plus"
    assert data["agent"]["model"] == "qwen-plus"


def test_write_config_preserves_existing(tmp_path):
    """测试 _write_config 不会覆盖已有配置的其他字段"""
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({"tools": {"bash_command": {"enabled": True}}}))
    secret_store = InMemorySecretStore()
    _write_config(
        config_path=config_path,
        provider_key="anthropic",
        api_key="sk-ant",
        base_url="https://api.anthropic.com",
        model_key="claude-sonnet",
        model_id="claude-sonnet-4-6",
        category_key="anthropic",
        secret_store=secret_store,
    )
    data = yaml.safe_load(config_path.read_text())
    # 已有配置被保留
    assert data["tools"]["bash_command"]["enabled"] is True
    # 新配置被写入（anthropic 分类用 "anthropic" 作为存储键）
    assert data["llm"]["providers"]["anthropic"]["api_key"] == "${secret:agentos/llm.providers.anthropic.api_key}"
    assert secret_store.get("agentos/llm.providers.anthropic.api_key") == "sk-ant"
    assert data["llm"]["default_model"] == "claude-sonnet"
    assert data["agent"]["model"] == "claude-sonnet"


def test_write_config_model_entry(tmp_path):
    """测试 _write_config 正确写入 llm.models 条目"""
    config_path = tmp_path / "config.yml"
    secret_store = InMemorySecretStore()
    _write_config(
        config_path=config_path,
        provider_key="deepseek",
        api_key="sk-ds",
        base_url="https://api.deepseek.com/v1",
        model_key="deepseek_chat",
        model_id="deepseek-chat",
        category_key="openai_compatible",
        secret_store=secret_store,
    )
    data = yaml.safe_load(config_path.read_text())
    model_entry = data["llm"]["models"]["deepseek_chat"]
    assert model_entry["provider"] == "openai"  # openai_compatible 统一用 openai
    assert model_entry["model_id"] == "deepseek-chat"


def test_write_config_anthropic_provider_key(tmp_path):
    """测试 Anthropic 分类使用 anthropic 作为 provider 存储键"""
    config_path = tmp_path / "config.yml"
    secret_store = InMemorySecretStore()
    _write_config(
        config_path=config_path,
        provider_key="anthropic",
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        model_key="claude_3_5_sonnet",
        model_id="claude-3-5-sonnet-20241022",
        category_key="anthropic",
        secret_store=secret_store,
    )
    data = yaml.safe_load(config_path.read_text())
    assert "anthropic" in data["llm"]["providers"]
    assert data["llm"]["models"]["claude_3_5_sonnet"]["provider"] == "anthropic"


def test_write_config_gemini_provider_key(tmp_path):
    """测试 Gemini 分类使用 gemini 作为 provider 存储键"""
    config_path = tmp_path / "config.yml"
    secret_store = InMemorySecretStore()
    _write_config(
        config_path=config_path,
        provider_key="gemini",
        api_key="AIza-test",
        base_url="https://generativelanguage.googleapis.com",
        model_key="gemini_2_0_flash",
        model_id="gemini-2.0-flash",
        category_key="gemini",
        secret_store=secret_store,
    )
    data = yaml.safe_load(config_path.read_text())
    assert "gemini" in data["llm"]["providers"]
    assert data["llm"]["models"]["gemini_2_0_flash"]["provider"] == "gemini"


def test_run_llm_setup_skip(tmp_path):
    """测试用户选择跳过时返回 False，不创建配置文件"""
    config_path = tmp_path / "config.yml"
    # LLM_PROVIDER_CATEGORIES 有 3 个分类，第 4 个选项是"跳过配置"
    with patch("agentos.app.cli.llm_setup.input", side_effect=["4"]):
        result = run_llm_setup_sync(config_path)
    assert result is False


def test_run_llm_setup_empty_api_key(tmp_path):
    """测试 API Key 为空时返回 False，不写配置"""
    config_path = tmp_path / "config.yml"
    # 选 OpenAI 兼容(1) -> 选 OpenAI(1) -> Base URL 默认 -> 空 API Key
    with patch("agentos.app.cli.llm_setup.input", side_effect=["1", "1", "", ""]):
        result = run_llm_setup_sync(config_path)
    assert result is False
    assert not config_path.exists()


def test_run_llm_setup_complete_flow(tmp_path):
    """测试完整流程：选择 OpenAI 兼容 -> qwen -> 默认 URL -> API Key -> 手动输入模型"""
    config_path = tmp_path / "config.yml"
    # 选 OpenAI 兼容(1) -> 通义千问(2) -> 默认 Base URL(空) -> API Key -> 手动输入 qwen-max
    with patch("agentos.app.cli.llm_setup.input", side_effect=["1", "2", "", "sk-qwen-test", "qwen-max"]):
        result = run_llm_setup_sync(config_path)
    assert result is True
    assert config_path.exists()
    data = yaml.safe_load(config_path.read_text())
    assert data["llm"]["providers"]["openai"]["api_key"] == "sk-qwen-test"
    assert data["llm"]["providers"]["openai"]["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert data["agent"]["model"] == "qwen_max"
