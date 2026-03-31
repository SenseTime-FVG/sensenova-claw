---
name: ppt-page-assets
description: 当只需要修复某一页或某个槽位的图片、插图、图标或背景资产，而其他页面无需重算时使用。
---

# PPT 单页资产修复

`ppt-review` 发现某页或某槽位的图片资产存在问题时，进入本 skill 做最小范围的资产替换与修复。

## 目标

针对单页或单槽位更新 `asset-plan.json`，必要时重新生成：

- `image_search_results.json`
- `image_selection.json`
- 对应的本地图片文件

所有修复结果仍必须落回同一个 `deck_dir`。

## 触发条件

- `ppt-review` 判定某张图片清晰度不足、相关性不足、存在明显水印或语义不一致
- `ppt-review` 判定某个 `real-photo` 槽位未兑现（仍为 placeholder 或 SVG 替代）
- `ppt-review` 判定某个槽位下载失败或本地路径失效
- `ppt-review` 判定某张图片与页面语义不符
- 用户主动要求替换某页的封面图、hero 图或特定槽位图片

## 输入

- `task-pack.json`（用于确认 `deck_dir`）
- `asset-plan.json`（必须已存在且可读）
- `storyboard.json`（用于确认页面语义和 `asset_requirements`）
- 指定的 `page_id` 和/或 `slot_id`
- 可选的 `style-spec.json`（用于风格一致性筛查）

## 输出

- 更新后的 `asset-plan.json`（仅修改目标槽位）
- 更新后的 `image_search_results.json`（如果重新搜图）
- 更新后的 `image_selection.json`（如果重新选图）
- 新的本地图片文件（写入 `deck_dir/images/`）

## 适用场景

- 只换封面图
- 只换第 5 页 hero 图
- 某个槽位下载失败需要重试
- 某张图与页面语义不符需要替换
- 某张图存在水印或清晰度问题
- 某页缺少规划中的多图槽位

## 执行规则

### 1. 依赖检查

- 确认 `task-pack.json`、`asset-plan.json`、`storyboard.json` 真实存在且可读。
- 如果目标文件不存在、槽位记录缺失或本地路径失效，先补齐依赖，不要猜测。
- 确认 `deck_dir/images/` 目录存在；如果不存在，先创建。

### 2. 定位目标槽位

- 根据 `page_id` 和/或 `slot_id` 在 `asset-plan.json` 中定位需要修复的槽位。
- 交叉核对 `storyboard.json.pages[n].asset_requirements`，确认槽位语义。
- 如果 `asset-plan.json` 中缺少对应槽位记录，先补建槽位条目。

### 3. 重新搜图

- 根据槽位的 `purpose`、`source_caption` 和页面语义重新生成搜图 query。
- query 保持单意图、短语化，不要把整页大纲拼成一长串。
- 执行搜图，将原始候选写入 `image_search_results.json` 对应槽位。
- 必须保留 query、候选列表和来源信息。

### 4. 候选筛选与下载

- 先判断候选是否与搜索意图和页面语义相关，再进入下载队列。
- 下载必须逐张进行，确认本地文件真实存在、非空、可读、确实是图片。
- 下载失败、内容无效、强水印、缩略图、语义不符的候选写入 `rejected_candidates`。

### 5. 下载后图片审核

硬性筛查（任一失败必须踢掉）：
- `清晰度`不足
- `相关性`不足
- 存在`明显水印`
- `槽位语义一致性`不符

弱筛查（可通过但必须记录 warning）：
- `构图`
- `风格一致性`

每张候选必须填写完整的 `quality_review`，包括 `clarity`、`relevance`、`watermark`、`semantic_alignment`、`composition`、`style_fit`、`hard_fail_reasons`、`soft_warnings`。

### 6. 最终选择与写回

- 最终选择只能从下载成功且硬性筛查全部通过的本地文件中产生。
- 更新 `asset-plan.json` 中目标槽位的 `selected_image`、`quality_review`、`rejected_candidates`、`status`。
- 更新 `image_selection.json` 对应记录。
- 其他槽位和页面的记录保持不变。

### 7. 失败处理

- 如果前一批候选全部失败，重新搜索并覆盖对应槽位的 `image_search_results.json` / `image_selection.json` 记录。
- 如果多轮搜索仍无法找到合适图片，将槽位标记为 `unresolved` 并在完成反馈中明确说明。

## 用户回显

- **开始反馈**：说明当前锁定的页面或槽位，以及将要更新哪些资产记录。
- **进行中**：如果需要重新搜图或重下多张图片，可补 1 条简短进度说明。
- **完成反馈**：总结已替换的本地图片、仍未解决的槽位，以及 `下一步`。

## 关键原则

- 优先保留其他槽位和页面不变。
- 更新后必须保持本地路径可读。
- 单页修复也必须保留搜图候选、筛选理由和下载结果，不能只留下最后一张图。
- 单页修复也必须执行下载后图片审核，不要因为是局部修复就放宽标准。
- 如果前一批候选全部失败，应重新搜索并覆盖对应槽位的记录。

## 禁止事项

- 不要跳过筛选过程，直接手工指定一张远程图片结束任务。
- 不要把失败的远程 URL 标成已完成。
- 不要把只有远程 URL 而没有下载成功的本地文件标记为 `selected=True`。
- 不要修改与目标槽位无关的其他页面资产。
- 不要把应由 `real-photo` 承载的槽位改写成 `svg-illustration` 来规避搜图。
- 不要删除其他槽位的 `rejected_candidates` 或 `quality_review` 记录。
- 不要把清晰度不足、水印明显或语义不符的图片标为通过。
