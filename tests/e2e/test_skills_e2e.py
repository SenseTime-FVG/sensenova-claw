"""
E2E 测试：验证 Skills 系统集成
"""
import tempfile
from pathlib import Path

from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder


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
        assert "## Skill Usage" in system_msg["content"]
        assert "当用户请求匹配到某个 skill 的名称或描述时" in system_msg["content"]
        assert "<available_skills>" in system_msg["content"]
        assert "<skill>" in system_msg["content"]
        assert "<name>test-skill</name>" in system_msg["content"]
        assert "<description>测试技能描述</description>" in system_msg["content"]
        assert f"<location>{skill_dir / 'SKILL.md'}</location>" in system_msg["content"]
        assert "test-skill" in system_msg["content"]


if __name__ == "__main__":
    test_skills_integration()


def test_research_union_builtin_skills_in_prompt():
    """验证内置 research-union / union-search-plus 能被注入 prompt。"""
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".sensenova-claw" / "skills"

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SkillRegistry(
            workspace_dir=Path(tmpdir),
            builtin_dir=builtin_dir,
        )
        registry.load_skills({})

        builder = ContextBuilder(skill_registry=registry)
        messages = builder.build_messages("请做一次深度调研")
        system_msg = messages[0]["content"]

        assert "research-union" in system_msg
        assert "union-search-plus" in system_msg


def test_mineru_choice_builtin_skill_in_prompt():
    """验证内置 mineru 渠道选择 skill 能被注入 prompt。"""
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".sensenova-claw" / "skills"

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SkillRegistry(
            workspace_dir=Path(tmpdir),
            builtin_dir=builtin_dir,
        )
        registry.load_skills({})

        builder = ContextBuilder(skill_registry=registry)
        messages = builder.build_messages("请帮我解析这个 PDF")
        system_msg = messages[0]["content"]

        assert "<name>mineru-document-extractor-choice</name>" in system_msg
        assert "MinerU" in system_msg
