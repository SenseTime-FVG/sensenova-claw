---
name: ppt-info-pack
description: 当需要把用户输入、上传材料和 research 结果汇总为统一信息源，并为 storyboard 提供唯一可追溯内容池时使用。
---

# PPT 信息汇总包

`info-pack.json` 是分页前的统一信息源。它把用户输入、上传材料和 research 结果整理成可引用的信息原子，作为 `ppt-storyboard` 的唯一信息来源。

## 目标

1. 读取 `task-pack.json`、可选 `source-map.json`、可选 `research-pack.json` / `research-pack.md`。
2. 产出 `${deck_dir}/info-pack.json`，作为分页前的唯一信息来源。
3. 把用户输入、上传材料、research-pack 中可用的信息整理成带稳定 ID 的 `InfoAtom`。
4. 为后续 `ppt-storyboard` 提供统一、轻量、可追溯的内容池，避免在 `ppt-page-html` 阶段现场补编可见信息。

## 触发条件

- `task-pack.json` 已产出。
- 如果 `task-pack.json.research_required` 为真，且 `ppt-research-pack` 已完成。
- 在 `ppt-style-spec` 与 `ppt-storyboard` 之前，由 `ppt-superpower` 调度进入。

## 输入

- `task-pack.json`：获取 `deck_dir`、主题、受众、页数、已知缺口。
- 用户输入：原始 query、补充要求、明确给出的标题 / 文案 / 数值 / 章节。
- `source-map.json`（可选）：来源分类结果。
- 上传材料（可选）：文档、网页、截图、已有 deck 等。
- `research-pack.json` / `research-pack.md`（按需）：结构化研究结果。

消费前必须确认以上工件真实存在且可读。如果 `task-pack.json` 缺失、路径不一致或 research 本应存在却未产出，先返回缺失依赖，不要猜测。

## 输出

- 输出路径：`${deck_dir}/info-pack.json`
- 不要手写、缩写、翻译或重拼 `deck_dir`。
- `info-pack.json` 是后续 `ppt-storyboard` 的唯一信息来源。

## 执行规则

### 汇总原则

- `info-pack.json` 必须收束所有可用信息来源：用户输入、上传材料、`research-pack`。
- 不要把用户输入和 research 结果散落在多个上游工件里让 `ppt-storyboard` 自己重新拼接。
- `info-pack.json` 负责信息汇总，不负责分页布局、风格判断或页面视觉。

### 信息原子化

- 每条可见信息都应被整理成可引用的 `InfoAtom`。
- `InfoAtom` 要尽量短、稳定、可组合，不要直接复制一大段原文。
- 标题、正文陈述、数值、图表序列、标签、caption、脚注都应进入 `InfoAtom` 池。
- 图表或表格数据不要只写成一句自然语言摘要；如果后续要渲染柱状图、折线图、饼图、表格行或对比矩阵，必须把这些可见数据整理成显式结构。
- 不要只把图表数据写成一句自然语言 `metric`，再指望 `ppt-page-html` 从句子里猜系列名、标签和值。
- 当 `kind == "chart-series"` 时，`payload` 至少要能表达图表标识、系列名、类目标签、数值和单位；摘要文字只能作为补充，不能替代结构化数据。
- 相同事实不要反复复制；应复用已有 `atom_id`。

### 来源追溯

- 每个 `InfoAtom` 都必须记录 `source_type`、`source_ref` 和 `confidence`。
- `source_type` 至少覆盖：`user`、`upload`、`research`。
- `source_ref` 应尽量指向具体来源位置，例如原始 query、上传文件名、`claim_id`、`evidence_id`、`chunk_id`。
- 对无法充分确认的信息，必须降低 `confidence` 或标记待确认，不要伪装成确定事实。

### 与 `ppt-storyboard` 的关系

- `ppt-storyboard` 只能从 `info-pack.json` 中选择、组合和分页。
- 不要让 `ppt-storyboard` 再直接从用户输入或 `research-pack` 临时抽信息。
- `ppt-storyboard` 中的标题、正文、数值、图表数据、标签、caption、脚注，都应显式回指 `InfoAtom` 的 `atom_id`。

### 缺口处理

- 如果某页所需信息在用户输入、上传材料和 research 中都不足，应在 `info-pack.json` 中留下 `known_gaps` 或 `unresolved_atoms`，供 `ppt-storyboard` 和后续 review 显式保留。
- 不要因为信息不够，就在汇总阶段主动脑补文案或数值。

## 数据结构

```python
from typing import Any, Literal

Json = dict[str, Any]

SourceType = Literal["user", "upload", "research"]
AtomKind = Literal[
    "title",
    "statement",
    "metric",
    "datum",
    "chart-series",
    "label",
    "caption",
    "footnote",
]


class InfoAtom:
    atom_id: str
    kind: AtomKind
    value: str
    payload: Json | None
    source_type: SourceType
    source_ref: str
    confidence: str
    notes: list[str]


class InfoPack:
    schema_version: str
    topic: str
    deck_dir: str
    atoms: list[InfoAtom]
    known_gaps: list[str]
    unresolved_atoms: list[str]
```

## 用户回显

- **开始反馈**：说明正在汇总用户输入、上传材料和 research 结果，并指出会产出 `info-pack.json`。
- **完成反馈**：总结收集到多少条 `InfoAtom`、是否仍有信息缺口，以及 `下一步` 会进入哪个工件。
- **阻塞反馈**：如果上游 research 应存在但缺失、来源不可读或信息冲突严重，要明确指出卡点和待补依赖。

## 关键原则

- `info-pack.json` 是分页前的唯一信息来源。
- `ppt-storyboard` 只能消费 `info-pack.json`，不能绕过它直接拼装可见信息。
- 所有可见信息都应尽量收敛为轻量 `InfoAtom`，用 `atom_id` 回指，不重复粘贴大段来源文本。
- 图表、表格、矩阵等结构化可见数据应优先进入 `payload`，不要只保留一句笼统描述。
- 信息不足时要显式留下缺口，不要脑补。

## 禁止事项

- 不要在这里做页面布局或视觉决策。
- 不要把 `info-pack.json` 做成第二份 `research-pack` 长文摘要。
- 不要省略 `source_type`、`source_ref` 或 `confidence`。
- 不要把用户输入、上传材料和 `research-pack` 之外的新信息写进 `info-pack.json`。
- 不要只把图表数据写成一句自然语言，导致 `ppt-storyboard` 和 `ppt-page-html` 无法显式回指。
