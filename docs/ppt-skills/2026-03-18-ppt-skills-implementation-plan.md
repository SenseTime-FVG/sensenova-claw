# PPT Skills 重构实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 PPT skills 重构为新的 `ppt-*` superpower 体系，默认支持快速路径，同时提供稳定的中间工件和按需下钻能力。

**Architecture:** 本次改动只触及 `.sensenova-claw/skills`、`docs/ppt-skills` 与测试文件，不修改 Sensenova-Claw 运行时代码。新体系以 `ppt-superpower` 为唯一入口，围绕 `task-pack.json`、`style-spec.json`、`storyboard.json` 等工件组织，并通过契约测试验证新 skill 集合、固定 schema 和旧 skill 的移除。

**Tech Stack:** Markdown skills、Python `unittest`、SkillRegistry

---

### Task 1: 锁定重构契约

**Files:**
- Create: `tests/unit/test_ppt_skill_suite.py`
- Test: `tests/unit/test_ppt_skill_suite.py`

- [x] **Step 1: 写失败测试**

```python
class TestPptSkillSuite(unittest.TestCase):
    def test_ppt_skill_suite_replaced_with_new_architecture(self):
        ...
```

- [x] **Step 2: 运行测试确认红灯**

Run: `python3 -m unittest tests.unit.test_ppt_skill_suite -q`
Expected: FAIL，提示缺少新 `ppt-*` skills，且设计文档未更新。

- [x] **Step 3: 保持测试不变，后续通过实现转绿**

### Task 2: 重写 PPT 技术设计文档

**Files:**
- Modify: `docs/ppt-skills/design.md`
- Create: `docs/ppt-skills/2026-03-18-ppt-skills-implementation-plan.md`
- Test: `tests/unit/test_ppt_skill_suite.py`

- [x] **Step 1: 用新架构重写设计文档**

文档需覆盖：
- 旧设计问题分析
- 新 skill 分层
- 默认必产物与可选工件
- `storyboard.json` 前端契约
- `ppt-speaker-notes` 的触发条件
- 测试用例矩阵

- [x] **Step 2: 运行契约测试中的文档断言**

Run: `python3 -m unittest tests.unit.test_ppt_skill_suite.TestPptSkillSuite.test_ppt_design_doc_matches_new_skill_system -q`
Expected: PASS

### Task 3: 全量替换 PPT skills

**Files:**
- Delete: `.sensenova-claw/skills/pptx/SKILL.md`
- Delete: `.sensenova-claw/skills/pptx/SKILL.md.en`
- Delete: `.sensenova-claw/skills/pptx/design.md`
- Delete: `.sensenova-claw/skills/ppt-outline-gen/SKILL.md`
- Delete: `.sensenova-claw/skills/ppt-outline-gen/SKILL.md.en`
- Delete: `.sensenova-claw/skills/ppt-style-extract/SKILL.md`
- Delete: `.sensenova-claw/skills/ppt-style-extract/SKILL.md.en`
- Delete: `.sensenova-claw/skills/ppt-image-selection/SKILL.md`
- Delete: `.sensenova-claw/skills/ppt-html-gen/SKILL.md`
- Delete: `.sensenova-claw/skills/ppt-html-gen/SKILL.md.en`
- Create: `.sensenova-claw/skills/ppt-superpower/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-source-analysis/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-task-pack/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-research-pack/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-template-pack/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-style-spec/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-storyboard/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-asset-plan/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-page-html/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-speaker-notes/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-review/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-page-plan/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-page-assets/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-page-polish/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-style-refine/SKILL.md`
- Create: `.sensenova-claw/skills/ppt-story-refine/SKILL.md`
- Test: `tests/unit/test_ppt_skill_suite.py`

- [x] **Step 1: 先删除旧 PPT skill 文件**

- [x] **Step 2: 按新架构创建核心 skills**

要求：
- 中文文档
- frontmatter 合法
- `ppt-style-spec`、`ppt-storyboard` 明确写为默认必产
- `ppt-storyboard` 内含固定 schema 示例
- `ppt-speaker-notes` 标明可选交付物

- [x] **Step 3: 补齐局部修复 skills**

- [x] **Step 4: 运行契约测试确认 skill 集合与内容转绿**

Run: `python3 -m unittest tests.unit.test_ppt_skill_suite -q`
Expected: PASS

### Task 4: 做最终自检

**Files:**
- Modify: `docs/ppt-skills/2026-03-18-ppt-skills-implementation-plan.md`
- Test: `tests/unit/test_ppt_skill_suite.py`

- [x] **Step 1: 自查计划与实现是否一致**

- [x] **Step 2: 重新运行完整契约测试**

Run: `python3 -m unittest tests.unit.test_ppt_skill_suite -q`
Expected: PASS

- [x] **Step 3: 记录仍未完成的验证项**

例如：
- 当前环境未安装 `pytest`，因此未执行 `python3 -m pytest`
- 当前验证以 `python3 -m unittest tests.unit.test_ppt_skill_suite -q` 与真实 SkillRegistry 加载烟测为主
