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

    def test_ppt_task_pack_defines_content_density_profile_contract(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-task-pack"]

        self.assertIn('ContentDensityProfile = Literal["analysis-heavy", "balanced", "showcase-light"]', body)
        self.assertIn("content_density_profile: ContentDensityProfile", body)
        self.assertIn("根据主题/场景选择默认 profile", body)
        self.assertIn("允许用户偏好覆盖", body)
        self.assertIn("analysis-heavy", body)
        self.assertIn("balanced", body)
        self.assertIn("showcase-light", body)

        self.assertIn("content_density_profile", design)
        self.assertIn("analysis-heavy", design)
        self.assertIn("balanced", design)
        self.assertIn("showcase-light", design)

    def test_ppt_task_pack_maps_theme_to_default_density_profile(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-task-pack"]

        self.assertIn("分析 / 汇报 / 评估类主题", body)
        self.assertIn("普通汇报 / 培训 / 项目介绍", body)
        self.assertIn("品牌 / 展示 / 活动 / 发布类主题", body)
        self.assertIn("用户明确要求更满或更克制时，可覆盖默认 profile", body)

        self.assertIn("分析 / 汇报 / 评估类主题", design)
        self.assertIn("普通汇报 / 培训 / 项目介绍", design)
        self.assertIn("品牌 / 展示 / 活动 / 发布类主题", design)
        self.assertIn("用户明确要求更满或更克制时，可覆盖默认 profile", design)

    def test_ppt_task_pack_keeps_density_contract_out_of_payload_budget_scope(self):
        skills = _load_workspace_skills()

        body = skills["ppt-task-pack"]

        self.assertIn("不要在这一轮引入 `payload_budget`", body)
        self.assertNotIn("payload_budget:", body)

    def test_ppt_superpower_maps_outline_review_requests_to_guided_mode(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("默认进入 `guided`", body)
        self.assertIn("确认优先", body)
        self.assertIn("先看大纲", body)
        self.assertIn("确认后再生成", body)
        self.assertIn("必须进入 `guided`", body)
        self.assertIn("不要直接生成 `pages/page_XX.html`", body)
        self.assertIn("不要只返回一段自由文本大纲", body)

    def test_ppt_superpower_requires_explicit_fast_opt_in(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("只有用户明确说", body)
        self.assertIn("直接生成", body)
        self.assertIn("不要确认", body)
        self.assertIn("自动继续", body)
        self.assertIn("一口气跑完", body)
        self.assertIn("才进入 `fast`", body)

    def test_ppt_superpower_waits_for_confirmation_after_default_artifacts(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("`task-pack.json`、`style-spec.json`、`storyboard.json` 后默认等待确认", body)

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

    def test_ppt_research_pack_declares_stable_traceback_ids(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-research-pack"]

        self.assertIn("claim_id: str", body)
        self.assertIn("evidence_id: str", body)
        self.assertIn("chunk_id: str", body)
        self.assertIn("稳定 ID", body)
        self.assertIn("供 storyboard 的 `source_claim_ids` / `source_evidence_ids` 回指", body)

        self.assertIn("claim_id", design)
        self.assertIn("evidence_id", design)
        self.assertIn("chunk_id", design)
        self.assertIn("供 storyboard 的 `source_claim_ids` / `source_evidence_ids` 回指", design)

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

    def test_ppt_storyboard_allows_empty_traceback_lists_without_research(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-storyboard"]

        self.assertIn("未触发 `research-pack` 时", body)
        self.assertIn("`source_claim_ids` 与 `source_evidence_ids` 应保留为空列表", body)
        self.assertIn("这是合法状态", body)

        self.assertIn("未触发 `research-pack` 时", design)
        self.assertIn("`source_claim_ids` 与 `source_evidence_ids` 应保留为空列表", design)
        self.assertIn("这是合法状态", design)

    def test_ppt_storyboard_separates_block_gaps_from_page_issues(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-storyboard"]

        self.assertIn("`unresolved_gaps` 只承接块级内容 / 证据 / claim 缺口", body)
        self.assertIn("`unresolved_issues` 只承接页级问题", body)
        self.assertIn("布局", body)
        self.assertIn("资产", body)
        self.assertIn("页级约束", body)

        self.assertIn("`unresolved_gaps` 只承接块级内容 / 证据 / claim 缺口", design)
        self.assertIn("`unresolved_issues` 只承接页级问题", design)

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

    def test_ppt_style_spec_explains_density_profile_as_capacity_strategy(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-style-spec"]

        self.assertIn("content_density_profile", body)
        self.assertIn("承载策略", body)
        self.assertIn("不是单纯视觉风格切换", body)
        self.assertIn("analysis-heavy", body)
        self.assertIn("balanced", body)
        self.assertIn("showcase-light", body)
        self.assertIn("只负责解释 profile，不重算默认 profile", body)
        self.assertNotIn("根据主题/场景选择默认 profile", body)
        self.assertNotIn("重算默认 profile", design)
        self.assertNotIn("payload_budget", body)
        self.assertIn("承载策略", design)
        self.assertIn("不是单纯视觉风格切换", design)

    def test_ppt_storyboard_defines_page_level_payload_budget_contract(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-storyboard"]

        self.assertIn("payload_budget", body)
        self.assertIn('payload_budget: "PayloadBudget"', body)
        self.assertIn("class PayloadBudget", body)
        self.assertIn("claim_count: int", body)
        self.assertIn("evidence_count: int", body)
        self.assertIn("structure_block_count: int", body)
        self.assertIn("require_comparison_or_summary: bool", body)
        self.assertIn("每页必须声明页级 `payload_budget`", body)

        self.assertIn("payload_budget", design)
        self.assertIn("class PayloadBudget", design)
        self.assertIn("每页必须声明页级 `payload_budget`", design)

    def test_ppt_storyboard_maps_density_profile_to_payload_budget(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-storyboard"]

        self.assertIn("content_density_profile", body)
        self.assertIn("analysis-heavy", body)
        self.assertIn("balanced", body)
        self.assertIn("showcase-light", body)
        self.assertIn("page_type", body)
        self.assertIn("narrative_role", body)
        self.assertIn("density_rules", body)
        self.assertIn("分析类页", body)
        self.assertIn("展示类页", body)
        self.assertIn("把 `content_density_profile` 转成可执行的 `payload_budget`", body)

        self.assertIn("content_density_profile", design)
        self.assertIn("把 `content_density_profile` 转成可执行的 `payload_budget`", design)
        self.assertIn("分析类页", design)
        self.assertIn("展示类页", design)

    def test_ppt_page_html_consumes_payload_budget_instead_of_collapsing_layout(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-page-html"]

        self.assertIn("payload_budget", body)
        self.assertIn("storyboard.json.pages[n].payload_budget", body)
        self.assertIn("必须按 `payload_budget` 落地", body)
        self.assertIn("claim_count", body)
        self.assertIn("evidence_count", body)
        self.assertIn("structure_block_count", body)
        self.assertIn("require_comparison_or_summary", body)
        self.assertIn("不允许把应承载 3 块内容的页面退回成“一个标题 + 一张大卡片”", body)
        self.assertNotIn("content_density_profile", body)

        self.assertIn("payload_budget", design)
        self.assertIn("不允许把应承载 3 块内容的页面退回成“一个标题 + 一张大卡片”", design)

    def test_ppt_review_flags_payload_budget_underdelivery(self):
        skills = _load_workspace_skills()
        design = DESIGN_DOC.read_text(encoding="utf-8")

        body = skills["ppt-review"]

        self.assertIn("payload_budget", body)
        self.assertIn("storyboard.json.pages[n].payload_budget", body)
        self.assertIn("承载不足", body)
        self.assertIn("结构块不足", body)
        self.assertIn("缺少对比或摘要", body)
        self.assertIn("claim_count", body)
        self.assertIn("evidence_count", body)
        self.assertIn("structure_block_count", body)
        self.assertIn("require_comparison_or_summary", body)
        self.assertNotIn("content_density_profile", body)

        self.assertIn("承载不足", design)
        self.assertIn("结构块不足", design)
        self.assertIn("缺少对比或摘要", design)


if __name__ == "__main__":
    unittest.main()
