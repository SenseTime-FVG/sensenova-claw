---
name: ppt-task-pack
description: 当需要把用户意图、页数、受众、语言、限制、交付物和信息缺口统一收束为一个稳定任务包时使用。
---

# PPT 任务包

将用户意图收束为一个稳定的任务边界定义，同时作为内容控制面评估信息缺口，为后续所有 skill 提供统一输入。

## 目标

1. 生成 `task-pack.json`，固定主题、受众、目标、语言、页数、交付物、限制和风格意图。
2. 评估内容缺口，决定是否需要进入 `ppt-research-pack`。
3. 确定并记录 `deck_dir`，作为后续所有 skill 的 canonical 输出根目录。
4. 确定 `content_density_profile`，为后续 `ppt-storyboard` 提供正文页承载策略。

## 触发条件

- 新建 deck 时，由 `ppt-superpower` 路由进入。
- 需要重新明确页数、受众、语言或交付物时。
- `ppt-source-analysis` 完成后，需要把来源分析结论转化为任务边界时。

## 输入

- 用户 query（必需）。
- `source-map.json`（可选，来自 `ppt-source-analysis`）。
- 用户上传的文件、链接、截图（可选，作为 `research_required` 判断信号）。

## 输出

- `${deck_dir}/task-pack.json`

## 执行规则

### 必须覆盖的字段

每个 `task-pack.json` 必须包含以下字段，不允许遗漏：

- `schema_version` -- 工件 schema 版本号。
- `topic` -- 主题。
- `audience` -- 受众。
- `goal` -- 演示目标。
- `language` -- 默认语言，与用户 query 保持一致。
- `total_pages` -- 目标页数；如果用户未明确给出，需写明合理假设。
- `mode` -- 当前建议模式（`fast` / `guided` / `surgical`）。
- `deliverables` -- 交付物需求列表；如果讲稿是交付物，必须显式声明。
- `must_have_sections` -- 必须覆盖的章节。
- `constraints` -- 约束条件。
- `known_gaps` -- 当前已知但尚未补齐的问题清单，记录用户未提供的信息、待确认项、缺失材料。
- `content_gap_assessment` -- 结构化内容缺口判断，记录当前内容缺什么、为什么缺、会阻塞什么。
- `research_required` -- 是否需要进入 `ppt-research-pack`，由本 skill 自行判断并显式记录。
- `research_needs` -- 研究需求列表，每项包含 topic、reason、scope、priority。
- `available_sources` -- 可用来源列表。
- `style_intent` -- 风格意图。
- `content_density_profile` -- 正文页内容承载 profile。
- `deck_dir` -- 输出根目录。
- `output_policy` -- 输出目录策略。

### 风格意图规则

- 风格意图必须先从用户 query 中抽取，而不是等到 `ppt-style-spec` 再临时猜测。
- 至少要覆盖 `scenario`（场景）、`tone`（气质）、`industry_context`（行业语境）和 `explicit_style_preference`（显式风格偏好）。
- 如果用户已经明确给出风格偏好、品牌语气、参考图或模板方向，必须在任务包中显式记录，供后续 `ppt-style-spec` 优先消费，不能覆盖它。

### 内容承载 profile 规则

- `content_density_profile` 是正文页的承载策略，不是单纯视觉风格切换。
- `ppt-task-pack` 负责根据主题和场景选择默认 profile，并允许用户偏好覆盖。
- `analysis-heavy`：适合分析 / 汇报 / 评估类主题，正文页默认允许更高论点、证据与结构承载。
- `balanced`：适合普通汇报 / 培训 / 项目介绍，正文页默认在信息量与留白之间保持均衡。
- `showcase-light`：适合品牌 / 展示 / 活动 / 发布类主题，正文页默认强调主视觉、节奏和更克制的文字承载。
- 用户明确要求更满或更克制时，可覆盖默认 profile；不要死守主题默认值。
- 本轮只固定 profile 控制面，不引入 `payload_budget`；`payload_budget` 由后续 `ppt-storyboard` 逐页展开。

### 内容缺口与 research 门控

- `known_gaps` 记录现象：用户未提供的信息、待确认项、缺失材料。
- `content_gap_assessment` 记录判断：这些缺口为什么会触发 research 或影响后续内容决策。
- 两个字段应职责分明：`known_gaps` 是现象层清单，`content_gap_assessment` 是结构化评估，避免内容重复。
- `research_required` 由 `task-pack.json` 自己判断并显式记录，是后续是否进入 `ppt-research-pack` 的唯一门控输入。
- `research_needs` 必须把需要补充的 topic、reason、scope、priority 写清楚，避免 research 退化成泛化搜索。
- 必须先生成 `task-pack.json`，不允许在 `ppt-task-pack` 之前做外部 research 决策。
- 上传报告、事实数据案例和长文档只是判断 `research_required` 的信号，不是绕过本 skill 的独立入口。

### Deck 目录规则

- `deck_dir` 是本轮任务的 canonical 输出根目录。
- `deck_dir` 必须在这里被明确固定，后续所有 skill 都复用同一个输出目录。
- 后续 skill 只能直接复制这个值，不要自行改写、缩写、翻译或重拼目录名。
- 如果用户没有指定输出地点，`deck_dir` 应使用 `query概述 + 时间戳` 自动创建，而不是把产物直接写到当前目录顶层。

## 数据结构

```python
from typing import Literal

Mode = Literal["fast", "guided", "surgical"]
OutputPolicy = Literal["user-provided", "reuse-existing", "auto-generated"]
ContentDensityProfile = Literal["analysis-heavy", "balanced", "showcase-light"]


class ResearchNeed:
    topic: str
    reason: str
    scope: list[str]
    priority: str


class StyleIntent:
    scenario: str
    audience_signal: str
    tone: list[str]
    industry_context: str
    explicit_style_preference: str | None


class TaskPack:
    schema_version: str
    topic: str
    audience: str
    goal: str
    language: str
    total_pages: int
    mode: Mode
    deliverables: list[str]
    must_have_sections: list[str]
    constraints: list[str]
    known_gaps: list[str]
    content_gap_assessment: list[str]
    research_required: bool
    research_needs: list[ResearchNeed]
    available_sources: list[str]
    style_intent: StyleIntent
    content_density_profile: ContentDensityProfile
    deck_dir: str
    output_policy: OutputPolicy
```

## 用户回显

- **开始反馈**：说明正在整理任务包，并告知会固定 `deck_dir`、页数假设和 mode。
- **完成反馈**：总结主题、受众、总页数、当前 mode、`deck_dir`、`research_required` 和关键假设，并说明 `下一步`。
- **阻塞**：如果 query 中存在必须依赖假设的边界条件，要在反馈里明确写出假设项或待确认项，不要静默带过。

## 关键原则

- 面向用户阅读的自然语言内容默认与用户 query 保持一致。
- `task-pack.json` 不只是任务收敛层，也是内容控制面：要先把内容缺口评估清楚，再决定 research 是否值得执行。
- 风格意图在这里就要抽取，不能推迟到 `ppt-style-spec` 再临时猜测。
- `deck_dir` 一旦固定，后续链路中不可更改。

## 禁止事项

- 不要在本 skill 之前做外部 research 决策。
- 不要省略 `content_gap_assessment`，只保留 `known_gaps`。
- 不要在本轮引入 `payload_budget`；本轮只固定 profile 控制面。
- 不要把产物直接写到当前目录顶层或 agent 根目录。
- 不要手写、缩写、翻译或重拼 `deck_dir` 目录名。
