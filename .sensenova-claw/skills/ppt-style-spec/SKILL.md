---
name: ppt-style-spec
description: 当需要为整套 PPT 建立统一而不单调的设计语言，并把用户要求、风格参考和模板约束收束为可复用的样式规格时使用。
---

# PPT 风格规格

`style-spec.json` 是默认必产工件，也是新的设计控制面。

## 目标

为后续 `ppt-storyboard` 和 `ppt-page-html` 提供统一的视觉控制规则。

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
- 色彩角色
- 字体策略
- 页面类型视觉原则
- 组件语气
- 丰富度规则
- 禁用项

## 建议结构

```python
class StyleSpec:
    schema_version: str
    design_theme: str
    design_keywords: list[str]
    color_roles: list["ColorRole"]
    typography: "TypographySpec"
    page_type_principles: list["PageTypePrinciple"]
    component_tone: list[str]
    diversity_rules: list[str]
    anti_patterns: list[str]
```

## 关键原则

- `style-spec.json` 为默认必产。
- 它是设计控制面，不是附属步骤。
- 页面类型视觉原则必须明确写出不同页面如何变化而不失统一。
- 禁用项必须明确，例如：
  - 不要退化成单一浅色商务模板
  - 不要所有页面都用同一布局
  - 不要出现与主题无关的装饰噪音
- 如果参考图不足，也必须生成一个有明确方向的基础风格，而不是空壳默认主题。
- 全局设计语言和局部装饰要分开描述，避免把偶发装饰误当全局规则。
