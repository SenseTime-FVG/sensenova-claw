---
name: ppt-style-extract
description: "从用户要求、PPT 参考图和报告或 brief 中提取可复用的全局演示风格体系。当任务需要在生成大纲或 HTML 页面前先产出结构化 style.json 时，使用本技能。"
---

# PPT 风格抽取

你负责为后续 HTML 幻灯片生成提取一套可复用的 deck 级视觉风格。

当任务包含以下任一情况时，使用本技能：

- 有 PPT 参考图
- 有明确的视觉风格要求
- 报告或 brief 中已经包含稳定的视觉线索

输出必须是严格的 JSON 对象，通常保存为 `style.json`。

## 输入

准备以下输入：

- 用户 query
- 参考图片（如果有）
- 报告或汇总后的 brief

如果真实的风格信号不足，就输出一个保守、克制的风格结果。不要臆造一套复杂风格。

## 核心目标

提取整套 deck 的共性视觉风格，并将其转换为结构化、可复用、可控的规范，供后续 HTML 页面按同一风格生成。

## 语言规则

- `style.json` 中的自然语言说明字段，例如 `core_theme`、`description`、`usage` 等，默认必须与用户 query 的语言一致。
- 只有当用户明确要求使用另一种语言时，才切换这些说明字段的语言。
- 固定 JSON 键名和 schema 字段名可以保持英文；但不要在中文 query 下默认写成英文风格说明。

## 抽取规则

### 全局与局部

- 只有在多数页面中反复出现的特征，才作为 `global style`
- 只在少量页面出现的特征，必须归为 `local style`
- 全局风格必须保持抽象：
  - 颜色
  - 字体
  - 阴影
  - 边框
  - 圆角
  - 半透明遮罩
  - 非语义性的背景纹理近似
- 具体装饰图形必须归为局部：
  - 吉祥物
  - 印章
  - 插画
  - 复杂 SVG 图案
  - 照片

判断原则：

- 移除后会破坏页面结构的元素，可以认为是全局
- 移除后只是少了装饰的元素，必须归为局部

### 只基于证据

- 只能基于真实输入抽取风格
- 不要虚构颜色、字体、组件或布局语言

### 实现安全性

风格结果必须适合 HTML/CSS 实现：

- 不依赖 Data URI
- 不包含 base64 图片载荷
- 不写复杂噪点或纹理生成逻辑
- 纹理效果用纯色、渐变、rgba 覆盖或 blur 近似
- 优先使用 `div`、`border-radius`、`box-shadow`、`transform` 和渐变来绘制装饰
- 只有 CSS 无法表达时，才使用极简 SVG

## 字体约束

整套 deck 只能选一套标题字体和一套正文字体，并保持一致。

允许的正文字体：

- `'Noto Sans SC', sans-serif`
- `'Noto Serif SC', serif`
- `'Inter', sans-serif`
- `'Source Han Sans SC', sans-serif`
- `'puhuiti-2-35', sans-serif`
- `'PingFang SC', sans-serif`
- `'Microsoft YaHei', sans-serif`
- `'Arial', sans-serif`

允许的标题字体：

- `'ZCOOL KuHei', sans-serif`
- `'Long Cang', cursive`
- `'Ma Shan Zheng', cursive`
- `'Zhi Mang Xing', cursive`
- `'ZCOOL QingKe HuangYou', sans-serif`
- `'ZCOOL XiaoWei', serif`
- `'Liu Jian Mao Cao', cursive`
- `'ZCOOL KuaiLe', cursive`

## 输出内容

`style.json` 至少应覆盖：

- `design_concept`
- `color_palette`
- `typography`
- `decorative_elements`
- `ui_components`

## 输出结构

只返回严格 JSON，不要解释文字，不要 Markdown 代码块。

`style.json` 必须稳定遵循下面这一个 canonical schema，不要混用其他变体键名。

- 不要输出 `typography.heading/body`
- 不要输出 `typography.headings/body_text`
- 不要把 `color_palette` 写成 `background/accent/text` 的嵌套对象
- 不要输出 `primary_blue`、`secondary_blue` 这类未在 schema 中声明的快捷键

如果你想表达“背景主色、强调色、标题字色、正文色”，一律通过 `color_palette` 数组中的 `role` 来编码；如果你想表达标题和正文排版策略，一律使用 `title_strategy` 与 `body_strategy`。

```json
{
  "design_concept": {
    "core_theme": "",
    "texture_and_material": {
      "description": "",
      "css_rules": ""
    },
    "shape_language": ""
  },
  "color_palette": [
    {
      "role": "",
      "hex": "#000000",
      "alpha": 1,
      "usage": "",
      "is_global": true
    }
  ],
  "typography": {
    "title_strategy": {
      "source_library": "",
      "font_family_css": "",
      "suggested_weight": ""
    },
    "body_strategy": {
      "source_library": "",
      "font_family_css": "",
      "base_line_height": 1.6
    }
  },
  "decorative_elements": {
    "global_background_layer": [
      {
        "description": "",
        "html_template": ""
      }
    ],
    "local_decorations": [
      {
        "target_page_type": "structure_page | content_page",
        "description": "",
        "html_template": ""
      }
    ]
  },
  "ui_components": {
    "charts": {
      "color_sequence": [],
      "echarts_options": {}
    },
    "lists": {
      "marker_style": ""
    },
    "dividers": {
      "css_border": ""
    }
  }
}
```

## 最终规则

- 只输出合法 JSON
- 最终结果里不要再带 Markdown 代码块
- JSON 前后都不要有自然语言说明
- 自然语言说明字段默认与用户 query 的语言一致
- 不能输出任何 schema 漂移版本；下游 HTML 生成依赖这里的键名稳定性
