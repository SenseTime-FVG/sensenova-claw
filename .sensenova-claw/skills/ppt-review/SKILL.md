---
name: ppt-review
description: 当需要审查整套 PPT 的叙事完整性、风格执行度、页面质量和局部返工建议，并决定是否进入页面级或槽位级修复时使用。
---

# PPT 整套审查

对整套 deck 做结构化审查，输出继续交付或局部返工建议。

## 目标

- 逐维度审查整套 deck 的叙事完整性、风格执行度、页面质量和资产状态。
- 产出结构化审查报告，写入 `deck_dir/review.json`。
- 给出总体结论（通过 / 有条件通过 / 阻塞），并为每个问题推荐精确的下钻 skill。

## 触发条件

- 所有页面 HTML 已生成，且 `ppt-page-assets` 已完成至少一轮资产落地。
- 用户显式要求审查，或流水线到达 review 节点。

## 输入

- `task-pack.json`：任务包，用于核对任务目标是否被满足。
- `style-spec.json`：风格规格，用于核对设计执行度。
- `storyboard.json`：分页叙事，用于核对页面一致性和 `payload_budget`。
- `asset-plan.json`（可选）：资产计划，用于交叉核对槽位兑现情况。
- `pages/page_*.html`：所有已生成的页面文件。

## 输出

- 输出路径必须严格为 `${deck_dir}/review.json`。
- 不能只在聊天消息里口头总结，必须写出文件。
- 必须写出 `review.json`。
- 至少包含以下内容：
  - **总体结论**：通过 / 有条件通过 / 阻塞。
  - **页面级问题列表**：每个问题标注 `page_id`、问题类型、严重程度。
  - **建议触发的下钻 skill**：针对每类问题推荐具体修复路径。
- `review.json` 的字段名、顶层字段顺序和嵌套对象结构必须固定，方便后续前后端稳定解析。

### 固定格式规则

- 所有顶层字段必须出现，字段顺序必须保持一致：`schema_version`、`deck_dir`、`status`、`can_export`、`summary`、`issue_count`、`blocking_count`、`warning_count`、`missing_dependencies`、`checks`、`issues`、`recommended_next_steps`、`notes`。
- 不要增加未定义顶层字段；额外说明只能写入 `notes`、`checks[*].summary`、`checks[*].evidence` 或 `issues[*].detail`。
- 空列表必须写成 `[]`，不要省略字段；无值字符串写成 `""`，可空字段写成 `null`，布尔值必须明确写成 `true` 或 `false`。
- `schema_version` 固定为 `ppt-review.v1`。
- `status` 只能是 `通过`、`有条件通过` 或 `阻塞`，含义保持原有判定规则不变。
- `can_export` 只表达该 review 是否允许进入导出；必须按原有总体结论和问题判定规则填写，不要因为新增字段改变 `status` 的含义。
- `checks` 必须按 `CheckId` 定义的顺序逐项输出，每个审查维度必须出现一次；无法检查时使用 `blocked` 或 `not_applicable`，不要删除该项。
- `issues` 只记录实际问题；无问题时写 `[]`，不要改写成自然语言段落。
- `recommended_next_steps` 只记录需要触发的后续 skill；无需修复时写 `[]`。
- 实际写入的 `review.json` 必须是合法 JSON，不要包含 Markdown、注释或 Python 语法。

## 数据结构

