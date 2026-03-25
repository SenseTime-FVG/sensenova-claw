---
name: ppt-page-html
description: 当需要根据 style-spec、storyboard 和 asset-plan 逐页生成 HTML 幻灯片，并严格遵守页面尺寸、本地图片和布局安全规则时使用。
---

# PPT HTML 页面生成

## 目标

根据 `style-spec.json`、`storyboard.json`、可选的 `asset-plan.json` 逐页生成 `pages/page_XX.html`。

每个 `storyboard.json.pages[n]` 都必须对应一个单独的 HTML 文件。

如果 `task-pack.json` 已记录 `deck_dir`，则所有 HTML 也必须写回该目录下的 `pages/`。

## 用户回显要求

- `开始反馈`：说明当前要生成哪些页面、会写入哪个 `pages/` 目录。
- `进行中反馈`：如果需要连续生成多页，可补 1 条进度更新，说明已完成页数或当前页范围。
- `完成反馈`：总结已生成的页面文件数量、是否保留了占位或未解决项，以及 `下一步`。
- 如果某页因为依赖缺失、资产缺失或布局冲突无法完成，必须立即告诉用户具体页码和卡点，不要静默跳过。

## 前置检查

- 消费前必须先确认 `task-pack.json`、`style-spec.json`、`storyboard.json` 以及要用到的 `asset-plan.json` 真实存在且可读。
- 如果目标文件不存在、落在错误目录、或与 `task-pack.json.deck_dir` 不一致，先停下并补齐依赖，不要猜测。

## 硬性规则

- 优先消费本地图片路径
- 不要直接把远程 URL 写进最终页面
- 用户可见文本默认与用户 query 语言保持一致
- 每页必须单独输出为一个 HTML 文件
- 不要输出单个包含整套 deck 的 HTML
- 不要编写 Python 脚本来批量生成页面
- 必须逐页直接生成最终 HTML
- 不要先写生成器脚本再批量产出页面
- 每一页都要直接参考对应的 `storyboard.json.pages[n]` 与同一份 `style-spec.json` 落地成最终 HTML 文件

### 固定画布

- 页面尺寸必须严格为 `1280x720`
- 不允许出现滚动条
- 所有内容必须完整落在视区内
- 缩放逻辑只能放在最外层容器，不能放在内容元素上

### 布局实现

- 只能用 Flexbox 或 CSS Grid 做对齐
- 不要用 `mt-auto`、`flex-grow` 或 `flex: 1` 伪造间距
- 不要用 `position: absolute + transform: translate(...)` 布局流式内容
- 图片和图表区域要靠明确尺寸控制，不能靠空 div 挤空间

### 页脚安全区

- 右下角 `160px x 60px` 必须保留给页码
- 任何内容都不能覆盖这块区域
- 页码必须放在 `<div id="footer">`
- 页脚必须带有等价于 `position: absolute; right: 40px; bottom: 20px;` 的内联定位

## 输出契约

- 按 `page_number` 顺序落盘到 `pages/page_XX.html`
- 一页对应一个文件，不拼成单个总 HTML
- 如果只重做局部页面，也只覆盖对应的页面文件

## 页面结构约束

HTML 必须保留这些层级：

- `.wrapper`
- `#bg`
- `#ct`
- `#footer`
- `#bg` 和 `#ct` 都必须铺满整页

## 风格执行规则

- 必须先读取并忠实消费 `style-spec.json` 的真实字段，不要只抓几个宽泛关键词后重新发明一套样式。
- 如果局部字段不完整，应从已有 `style-spec.json` 中做兼容推导，不要退回通用默认样式。
- 必须延续 deck 级的配色、字体、背景层次、卡片语法和装饰方向，不能因为实现方便把页面做成另一套模板。
- 必须显式消费 `background_system`、`foreground_motifs`、`component_skins`、`density_rules`、`page_type_variants` 这些风格控制字段。
- 优先按 `style_variant` 映射页面壳子；只有缺少 variant 映射时，才允许退回 `page_type` 层级。
- `style-spec.json` 里的 `variant_key`、`layout_shell`、`header_strategy` 必须被具体落地，不要只把它们当参考文字。
- 可见标题必须放在 `#ct` 内，或放在单独的 `#header` 容器内。
- 不要把 `.header` 当作 `#bg` 和 `#ct` 之间的裸兄弟节点，否则很容易被内容层盖住。
- 必须显式消费 `svg_motif_library` 与 variant 的 `required_svg_motifs`。
- 非极简页面必须至少 1 层背景装饰，且至少 1 处前景装饰。
- 如果页面只有纯色或渐变背景，而没有按 recipe 落地 motif，应视为未完成。
- 背景装饰层必须是用户可感知的视觉层，不能退化成几乎看不见的微小角标、单个噪点或没有存在感的极淡纹理。
- 正文 / 内容页即使包含真实图片，也不能把主视觉照片当成背景装饰层的替代；照片存在时，背景 recipe 仍要落地。
- 根据 recipe 落地的背景 motif 元素，必须带 `data-layer="bg-motif"`。
- 根据 recipe 落地的前景 motif 元素，必须带 `data-layer="fg-motif"`。
- 每个按 recipe 落地的 motif 都必须写上 `data-motif-key="<motif_key>"`。
- 这些标记是为了让 review 和导出前校验可以核对，不要省略。
- 真实图片或主视觉照片不能替代这些标记。
- 不要只做纯色背景 + 普通白卡片，除非 `style-spec` 明确要求极简。
- 每页至少要有可感知的背景系统和前景装饰层，组件也要体现对应皮肤，而不是只改文字颜色或边框粗细。
- 同一套 deck 内，封面页、分析页、结论页、风险页等要按 `page_type_variants` 拉开差异，不能所有页面共用一张安全模板。
- 不能把多个不同 `style_variant` 页面落成同一种安全模板。
- 不要让大多数正文页都复用同一套左竖线标题 + 毛玻璃卡片。
- 局部重做页面时，也必须与同 deck 其他页面保持同一视觉系统。

## 资源规则

- 如果 `asset-plan.json` 中某个槽位 `selected=False`，需要保留明确占位或替代方案。
- 如果 `local_path` 存在，应优先引用本地相对路径。
- 如果 `asset-plan.json` 已经给出成功下载的本地图片，最终 HTML 必须显式消费该槽位，不能静默忽略。
- 必须逐项消费 `storyboard.json.pages[n].asset_requirements`，不要用一个通用 motif 替代不同页面的具体资产要求。
- 如果页面要求 `real-photo`，应优先消费对应本地图片；若图片缺失，只能保留与该槽位语义一致的明确 placeholder，不要改画成 SVG 小图标。
- 如果页面要求某个具体 `svg-icon` 或 `svg-illustration`，就要画出对应元素，不要偷换成另一个更通用的 motif。
- 图标、装饰性元素、可直接绘制的插画必须优先用内联 SVG 落地。
- 不要把图标画成 placeholder，也不要把 generic 插画留成一个虚线框。
- 只有真实照片、二维码、用户专有素材在缺失时，才允许保留 placeholder。
- 如果图片还未就绪，必须保留明确占位，并把预期视觉与页面语义对应起来。
- 图片、图表、表格应与 `storyboard.json` 的页面意图一致。

## 质量原则

- 忠实消费 `style-spec.json`
- 忠实消费 `storyboard.json`
- 同一套 deck 中既要统一，也要避免页面完全重复
- 不要为了“简洁”擅自删掉关键内容
- 不要因为实现方便弱化原有风格层次、背景氛围或版式张力
- 对存在资产需求的页面，不能静默忽略图片槽位
