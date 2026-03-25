"""PPT skill 体系契约测试。"""

from pathlib import Path
import unittest

from sensenova_claw.capabilities.skills.registry import SkillRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / ".sensenova-claw" / "skills"
DESIGN_DOC = PROJECT_ROOT / "docs" / "ppt-skills" / "design.md"


def _load_workspace_skills() -> dict[str, str]:
    registry = SkillRegistry(
        workspace_dir=PROJECT_ROOT / "pytest_tmp" / "no-workspace-skills",
        user_dir=PROJECT_ROOT / "pytest_tmp" / "no-user-skills",
        builtin_dir=SKILLS_DIR,
    )
    registry.load_skills({})
    return {skill.name: skill.body for skill in registry.get_all()}


class TestPptSkillSuite(unittest.TestCase):
    def test_ppt_skill_suite_replaced_with_new_architecture(self):
        skills = _load_workspace_skills()

        expected = {
            "ppt-superpower",
            "ppt-source-analysis",
            "ppt-task-pack",
            "ppt-research-pack",
            "ppt-template-pack",
            "ppt-style-spec",
            "ppt-storyboard",
            "ppt-asset-plan",
            "ppt-page-html",
            "ppt-speaker-notes",
            "ppt-review",
            "ppt-page-plan",
            "ppt-page-assets",
            "ppt-page-polish",
            "ppt-style-refine",
            "ppt-story-refine",
        }

        self.assertTrue(expected.issubset(skills.keys()))
        self.assertNotIn("pptx", skills)
        self.assertNotIn("ppt-outline-gen", skills)
        self.assertNotIn("ppt-style-extract", skills)
        self.assertNotIn("ppt-image-selection", skills)
        self.assertNotIn("ppt-html-gen", skills)

        body = skills["ppt-superpower"]
        for legacy_skill in {"pptx", "ppt-outline-gen", "ppt-style-extract", "ppt-image-selection", "ppt-html-gen"}:
            self.assertIn(f"`{legacy_skill}`", body)
        self.assertIn("不要再调用旧", body)

    def test_ppt_superpower_declares_default_required_artifacts(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("fast", body)
        self.assertIn("guided", body)
        self.assertIn("surgical", body)
        self.assertIn("style-spec.json", body)
        self.assertIn("storyboard.json", body)
        self.assertIn("默认必产", body)

    def test_ppt_superpower_declares_deck_directory_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("deck_dir", body)
        self.assertIn("query概述 + 时间戳", body)
        self.assertIn("不要把中间结果直接写到 agent 根目录", body)
        self.assertIn("pages/", body)
        self.assertIn("images/", body)

    def test_ppt_superpower_requires_subdirectories_initialized_up_front(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("创建 `deck_dir` 后", body)
        self.assertIn("立即创建 `pages/` 与 `images/`", body)

    def test_ppt_superpower_and_task_pack_define_canonical_deck_dir_reuse(self):
        skills = _load_workspace_skills()

        superpower = skills["ppt-superpower"]
        task_pack = skills["ppt-task-pack"]
        self.assertIn("后续所有 skill 都必须直接复用这个值", superpower)
        self.assertIn("不要手写、缩写、翻译或重拼目录名", superpower)
        self.assertIn("canonical 输出根目录", task_pack)
        self.assertIn("后续 skill 只能直接复制这个值", task_pack)

    def test_ppt_task_pack_captures_style_intent_signals(self):
        skills = _load_workspace_skills()

        body = skills["ppt-task-pack"]
        self.assertIn("风格意图", body)
        self.assertIn("场景", body)
        self.assertIn("气质", body)
        self.assertIn("行业语境", body)
        self.assertIn("如果用户已经明确给出风格偏好", body)

    def test_ppt_superpower_maps_outline_review_requests_to_guided_mode(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("先看大纲", body)
        self.assertIn("确认后再生成", body)
        self.assertIn("必须进入 `guided`", body)
        self.assertIn("不要直接生成 `pages/page_XX.html`", body)
        self.assertIn("不要只返回一段自由文本大纲", body)

    def test_ppt_superpower_declares_stage_feedback_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("阶段回显", body)
        self.assertIn("不要长时间沉默", body)
        self.assertIn("开始反馈", body)
        self.assertIn("完成反馈", body)
        self.assertIn("进行中反馈", body)
        self.assertIn("阻塞反馈", body)
        self.assertIn("`fast`", body)
        self.assertIn("`guided`", body)
        self.assertIn("`surgical`", body)

    def test_ppt_superpower_forces_task_pack_before_research_decision(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("必须先固定 `deck_dir`", body)
        self.assertIn("必须先生成 `task-pack.json`", body)
        self.assertIn("只有 `task-pack.json` 明确存在内容缺口时，才进入 `ppt-research-pack`", body)
        self.assertIn("不允许在 `task-pack` 之前做外部 research 决策", body)

    def test_ppt_task_pack_and_research_pack_coordinate_research_required_gate(self):
        skills = _load_workspace_skills()

        task_pack_body = skills["ppt-task-pack"]
        research_pack_body = skills["ppt-research-pack"]

        self.assertIn("research_required", task_pack_body)
        self.assertIn("必须先生成 `task-pack.json`", task_pack_body)
        self.assertIn("不允许在 `task-pack` 之前做外部 research 决策", task_pack_body)

        self.assertIn("必须先读取 `task-pack.json`", research_pack_body)
        self.assertIn("research_required", research_pack_body)
        self.assertIn("research 不是默认第一步", research_pack_body)
        self.assertIn("是否运行 research 取决于 `task-pack.json.research_required`", research_pack_body)

    def test_ppt_research_pack_treats_source_signals_as_task_pack_input(self):
        skills = _load_workspace_skills()

        task_pack_body = skills["ppt-task-pack"]
        research_pack_body = skills["ppt-research-pack"]

        self.assertIn("上传报告", research_pack_body)
        self.assertIn("主题涉及事实、数据、案例", research_pack_body)
        self.assertIn("需要把长文档整理成可用于分页叙事的研究结果", research_pack_body)
        self.assertIn("只是 `task-pack` 计算 `research_required` 的信号", research_pack_body)
        self.assertIn("先进入 `ppt-task-pack`", research_pack_body)
        self.assertIn("由 `task-pack.json.research_required` 决定是否进入 `ppt-research-pack`", research_pack_body)
        self.assertIn("research_required", task_pack_body)

    def test_ppt_task_pack_elevates_content_gap_assessment_to_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-task-pack"]

        self.assertIn("content_gap_assessment", body)
        self.assertIn("research_required", body)
        self.assertIn("research_needs", body)
        self.assertIn("class ResearchNeed", body)
        self.assertIn("topic: str", body)
        self.assertIn("reason: str", body)
        self.assertIn("scope: list[str]", body)
        self.assertIn("priority: str", body)

    def test_ppt_task_pack_separates_known_gaps_from_content_gap_assessment(self):
        skills = _load_workspace_skills()

        skill_body = skills["ppt-task-pack"]
        design = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("`known_gaps`", skill_body)
        self.assertIn("`content_gap_assessment`", skill_body)
        self.assertIn("`known_gaps` 保留", skill_body)
        self.assertIn("`content_gap_assessment` 负责", skill_body)
        self.assertIn("避免两个字段看起来重复", skill_body)

        self.assertIn("`known_gaps` 保留", design)
        self.assertIn("`content_gap_assessment` 负责", design)

    def test_ppt_research_pack_defines_pageworthy_content_pool_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-research-pack"]

        self.assertIn("class ResearchPack", body)
        self.assertIn("claims", body)
        self.assertIn("evidence_points", body)
        self.assertIn("pageworthy_chunks", body)
        self.assertIn("risks_or_uncertainties", body)

    def test_ppt_research_pack_defines_structured_research_pack_fields(self):
        skills = _load_workspace_skills()

        body = skills["ppt-research-pack"]

        self.assertIn("claims: list[Claim]", body)
        self.assertIn("evidence_points: list[EvidencePoint]", body)
        self.assertIn("pageworthy_chunks: list[PageworthyChunk]", body)
        self.assertIn("risks_or_uncertainties: list[str]", body)
        self.assertIn("`risks_or_uncertainties`", body)
        self.assertIn("信息缺口", body)
        self.assertIn("证据不确定性", body)

    def test_ppt_storyboard_declares_research_traceback_fields(self):
        skills = _load_workspace_skills()

        body = skills["ppt-storyboard"]

        self.assertIn("source_claim_ids: list[str]", body)
        self.assertIn("source_evidence_ids: list[str]", body)
        self.assertIn("unresolved_gaps: list[str]", body)
        self.assertIn("storyboard 是 research 的消费层", body)
        self.assertIn("不允许只拿 research 主题词重新写一遍", body)
        self.assertIn("每页必须能说明主 claim 和 evidence 从哪里来", body)
        self.assertIn("缺证据时要显式记录 `unresolved_gaps`", body)

    def test_ppt_design_doc_declares_storyboard_as_research_consumer(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("storyboard 是 research 的消费层", content)
        self.assertIn("source_claim_ids", content)
        self.assertIn("source_evidence_ids", content)
        self.assertIn("unresolved_gaps", content)
        self.assertIn("缺证据时要显式记录 `unresolved_gaps`", content)

    def test_key_ppt_skills_define_user_feedback_hooks(self):
        skills = _load_workspace_skills()

        for skill_name in [
            "ppt-source-analysis",
            "ppt-task-pack",
            "ppt-style-spec",
            "ppt-storyboard",
            "ppt-research-pack",
            "ppt-template-pack",
            "ppt-asset-plan",
            "ppt-page-html",
            "ppt-review",
            "ppt-page-plan",
            "ppt-page-assets",
            "ppt-page-polish",
            "ppt-style-refine",
            "ppt-story-refine",
            "ppt-export-pptx",
        ]:
            body = skills[skill_name]
            self.assertIn("开始反馈", body, msg=f"{skill_name} 缺少开始反馈")
            self.assertIn("完成反馈", body, msg=f"{skill_name} 缺少完成反馈")
            self.assertIn("下一步", body, msg=f"{skill_name} 缺少下一步说明")

    def test_ppt_design_doc_contains_skill_inventory_table(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("### 4.4 技能清单速览", content)
        self.assertIn("| Skill | 类型 | 触发时机 | 主要输入 | 主要产物 | 用户回显 |", content)
        self.assertIn("| `ppt-superpower` | 总控入口 |", content)
        self.assertIn("| `ppt-page-html` | 页面生成 |", content)
        self.assertIn("| `ppt-style-refine` | 全局风格修复 |", content)
        self.assertIn("| `ppt-review` | 结果审查 |", content)

    def test_ppt_design_doc_experiment_one_default_path_runs_task_pack_before_research(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("deck_dir -> task-pack -> research(按需) -> style-spec -> storyboard", content)
        self.assertIn("无上传文件时的最小路径", content)
        self.assertIn("有上传文件时的常规路径", content)

    def test_ppt_design_doc_treats_content_sources_as_task_pack_only_signals(self):
        skills = _load_workspace_skills()

        design = DESIGN_DOC.read_text(encoding="utf-8")
        research_body = skills["ppt-research-pack"]

        self.assertIn("上传报告、主题涉及事实 / 数据 / 案例、长文档整理等都只是 `task-pack` 判断 `research_required` 的信号", design)
        self.assertIn("先进入 `ppt-task-pack`", design)
        self.assertIn("由 `task-pack.json.research_required` 决定是否进入 `ppt-research-pack`", design)
        self.assertIn("上传报告、事实数据案例和长文档只是 `task-pack` 计算 `research_required` 的信号", research_body)
        self.assertIn("必须先读取 `task-pack.json`", research_body)
        self.assertIn("research 不是默认第一步", research_body)
        self.assertIn("是否运行 research 取决于 `task-pack.json.research_required`", research_body)

    def test_ppt_design_doc_marks_research_as_pageworthy_content_upstream(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("research 不是摘要，而是“可上页内容池”", content)
        self.assertIn("pageworthy chunks 是 storyboard 的上游输入", content)


if __name__ == "__main__":
    unittest.main()
