---
name: ppt-style-spec
description: 当需要为整套 PPT 建立统一而不单调的设计语言，并把用户要求、风格参考和模板约束收束为可复用的样式规格时使用。
---

# PPT 风格规格

`style-spec.json` 是默认必产工件，也是新的设计控制面。

## 目标

为后续 `ppt-storyboard` 和 `ppt-page-html` 提供统一的视觉控制规则。

## 风格判断顺序

- 优先理解用户需求，再决定具体风格方向。
- 必须先读取 `task-pack.json` 中的 `风格意图`，结合主题、场景、受众、行业语境和参考材料推断主风格。
- 必须先读取 `task-pack.json` 中的 `content_density_profile`，把它解释为正文页的承载策略，再落到 `density_rules` 和页面类型原则。
- 只有在风格信号不足时，才允许使用兜底风格。
- 兜底风格只允许是 `商务` 或 `海报`，不能把它们误当成默认唯一风格。
- 如果用户已经明确给出风格偏好、参考图、模板或品牌方向，必须优先服从这些信号，不要被兜底风格覆盖。

## 内容承载 profile 解释

- `content_density_profile` 表示正文页的承载策略，不是单纯视觉风格切换。
- `analysis-heavy` 表示分析 / 汇报 / 评估类 deck 可承载更高论点密度、证据密度和结构密度。
- `balanced` 表示普通汇报 / 培训 / 项目介绍类 deck 在信息量、视觉承载与留白之间取中位策略。
- `showcase-light` 表示品牌 / 展示 / 活动 / 发布类 deck 采用更克制的正文承载，把重心让给主视觉、节奏和记忆点。
- `style-spec` 只负责解释 profile，不重算默认 profile。
- `style-spec` 在这一轮只负责解释这些 profile 对 `density_rules`、页面壳子和组件承载的影响，不要提前展开其他预算字段。

## 用户回显要求

- `开始反馈`：说明正在建立整套 deck 的设计控制面，并指出会产出 `style-spec.json`。
- `完成反馈`：用简短语言总结设计主题、关键风格关键词、主色/字体方向，并说明 `下一步`。
- 如果参考图不足、模板约束不完整或只能先给出基础版风格，应在反馈中明确说明，不要假装风格已经完全收敛。

## 输入与输出路径

- 必须先读取 `task-pack.json`，从中取得唯一可信的 `deck_dir`。
- 输出路径必须严格为 `${deck_dir}/style-spec.json`。
- 不要手写、缩写、翻译或重拼目录名。
- 如果 `task-pack.json` 缺失、不可读或没有 `deck_dir`，先补齐上游工件，不要猜测输出路径。

## 必须覆盖

- 设计主题
- 设计关键词
- 主风格原型
- 兜底风格原型
- 色彩角色
- 字体策略
- 背景系统
- 前景装饰语法
- SVG 装饰元素库
- 组件皮肤
- 信息密度规则
- 页面类型视觉原则
- variant 级页面壳子映射
- 组件语气
- 丰富度规则
- 禁用项

## 建议结构

```python
class StyleSpec:
    schema_version: str
    design_theme: str
    design_keywords: list[str]
    visual_archetype: str
    fallback_archetype: str
    color_roles: list["ColorRole"]
    typography: "TypographySpec"
    background_system: list[str]
    foreground_motifs: list[str]
    svg_motif_library: list["SvgMotif"]
    component_skins: list[str]
    density_rules: list[str]
    page_type_variants: list["PageTypeVariant"]
    page_type_principles: list["PageTypePrinciple"]
    component_tone: list[str]
    diversity_rules: list[str]
    anti_patterns: list[str]


class PageTypeVariant:
    variant_key: str
    page_type: str
    layout_shell: str
    header_strategy: str
    background_strategy: str
    foreground_strategy: str
    required_svg_motifs: list[str]
    background_motif_recipe: list["MotifPlacement"]
    foreground_motif_recipe: list["MotifPlacement"]
    component_strategy: str


class SvgMotif:
    motif_key: str
    usage_layer: str
    drawing_hint: str
    palette_binding: list[str]


class MotifPlacement:
    motif_key: str
    placement_hint: str
    density_hint: str
    opacity_hint: str
```

## 关键原则

- `style-spec.json` 为默认必产。
- 它是设计控制面，不是附属步骤。
- 必须优先理解用户需求，而不是先套商务模板再事后修饰。
- `visual_archetype` 要表达根据用户需求推断出的主风格；只有在风格信号不足时，`fallback_archetype` 才能取 `商务` 或 `海报`。
- 必须显式解释 `content_density_profile` 对正文页承载方式的影响，不要把它误写成颜色或装饰风格切换。
- `background_system` 必须明确背景层次、渐变 / 纹理 / 几何层 / 光晕 / 分区底纹等规则，避免页面退回纯色底。
- `foreground_motifs` 必须明确角标、编号块、导视线、强调框、标签等前景装饰语法。
- 背景和前景都要给出可绘制的装饰元素，不要只停留在文字描述。
- `svg_motif_library` 必须列出可直接绘制的 SVG 元素库，例如叶片簇、手绘箭头、胶带贴纸、望远镜、放大镜、鸟类足迹等。
- `插画感`、`手作感` 这类风格词，默认只增强装饰层与组件皮肤；不要把它们误用成“所有视觉都改成插画、无需真实图片”。
- `component_skins` 必须定义卡片、数据面板、表格、引言块、图表容器等组件怎么做出统一但不单薄的皮肤。
- `density_rules` 必须说明哪些页面可以更浓、哪些页面必须克制，避免全 deck 只有一种密度；并且要与 `analysis-heavy`、`balanced`、`showcase-light` 的承载语义一致。
- `page_type_variants` 必须明确封面页、目录页、分析页、结论页、风险页等页面如何变化而不失统一。
- `page_type_variants` 不要只按 `page_type` 粗分；要能覆盖 `style_variant`，让后续页面可以直接映射到具体壳子。
- 每个 variant 都要有可执行的 `variant_key`、`layout_shell`、`header_strategy` 等字段，避免只剩“科技感 / 高级感”这类空泛描述。
- 每个 variant 都应声明 `required_svg_motifs`，让 `ppt-page-html` 知道这一页至少要画哪些装饰或插画元素。
- 每个 variant 还必须给出 `background_motif_recipe` 与 `foreground_motif_recipe`，明确 motif 放在哪、疏密如何、透明度如何。
- 非极简 variant 的 `background_motif_recipe` 与 `foreground_motif_recipe` 不能同时为空；至少一侧要提供可感知的装饰配方。
- 正文 / 内容页 variant 不能把 `background_motif_recipe` 留空。
- 正文 / 内容页不要只给一个角落里的小图标就算完成。
- 正文 / 内容页的背景 recipe 至少要有一个大面积或跨边缘的 motif 配方，例如 `full-screen`、`edge-band`、`corner-cluster`、`side-panel`、`top-ribbon`。
- 如果页面包含真实图片或主视觉照片，真实图片也不能替代背景装饰配方；背景与前景 recipe 仍然要成立。
- 不要只写“有叶片感”这类抽象描述。
- 页面类型视觉原则必须明确写出不同页面如何变化而不失统一。
- 禁用项必须明确，例如：
  - 不要退化成单一浅色商务模板
  - 不要把所有页面都做成纯色背景 + 普通白卡片
  - 不要所有页面都用同一布局
  - 不要出现与主题无关的装饰噪音
- 如果参考图不足，也必须生成一个有明确方向的基础风格，而不是空壳默认主题。
- 全局设计语言和局部装饰要分开描述，避免把偶发装饰误当全局规则。
