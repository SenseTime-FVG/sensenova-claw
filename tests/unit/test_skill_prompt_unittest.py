"""Skills prompt 注入回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sensenova_claw.capabilities.skills.registry import Skill, SkillRegistry
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder


class TestSkillPromptInstructions(unittest.TestCase):
    def test_system_prompt_injects_ppt_confirmation_first_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "ppt-superpower"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: ppt-superpower\ndescription: PPT orchestration\n---\nbody",
                encoding="utf-8",
            )

            registry = SkillRegistry(workspace_dir=Path(tmpdir) / "workspace-skills")
            registry.register(Skill("ppt-superpower", "PPT orchestration", "body", skill_dir))

            messages = ContextBuilder(skill_registry=registry).build_messages("做一个 PPT")
            sys_prompt = messages[0]["content"]

            self.assertIn("先用 read_file 读取", sys_prompt)
            self.assertIn(
                "PPT 默认进入确认优先路径；除非用户明确授权自动继续，否则不要默认走 fast。",
                sys_prompt,
            )


if __name__ == "__main__":
    unittest.main()