```python
from typing import Literal

ReviewStatus = Literal["通过", "有条件通过", "阻塞"]
CheckStatus = Literal["pass", "warn", "fail", "not_applicable", "blocked"]
ReviewSeverity = Literal["warning", "blocking"]
IssueScope = Literal["deck", "page", "slot", "asset"]
NextStepPriority = Literal["high", "medium", "low"]
SkillName = Literal[
    "ppt-page-plan",
    "ppt-page-polish",
    "ppt-page-assets",
    "ppt-style-refine",
    "ppt-story-refine",
    "ppt-asset-plan",
]
CheckId = Literal[
    "task_fulfillment",
    "style_execution",
    "narrative_consistency",
    "payload_budget_delivery",
    "page_asset_fulfillment",
    "style_drift",
    "overflow_or_underfilled",
    "payload_underdelivery",
    "structure_block_underdelivery",
    "comparison_or_summary_missing",
    "unresolved_asset_handling",
    "bg_motif_layer",
    "fg_motif_layer",
    "motif_strength",
    "real_photo_delivery",
    "image_quality",
    "source_consistency",
]


class ReviewReport:
    schema_version: Literal["ppt-review.v1"]
    deck_dir: str
    status: ReviewStatus
    can_export: bool
    summary: str
    issue_count: int
    blocking_count: int
    warning_count: int
    missing_dependencies: list[str]
    checks: list["ReviewCheck"]
    issues: list["ReviewIssue"]
    recommended_next_steps: list["ReviewNextStep"]
    notes: list[str]


class ReviewCheck:
    check_id: CheckId
    name: str
    status: CheckStatus
    summary: str
    page_ids: list[str]
    evidence: list["ReviewEvidence"]


class ReviewIssue:
    issue_id: str
    scope: IssueScope
    page_id: str | None
    slot_id: str | None
    issue_type: str
    severity: ReviewSeverity
    title: str
    detail: str
    evidence: list["ReviewEvidence"]
    suggested_skill: SkillName | None
    suggested_action: str
    affected_files: list[str]


class ReviewNextStep:
    skill: SkillName
    reason: str
    scope: IssueScope
    page_ids: list[str]
    slot_ids: list[str]
    priority: NextStepPriority


class ReviewEvidence:
    file: str
    selector: str | None
    detail: str
```

## 执行规则

### 审查维度

以下维度必须逐项检查，不得跳过：

1. **任务满足度**：`task-pack.json` 中的目标、页数、场景是否被满足。
2. **风格执行度**：`style-spec.json` 是否被忠实执行。
3. **叙事一致性**：`storyboard.json` 与最终页面是否一致。
4. **承载预算兑现**：`storyboard.json.pages[n].payload_budget` 是否被兑现——逐页对照 `claim_count`、`evidence_count`、`structure_block_count`、`require_comparison_or_summary`。
5. **页级资产满足**：是否满足页级 `asset_requirements`。
6. **风格漂移**：页面之间是否存在风格漂移。
7. **溢出与过空**：单页是否溢出、过空或信息失衡。
8. **承载不足**：`payload_budget` 明确要求多块承载，但页面只剩松散标题区或单一大卡片。
9. **结构块不足**：结构块数量低于预算要求。
10. **对比/摘要缺失**：预算要求了对比或摘要但页面没有兑现。
    - 缺少对比或摘要应直接记为问题。
11. **unresolved 处理**：资产计划中的 `unresolved` 是否需要继续处理。
12. **背景装饰层**：是否缺少 `data-layer="bg-motif"` 标记；是否只有纯色或渐变背景。
13. **前景装饰层**：是否缺少 `data-layer="fg-motif"` 标记。
    - 缺少背景装饰层应直接记为问题。
    - 缺少前景装饰层应直接记为问题。
14. **装饰层强度**：装饰层是否只是很小的角标或极弱纹理，不足以构成真正的背景/前景层。
15. **real-photo 兑现**：如果要求真实图片却只落了 SVG 或 placeholder；如果某页仍存在必需 `real-photo` 槽位未兑现。
16. **图片质量**：已落地真实图片的清晰度、相关性、水印、槽位语义一致性。
17. **信息来源一致性**：页面里是否出现 storyboard 之外的新文本、新数值或新图表数据。

### 核对方式

