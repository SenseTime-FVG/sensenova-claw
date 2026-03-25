from __future__ import annotations

from pathlib import Path

from sensenova_claw.capabilities.skills.registry import SkillRegistry


def test_secret_config_bridge_skill_can_be_loaded_from_builtin_dir(tmp_path: Path) -> None:
    """验证内置 secret skill 可被 SkillRegistry 加载。"""
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".sensenova-claw" / "skills"

    registry = SkillRegistry(
        workspace_dir=tmp_path / "skills",
        builtin_dir=builtin_dir,
    )
    registry.load_skills({})

    skill = registry.get("secret-config-bridge")

    assert skill is not None
    assert "GET /api/config/secret" in skill.body
    assert "PUT /api/config/sections" in skill.body
    assert "tools.brave_search.api_key" in skill.body
    assert "优先读取对应 skill 目录下的 `secret.yml`" in skill.body
    assert "OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY" in skill.body
    assert "不要在最终回复中泄露 secret 明文" in skill.body


def test_openai_whisper_api_skill_has_secret_mapping_file() -> None:
    """验证示例 skill 已提供 secret.yml 映射。"""
    project_root = Path(__file__).resolve().parents[2]
    secret_file = (
        project_root
        / ".sensenova-claw"
        / "skills"
        / "openai-whisper-api"
        / "secret.yml"
    )

    assert secret_file.exists()
    assert (
        secret_file.read_text(encoding="utf-8").strip()
        == "OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY"
    )
