---
name: ppt-style-refine
description: 当整套 PPT 的风格方向正确但仍显单一、品牌感不足、页面变体不够，或 review 发现全局设计规则需要增强时使用。
---

# PPT 风格增强

`ppt-review` 发现全局设计规则薄弱或页面之间视觉变化不足时，进入本 skill 更新 `style-spec.json` 的设计控制面。

## 目标

在不推翻整套设计方向的前提下，增强 `style-spec.json` 中的具体设计规则，提升视觉丰富度和品牌一致性。

## 触发条件

- `ppt-review` 判定整套 deck 设计太素、缺少装饰层次
- `ppt-review` 判定品牌化不够，配色或组件皮肤过于通用
- `ppt-review` 判定页面之间变化太少，多页共用同一安全模板
- `ppt-review` 判定图表语言不统一、组件皮肤退化
- `ppt-review` 判定 motif recipe 缺失或装饰层过弱
- 用户主动要求增强风格表现力

## 输入

- `style-spec.json`（必须已存在且可读）
- `task-pack.json`（用于确认风格意图和 `content_density_profile`）
- `ppt-review` 的问题描述或用户补充要求
- 可选的 `storyboard.json`（用于确认受影响的页面类型和 variant 分布）

## 输出

- 更新后的 `style-spec.json`
- 影响说明：列出哪些 `style_variant` 或页面类型的视觉原则发生了变化，以及后续需要重新生成的页面范围

## 执行规则

### 1. 依赖检查

- 确认 `style-spec.json` 真实存在且可读。
- 如果目标文件不存在、路径不一致或原始风格规则缺失，先补齐依赖，不要猜测。
- 读取 `task-pack.json.style_intent` 确认原始风格方向，作为增强的基线。

### 2. 问题诊断

- 对照 `ppt-review` 的问题描述，定位 `style-spec.json` 中需要增强的具体字段。
- 按以下维度逐项评估当前风格是否足够：
  - 配色系统：`color_roles` 是否只有主色和灰色，缺少强调色、渐变色、语义色
  - 字体策略：`typography` 是否只有单一字体、缺少层级区分
  - 背景系统：`background_system` 是否退化为纯色底，缺少纹理、渐变、几何层
  - 前景装饰：`foreground_motifs` 是否缺少角标、编号块、导视线、强调框
  - SVG 元素库：`svg_motif_library` 是否元素不足，导致装饰重复
  - 组件皮肤：`component_skins` 是否退化为默认白卡片
  - 密度规则：`density_rules` 是否全 deck 只有一种密度
  - 页面变体：`page_type_variants` 是否缺少差异化壳子
  - motif 配方：各 variant 的 `background_motif_recipe` 和 `foreground_motif_recipe` 是否充分

### 3. 增强执行

可调整的字段清单：

- `color_roles`：补充强调色、渐变色对、语义色（成功/警告/信息）
- `typography`：增加字号层级对比、标题与正文的字重差异
- `background_system`：补充纹理层、几何层、光晕层、分区底纹规则
- `foreground_motifs`：补充装饰语法（角标、编号块、导视线、标签、强调框）
- `svg_motif_library`：增加可直接绘制的 SVG 元素，确保不同页面可用不同装饰
- `component_skins`：定义卡片、数据面板、表格、引言块、图表容器的增强皮肤
- `density_rules`：区分不同页面类型的密度策略
- `page_type_variants`：增加差异化的 `layout_shell`、`header_strategy`、`background_strategy`
- `background_motif_recipe` / `foreground_motif_recipe`：为各 variant 补充具体的 motif 放置配方
- `diversity_rules`：补充防止页面视觉重复的规则
- `anti_patterns`：补充具体禁用模式

### 4. 连续性验证

- 增强后的风格必须与 `task-pack.json.style_intent` 的原始方向一致。
- `visual_archetype` 和 `design_theme` 不应被改变，除非用户明确要求换方向。
- `content_density_profile` 的解释不应被增强操作篡改。
- 确认增强后的 variant 仍然能覆盖 `storyboard.json` 中所有页面引用的 `style_variant`。

### 5. 写回与影响说明

- 仅更新 `style-spec.json` 中需要增强的字段，保留其他字段不变。
- 写回后验证 JSON 格式正确、必要字段完整。
- 输出影响说明，列出受影响的 variant 和页面类型，以便后续决定是否需要重新生成页面 HTML。

## 用户回显

- **开始**：说明正在增强全局风格规则，而不是直接重画 HTML。
- **完成**：总结更新了哪些风格规则、会影响哪些页面类型，以及 `下一步`。

## 关键原则

- 修的是设计控制面，不是直接改 HTML。
- 必须保持原有主题方向连续。
- 增强后应给出对 `style_variant` 或页面类型视觉原则的影响说明。
- 增强粒度要具体到可执行字段，不要只增加抽象描述。
- 每个 variant 的 motif recipe 至少要有一个大面积或跨边缘的配方，不要只添加角落小图标。
- `插画感`、`手作感` 这类风格词只增强装饰层与组件皮肤，不等于把所有图片需求改成 SVG。

## 禁止事项

- 不要推翻原有设计方向，另起一套全新风格。
- 不要直接修改页面 HTML。
- 不要修改 `storyboard.json` 或 `asset-plan.json`。
- 不要篡改 `visual_archetype` 或 `design_theme`（除非用户明确要求）。
- 不要把 `content_density_profile` 的语义从承载策略改成视觉风格切换。
- 不要删除已有的 variant 映射，导致页面引用失效。
- 不要添加与主题无关的装饰噪音。
