---
name: ppt-story-refine
description: 当整套 PPT 的事实和素材基本齐全，但叙事顺序、章节节奏、结论前置程度或页面分配不合理，需要只调整故事线时使用。
---

# PPT 叙事修正

`ppt-review` 发现叙事结构层面的问题（顺序、节奏、分配）时，进入本 skill 调整 `storyboard.json` 的故事线。

## 目标

在不重做研究与设计控制面的前提下，更新 `storyboard.json` 的叙事结构，使故事线更清晰、节奏更合理。

## 触发条件

- `ppt-review` 判定结论出现太晚，受众无法快速抓住核心观点
- `ppt-review` 判定章节顺序不合逻辑，叙事跳跃
- `ppt-review` 判定某部分页数分配失衡（过多或过少）
- `ppt-review` 判定页面承担的叙事角色模糊或重叠
- `ppt-review` 判定缺少过渡页或收束页，导致节奏断裂
- 用户主动要求调整故事线或章节顺序

## 输入

- `storyboard.json`（必须已存在且可读）
- `task-pack.json`（用于确认总页数、`must_have_sections`、`content_density_profile`）
- `ppt-review` 的问题描述或用户补充要求
- 可选的 `style-spec.json`（用于确认 variant 映射是否仍然成立）
- 可选的 `research-pack.json`（用于确认内容引用仍然有效）

## 输出

- 更新后的 `storyboard.json`
- 变更摘要：列出哪些页面被移动、合并、拆分或删除
- 影响说明：列出需要连带更新的下游工件（如果有）

## 执行规则

### 1. 依赖检查

- 确认 `storyboard.json` 真实存在且可读。
- 确认 `task-pack.json` 存在，读取 `total_pages`、`must_have_sections`、`content_density_profile`。
- 如果目标文件不存在或路径不一致，先补齐依赖，不要猜测。

### 2. 叙事问题评估

- 对照 `ppt-review` 的问题描述，逐页审视当前叙事结构：
  - 每页的 `narrative_role` 是否清晰且不重叠
  - 页面顺序是否符合逻辑递进（背景 -> 问题 -> 分析 -> 方案 -> 结论）
  - 核心结论是否在前 1/3 出现（如果是汇报型 deck）
  - 章节之间是否有平滑过渡
  - 各章节页数分配是否与内容权重匹配
  - 是否存在无明确叙事角色的"多余页"

### 3. 调整策略

允许的调整操作：
- **页面重排**：改变 `page_number` 顺序，重新分配 `section` 归属
- **页面合并**：将两页的 `content_blocks` 合并为一页，删除冗余页
- **页面拆分**：将过载页拆为两页，各自分配 `content_blocks` 和 `payload_budget`
- **页面新增**：在章节间插入过渡页或收束页
- **叙事角色重定义**：更新 `narrative_role`、`audience_takeaway`

### 4. 页码重排规则

- 调整后必须重新编排 `page_number`，从 1 开始连续递增。
- `page_id` 保持不变（已有页面），新增页面分配新的 `page_id`。
- `total_pages` 必须同步更新。
- 如果总页数变化超出 `task-pack.json.total_pages` 的 +-2 页范围，必须在反馈中说明原因。

### 5. 内容引用完整性

- 调整后每个 `content_blocks[n]` 的 `source_claim_ids` 和 `source_evidence_ids` 必须仍然有效。
- 合并页面时，合并后的 `content_blocks` 不能丢失原有引用。
- 删除页面时，被删页面的内容引用应迁移到其他页面或明确标记为不再需要。
- `unresolved_gaps` 不能因为调整而被静默丢弃。

### 6. 预算重评估

- 合并或拆分页面后，必须重新评估受影响页面的 `payload_budget`。
- 参照 `content_density_profile` 和页面的 `page_type` / `narrative_role` 重新分配预算。
- 不要让合并后的页面预算超载，也不要让拆分后的页面预算为空。

### 7. 下游影响评估

- 列出调整后可能需要连带更新的工件：
  - 页码变化 -> `pages/page_XX.html` 文件名需要重命名
  - 页面删除 -> 对应 HTML 文件需要清理
  - `style_variant` 引用变化 -> 确认 `style-spec.json` 中仍存在对应 variant
  - `asset_requirements` 变化 -> 确认 `asset-plan.json` 槽位映射仍然有效
- 不主动修改下游工件，但必须在影响说明中列出。

## 用户回显

- **开始反馈**：说明正在调整叙事结构，并指出本次影响的是哪些章节或页面范围。
- **完成反馈**：总结故事线如何调整、受影响页数以及 `下一步`。

## 关键原则

- 先修叙事，再决定是否需要连带调整页面或资产。
- 尽量保持已有 `style_variant` 和可用资源复用。
- 局部改动要明确影响范围。
- `page_id` 保持稳定，便于前端回填和下游工件关联。
- `must_have_sections` 中的必要章节不能在调整中被删除。
- 调整后的叙事必须仍然服务于 `task-pack.json.goal`。

## 禁止事项

- 不要重做研究（`research-pack`）。
- 不要修改 `style-spec.json`。
- 不要直接修改页面 HTML。
- 不要修改 `asset-plan.json`。
- 不要删除 `must_have_sections` 中的必要章节。
- 不要在没有内容支撑的情况下凭空新增页面。
- 不要把 `source_claim_ids` 或 `source_evidence_ids` 改为伪造引用。
- 不要因为调整困难就建议整套重做。
