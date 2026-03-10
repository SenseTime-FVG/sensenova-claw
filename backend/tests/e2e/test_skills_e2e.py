"""
E2E 测试：验证 Skills 系统集成
"""
from pathlib import Path
from app.skills.registry import SkillRegistry
from app.runtime.context_builder import ContextBuilder


def test_skills_integration():
    """测试 Skills 系统与 ContextBuilder 集成"""
    # 使用内置 skills 目录
    skills_dir = Path(__file__).parent.parent / "app" / "skills"

    # 初始化 SkillRegistry
    registry = SkillRegistry(workspace_dir=skills_dir)
    registry.load_skills({})

    skills = registry.get_all()
    print(f"Loaded {len(skills)} skills")

    # 初始化 ContextBuilder
    builder = ContextBuilder(skill_registry=registry)

    # 构建消息
    messages = builder.build_messages("test input")

    # 验证 system prompt 包含 skills
    system_msg = messages[0]
    assert system_msg["role"] == "system"
    assert "<available_skills>" in system_msg["content"]

    print("Skills injected to system prompt")
    print(f"System prompt length: {len(system_msg['content'])} chars")

    # 显示前几个 skills
    for skill in skills[:3]:
        print(f"  - {skill.name}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_skills_integration()
