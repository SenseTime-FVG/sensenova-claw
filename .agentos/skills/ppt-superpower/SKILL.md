---
name: ppt-superpower
description: 当用户需要新建整套 PPT、继续已有 PPT 工件、或只修改某个局部页面时使用；它负责在 fast、guided、surgical 三种模式中选择最合适的推进路径。
---

# PPT Superpower

这是新的 PPT 总控技能，也是默认入口。

## 核心职责

1. 先确定本次任务的 `deck_dir`，保证输出目录自包含。
2. 判断任务属于：
   - 新建整套 PPT
   - 继续已有工件
   - 局部修改
   - 只生成某个中间工件
3. 决定运行模式：
   - `fast`
   - `guided`
   - `surgical`
4. 判断已有工件是否可复用。
5. 决定下一步最值得生成的工件，而不是机械跑完整条长链路。

## Deck 目录规则

在生成任何工件之前，必须先解析并固定 `deck_dir`。

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

推荐结构：

```text
deck_dir/
  task-pack.json
  style-spec.json
  storyboard.json
  asset-plan.json
  image_search_results.json
  image_selection.json
  review.md
  pages/
    page_01.html
  images/
    page_01_hero.png
```

## 默认规则

- `task-pack.json`、`style-spec.json`、`storyboard.json` 是默认必产工件。
- `task-pack.json` 中必须显式记录 `deck_dir`，供后续 skill 复用。
- 如果存在上传文件、链接、截图或模板，先进入 `ppt-source-analysis`。
- 如果存在内容缺口，再进入 `ppt-research-pack`。
- 如果存在模板约束，再进入 `ppt-template-pack`。
- 如果存在图片槽位缺口，再进入 `ppt-asset-plan`，并保留搜图候选、筛选记录、下载结果。
- 页面结果交给 `ppt-page-html`，并按 `pages/page_XX.html` 逐页落盘。
- 最终结果必须经过 `ppt-review`。

## 路径选择

### fast

适合简单、目标明确、希望尽快生成整套 PPT 的场景。

默认路径：

1. `ppt-task-pack`
2. `ppt-style-spec`
3. `ppt-storyboard`
4. `ppt-page-html`
5. `ppt-review`

### guided

适合需要阶段确认的场景。优先落盘并展示关键工件：

- 如果用户说“先看大纲”“先确认大纲”“先看风格和大纲”或“确认后再生成”，必须进入 `guided`。
- 此时应先产出并展示 `task-pack.json`、`style-spec.json`、`storyboard.json`。
- 在用户确认前，不要直接生成 `pages/page_XX.html`。
- 不要只返回一段自由文本大纲，必须落盘并展示结构化工件。

- `task-pack.json`
- `style-spec.json`
- `storyboard.json`

### surgical

适合局部修复：

- 只改第 3 页
- 只替换某个图片槽位
- 只增强某套风格规则

## 禁止事项

- 不要再调用旧 `pptx`、`ppt-outline-gen`、`ppt-style-extract`、`ppt-image-selection`、`ppt-html-gen`。
- 不要跳过 `style-spec.json` 或 `storyboard.json` 直接开始 HTML 生成。
- 不要跳过图片筛选和本地下载验证，直接把远程 URL 当成最终资产。
- 不要把用户上传文件的内容、风格、模板角色混在一起使用。
- 不要把中间结果直接写到 agent 根目录。
- 不要把整套 deck 拼成单个 HTML 文件交付。
