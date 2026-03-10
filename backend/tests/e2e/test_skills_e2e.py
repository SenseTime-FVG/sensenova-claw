"""
E2E 测试：验证 Skills 系统集成
"""
import tempfile
from pathlib import Path

from app.skills.registry import SkillRegistry
from app.runtime.context_builder import ContextBuilder


def test_skills_integration():
    """测试 Skills 系统与 ContextBuilder 集成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试用 skill（不依赖外部二进制）
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: 测试技能描述\n---\n这是测试技能内容\n",
            encoding="utf-8",
        )

        # 初始化 SkillRegistry
        registry = SkillRegistry(workspace_dir=Path(tmpdir))
        registry.load_skills({})

        skills = registry.get_all()
        assert len(skills) >= 1, f"Expected at least 1 skill, got {len(skills)}"

        # 初始化 ContextBuilder
        builder = ContextBuilder(skill_registry=registry)

        # 构建消息
        messages = builder.build_messages("test input")

        # 验证 system prompt 包含 skills
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "<available_skills>" in system_msg["content"]
        assert "test-skill" in system_msg["content"]


if __name__ == "__main__":
    test_skills_integration()
