"""PPT skill 体系契约测试。"""

from pathlib import Path
import unittest

from agentos.capabilities.skills.registry import SkillRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / ".agentos" / "skills"
DESIGN_DOC = PROJECT_ROOT / "docs" / "ppt-skills" / "design.md"


def _load_workspace_skills() -> dict[str, str]:
    registry = SkillRegistry(
        workspace_dir=SKILLS_DIR,
        user_dir=PROJECT_ROOT / "pytest_tmp" / "no-user-skills",
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
        self.assertIn("ppt-image-selection", skills)
        self.assertIn("ppt-html-gen", skills)

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

    def test_ppt_superpower_maps_outline_review_requests_to_guided_mode(self):
        skills = _load_workspace_skills()

        body = skills["ppt-superpower"]
        self.assertIn("先看大纲", body)
        self.assertIn("确认后再生成", body)
        self.assertIn("必须进入 `guided`", body)
        self.assertIn("不要直接生成 `pages/page_XX.html`", body)
        self.assertIn("不要只返回一段自由文本大纲", body)

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

    def test_ppt_style_spec_skill_is_mandatory_design_control_plane(self):
        skills = _load_workspace_skills()

        body = skills["ppt-style-spec"]
        self.assertIn("默认必产", body)
        self.assertIn("设计控制面", body)
        self.assertIn("页面类型视觉原则", body)
        self.assertIn("禁用项", body)

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
        self.assertIn("如果 `local_path` 存在，应优先引用本地相对路径", body)
        self.assertIn("保留明确占位", body)
        self.assertIn("不能静默忽略", body)

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
        ]

        for term in expected_terms:
            self.assertIn(term, content)

    def test_ppt_design_doc_contains_skill_inventory_table(self):
        content = DESIGN_DOC.read_text(encoding="utf-8")

        self.assertIn("### 4.4 技能清单速览", content)
        self.assertIn("| Skill | 类型 | 触发时机 | 主要输入 | 主要产物 |", content)
        self.assertIn("| `ppt-superpower` | 总控入口 |", content)
        self.assertIn("| `ppt-page-html` | 页面生成 |", content)
        self.assertIn("| `ppt-style-refine` | 全局风格修复 |", content)
        self.assertIn("| `ppt-review` | 结果审查 |", content)


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

    def test_ppt_export_pptx_not_in_superpower_default_path(self):
        """ppt-export-pptx 不应出现在 ppt-superpower 的默认快路径中"""
        superpower_md = (SKILLS_DIR / "ppt-superpower" / "SKILL.md").read_text()
        self.assertNotIn("ppt-export-pptx", superpower_md, "不应在 superpower 默认路径中")


if __name__ == "__main__":
    unittest.main()
