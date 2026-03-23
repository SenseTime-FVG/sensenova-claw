"""B06: Config 加载 + 环境变量替换"""
import os
from pathlib import Path
from agentos.platform.config.config import Config, DEFAULT_CONFIG


class TestConfig:
    def test_default_values(self, tmp_path):
        """无 config.yml 时使用默认值"""
        cfg = Config(config_path=tmp_path / "nonexist.yml")
        assert cfg.get("llm.default_model") == "mock"
        assert cfg.get("server.port") == 8000

    def test_get_nested(self, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexist.yml")
        assert cfg.get("tools.bash_command.enabled") is True
        assert cfg.get("tools.bash_command.timeout") == 15

    def test_get_default(self, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexist.yml")
        assert cfg.get("nonexist.key", "fallback") == "fallback"

    def test_env_substitution(self, tmp_path):
        yml = tmp_path / "config.yml"
        yml.write_text(
            "OPENAI_API_KEY: ${TEST_AGENTOS_KEY}\n"
            "agent:\n  model: gpt-5.4\n",
            encoding="utf-8",
        )
        os.environ["TEST_AGENTOS_KEY"] = "sk-test-123"
        try:
            cfg = Config(config_path=yml)
            assert cfg.get("OPENAI_API_KEY") == "sk-test-123"
        finally:
            os.environ.pop("TEST_AGENTOS_KEY", None)

    def test_env_substitution_still_works_with_secret_store(self, tmp_path):
        yml = tmp_path / "config.yml"
        yml.write_text("OPENAI_API_KEY: ${TEST_AGENTOS_KEY}\n", encoding="utf-8")
        os.environ["TEST_AGENTOS_KEY"] = "sk-test-env-secret"
        try:
            cfg = Config(config_path=yml, secret_store=object())
            assert cfg.get("OPENAI_API_KEY") == "sk-test-env-secret"
        finally:
            os.environ.pop("TEST_AGENTOS_KEY", None)

    def test_deep_merge(self, tmp_path):
        yml = tmp_path / "config.yml"
        yml.write_text(
            "agent:\n  model: gpt-5.4\n",
            encoding="utf-8",
        )
        cfg = Config(config_path=yml)
        # 用户覆盖的值
        assert cfg.get("agent.model") == "gpt-5.4"
        # 默认值保留
        assert cfg.get("agent.temperature") == 0.2

    def test_set_runtime(self, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexist.yml")
        cfg.set("agent.model", "claude-opus")
        assert cfg.get("agent.model") == "claude-opus"

    def test_get_model_extra_body(self, tmp_path):
        yml = tmp_path / "config.yml"
        yml.write_text(
            "llm:\n"
            "  models:\n"
            "    o3:\n"
            "      provider: openai\n"
            "      model_id: o3\n"
            "      extra_body:\n"
            "        reasoning_effort: high\n"
            "    gpt-4o:\n"
            "      provider: openai\n"
            "      model_id: gpt-4o\n",
            encoding="utf-8",
        )
        cfg = Config(config_path=yml)
        # 有 extra_body 的模型
        assert cfg.get_model_extra_body("o3") == {"reasoning_effort": "high"}
        # 无 extra_body 的模型
        assert cfg.get_model_extra_body("gpt-4o") == {}
        # 不存在的模型
        assert cfg.get_model_extra_body("nonexist") == {}

    def test_get_model_extra_body_nested(self, tmp_path):
        yml = tmp_path / "config.yml"
        yml.write_text(
            "llm:\n"
            "  models:\n"
            "    claude-thinking:\n"
            "      provider: anthropic\n"
            "      model_id: claude-opus-4-6\n"
            "      extra_body:\n"
            "        thinking:\n"
            "          type: adaptive\n",
            encoding="utf-8",
        )
        cfg = Config(config_path=yml)
        assert cfg.get_model_extra_body("claude-thinking") == {
            "thinking": {"type": "adaptive"}
        }