- 消费前必须先确认 `task-pack.json`、`style-spec.json`、`storyboard.json` 以及已产出的页面文件真实存在且可读。
- 如果目标文件不存在、目录不一致或交付物缺页，先标记缺失依赖，不要猜测。
- 必须直接读取页面 HTML，必要时结合 DOM/CSS 结构核对装饰层，不要只根据模型自述判定通过。
- 必须交叉核对 `storyboard.json.pages[n].asset_requirements`、`asset-plan.json.slots` 与最终 HTML，不要只看其中一层。
- 必须核对 `storyboard.json.pages[n].title_atom_ids`、`display_items` 与最终 HTML，不要接受页面阶段现场补编。
- 对图表页，必须逐项核对图表标题、系列名、数值、图例是否都能回指到 `display_items` 与 `atom_ids`。
- 如果图表中的可见文本或数值没有 `data-display-id` 或 `data-atom-ids`，不得判定通过。
- 必须检查页面里是否存在 `data-layer="bg-motif"` 与 `data-layer="fg-motif"` 装饰层证据。
- 如果 style-spec recipe 要求某个 motif，就要在页面里找到对应的 `data-motif-key`。
- 如果页面里出现 storyboard 之外的新文本、新数值或新图表数据，必须判定为阻塞。
- 必须检查标题元素是否放在 `#ct` 或 `#header`。
- 不要把仅存在于源码但被层级盖住的标题判成通过；如果 `.header` 落在 `#ct` 外面，应视为标题不可见。

### 图片质量复核

- 必须复核已落地真实图片的质量，不要因为"已经下载成功"就默认通过。
- 对已选图片至少复核这些硬性项：`清晰度`、`相关性`、`明显水印`、`槽位语义一致性`。
- 任一硬性项失败，必须判定为阻塞，不得交付。
- `构图` 与 `风格一致性` 属于弱筛查；没有明显大问题时可以通过，但要在 review 中留下告警或备注。

### 路由逻辑

- 能局部修复的问题，不要整套推倒重来。
- 如果只是某页问题，应转到 `ppt-page-plan`、`ppt-page-polish` 或 `ppt-page-assets`。
- 如果某页仍存在必需 `real-photo` 槽位未兑现或真实图片质量不合格，应转到 `ppt-page-assets`。
- 如果是全局设计问题，应转到 `ppt-style-refine`。
- 如果是叙事节奏问题，应转到 `ppt-story-refine`。
- 资产类问题应转到 `ppt-page-assets` 或回到 `ppt-asset-plan` 继续补齐。

## 用户回显

- **开始反馈**：说明正在审查整套 deck，并指出会检查结构、风格、页面质量和资产状态。
- **完成反馈**：给出总体结论、问题数量、推荐下钻 skill 和 `下一步`。
- 如果 review 发现阻塞性交付问题，要在反馈里明确指出不能直接交付的原因，不要只给笼统评价。

## 关键原则

- 审查结果必须写回文件，不能只在聊天消息里口头总结。
- 必须逐页对照 `payload_budget`，不得只看整体印象。
- DOM/CSS 结构核对是必须步骤，不能只凭模型记忆判定通过。
- 交叉核对三层资产（storyboard 要求、asset-plan 槽位、最终 HTML）是必须步骤。
- 页面信息回指核对也是必须步骤；不要接受页面阶段现场补编。
- 如果没有 `review.json`，后续不要直接进入导出。

## 禁止事项

- 如果页面只有纯色或渐变背景，且缺少背景装饰层或前景装饰层，不能直接交付。
- 如果页面要求真实图片却只落了 SVG 或 placeholder，不能直接交付。
- 如果某页仍存在必需 `real-photo` 槽位未兑现，即使页面其他部分完成，也必须判定为阻塞。
- 如果已落地真实图片存在清晰度不足、相关性不足、明显水印或槽位语义不一致，必须判定为阻塞。
- 如果页面里出现 storyboard 之外的新文本、新数值或新图表数据，必须判定为阻塞。
- 如果图表标题、系列名、数值、图例没有显式回指，或只存在于 HTML 而不存在于 `storyboard.json.display_items`，必须判定为阻塞。
- 如果图表中的可见文本或数值没有 `data-display-id` 或 `data-atom-ids`，不得判定通过。
- 不要接受页面阶段现场补编。
- 不要写成 `Pass with minor notes`，也不要建议立即导出。
- 如果 `payload_budget` 明确要求多块承载，但页面只剩一个松散标题区或单一大卡片，不能直接交付。
