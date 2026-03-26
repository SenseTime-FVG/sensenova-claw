---
name: ppt-asset-plan
description: 当 storyboard 中存在图片或视觉资产缺口，需要为页面或槽位生成可追踪的资产计划，并优先落地本地图片文件时使用。
---

# PPT 资产计划

## 目标

产出 `asset-plan.json`，并在需要真实插图时同时落地：

- `image_search_results.json`
- `image_selection.json`
- `images/` 目录

这些文件必须与 `task-pack.json`、`storyboard.json`、`pages/page_XX.html` 一起保存在同一个 `deck_dir` 中。

## 用户回显要求

- `开始反馈`：说明当前有多少页面、多少槽位需要补图，以及将会生成哪些资产工件。
- `进行中反馈`：如果搜图、下载或校验明显耗时，可以补 1 条进度更新，说明已完成多少槽位、还有多少未处理。
- `完成反馈`：总结成功落地的本地图片数量、仍然 `unresolved` 的槽位数量，以及 `下一步`。
- 如果目录缺失、下载失败、校验失败或某个槽位无图可用，要立即给出阻塞或风险说明，不要等整批结束后才提。

## 输入来源

- `task-pack.json` 中的 `deck_dir`
- `storyboard.json` 中的 `asset_requirements`
- 可选的 `style-spec.json`
- 可选的模板资产

## 建议结构

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
    asset_kind: str
    render_strategy: str
    source_caption: str
    query: str
    selected: bool
    selected_image: "SelectedImage | None"
    quality_review: "AssetQualityReview | None"
    rejected_candidates: list["RejectedCandidate"]
    status: str
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

## 工作流

### 0. 依赖检查

- 消费前必须先确认 `task-pack.json`、`storyboard.json` 以及要用到的 `style-spec.json` 真实存在且可读。
- 如果目标文件不存在、路径与 `task-pack.json.deck_dir` 不一致，或关键字段缺失，先补齐依赖，不要猜测。

### 1. 初始化资产目录

- 下载前必须先创建 `deck_dir/images`。
- 不要假设 `images/` 已存在；如果目录不存在，先初始化，再进入搜图与下载阶段。

### 2. 提取待补资产

从 `storyboard.json.pages[*]` 中提取有图片、插图、背景图、图标需求的槽位，并保留页面标题、页面类型、槽位用途、当前页核心摘要。

- 必须先根据 `asset_requirements` 识别资产类型，例如 `real-photo`、`svg-illustration`、`svg-icon`、`qr-placeholder`。
- `real-photo` 这类真实图片槽位使用 `download-local`。
- `svg-illustration`、`svg-icon` 这类可直接绘制的资产使用 `draw-inline-svg`。
- 不要为可直接绘制的图标或插画走搜图下载。
- 如果 `asset_requirements` 写得过轻，但 `visual_requirements` 或页面语义明显指向真实图片，应补出对应的 `real-photo` 槽位，并在 `reason` 中注明这是对 storyboard 轻标注的修正。
- 如果页面实际布局需要多个独立真实图片槽位，`asset-plan.json` 中的 `real-photo` 槽位数量不能少于该页实际需求。
- 不要让三张人物卡只规划一个图片槽位，也不要让双图展示页只落一个 `selected_image`。
- 如果当前只能补齐部分真实图片，必须把缺失槽位记为 `unresolved`，而不是静默省略。
- 不要静默接受“整套都只有 SVG”的结果。
- 不要把人物、产品、场景、活动现场、作品样张、环境氛围这类应由真实图片承载的内容误判成 `svg-illustration`。

### 3. 生成搜图 query

- 优先使用槽位 caption 或描述作为主 query。
- 可以在内部把中文 query 改写成更适合搜图的英文短语，但不要篡改源字段语言。
- query 保持单意图、短语化，不要把整页大纲拼成一长串。
- 只有 `real-photo` 或等价真实图片槽位才需要生成搜图 query。

### 4. 搜图并保留候选

- 为每个槽位执行搜图，并把原始候选写入 `image_search_results.json`。
- 不要只保留最终图，必须保留 query、候选列表和来源信息，便于后续审查筛选过程。

### 5. 候选筛选与下载

- 先判断候选是否与搜索意图和页面语义相关，再进入下载队列。
- 先下载验证，再做最终选择。
- 下载必须逐张进行，并确认本地文件真实存在、非空、可读、确实是图片。
- 优先保留稳定、可直接下载、分辨率合适、无明显强水印的资源。
- 下载失败、内容无效、强水印、缩略图、语义不符的候选，都要写入 `rejected_candidates`。

### 6. 下载后图片审核

- 下载成功不等于可用；每张候选都必须经过下载后图片审核。
- 以下属于硬性筛查，任一失败都必须踢掉，不能进入最终选择：
  - `清晰度` 不足
  - `相关性` 不足
  - 存在 `明显水印`
  - 与当前图片槽位语义一致性不符
- 以下属于弱筛查，可以通过但必须记录：
  - `构图`
  - `风格一致性`
- `quality_review` 必须显式记录：
  - `clarity`
  - `relevance`
  - `watermark`
  - `semantic_alignment`
  - `composition`
  - `style_fit`
  - `hard_fail_reasons`
  - `soft_warnings`
- 只有当 `clarity/relevance/watermark/semantic_alignment` 全部通过时，才允许 `selected=True`。
- 如果图片只是构图一般、风格不够统一，但没有明显大问题，可以保留为通过候选，同时把问题写进 `soft_warnings`。

### 7. 最终选择

- 最终选择只能从下载成功且校验通过的本地文件中产生。
- `selected_image.local_path` 必须指向 `deck_dir/images/...` 下真实存在的文件。
- `selected_image` 一旦被选中，必须同步保留对应的 `quality_review`。
- 如果某个槽位没有成功下载任何图片，必须标记为 `unresolved`，不能静默丢失。
- 如果 `storyboard` 某页声明了多个独立 `real-photo` 需求，而 `asset-plan` 最终只成功落了一部分，必须在该页保留未兑现槽位，不要把缺口藏掉。

## 关键规则

- 优先将最终图片落地为本地文件。
- `image_search_results.json` 必须保留每个槽位的原始候选与 query。
- `image_selection.json` 和 `asset-plan.json` 必须保留 `selected_image` 与 `rejected_candidates`。
- `image_selection.json` 和 `asset-plan.json` 也必须保留下载后图片审核结果，不要只写“选中了哪张图”。
- `asset-plan.json` 中必须显式记录 `asset_kind` 与 `render_strategy`。
- 如果本地文件不存在，必须标记 `unresolved`。
- 如果只有远程 URL 而没有下载成功的本地文件，不得标记为 `selected=True`。
- 不要把远程 URL 伪装成最终本地资产。
- 如果 deck 主题天然需要人物 / 产品 / 场景图片，而计划中没有任何 `real-photo` 槽位，必须把它当成风险或缺陷显式指出，不要假装资产规划已经完整。
- 不要跳过筛选过程，也不要把“没有展示筛选过程”的结果当成完成。
- 某个槽位失败不应阻塞其他页面继续生成。
- 与页面语义不相关的图片不能硬塞。
- 清晰度不足、明显水印、语义不符的图片，即使已经下载成功，也不能算完成。
