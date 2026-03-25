---
name: ppt-task-pack
description: 当需要把用户意图、页数、受众、语言、限制、交付物和信息缺口统一收束为一个稳定任务包时使用。
---

# PPT 任务包

## 目标

必须先生成 `task-pack.json`，为后续所有技能提供统一的任务边界。
实验 1 中，`task-pack` 同时是内容控制面：要先判断内容缺口，再决定是否需要 research。

## 用户回显要求

- `开始反馈`：说明正在整理任务包，并告知会固定 `deck_dir`、页数假设和 mode。
- `完成反馈`：总结主题、受众、总页数、当前 mode、`deck_dir` 和 `下一步`。
- 如果 query 中存在必须依赖假设的边界条件，要在反馈里明确写出假设项或待确认项，不要静默带过。

## 必须覆盖

- 主题
- 受众
- 演示目标
- 风格意图
- 正文页内容承载 profile
- 目标页数
- 默认语言
- 必须覆盖的章节
- 约束条件
- 当前交付物需求
- 已知缺口
- 内容缺口评估
- 研究需求列表
- 当前建议模式

## 建议结构

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

## 关键原则

- 面向用户阅读的自然语言内容默认与用户 query 保持一致。
- 如果页数没有明确给出，需要在任务包中写明合理假设。
- 如果讲稿是交付物，必须在 `deliverables` 中显式声明。
- `风格意图` 必须先从用户需求中抽取，而不是等到 `style-spec` 再临时猜测。
- 至少要记录 `场景`、`气质`、`行业语境` 以及用户是否已经给出明确风格偏好。
- 如果用户已经明确给出风格偏好、品牌语气、参考图或模板方向，必须在任务包中显式记录，后续 `style-spec` 不能覆盖它。
- `content_density_profile` 是正文页的承载策略，不是单纯视觉风格切换。
- `ppt-task-pack` 负责根据主题/场景选择默认 profile，并允许用户偏好覆盖。
- `analysis-heavy` 适合分析 / 汇报 / 评估类主题，正文页默认允许更高论点、证据与结构承载。
- `balanced` 适合普通汇报 / 培训 / 项目介绍，正文页默认在信息量与留白之间保持均衡。
- `showcase-light` 适合品牌 / 展示 / 活动 / 发布类主题，正文页默认强调主视觉、节奏和更克制的文字承载。
- 用户明确要求更满或更克制时，可覆盖默认 profile；不要死守主题默认值。
- `deck_dir` 是本轮任务的 canonical 输出根目录。
- `deck_dir` 必须在这里被明确固定，后续所有 skill 都复用同一个输出目录。
- 后续 skill 只能直接复制这个值，不要自行改写、缩写、翻译或重拼目录名。
- 如果用户没有指定输出地点，`deck_dir` 应使用 `query概述 + 时间戳` 自动创建，而不是把产物直接写到当前目录顶层。
- `known_gaps` 保留“当前已知但尚未补齐的问题清单”角色，适合记录用户未提供的信息、待确认项、缺失材料等简短缺口。
- `content_gap_assessment` 必须显式列出当前内容还缺什么、为什么缺，以及这些缺口会阻塞哪些后续判断。
- `content_gap_assessment` 负责更结构化的判断，用来解释缺口对 research、分页叙事和内容决策的影响。
- 避免两个字段看起来重复：`known_gaps` 记录现象，`content_gap_assessment` 记录判断。
- `research_required` 由 `task-pack.json` 自己判断并显式记录。
- `research_needs` 必须把需要补充的 topic、reason、scope、priority 写清楚，避免 research 退化成泛化搜索。
- 不允许在 `task-pack` 之前做外部 research 决策。
