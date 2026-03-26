---
name: ppt-template-pack
description: 当用户提供已有模板、参考 deck 或页面样例，需要拆解其布局结构、组件规则和设计约束以供后续复用时使用。
---

# PPT 模板包

## 目标

产出 `template-pack.json`，明确模板可复用的结构与约束。

## 用户回显要求

- `开始反馈`：说明正在拆解模板或参考 deck，并指出目标是 `template-pack.json`。
- `完成反馈`：简要概括识别出的布局规则、组件约束和 `下一步`。
- 如果模板只能部分复用，也要在反馈中说明保留范围和限制，不要默认整套照搬。

## 需要识别的内容

- 页面类型分布
- 布局模式
- 组件组织方式
- 标题与正文层级
- 图表与图片的放置习惯
- 局部装饰与全局规则的边界

## 建议结构

```python
class TemplatePack:
    schema_version: str
    page_patterns: list[str]
    layout_rules: list[str]
    component_rules: list[str]
    style_constraints: list[str]
    reusable_assets: list[str]
```

## 关键原则

- 模板包提供约束，不直接替代 `style-spec.json`。
- 模板中的局部装饰不要误判成全 deck 必须复用的全局规则。
- 模板包可以影响 `ppt-storyboard` 和 `ppt-page-html`，但不负责内容研究。
