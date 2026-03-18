from __future__ import annotations

from pathlib import Path

from agentos.platform.config.config import Config


def test_load_parent_project_and_legacy_config(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".agentos").mkdir(parents=True)
    (root / ".agentos" / "config.yaml").write_text(
        "agent:\n  provider: openai\n",
        encoding="utf-8",
    )

    (root / "config.yml").write_text(
        "OPENAI_BASE_URL: https://api.example.com/v1\n"
        "OPENAI_API_KEY: sk-test\n"
        "SERPER_API_KEY: serper-test\n",
        encoding="utf-8",
    )

    # user_config_dir 指向空目录，避免加载真实用户配置
    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")

    assert cfg.get("agent.provider") == "openai"
    assert cfg.get("agent.default_model") == "gpt-4o-mini"
    assert cfg.get("llm_providers.openai.base_url") == "https://api.example.com/v1"
    assert cfg.get("llm_providers.openai.api_key") == "sk-test"
    assert cfg.get("tools.serper_search.api_key") == "serper-test"


def test_legacy_search_api_keys_are_mapped(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / "config.yml").write_text(
        "BRAVE_SEARCH_API_KEY: brave-test\n"
        "BAIDU_APPBUILDER_API_KEY: baidu-test\n"
        "TAVILY_API_KEY: tavily-test\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")

    assert cfg.get("tools.brave_search.api_key") == "brave-test"
    assert cfg.get("tools.baidu_search.api_key") == "baidu-test"
    assert cfg.get("tools.tavily_search.api_key") == "tavily-test"


def test_nearer_project_config_overrides_parent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".agentos").mkdir(parents=True)
    (root / ".agentos" / "config.yaml").write_text(
        "agent:\n  provider: openai\n",
        encoding="utf-8",
    )

    (backend_dir / ".agentos").mkdir(parents=True)
    (backend_dir / ".agentos" / "config.yaml").write_text(
        "agent:\n  provider: mock\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")
    assert cfg.get("agent.provider") == "mock"
    assert cfg.get("agent.default_model") == "mock-agent-v1"


def test_legacy_openai_key_enables_openai_provider_without_project_config(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / "config.yml").write_text(
        "OPENAI_API_KEY: sk-test\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")

    assert cfg.get("agent.provider") == "openai"
    assert cfg.get("agent.default_model") == "gpt-4o-mini"
    assert cfg.get("llm_providers.openai.api_key") == "sk-test"


def test_legacy_openai_key_does_not_override_explicit_provider(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / ".agentos").mkdir(parents=True)
    (root / ".agentos" / "config.yaml").write_text(
        "agent:\n  provider: mock\n",
        encoding="utf-8",
    )
    (root / "config.yml").write_text(
        "OPENAI_API_KEY: sk-test\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")

    assert cfg.get("agent.provider") == "mock"
    assert cfg.get("agent.default_model") == "mock-agent-v1"


def test_legacy_model_is_applied_to_openai_and_agent_model(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)

    (root / "config.yml").write_text(
        "OPENAI_API_KEY: sk-test\n"
        "MODEL: gpt-5.2\n",
        encoding="utf-8",
    )

    cfg = Config(project_root=backend_dir, user_config_dir=tmp_path / "no_user_config")

    assert cfg.get("agent.provider") == "openai"
    assert cfg.get("agent.default_model") == "gpt-5.2"
    assert cfg.get("llm_providers.openai.default_model") == "gpt-5.2"
