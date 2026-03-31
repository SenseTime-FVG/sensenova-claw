---
name: ppt-page-plan
description: 当只需要重做某一页的页面目标、内容块、布局方向或视觉需求，而不希望重跑整套 storyboard 时使用。
---

# PPT 单页规划

`ppt-review` 发现某页叙事角色、内容块或布局方向有问题时，进入本 skill 做最小范围的页面级规划修正。

## 目标

仅修改指定 `page_id` 对应的页面规划，并保持整套叙事连贯。

## 触发条件

- `ppt-review` 判定某页 `narrative_role` 模糊或与上下页重叠
- `ppt-review` 判定某页 `payload_budget` 与实际内容不匹配
- `ppt-review` 判定某页 `content_blocks` 缺失或冗余
- `ppt-review` 判定某页 `layout_intent` 与页面类型冲突
- 用户主动要求重新规划某一页

## 输入

- `storyboard.json`（必须已存在且可读）
- 指定 `page_id`
- 用户补充要求（如有）
- 可选的 `style-spec.json`（用于确认 `style_variant` 映射）
- 可选的 `task-pack.json`（用于确认 `content_density_profile`）

## 输出

- 更新后的 `storyboard.json`，仅修改目标 `page_id` 对应的 `StoryboardPage` 对象
- 对其他页面的最小影响说明（如果有）

## 执行规则

### 1. 依赖检查

- 读取 `storyboard.json`，确认 `page_id` 存在且锚点有效。
- 如果 `page_id` 不存在或页面锚点已失效，停下并反馈，不要猜测。
- 读取 `style-spec.json`，确认目标页引用的 `style_variant` 在 `page_type_variants` 中存在。

### 2. 问题诊断

- 对照 `ppt-review` 的问题描述或用户要求，定位需要修改的字段。
- 可修改的字段范围：`title`、`narrative_role`、`audience_takeaway`、`layout_intent`、`style_variant`、`payload_budget`、`content_blocks`、`visual_requirements`、`data_requirements`、`asset_requirements`、`unresolved_issues`、`presenter_intent`。
- 不可修改的字段：`page_id`、`page_number`、`section`（除非用户明确要求换章节）。

### 3. 内容块调整

- 如果需要增减 `content_blocks`，必须同步更新 `payload_budget` 中的 `claim_count`、`evidence_count`、`structure_block_count`。
- 新增的 `content_blocks` 必须填写 `source_claim_ids` 和 `source_evidence_ids`，引用 `research-pack` 中实际存在的条目。
- 删除的 `content_blocks` 对应的内容应说明去向（合并到其他块、移到其他页、或确认不需要）。

### 4. payload_budget 调整

- 必须参照 `task-pack.json.content_density_profile` 和 `style-spec.json.density_rules` 重新评估预算。
- `analysis-heavy` 页允许更高预算；`showcase-light` 页可适当降低但不能为零。
- 调整后的预算必须与 `content_blocks` 实际数量和深度匹配。

### 5. 影响范围评估

- 检查上一页的 `audience_takeaway` 是否仍然能平滑过渡到本页。
- 检查下一页的 `narrative_role` 是否因本页变化而需要调整。
- 如果存在影响，在输出中明确列出需要同步更新的最小页面范围，但不主动修改其他页面。

### 6. 写回

- 仅覆盖 `storyboard.json` 中目标 `page_id` 对应的对象，其他页面保持不变。
- 写回后验证 JSON 格式正确、`total_pages` 未变。

## 可处理的问题类型

- 叙事角色模糊：`narrative_role` 过于宽泛或与相邻页重叠
- 内容块不足：`content_blocks` 数量少于 `payload_budget` 要求
- 内容块冗余：承载了不属于本页的内容
- 布局方向错误：`layout_intent` 与 `style_variant` 的 `layout_shell` 冲突
- 资产需求缺失：`asset_requirements` 未覆盖页面语义所需的图片或插画
- 视觉需求不清：`visual_requirements` 描述模糊，无法指导 `ppt-page-html`

## 用户回显

- **开始反馈**：说明当前锁定的 `page_id` 和本次只会调整该页规划。
- **完成反馈**：总结本页规划变化、是否影响相邻页，以及 `下一步`。

## 关键原则

- 消费前必须先确认 `storyboard.json` 真实存在且可读。
- 如果目标文件不存在、`page_id` 不存在或页面锚点已失效，先补齐依赖，不要猜测。
- 只修这页，不重跑整套。
- 保持 `page_id` 稳定，便于前端回填。
- 如果页面改动会影响上下页过渡，明确指出需要同步更新的最小范围。
- `style_variant` 必须引用 `style-spec.json` 中已声明的 variant，不要重新发明名称。
- `asset_requirements` 必须用可指导分流的提示（如 `real-photo`、`svg-illustration`、`svg-icon`），不要写模糊描述。

## 禁止事项

- 不要重跑整套 storyboard。
- 不要修改其他 `page_id` 的内容。
- 不要更改 `page_id` 或 `page_number`。
- 不要在没有 `research-pack` 引用的情况下伪造 `source_claim_ids` 或 `source_evidence_ids`。
- 不要把 `payload_budget` 全部清零以"简化"页面。
- 不要因为修改困难就建议整套重做。
