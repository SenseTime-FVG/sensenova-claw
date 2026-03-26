from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sensenova_claw.capabilities.tools.secret_tools import GetSecretTool, WriteSecretTool


@pytest.fixture
def secret_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    monkeypatch.setenv("SENSENOVA_SECRET_TOOLS_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("SENSENOVA_SECRET_TOOLS_DISABLE_KEYRING", "1")
    return secret_file


@pytest.mark.asyncio
async def test_write_secret_tool_writes_normalized_ref(secret_env: Path) -> None:
    tool = WriteSecretTool()

    result = await tool.execute(
        path="skills.code-review.REVIEW_API_KEY",
        value="review-secret-1",
    )

    assert result == {
        "ok": True,
        "path": "skills.code-review.REVIEW_API_KEY",
        "ref": "sensenova_claw/skills.code-review.REVIEW_API_KEY",
    }

    stored = yaml.safe_load(secret_env.read_text(encoding="utf-8"))
    assert stored == {
        "sensenova_claw/skills.code-review.REVIEW_API_KEY": "review-secret-1",
    }


@pytest.mark.asyncio
async def test_get_secret_tool_supports_secret_prefix(secret_env: Path) -> None:
    secret_env.parent.mkdir(parents=True, exist_ok=True)
    secret_env.write_text(
        yaml.dump(
            {
                "sensenova_claw/tools.brave_search.api_key": "brave-secret-2",
            },
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    tool = GetSecretTool()

    result = await tool.execute(path="secret:tools.brave_search.api_key")

    assert result == {
        "ok": True,
        "path": "tools.brave_search.api_key",
        "ref": "sensenova_claw/tools.brave_search.api_key",
        "value": "brave-secret-2",
    }


@pytest.mark.asyncio
async def test_secret_tools_reject_invalid_path(secret_env: Path) -> None:
    tool = GetSecretTool()

    with pytest.raises(ValueError, match="不支持的 secret path"):
        await tool.execute(path="agent.model")
