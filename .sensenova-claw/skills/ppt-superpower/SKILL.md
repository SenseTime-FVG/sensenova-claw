---
name: ppt-superpower
description: 当用户需要新建整套 PPT、继续已有 PPT 工件、或只修改某个局部页面时使用；它负责在 fast、guided、surgical 三种模式中选择最合适的推进路径。
---

# PPT 总控入口

PPT 流水线的唯一默认入口，负责判断任务类型、确定运行模式、固定输出目录并路由到下游 skill。

## 目标

1. 固定 `deck_dir`，保证输出目录自包含。
2. 判断任务类型：新建整套 PPT、继续已有工件、局部修改、只生成某个中间工件。
3. 决定运行模式：`fast`、`guided`、`surgical`。
4. 判断已有工件是否可复用。
5. 决定下一步最值得生成的工件，而不是机械跑完整条长链路。

## 触发条件

- 用户提出整套 PPT 生成需求。
- 用户要求在已有 deck 基础上继续修改。
- 用户要求局部修改某页、某个槽位或某类全局风格。
- 用户要求只生成某个中间工件（如只看大纲、只看风格）。

## 输出

本 skill 不直接产出文件工件，而是完成以下决策后路由到下游 skill：

- 确定并创建 `deck_dir`（含 `pages/` 和 `images/` 子目录）。
- 确定运行模式（`fast` / `guided` / `surgical`）。
- 确定下一步进入的 skill。

下游路由目标：

| 场景 | 首选下游 skill |
| --- | --- |
| 存在上传文件、链接、截图、模板 | `ppt-source-analysis` |
| 新建整套或重新明确任务边界 | `ppt-task-pack` |
| 局部修改页面结构 | `ppt-page-plan` |
| 局部修改页面资产 | `ppt-page-assets` |
| 局部修改页面视觉 | `ppt-page-polish` |
| 局部修改全局风格 | `ppt-style-refine` |
| 局部修改叙事结构 | `ppt-story-refine` |

## 执行规则

### Deck 目录规则

在生成任何工件之前，必须先解析并固定 `deck_dir`。
必须先固定 `deck_dir`。

优先级：

1. 如果用户明确指定输出地点，直接使用用户指定目录。
2. 如果任务是在已有 deck 基础上继续修改，复用原有 `deck_dir`。
3. 否则创建新的目录，目录名使用 `query概述 + 时间戳`，例如 `AI_产品发布会_20260318_154500`。

总规则：

- 所有中间工件、图片、本地页面、review 结果都必须写到同一个 `deck_dir`。
- 不要把中间结果直接写到 agent 根目录、当前工作目录顶层或零散的临时位置。
- `deck_dir` 应是可整体交付、可整体继续编辑的自包含目录。
- `task-pack.json` 一旦写出 `deck_dir`，后续所有 skill 都必须直接复用这个值。
- 不要手写、缩写、翻译或重拼目录名。
- 目录名中的 `query概述` 可以做适度压缩，但必须仍能表达任务主题。
- 创建 `deck_dir` 后，必须立即创建 `pages/` 与 `images/`。
- 不要等到 HTML 落盘或图片下载阶段，再赌子目录会被隐式创建。

推荐目录结构：

```text
deck_dir/
  task-pack.json
  info-pack.json
  style-spec.json
  storyboard.json
  asset-plan.json
  image_search_results.json
  image_selection.json
  review.md
  <目录名>.pptx          <- ppt-export-pptx 最终输出
  pages/
    page_01.html
  images/
    page_01_hero.png
```

### 默认规则

