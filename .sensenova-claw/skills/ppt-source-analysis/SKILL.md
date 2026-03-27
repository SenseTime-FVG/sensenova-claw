---
name: ppt-source-analysis
description: 当用户上传报告、网页、截图、参考图、模板或已有 deck，需要先判断这些输入分别承担内容素材、风格参考还是模板参考职责时使用。
---

# PPT 来源分析

识别用户上传输入的角色和价值，产出 `source-map.json`，为后续 skill 提供清晰的来源分类。

## 目标

1. 逐一分析用户提供的每个输入（文件、链接、截图、模板、已有 deck 等）。
2. 为每个输入判定其角色：内容素材、风格参考、模板参考或混合来源。
3. 产出 `source-map.json`，明确每个输入的角色、优势、局限性和建议下游路径。
4. 为后续 `ppt-task-pack`、`ppt-research-pack`、`ppt-template-pack`、`ppt-style-spec` 提供可消费的来源分类。

## 触发条件

- 用户上传了报告、网页、截图、参考图、模板或已有 deck 等外部输入。
- 用户提供了链接或引用了外部资料。
- `ppt-superpower` 检测到存在外部输入，路由进入本 skill。

## 输入

- 用户上传的文件（报告、文档、PPT、PDF、图片等）。
- 用户提供的链接（网页、在线文档等）。
- 用户提供的截图或参考图。
- 已有 deck 目录中的工件。

## 输出

- `${deck_dir}/source-map.json`

## 执行规则

### 角色分类标准

每个输入必须被归类到以下一种或多种角色中：

- `content_source`：提供事实、论点、章节和正文信息。典型输入包括研究报告、行业分析、产品文档、会议纪要、数据表格、新闻稿。
- `style_reference`：提供配色、字体气质、装饰语法、视觉方向。典型输入包括参考 PPT 截图、设计稿、海报、品牌手册、风格 Mood Board。
- `template_reference`：提供布局结构、组件模式、版式约束。典型输入包括已有 PPT 模板、样页、版式参考文件。
- `mixed_source`：同一输入同时承担多种角色。典型情况是一份已有 PPT 既提供内容，也提供风格或版式参考。

### 角色判断流程

对每个输入，按以下顺序评估：

1. **格式识别**：判断输入的文件类型和格式（文档、表格、图片、PPT、网页等）。
2. **内容扫描**：快速扫描输入的核心内容，提取主题、结构和信息密度。
3. **角色匹配**：根据内容特征判定角色归属。
4. **价值评估**：评估该输入对后续流程的可用性，记录优势和局限性。
5. **下游路由**：为该输入推荐最适合的下游 skill。

### 混合来源处理

- 不要强行把混合来源压成单一角色。
- 如果同一个文件既有内容价值又有风格价值，`roles` 中应同时记录 `content_source` 和 `style_reference`。
- 在 `summary` 中说明该输入在不同角色维度上各自的价值和局限。
- `recommended_next_skills` 应包含所有相关的下游 skill，而不是只推荐其中一个。

### 异常与边界情况

- 如果输入损坏、无法读取或格式不支持，必须在 `limitations` 中明确记录，并在用户回显中点明风险。
- 如果角色判断存在明显歧义（例如一份文档可能是内容素材也可能是模板），应归类为 `mixed_source`，并在 `summary` 中说明歧义点。
- 如果输入信息量极低（例如一张模糊截图），仍需记录在 `source-map.json` 中，但应在 `limitations` 里注明可用性受限。
- 不要静默丢弃任何用户提供的输入。

### 下游路由建议

根据角色分类，推荐下游 skill：

| 角色 | 建议下游 skill |
| --- | --- |
| `content_source` | `ppt-task-pack`（作为 `research_required` 的判断信号）、`ppt-research-pack` |
| `style_reference` | `ppt-style-spec` |
| `template_reference` | `ppt-template-pack` |
| `mixed_source` | 根据各角色维度分别推荐，可能同时包含多个下游 skill |

## 数据结构

```python
class SourceMap:
    schema_version: str
    items: list["SourceItem"]


class SourceItem:
    source_id: str             # 唯一标识
    source_kind: str           # 输入类型：document / spreadsheet / image / ppt / webpage / link / screenshot 等
    roles: list[str]           # 角色列表：content_source / style_reference / template_reference / mixed_source
    summary: str               # 内容概述及角色价值说明
    strengths: list[str]       # 该输入的优势
    limitations: list[str]     # 该输入的局限性或风险
    recommended_next_skills: list[str]  # 建议消费该输入的下游 skill
```

## 用户回显

- **开始**：说明正在分析哪些输入来源，以及本阶段会产出 `source-map.json`。
- **完成**：概括识别出的来源角色（如"3 个内容来源、1 个风格参考、1 个混合来源"）、主要限制和推荐的下一步。
- **阻塞**：如果输入损坏、无法读取或角色判断存在明显歧义，要在反馈里点明风险，不要静默略过。

## 关键原则

- 只负责识别输入价值和角色分类，不负责消费完整内容或生成页面。
- 不要在这里生成大纲、页面或风格定义。
- 内容素材的消费应交给 `ppt-task-pack` 和 `ppt-research-pack`。
- 风格参考的消费应交给 `ppt-style-spec`。
- 模板参考的消费应交给 `ppt-template-pack`。
- 上传报告、事实数据案例和长文档只是后续 `ppt-task-pack` 判断 `research_required` 的信号，不是绕过 `ppt-task-pack` 直接进入 research 的入口。

## 禁止事项

- 不要强行把混合来源压成单一角色。
- 不要直接在这里生成大纲或页面。
- 不要消费完整内容并产出摘要，那是 `ppt-research-pack` 的职责。
- 不要静默丢弃任何用户提供的输入。
- 不要为无法读取的输入伪造角色判断。
