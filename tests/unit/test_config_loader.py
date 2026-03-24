"""配置加载测试

使用 /tmp 下的隔离目录，避免 pytest tmp_path 位于项目目录内
导致 Config 向上遍历时加载到真实 config.yml。
"""
from __future__ import annotations

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

    cfg = Config(project_root=backend_dir, user_config_dir=isolated_tmp / "no_user_config")

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

    cfg = Config(project_root=backend_dir, user_config_dir=isolated_tmp / "no_user_config")
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
