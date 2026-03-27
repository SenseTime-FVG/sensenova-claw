---
name: ppt-page-html
description: 当需要根据 style-spec、storyboard 和 asset-plan 逐页生成 1280×720 HTML 幻灯片时使用。
---

# PPT 页面生成

根据上游工件逐页生成 HTML 幻灯片，每页一个文件，严格遵守画布尺寸、风格规格和内容预算。

## 目标

为 `storyboard.json` 中的每一页生成对应的 `pages/page_XX.html` 文件。

## 触发条件

- `ppt-storyboard` 完成且用户确认通过。
- `ppt-asset-plan` 完成后（如存在资产需求）。
- `ppt-review` 要求重做某些页面时，仅覆盖对应文件。

## 输入

- `task-pack.json`：获取 `deck_dir`。
- `style-spec.json`：设计控制面（配色、字体、背景系统、前景装饰、组件皮肤、页面壳子映射）。
- `storyboard.json`：每页的内容块、布局意图、`payload_budget`、`style_variant`、`asset_requirements`。
- 可选 `asset-plan.json`：本地图片路径与资产状态。

消费前必须确认以上文件真实存在且可读，路径与 `deck_dir` 一致。

## 输出

- `pages/page_01.html` … `pages/page_XX.html`，按 `page_number` 顺序。
- 一页对应一个文件，不拼成单个总 HTML。
- 局部重做时只覆盖对应页面文件。

## 执行规则

### 画布与布局

- 页面尺寸严格 `1280×720`，不允许滚动条，所有内容必须在视区内。
- 缩放逻辑只能放在最外层容器。
- 只用 Flexbox 或 CSS Grid 做对齐。
- 图片和图表区域靠明确尺寸控制。

### 页面结构

HTML 必须保留以下层级：

```
.wrapper
  #bg        ← 铺满整页
  #ct        ← 铺满整页
  #footer
```

- 可见标题必须放在 `#ct` 内，或放在单独的 `#header` 容器内。
- 不要把 `.header` 当作 `#bg` 和 `#ct` 之间的裸兄弟节点，否则导出时会被内容层盖住或丢失。

### 页脚安全区

- 右下角 `160×60px` 保留给页码。
- 页码放在 `<div id="footer">`，内联定位 `position: absolute; right: 40px; bottom: 20px;`。

### 风格执行

- 忠实消费 `style-spec.json` 的真实字段，不要只抓几个关键词后重新发明样式。
- 局部字段不完整时，从已有 `style-spec.json` 做兼容推导，不退回通用默认。
- 显式消费 `background_system`、`foreground_motifs`、`component_skins`、`density_rules`、`page_type_variants`。
- 优先按 `style_variant` 映射页面壳子；缺少映射时才退回 `page_type` 层级。
- `variant_key`、`layout_shell`、`header_strategy` 必须被具体落地。

**装饰层规则**：

- 非极简页面必须至少 1 层背景装饰 + 至少 1 处前景装饰。
- 背景装饰层必须是用户可感知的视觉层，不能退化为微小角标或极淡纹理。
- 正文页即使包含真实图片，背景 recipe 仍要落地。
- 显式消费 `svg_motif_library` 与 variant 的 `required_svg_motifs`。

**装饰标记**（供 review 和导出校验核对）：

- 背景 motif 元素：`data-layer="bg-motif"`
- 前景 motif 元素：`data-layer="fg-motif"`
- 每个 motif：`data-motif-key="<motif_key>"`
- 真实图片不能替代这些标记。

**页面差异**：

- 封面页、分析页、结论页、风险页等按 `page_type_variants` 拉开差异。
- 不能所有页面共用一张安全模板。
- 不能把多个不同 `style_variant` 页面落成同一种模板。
- 局部重做页面时，与同 deck 其他页面保持同一视觉系统。

### 内容预算执行

必须按 `payload_budget` 落地：

| 字段 | 含义 |
|------|------|
| `claim_count` | 独立论点承载位数量，不要把多个 claim 压成一段长文 |
| `evidence_count` | 证据承载位数量（数据点、指标、来源说明、案例事实等） |
| `structure_block_count` | 可感知内容结构块数量（对比区、数据卡、步骤块、图文块等） |
| `require_comparison_or_summary` | 为 `True` 时必须有对比结构或摘要结构 |

- 对比：优先双列 / 多列 / before-after / 指标对照。
- 摘要：结论块、takeaway 区或 recap 区。
- 视觉张力不能成为删减预算的理由；空间紧张时调布局和组件尺寸，不静默降低承载。

### 资源消费

- 优先消费本地图片路径，不要直接把远程 URL 写进页面。
- `asset-plan.json` 已落地的本地图片必须显式消费，不能静默忽略。
- 逐项消费 `storyboard.json.pages[n].asset_requirements`。
- `real-photo` 缺失时保留语义一致的明确 placeholder，不改画为 SVG 小图标。
- `svg-icon` / `svg-illustration` 用内联 SVG 落地，不画成 placeholder 或虚线框。
- 只有真实照片、二维码、用户专有素材在缺失时才允许保留 placeholder。

## 用户回显

- **开始**：说明当前要生成哪些页面、写入哪个 `pages/` 目录。
- **进行中**：连续生成多页时，补 1 条进度更新。
- **完成**：总结已生成页面数、保留的占位或未解决项、下一步。
- **阻塞**：某页依赖缺失、资产缺失或布局冲突时，立即告知页码和卡点。

## 关键原则

- 每页必须单独输出为一个 HTML 文件，逐页直接生成最终 HTML。
- 忠实消费 `style-spec.json` 和 `storyboard.json`。
- 同一套 deck 既要统一又要避免页面完全重复。
- 用户可见文本默认与用户 query 语言保持一致。

## 禁止事项

- 不要输出单个包含整套 deck 的 HTML。
- 不要编写 Python 脚本批量生成页面。
- 不要用 `mt-auto`、`flex-grow`、`flex: 1` 伪造间距。
- 不要用 `position: absolute + transform: translate(...)` 布局流式内容。
- 不要只做纯色背景 + 普通白卡片（除非 style-spec 明确要求极简）。
- 不要让大多数正文页复用同一套左竖线标题 + 毛玻璃卡片。
- 不要为了"简洁"擅自删掉关键内容。
- 不要因为实现方便弱化风格层次、背景氛围或版式张力。
- 不要静默忽略存在资产需求的图片槽位。
