"""B06: Config 加载 + 环境变量替换"""
import os
from pathlib import Path
from agentos.platform.config.config import Config, DEFAULT_CONFIG


class TestConfig:
    def test_default_values(self, tmp_path):
        """无 config.yml 时使用默认值"""
        cfg = Config(config_path=tmp_path / "nonexist.yml")
        assert cfg.get("agent.model") == "mock"
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