- 必须先生成 `task-pack.json`。
- 默认还要生成 `info-pack.json`，作为分页前的统一信息来源。
- `task-pack.json`、`style-spec.json`、`storyboard.json` 是默认必产工件。
- 默认进入确认优先路径：先产出 `task-pack.json`、`style-spec.json`、`storyboard.json`，再等待用户确认。
- `task-pack.json`、`style-spec.json`、`storyboard.json` 后默认等待确认；不要默认继续到 `ppt-page-html`。
- `task-pack.json` 中必须显式记录 `deck_dir`，供后续 skill 复用。
- 只有 `task-pack.json` 明确存在内容缺口时，才进入 `ppt-research-pack`。
- 不允许在 `ppt-task-pack` 之前做外部 research 决策。
- 不允许在 `task-pack` 之前做外部 research 决策。
- `task-pack.json` 与按需的 `ppt-research-pack` 完成后，必须进入 `ppt-info-pack`，先收束统一信息源，再进入 `ppt-style-spec` 与 `ppt-storyboard`。
- 如果存在上传文件、链接、截图或模板，先进入 `ppt-source-analysis`。
- 如果存在模板约束，再进入 `ppt-template-pack`。
- 如果存在图片槽位缺口，再进入 `ppt-asset-plan`，并保留搜图候选、筛选记录、下载结果。
- 如果 `storyboard.json` 中存在 `real-photo` 或其他必须真实图片的槽位，必须先进入 `ppt-asset-plan`，再进入 `ppt-page-html`。
- 如果 `storyboard.json` 虽然没有明确写出 `real-photo`，但 `visual_requirements`、页面语义或主题明显需要人物 / 产品 / 场景 / 活动现场图片，也必须先进入 `ppt-asset-plan`，不要直接跳到 `ppt-page-html`。
- 如果页面只需要 `svg-illustration`、`svg-icon` 这类可直接绘制的插画或图标，可以直接交给 `ppt-page-html`，不要为它们强行走搜图下载。
- 页面结果交给 `ppt-page-html`，并按 `pages/page_XX.html` 逐页落盘。
- 最终结果必须经过 `ppt-review`，并写出 `review.md` 或 `review.json`。
- 如果没有 `review.md` 或 `review.json`，不要直接进入 `ppt-export-pptx`。
- review 通过后，最后一步调用 `ppt-export-pptx` 将 HTML 导出为 PPTX 文件。
  - 执行：`node .sensenova-claw/skills/ppt-export-pptx/html_to_pptx.mjs --deck-dir <deck_dir>`
  - 输出文件名与 `deck_dir` 目录名一致，如 `<deck_dir>/AI_产品发布会_20260318_154500.pptx`
  - 首次使用前需执行 `cd .sensenova-claw/skills/ppt-export-pptx && npm install`

### 路径选择

#### fast

显式 opt-in 模式。只有用户明确说"直接生成""不要确认""自动继续"或"一口气跑完"时，才进入 `fast`。

默认路径：

1. `ppt-task-pack`
2. 如果 `task-pack.json.research_required` 为真，进入 `ppt-research-pack`
3. `ppt-info-pack`
4. `ppt-style-spec`
5. `ppt-storyboard`
6. `ppt-asset-plan`（如需要）
7. `ppt-page-html`
8. `ppt-review`
9. `ppt-export-pptx`（如需要）

`fast` 也必须给用户简短回显，但这些回显默认是非阻塞的：

- 每完成一个关键工件，就用一句话告诉用户产物和下一步。
- 除非命中阻塞反馈，否则不等待用户回复，继续推进。

#### guided

默认模式，适合需要阶段确认的场景。

- 默认进入 `guided`，走确认优先路径。
- 如果用户说"先看大纲""先确认大纲""先看风格和大纲"或"确认后再生成"，必须进入 `guided`。
- 此时应先产出并展示 `task-pack.json`；如果 `task-pack.json.research_required` 为真，再按需进入 `ppt-research-pack`，然后继续 `info-pack.json`、`style-spec.json`、`storyboard.json`。
- `task-pack.json`、`style-spec.json`、`storyboard.json` 后默认等待确认，再决定是否继续后续页面生成。
- 在用户确认前，不要直接生成 `pages/page_XX.html`。
- 不要只返回一段自由文本大纲，必须落盘并展示结构化工件。
- `guided` 除了常规开始反馈 / 完成反馈外，还必须在等待确认时明确给出待确认点、已产出工件和下一步选项。

