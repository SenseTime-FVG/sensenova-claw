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

    def test_ppt_storyboard_skill_contains_frontend_contract_schema(self):
        skills = _load_workspace_skills()

        body = skills["ppt-storyboard"]
        required_fields = [
            "schema_version",
            "ppt_title",
            "language",
            "total_pages",
            "mode",
            "pages",
            "page_id",
            "page_number",
            "narrative_role",
            "audience_takeaway",
            "layout_intent",
            "style_variant",
            "content_blocks",
            "visual_requirements",
            "asset_requirements",
            "presenter_intent",
        ]

        for field in required_fields:
            self.assertIn(field, body)

    def test_ppt_storyboard_requires_style_variant_to_reference_style_spec_mapping(self):
        skills = _load_workspace_skills()

        body = skills["ppt-storyboard"]
        self.assertIn("`style_variant`", body)
        self.assertIn("必须直接引用 `style-spec.json`", body)
        self.assertIn("不要把它写成宽泛形容词", body)
        self.assertIn("后续 `ppt-page-html` 可直接按 variant 落地", body)

    def test_ppt_storyboard_asset_requirements_include_asset_kind_hints(self):
        skills = _load_workspace_skills()

        body = skills["ppt-storyboard"]
        self.assertIn("`asset_requirements`", body)
        self.assertIn("不要只写模糊的槽位名", body)
        self.assertIn("`svg-illustration`", body)
        self.assertIn("`svg-icon`", body)
        self.assertIn("`real-photo`", body)
        self.assertIn("`qr-placeholder`", body)

    def test_ppt_storyboard_routes_photo_like_subjects_to_real_photo(self):
        skills = _load_workspace_skills()

        body = skills["ppt-storyboard"]
        self.assertIn("资产类型判断必须先看页面语义", body)
        self.assertIn("人物", body)
        self.assertIn("产品", body)
        self.assertIn("场景", body)
        self.assertIn("活动现场", body)
        self.assertIn("默认应规划为 `real-photo`", body)
        self.assertIn("`插画感` 只影响装饰语法", body)
        self.assertIn("不要因为风格里有插画感", body)
        self.assertIn("就把整套 deck 的图片需求都改写成 `svg-illustration`", body)

    def test_ppt_style_spec_skill_is_mandatory_design_control_plane(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("默认必产", body)
        self.assertIn("设计控制面", body)
        self.assertIn("页面类型视觉原则", body)
        self.assertIn("禁用项", body)

    def test_ppt_style_spec_prioritizes_user_need_and_fallback_archetypes(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("优先理解用户需求", body)
        self.assertIn("只有在风格信号不足时", body)
        self.assertIn("商务", body)
        self.assertIn("海报", body)
        self.assertIn("visual_archetype", body)
        self.assertIn("fallback_archetype", body)
        self.assertIn("background_system", body)
        self.assertIn("foreground_motifs", body)
        self.assertIn("component_skins", body)
        self.assertIn("density_rules", body)
        self.assertIn("page_type_variants", body)

    def test_ppt_style_spec_requires_variant_level_shell_mapping(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("variant_key", body)
        self.assertIn("header_strategy", body)
        self.assertIn("layout_shell", body)
        self.assertIn("不要只按 `page_type` 粗分", body)
        self.assertIn("要能覆盖 `style_variant`", body)

    def test_ppt_style_spec_requires_svg_motif_library_and_variant_decorations(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("svg_motif_library", body)
        self.assertIn("required_svg_motifs", body)
        self.assertIn("背景和前景都要给出可绘制的装饰元素", body)
        self.assertIn("不要只停留在文字描述", body)

    def test_ppt_style_spec_requires_explicit_motif_recipes(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("background_motif_recipe", body)
        self.assertIn("foreground_motif_recipe", body)
        self.assertIn("placement_hint", body)
        self.assertIn("density_hint", body)
        self.assertIn("不要只写“有叶片感”这类抽象描述", body)

    def test_ppt_style_spec_requires_perceivable_background_recipes_for_content_variants(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("正文", body)
        self.assertIn("内容页", body)
        self.assertIn("不能把 `background_motif_recipe` 留空", body)
        self.assertIn("不要只给一个角落里的小图标", body)
        self.assertIn("至少要有一个大面积或跨边缘", body)
        self.assertIn("真实图片也不能替代背景装饰配方", body)

    def test_ppt_style_spec_requires_exact_task_pack_deck_dir_for_output(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("必须先读取 `task-pack.json`", body)
        self.assertIn("输出路径必须严格为 `${deck_dir}/style-spec.json`", body)
        self.assertIn("不要手写、缩写、翻译或重拼目录名", body)

    def test_ppt_speaker_notes_skill_is_optional_output(self):
        skills = _load_workspace_skills()

        body = skills["ppt-speaker-notes"]
        self.assertIn("可选交付物", body)
        self.assertIn("storyboard.json", body)
        self.assertIn("pages/page_XX.html", body)

    def test_ppt_page_html_skill_requires_one_file_per_page(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("pages/page_XX.html", body)
        self.assertIn("每页", body)
        self.assertIn("单独", body)
        self.assertIn("不要输出单个包含整套 deck 的 HTML", body)
        self.assertNotIn("单页或整套 HTML 幻灯片", body)

    def test_ppt_asset_plan_preserves_search_screening_and_download_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-asset-plan"]
        self.assertIn("image_search_results.json", body)
        self.assertIn("image_selection.json", body)
        self.assertIn("先下载验证，再做最终选择", body)
        self.assertIn("selected_image", body)
        self.assertIn("rejected_candidates", body)
        self.assertIn("deck_dir", body)

    def test_ppt_asset_plan_requires_images_dir_before_download(self):
        skills = _load_workspace_skills()

        body = skills["ppt-asset-plan"]
        self.assertIn("下载前必须先创建 `deck_dir/images`", body)
        self.assertIn("不要假设 `images/` 已存在", body)

    def test_ppt_asset_plan_distinguishes_real_images_from_svg_drawables(self):
        skills = _load_workspace_skills()

        body = skills["ppt-asset-plan"]
        self.assertIn("`real-photo`", body)
        self.assertIn("`download-local`", body)
        self.assertIn("`svg-illustration`", body)
        self.assertIn("`svg-icon`", body)
        self.assertIn("不要为可直接绘制的图标或插画走搜图下载", body)

    def test_ppt_asset_plan_backfills_real_photo_slots_when_storyboard_underlabels_them(self):
        skills = _load_workspace_skills()

        body = skills["ppt-asset-plan"]
        self.assertIn("如果 `asset_requirements` 写得过轻", body)
        self.assertIn("但 `visual_requirements` 或页面语义明显指向真实图片", body)
        self.assertIn("补出对应的 `real-photo` 槽位", body)
        self.assertIn("不要静默接受“整套都只有 SVG”", body)
        self.assertIn("不要把人物、产品、场景、活动现场", body)
        self.assertIn("误判成 `svg-illustration`", body)

    def test_ppt_page_assets_keeps_local_asset_and_screening_trace(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-assets"]
        self.assertIn("image_search_results.json", body)
        self.assertIn("image_selection.json", body)
        self.assertIn("不要跳过筛选过程", body)
        self.assertIn("远程 URL", body)

    def test_ppt_page_html_preserves_style_and_asset_requirements(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("不要退回通用默认样式", body)
        self.assertIn("不要编写 Python 脚本来批量生成页面", body)
        self.assertIn("必须逐页直接生成最终 HTML", body)
        self.assertIn("不要先写生成器脚本再批量产出页面", body)
        self.assertIn("background_system", body)
        self.assertIn("foreground_motifs", body)
        self.assertIn("component_skins", body)
        self.assertIn("不要只做纯色背景 + 普通白卡片", body)
        self.assertIn("除非 `style-spec` 明确要求极简", body)
        self.assertIn("优先按 `style_variant` 映射页面壳子", body)
        self.assertIn("不能把多个不同 `style_variant` 页面落成同一种安全模板", body)
        self.assertIn("不要让大多数正文页都复用同一套左竖线标题 + 毛玻璃卡片", body)
        self.assertIn("如果 `local_path` 存在，应优先引用本地相对路径", body)
        self.assertIn("保留明确占位", body)
        self.assertIn("不能静默忽略", body)

    def test_ppt_page_html_requires_inline_svg_for_drawable_elements(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("内联 SVG", body)
        self.assertIn("图标、装饰性元素、可直接绘制的插画", body)
        self.assertIn("不要把图标画成 placeholder", body)
        self.assertIn("只有真实照片、二维码、用户专有素材", body)
        self.assertIn("才允许保留 placeholder", body)

    def test_ppt_page_html_must_consume_page_level_asset_requirements_exactly(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("必须逐项消费 `storyboard.json.pages[n].asset_requirements`", body)
        self.assertIn("不要用一个通用 motif", body)
        self.assertIn("替代不同页面的具体资产要求", body)
        self.assertIn("如果页面要求 `real-photo`", body)
        self.assertIn("不要改画成 SVG 小图标", body)
        self.assertIn("如果页面要求某个具体 `svg-icon` 或 `svg-illustration`", body)
        self.assertIn("就要画出对应元素", body)

    def test_ppt_page_html_requires_decorative_layers_for_non_minimal_pages(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("非极简页面", body)
        self.assertIn("至少 1 层背景装饰", body)
        self.assertIn("至少 1 处前景装饰", body)
        self.assertIn("只有纯色或渐变背景", body)
        self.assertIn("应视为未完成", body)

    def test_ppt_page_html_requires_markerized_motif_layers(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn('data-layer="bg-motif"', body)
        self.assertIn('data-layer="fg-motif"', body)
        self.assertIn('data-motif-key', body)
        self.assertIn("让 review 和导出前校验可以核对", body)
        self.assertIn("真实图片或主视觉照片不能替代这些标记", body)

    def test_ppt_page_html_requires_visible_title_layering(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("可见标题必须放在 `#ct` 内", body)
        self.assertIn("或放在单独的 `#header` 容器内", body)
        self.assertIn("不要把 `.header` 当作 `#bg` 和 `#ct` 之间的裸兄弟节点", body)
        self.assertIn("否则很容易被内容层盖住", body)

    def test_ppt_superpower_routes_real_image_slots_to_asset_plan_before_html(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("如果 `storyboard.json` 中存在 `real-photo`", body)
        self.assertIn("必须先进入 `ppt-asset-plan`", body)
        self.assertIn("再进入 `ppt-page-html`", body)

    def test_ppt_review_flags_missing_decorative_layers(self):
        skills = _load_workspace_skills()

        body = skills["ppt-review"]
        self.assertIn("缺少背景装饰层", body)
        self.assertIn("缺少前景装饰层", body)
        self.assertIn("只有纯色或渐变背景", body)
        self.assertIn("不能直接交付", body)
        self.assertIn("`ppt-page-polish`", body)

    def test_ppt_review_requires_html_evidence_for_decorative_layers(self):
        skills = _load_workspace_skills()

        body = skills["ppt-review"]
        self.assertIn("必须直接读取页面 HTML", body)
        self.assertIn("不要只根据模型自述", body)
        self.assertIn('data-layer="bg-motif"', body)
        self.assertIn('data-layer="fg-motif"', body)
        self.assertIn("如果 style-spec recipe 要求某个 motif", body)
        self.assertIn("就要在页面里找到对应的 `data-motif-key`", body)

    def test_ppt_review_checks_title_visibility_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-review"]
        self.assertIn("标题元素是否放在 `#ct` 或 `#header`", body)
        self.assertIn("不要把仅存在于源码但被层级盖住的标题判成通过", body)
        self.assertIn("`.header` 落在 `#ct` 外面", body)
        self.assertIn("应视为标题不可见", body)

    def test_ppt_review_requires_written_artifact_and_export_gate(self):
        skills = _load_workspace_skills()

        review_body = skills["ppt-review"]
        export_body = skills["ppt-export-pptx"]
        superpower_body = skills["ppt-superpower"]
        self.assertIn("必须写出 `review.md` 或 `review.json`", review_body)
        self.assertIn("是否满足页级 `asset_requirements`", review_body)
        self.assertIn("如果要求真实图片却只落了 SVG 或 placeholder", review_body)
        self.assertIn("不能直接交付", review_body)
        self.assertIn("没有 `review.md` 或 `review.json`", superpower_body)
        self.assertIn("不要直接进入 `ppt-export-pptx`", superpower_body)
        self.assertIn("必须先确认 `review.md` 或 `review.json` 存在", export_body)
        self.assertIn("如果 review 标记为阻塞", export_body)
        self.assertIn("不得继续导出", export_body)

    def test_ppt_page_html_restores_strict_canvas_and_footer_contract(self):
        skills = _load_workspace_skills()

        body = skills["ppt-page-html"]
        self.assertIn("页面尺寸必须严格为 `1280x720`", body)
        self.assertIn("所有内容必须完整落在视区内", body)
        self.assertIn("右下角 `160px x 60px` 必须保留给页码", body)
        self.assertIn("页码必须放在 `<div id=\"footer\">`", body)
        self.assertIn("`#bg` 和 `#ct` 都必须铺满整页", body)

    def test_downstream_ppt_skills_require_dependency_existence_checks(self):
        skills = _load_workspace_skills()

        for skill_name in [
            "ppt-storyboard",
            "ppt-asset-plan",
            "ppt-page-html",
            "ppt-page-plan",
            "ppt-page-assets",
            "ppt-style-refine",
            "ppt-review",
        ]:
            body = skills[skill_name]
            self.assertIn("消费前必须先确认", body, msg=f"{skill_name} 缺少前置存在性检查")
            self.assertIn("如果目标文件不存在", body, msg=f"{skill_name} 缺少缺失依赖处理")
            self.assertIn("不要猜测", body, msg=f"{skill_name} 缺少禁止猜测约束")

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

    def test_ppt_design_doc_matches_new_skill_system(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        expected_terms = [
            "ppt-superpower",
            "ppt-source-analysis",
            "ppt-style-spec",
            "ppt-storyboard",
            "storyboard.json",
            "style-spec.json",
            "ppt-speaker-notes",
            "快速优先",
            "可选交付物",
            "deck_dir",
            "image_search_results.json",
            "image_selection.json",
            "query概述 + 时间戳",
            "160px x 60px",
            "立即创建 `pages/` 与 `images/`",
            "canonical 输出根目录",
            "不要手写、缩写、翻译或重拼目录名",
            "消费前必须先确认",
            "阶段回显",
            "开始反馈",
            "完成反馈",
            "阻塞反馈",
            "不要编写 Python 脚本来批量生成页面",
            "必须逐页直接生成最终 HTML",
            "风格意图",
            "优先理解用户需求",
            "商务",
            "海报",
            "visual_archetype",
            "fallback_archetype",
            "background_system",
            "foreground_motifs",
            "component_skins",
            "density_rules",
            "page_type_variants",
            "variant_key",
            "layout_shell",
            "必须直接引用 `style-spec.json`",
            "不要把它写成宽泛形容词",
            "优先按 `style_variant` 映射页面壳子",
            "svg_motif_library",
            "required_svg_motifs",
            "资产类型判断必须先看页面语义",
            "默认应规划为 `real-photo`",
            "`插画感` 只影响装饰语法",
            "不要因为风格里有插画感",
            "背景和前景都要给出可绘制的装饰元素",
            "`svg-illustration`",
            "`svg-icon`",
            "`real-photo`",
            "`qr-placeholder`",
            "如果 `asset_requirements` 写得过轻",
            "补出对应的 `real-photo` 槽位",
            "内联 SVG",
            "不要把图标画成 placeholder",
            "必须逐项消费 `storyboard.json.pages[n].asset_requirements`",
            "不要用一个通用 motif",
            "如果页面要求 `real-photo`",
            "只有真实照片、二维码、用户专有素材",
            "background_motif_recipe",
            "foreground_motif_recipe",
            "placement_hint",
            "density_hint",
            "不能把 `background_motif_recipe` 留空",
            "不要只给一个角落里的小图标",
            "至少要有一个大面积或跨边缘",
            "真实图片也不能替代背景装饰配方",
            "非极简页面",
            "至少 1 层背景装饰",
            "至少 1 处前景装饰",
            "只有纯色或渐变背景",
            "应视为未完成",
            'data-layer="bg-motif"',
            'data-layer="fg-motif"',
            "data-motif-key",
            "让 review 和导出前校验可以核对",
            "真实图片或主视觉照片不能替代这些标记",
            "可见标题必须放在 `#ct` 内",
            "或放在单独的 `#header` 容器内",
            "不要把 `.header` 当作 `#bg` 和 `#ct` 之间的裸兄弟节点",
            "否则很容易被内容层盖住",
            "必须直接读取页面 HTML",
            "不要只根据模型自述",
            "如果 style-spec recipe 要求某个 motif",
            "就要在页面里找到对应的 `data-motif-key`",
            "标题元素是否放在 `#ct` 或 `#header`",
            "不要把仅存在于源码但被层级盖住的标题判成通过",
            "`.header` 落在 `#ct` 外面",
            "应视为标题不可见",
            "必须写出 `review.md` 或 `review.json`",
            "是否满足页级 `asset_requirements`",
            "如果要求真实图片却只落了 SVG 或 placeholder",
            "没有 `review.md` 或 `review.json`",
            "不得继续导出",
            "强约束渲染契约",
            "预置装饰模板库",
            "后置抛光补层",
            "当前优先实现方案 1",
        ]

        for term in expected_terms:
            self.assertIn(term, content)

    def test_ppt_design_doc_contains_skill_inventory_table(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("### 4.4 技能清单速览", content)
        self.assertIn("| Skill | 类型 | 触发时机 | 主要输入 | 主要产物 | 用户回显 |", content)
        self.assertIn("| `ppt-superpower` | 总控入口 |", content)
        self.assertIn("| `ppt-page-html` | 页面生成 |", content)
        self.assertIn("| `ppt-style-refine` | 全局风格修复 |", content)
        self.assertIn("| `ppt-review` | 结果审查 |", content)

    def test_ppt_design_doc_records_decorative_layer_options(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("强约束渲染契约", content)
        self.assertIn("预置装饰模板库", content)
        self.assertIn("后置抛光补层", content)
        self.assertIn("当前优先实现方案 1", content)

    def test_ppt_design_doc_experiment_one_default_path_runs_task_pack_before_research(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("deck_dir -> task-pack -> research(按需) -> style-spec -> storyboard", content)
        self.assertIn("无上传文件时的最小路径", content)
        self.assertIn("有上传文件时的常规路径", content)

    # ── ppt-export-pptx 契约测试 ──

    def test_ppt_export_pptx_skill_exists(self):
        """ppt-export-pptx skill 存在且 SKILL.md 格式正确"""
        skill_dir = SKILLS_DIR / "ppt-export-pptx"
        self.assertTrue(skill_dir.exists(), "ppt-export-pptx skill 目录应该存在")
        skill_md = skill_dir / "SKILL.md"
        self.assertTrue(skill_md.exists(), "SKILL.md 应该存在")

        content = skill_md.read_text()
        self.assertIn("name: ppt-export-pptx", content, "应声明 skill name")

    def test_ppt_export_pptx_script_exists(self):
        """转换脚本和依赖文件应存在"""
        skill_dir = SKILLS_DIR / "ppt-export-pptx"
        self.assertTrue((skill_dir / "html_to_pptx.mjs").exists(), "主脚本应存在")
        self.assertTrue((skill_dir / "package.json").exists(), "package.json 应存在")
        self.assertTrue((skill_dir / "lib" / "dom_extractor.mjs").exists(), "DOM 提取模块应存在")
        self.assertTrue((skill_dir / "lib" / "pptx_builder.mjs").exists(), "PPTX 构建模块应存在")
        self.assertTrue((skill_dir / "lib" / "style_parser.mjs").exists(), "样式解析模块应存在")

    def test_ppt_export_pptx_package_json(self):
        """package.json 应声明正确的依赖"""
        import json
        pkg = json.loads((SKILLS_DIR / "ppt-export-pptx" / "package.json").read_text())
        self.assertEqual(pkg.get("type"), "module", "应使用 ESM")
        deps = pkg.get("dependencies", {})
        self.assertIn("pptxgenjs", deps, "应依赖 pptxgenjs")

    def test_ppt_export_pptx_declares_real_path_and_feedback(self):
        """ppt-export-pptx 应声明真实脚本路径与阶段反馈"""
        skill_md = (SKILLS_DIR / "ppt-export-pptx" / "SKILL.md").read_text()
        self.assertIn(".sensenova-claw/skills/ppt-export-pptx", skill_md)
        self.assertIn("开始反馈", skill_md)
        self.assertIn("完成反馈", skill_md)
        self.assertIn("必须先确认 `review.md` 或 `review.json` 存在", skill_md)
        self.assertIn("如果 review 标记为阻塞", skill_md)

    def test_ppt_export_script_requires_review_artifact(self):
        """导出脚本应在转换前检查 review 工件"""
        script = (SKILLS_DIR / "ppt-export-pptx" / "html_to_pptx.mjs").read_text()
        guard = (SKILLS_DIR / "ppt-export-pptx" / "lib" / "cli_guards.mjs").read_text()
        self.assertIn("ensureDeckPreconditions", script)
        self.assertIn("review.md", guard)
        self.assertIn("review.json", guard)
        self.assertIn("review", guard)


if __name__ == "__main__":
    unittest.main()
