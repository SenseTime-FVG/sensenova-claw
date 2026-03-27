---
name: ppt-asset-plan
description: 当 storyboard 中存在图片或视觉资产缺口，需要为页面或槽位生成可追踪的资产计划，并优先落地本地图片文件时使用。
---

# PPT 资产计划

为每个视觉资产槽位生成可追踪的采购计划，并将真实图片落地为本地文件。

## 目标

产出 `asset-plan.json`，并在需要真实图片时同时落地：

- `image_search_results.json`（搜图候选记录）
- `image_selection.json`（最终选择与淘汰记录）
- `images/` 目录（本地图片文件）

所有文件必须保存在同一个 `deck_dir` 中。

## 触发条件

- `ppt-storyboard` 完成后，页面存在 `asset_requirements`。
- `ppt-review` 发现资产缺口，转入全量资产补齐。
- 用户要求重新搜图或更换图片。

## 输入

- `task-pack.json`：获取 `deck_dir`。
- `storyboard.json`：获取各页 `asset_requirements`、`visual_requirements`、页面语义。
- 可选 `style-spec.json`：获取风格方向，用于搜图 query 和风格一致性评审。

消费前必须确认以上文件真实存在且可读。路径与 `task-pack.json.deck_dir` 不一致时，先补齐依赖。

## 输出

| 文件 | 说明 |
|------|------|
| `asset-plan.json` | 每个槽位的完整采购记录 |
| `image_search_results.json` | 搜图候选与 query |
| `image_selection.json` | 选中图与淘汰图 |
| `images/*.png/jpg` | 本地图片文件 |

## 执行规则

### 第 0 步：初始化

- 确认 `deck_dir/images/` 目录存在，不存在则创建。
- 不要假设 `images/` 已存在。

### 第 1 步：提取待补资产

从 `storyboard.json.pages[*].asset_requirements` 提取槽位，保留页面标题、类型、用途、核心摘要。

- 按 `asset_requirements` 识别类型：`real-photo`、`svg-illustration`、`svg-icon`、`qr-placeholder`。
- `real-photo` 使用 `download-local` 策略。
- `svg-illustration`、`svg-icon` 使用 `draw-inline-svg` 策略，不走搜图下载。
- 如果 `asset_requirements` 过轻但页面语义明显指向真实图片，应补出 `real-photo` 槽位，并在 `reason` 中注明修正原因。
- 一页需要多张独立真实图片时，必须拆成多个槽位。三张人物卡不能共享一个槽位，双图展示页不能只落一个 `selected_image`。
- 不要把人物、产品、场景、活动现场、作品样张等应由真实图片承载的内容误判为 `svg-illustration`。

### 第 2 步：生成搜图 query

- 仅 `real-photo` 槽位需要生成 query。
- 优先使用槽位 caption 或描述作为主 query。
- 可在内部改写为英文短语以提升搜图质量，但不篡改源字段语言。
- query 保持单意图、短语化，不要把整页大纲拼成长串。

### 第 3 步：搜图并保留候选

- 为每个槽位执行搜图，原始候选写入 `image_search_results.json`。
- 必须保留 query、候选列表和来源信息，不能只保留最终图。

### 第 4 步：候选筛选与下载

- 先判断候选与搜索意图、页面语义的相关性，再进入下载队列。
- 逐张下载并确认本地文件真实存在、非空、可读、确实是图片。
- 优先保留稳定可下载、分辨率合适、无强水印的资源。
- 下载失败、内容无效、强水印、缩略图、语义不符的候选写入 `rejected_candidates`。

### 第 5 步：下载后图片审核

下载成功不等于可用。每张候选必须经过审核。

**硬性筛查**（任一失败必须踢掉）：

| 维度 | 字段 |
|------|------|
| 清晰度 | `clarity` |
| 相关性 | `relevance` |
| 水印 | `watermark` |
| 槽位语义一致性 | `semantic_alignment` |

**弱筛查**（可通过但必须记录）：

| 维度 | 字段 |
|------|------|
| 构图 | `composition` |
| 风格一致性 | `style_fit` |

- `quality_review` 必须显式记录以上六个字段及 `hard_fail_reasons`、`soft_warnings`。
- 只有硬性项全部通过时，才允许 `selected=True`。

### 第 6 步：最终选择

- 只能从下载成功且校验通过的本地文件中选择。
- `selected_image.local_path` 必须指向 `deck_dir/images/` 下真实存在的文件。
- 被选图必须同步保留 `quality_review`。
- 某槽位无成功下载，标记为 `unresolved`。
- 某页声明多个 `real-photo` 但只成功部分，必须保留未兑现槽位。

## 数据结构

```python
class AssetPlan:
    schema_version: str
    deck_dir: str
    slots: list["AssetSlot"]


class AssetSlot:
    page_id: str
    page_title: str
    slot_id: str
    purpose: str
    asset_kind: str          # real-photo / svg-illustration / svg-icon / qr-placeholder
    render_strategy: str     # download-local / draw-inline-svg
    source_caption: str
    query: str
    selected: bool
    selected_image: "SelectedImage | None"
    quality_review: "AssetQualityReview | None"
    rejected_candidates: list["RejectedCandidate"]
    status: str              # resolved / unresolved
    reason: str


class SelectedImage:
    title: str
    image_url: str
    local_path: str
    source_page: str
    source_domain: str


class AssetQualityReview:
    clarity: str
    relevance: str
    watermark: str
    semantic_alignment: str
    composition: str
    style_fit: str
    hard_fail_reasons: list[str]
    soft_warnings: list[str]


class RejectedCandidate:
    image_url: str
    rejection_stage: str
    reason: str
```

## 用户回显

- **开始**：说明有多少页面、多少槽位需要补图，以及将会生成哪些工件。
- **进行中**：搜图/下载明显耗时时，补 1 条进度更新，说明已完成和未处理的槽位数。
- **完成**：总结成功落地的本地图片数量、仍 `unresolved` 的槽位数量和下一步。
- **阻塞**：目录缺失、下载失败、校验失败、无图可用时，立即说明卡点，不等整批结束。

## 关键原则

- 优先将最终图片落地为本地文件。
- 搜图记录、筛选记录、审核记录必须完整保留，不能只写"选中了哪张图"。
- `asset-plan.json` 必须显式记录 `asset_kind` 与 `render_strategy`。
- 某个槽位失败不应阻塞其他页面继续生成。
- 只能补齐部分图片时，缺失槽位必须记为 `unresolved`。
- 如果 deck 主题天然需要真实图片而计划中没有 `real-photo` 槽位，必须显式指出风险。

## 禁止事项

- 不要把远程 URL 伪装成最终本地资产。只有远程 URL 而无成功下载的本地文件，不得标记 `selected=True`。
- 不要跳过筛选过程。
- 不要静默接受"整套都只有 SVG"的结果。
- 不要为可直接绘制的图标或插画走搜图下载。
- 不要把清晰度不足、明显水印、语义不符的图片当作完成。
- 不要与页面语义不相关的图片硬塞。
