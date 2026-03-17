---
name: ppt-outline-gen
description: "根据报告、brief、图片和受众上下文生成完整的 PPT 大纲 JSON。当任务需要在 HTML 生成前完成严格页数规划、页面类型选择、布局决策、图片分配和补图建议时，使用本技能。"
---

# PPT 大纲生成

你负责生成整套演示文稿的逐页大纲。

当任务已经具备以下材料时，使用本技能：

- 报告或汇总后的 brief
- 已有图片或图片元信息
- 作者身份
- 使用场景
- 目标受众
- 目标页数

输出必须是严格的 JSON 对象。

## 核心目标

生成一份结构完整、视觉合理、可直接供后续 HTML 页面生成使用的 PPT 大纲。

对每一页，需要确定：

- 页面标题
- 页面类型
- 布局形态
- 内容块
- 图片使用方式
- 需要补充的图片建议

## 所需输入

你应当具备：

- `report`
- `pictures`
- `character`
- `scenario`
- `audience`
- `page_number`

## 全局规则

### 语言一致性

- 大纲中的页面标题、`content` 内的文本、补图说明中的自然语言字段，默认必须与用户 query 的语言一致。
- 只有当用户明确要求使用另一种语言时，才切换这些自然语言字段的输出语言。
- JSON 键名、结构字段名、固定 schema 字段可以保持英文；但用户真正会看到的标题和正文不要无故切换语言。
- `needed_pictures` 中的 `caption`、`description`、`tag` 等自然语言字段也必须遵守这一规则；中文 query 下不要把这些字段默认写成英文。
- 如果下游搜图阶段需要英文 query，可以在执行搜图时自行翻译或改写搜索词，但不要把大纲本身写成英文。

### 页数规划

- 必须严格生成到目标页数
- 第 1 页必须是封面页，`page_type` 为 `title`
- 最后一页必须是结束页或感谢页，`page_type` 为 `ending`
- 目录页最多只能有 1 页
- 需要时可以插入章节过渡页

### 结构质量

- 整套 deck 必须逻辑连贯
- 页面顺序应从开场、展开到结尾自然推进
- 如果报告本身已经隐含了页结构，应尽量保留
- 不要因为布局不方便就删减报告里的关键 sub-point，应优先换更合适的布局

### 布局多样性

- 在合适的前提下保持布局多样性
- 避免过度复用少数几种页面模板
- 布局必须与内容量和内容类型匹配
- 如果页面没有 `needed_pictures`，不要预留图片位，也不要选用本质上依赖图片才能成立的布局类别。

### 内容密度

- 每页都要内容充实，但仍适合展示
- 正文页优先承载来自 brief 的真实信息，不要为了“好看”过度压缩内容
- 单页最多 7 个内容块
- 6-7 块内容的页面在整套 deck 中可以占到 60%，前提是布局仍然清晰可读
- 当内容过密时，应拆页或删去次要内容
- 每个核心 `sub_point` 应尽量保留 1-3 句完整信息，而不是只剩标题式短语
- 当用户要求“介绍类”“分析类”“汇报类”PPT 时，正文页应默认更充实，避免大面积空白与信息稀释

### 图片、图表和表格

- 尽量复用已有图片
- 同一张已有图片只能使用一次
- 如果页面规划了图片区域，图片使用必须和布局保持一致
- 单页图片和图表合计不应超过 4 个
- 如果报告中包含大量数据，应优先安排图表，而不是额外搜图

## Sub-point 规则

每页内容都放在 `content` 下。

对每个 `sub_point`：

- 包含 `icon`
- 包含 `sub_point_name`
- 包含 `text`
- 可选 `table`
- 可选 `chart`
- 可选 `picture`
- 可选 `sub_sub_points`

对每个 `sub_sub_point`：

- 只能有 `icon`
- `sub_sub_point_name`
- `text`
- 可选 `picture`

在同一个 `sub_point` 内，除文本外，表格、图表、图片最多只保留一种主要附加视觉元素。

如果页面带图：

- 仍然要保留足够的文字信息，不要因为放了一张图就只剩 1-2 句说明
- 正文页通常至少应有 2 个实质性 `sub_point`

## 补图规则

当某页还需要补充视觉元素时，使用 `needed_pictures`。

每个补图项必须包含：

- `id`
- `caption`
- `tag`
- `size`

规则：

- 非背景图的补图必须在该页某个内容块中被引用
- 如果补图没有真正落位到内容中，就应删除
- `caption` 要短，适合搜索，不要写完整句子
- `caption` 要具体、常见、便于搜索
- 避免年份、具体数值、图表式 caption 或抽象口号
- `caption` 应优先对应现实世界中常见、可稳定搜到的视觉对象或场景，避免过度理想化的“概念图”描述
- `caption` 和 `tag` 必须足以供下游 `ppt-image-selection` 直接构造搜图 query 并完成筛选
- 对同一页的多个补图项，`caption` 不能高度重复，否则会导致下游搜图结果同质化
- 如果页面更适合图表或表格，就不要为了凑流程强行规划补图
- 如果最终判断该页不需要补图，就应同时移除与图片相关的布局预留和 `picture` 槽位，不要留下空白图片区。

## 上下文适配

大纲必须体现：

- 作者身份
- 演示场景
- 受众类型
- 目标页数

这会影响：

- 语气
- 抽象程度
- 术语使用
- 是否强调方法、结论、风险、行动或教学

## 输出结构

只返回严格 JSON。不要解释，不要 Markdown 代码块。

```json
{
  "title": "deck title",
  "page1": {
    "title": "",
    "template_id": "",
    "page_type": "title | content | catalog | transition | summary | ending",
    "layout": {
      "category": "single_column | two_column_horizontal | two_column_vertical | three_column | image_left_text_right | text_left_image_right | chart_left_text_right | text_left_chart_right | table_left_text_right | text_left_table_right | grid | free | centered | custom",
      "custom_description": ""
    },
    "content": {
      "sub_point1": {
        "icon": "fa-lightbulb",
        "sub_point_name": "",
        "text": "「」",
        "table": "",
        "chart": "",
        "picture": "",
        "sub_sub_points": {}
      }
    },
    "needed_pictures": [],
    "page_number": "第1页，共N页"
  }
}
```

## 最终规则

- 只输出合法 JSON
- 不要额外解释
- 大纲必须严格页数匹配，结构清晰，并可直接进入后续图片检索与页面生成
- 不要把内容从 brief 压缩成只剩提纲词；应尽量把关键信息保留到页面级文本中
- 所有自然语言内容默认与用户 query 的语言保持一致
