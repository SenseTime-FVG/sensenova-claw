"""配置加载测试

使用 /tmp 下的隔离目录，避免 pytest tmp_path 位于项目目录内
导致 Config 向上遍历时加载到真实 config.yml。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from sensenova_claw.platform.config.config import Config


@pytest.fixture()
def isolated_tmp():
    """创建 /tmp 下的隔离临时目录"""
    d = Path(tempfile.mkdtemp(prefix="sensenova_claw_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_load_parent_project_and_legacy_config(isolated_tmp: Path) -> None:
    root = isolated_tmp / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".sensenova-claw").mkdir(parents=True)
    (root / ".sensenova-claw" / "config.yaml").write_text(
        "agent:\n  model: gpt-5.4\n",
        encoding="utf-8",
    )

    (root / "config.yml").write_text(
        "OPENAI_BASE_URL: https://api.example.com/v1\n"
        "OPENAI_API_KEY: sk-test\n"
        "SERPER_API_KEY: serper-test\n",
        encoding="utf-8",
    )

    cfg = Config(
        project_root=backend_dir,
        user_config_dir=isolated_tmp / "no_user_config",
    )

    assert cfg.get("agent.model") == "gpt-5.4"
    assert cfg.get("llm.providers.openai.base_url") == "https://api.example.com/v1"
    assert cfg.get("llm.providers.openai.api_key") == "sk-test"
    assert cfg.get("tools.serper_search.api_key") == "serper-test"


def test_nearer_project_config_overrides_parent(isolated_tmp: Path) -> None:
    root = isolated_tmp / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".sensenova-claw").mkdir(parents=True)
    (root / ".sensenova-claw" / "config.yaml").write_text(
        "agent:\n  model: gpt-5.4\n",
        encoding="utf-8",
    )

    (backend_dir / ".sensenova-claw").mkdir(parents=True)
    (backend_dir / ".sensenova-claw" / "config.yaml").write_text(
        "agent:\n  model: mock\n",
        encoding="utf-8",
    )

    cfg = Config(
        project_root=backend_dir,
        user_config_dir=isolated_tmp / "no_user_config",
    )
    assert cfg.get("agent.model") == "mock"


def test_legacy_openai_key_enables_openai_provider(isolated_tmp: Path) -> None:
    root = isolated_tmp / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / "config.yml").write_text(
        "OPENAI_API_KEY: sk-test\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=isolated_tmp / "no_user_config")

    assert cfg.get("llm.default_model") == "gpt-5.4"
    assert cfg.get("agent.model") == "gpt-5.4"
    assert cfg.get("llm.providers.openai.api_key") == "sk-test"


def test_legacy_openai_key_does_not_override_explicit_model(isolated_tmp: Path) -> None:
    root = isolated_tmp / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".sensenova-claw").mkdir(parents=True)
    (root / ".sensenova-claw" / "config.yaml").write_text(
        "llm:\n  default_model: mock\nagent:\n  model: mock\n",
        encoding="utf-8",
    )
    (root / "config.yml").write_text(
        "OPENAI_API_KEY: sk-test\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=isolated_tmp / "no_user_config")

    assert cfg.get("llm.default_model") == "mock"
    assert cfg.get("agent.model") == "mock"


def test_config_uses_env_home_for_default_config_path(isolated_tmp: Path) -> None:
    custom_home = isolated_tmp / "custom-home"
    custom_home.mkdir(parents=True)
    config_file = custom_home / "config.yml"
    config_file.write_text("server:\n  port: 9001\n", encoding="utf-8")

    previous_home = os.environ.get("SENSENOVA_CLAW_HOME")
    os.environ["SENSENOVA_CLAW_HOME"] = str(custom_home)
    try:
        cfg = Config()
    finally:
        if previous_home is None:
            os.environ.pop("SENSENOVA_CLAW_HOME", None)
        else:
            os.environ["SENSENOVA_CLAW_HOME"] = previous_home

    assert cfg.get("server.port") == 9001


def test_resolve_model_only_accepts_model_key_without_model_id_fallback(isolated_tmp: Path) -> None:
    root = isolated_tmp / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    config_path = root / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      source_type: openai\n"
        "      api_key: sk-test\n"
        "  models:\n"
        "    alias-model:\n"
        "      provider: openai\n"
        "      model_id: actual-model-id\n"
        "    empty-model-id:\n"
        "      provider: openai\n"
        "      model_id: ''\n"
        "  default_model: alias-model\n",
        encoding="utf-8",
    )

    cfg = Config(config_path=config_path)

    assert cfg.resolve_model("alias-model") == ("openai", "actual-model-id")
    assert cfg.resolve_model("actual-model-id") == ("mock", "")
    assert cfg.resolve_model("missing-model") == ("mock", "")
    assert cfg.resolve_model("empty-model-id") == ("openai", "")
    assert cfg.get_model_max_output_tokens("actual-model-id") == 16384
    assert cfg.get_model_extra_body("actual-model-id") == {}
