---
name: ppt-source-analysis
description: 当用户上传报告、网页、截图、参考图、模板或已有 deck，需要先判断这些输入分别承担内容素材、风格参考还是模板参考职责时使用。
---

# PPT 来源分析

先分析来源，再决定后续链路。

## 输出目标

产出 `source-map.json`，明确每个输入的角色、可用性和建议下游路径。

## 用户回显要求

- `开始反馈`：说明正在分析哪些输入来源，以及本阶段会产出 `source-map.json`。
- `完成反馈`：概括识别出的来源角色、主要限制和 `下一步` 推荐的下游 skill。
- 如果输入损坏、无法读取或角色判断存在明显歧义，要在反馈里点明风险，不要静默略过。

## 分类规则

- `content_source`：提供事实、论点、章节和正文信息。
- `style_reference`：提供配色、字体气质、装饰语法、视觉方向。
- `template_reference`：提供布局结构、组件模式、版式约束。
- `mixed_source`：同一输入同时承担多种角色。

## 建议结构

```python
class SourceMap:
    schema_version: str
    items: list["SourceItem"]


class SourceItem:
    source_id: str
    source_kind: str
    roles: list[str]
    summary: str
    strengths: list[str]
    limitations: list[str]
    recommended_next_skills: list[str]
```

## 关键原则

- 不要强行把混合来源压成单一角色。
- 不要直接在这里生成大纲或页面。
- 这里只负责识别输入价值，不负责消费完整内容。