#### surgical

适合局部修复，不重跑整套。

- 只改指定页面、指定槽位、指定风格或叙事局部。
- 阶段回显必须点明当前锁定的 `page_id`、`slot_id` 或被修改的工件范围，避免用户误以为会重跑整套。

典型入口：

- 页面结构问题：`ppt-page-plan`
- 单页资产问题：`ppt-page-assets`
- 单页视觉问题：`ppt-page-polish`
- 全局风格问题：`ppt-style-refine`
- 叙事顺序问题：`ppt-story-refine`

## 用户回显

PPT 链路通常较长。无论最终进入 `fast`、`guided` 还是 `surgical`，都不要在任务开始后长时间沉默。
- 不要长时间沉默。

- **开始反馈**：任务开始后的第一条消息，就应说明本轮目标、当前 mode、`deck_dir` 和第一步要做什么。
- **进行中反馈**：每进入一个关键阶段，都至少给出一条开始反馈和一条完成反馈。开始反馈要说清当前正在处理哪个阶段、覆盖范围是什么、预期会产出哪个工件。完成反馈要说清已经生成或更新了什么、当前最关键的结论或未解决项是什么、下一步会进入哪个阶段。如果阶段明显耗时（搜图下载、逐页 HTML、整套 review、导出 PPTX），可额外补一条进行中反馈，说明当前进度，但不要刷屏。
- **完成反馈**：说明已完成的全部工件、整体结论和后续建议。
- **阻塞反馈**：如果依赖缺失、路径不一致、下载失败、页面生成失败或导出失败，要立即给出阻塞反馈，说明卡点、已保留结果和建议下一步，不要静默跳过。

总规则：

- 阶段回显必须简短，不要把整份 JSON 或整页 HTML 原样回贴给用户。
- `guided` 在等待用户决策时使用 `awaiting_confirmation` 语义，并明确告诉用户当前停在哪个工件。

## 关键原则

- 围绕工件组织，而不是围绕抽象步骤组织。用户中断、前端展示、局部返工、继续推进都围绕 `task-pack.json`、`style-spec.json`、`storyboard.json`、`asset-plan.json`、`pages/page_XX.html` 展开。
- 默认短路径，按需下钻。默认路径只生成最关键的工件，只有命中触发器时才下钻到页面级、槽位级或局部修复。
- 决定下一步最值得生成的工件，而不是机械跑完整条长链路。
- 每个 skill 先检查上游工件是否存在、可读、且路径与 `task-pack.json.deck_dir` 一致；不允许猜测继续。

## 禁止事项

- 不要在未固定 `deck_dir` 的情况下开始生成任何工件。
- 不要把中间结果散落到 agent 根目录或当前工作目录顶层。
- 不要在 `guided` 模式下未经用户确认就直接生成页面 HTML。
- 不要跳过阶段回显，长时间沉默后一次性输出全部结果。
- 不要把整份 JSON 或整页 HTML 原样回贴给用户作为回显。
- 不要手写、缩写、翻译或重拼 `deck_dir` 目录名。
- 不要在未创建 `pages/` 和 `images/` 子目录的情况下开始后续流程。
- 不要再调用旧 `pptx`、`ppt-outline-gen`、`ppt-style-extract`、`ppt-image-selection`、`ppt-html-gen`。
- 不要跳过 `style-spec.json` 或 `storyboard.json` 直接开始 HTML 生成。
- 不要跳过 `info-pack.json`，直接让 `ppt-storyboard` 从零拼装页面信息。
- 不要跳过图片筛选和本地下载验证，直接把远程 URL 当成最终资产。
- 不要把用户上传文件的内容、风格、模板角色混在一起使用。
- 不要把整套 deck 拼成单个 HTML 文件交付。
