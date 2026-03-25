---
name: ppt-storyboard
description: 当需要把任务包、研究结果、风格规格和模板约束转换成固定 schema 的分页叙事结果，并供前端展示和后续页面生成直接消费时使用。
---

# PPT Storyboard

`storyboard.json` 是默认必产工件，也是前端契约。

## 目标

同时满足三件事：

1. 前端可稳定展示阶段性结果
2. 用户可基于页面级对象进行局部修改
3. `ppt-page-html` 可以直接消费

## 用户回显要求

- `开始反馈`：说明正在把任务包、research 条目和风格规格转成分页叙事，并指出会产出 `storyboard.json`。
- `完成反馈`：概括总页数、主要章节、页面分布、未解决项数量和 `下一步`。
- 如果当前处于 `guided`，完成反馈必须明确提示用户现在可以先审阅 `storyboard.json`，不要只返回一段自由文本大纲。

## 固定 schema

```python
from typing import Literal

Mode = Literal["fast", "guided", "surgical"]

class Storyboard:
    schema_version: str
    ppt_title: str
    language: str
    total_pages: int
    mode: Mode
    pages: list["StoryboardPage"]


class StoryboardPage:
    page_id: str
    page_number: int
    title: str
    page_type: str
    section: str
    narrative_role: str
    audience_takeaway: str
    layout_intent: str
    style_variant: str
    content_blocks: list["ContentBlock"]
    visual_requirements: list[str]
    data_requirements: list[str]
    asset_requirements: list[str]
    unresolved_issues: list[str]
    presenter_intent: str


class ContentBlock:
    block_id: str
    heading: str
    summary: str
    source_claim_ids: list[str]
    source_evidence_ids: list[str]
    unresolved_gaps: list[str]
```

## 关键规则

- storyboard 是 research 的消费层。
- 消费前必须先确认 `task-pack.json`、`style-spec.json`，以及按需存在的 `research-pack.json` / `research-pack.md` 真实存在且可读。
- 如果目标文件不存在、路径不一致或关键字段缺失，先返回缺失依赖并补齐上游工件，不要猜测。
- `storyboard.json` 为默认必产。
- 页数必须严格匹配任务包要求。
- 页面自然语言内容默认与用户 query 保持一致。
- 页面顺序必须体现清晰叙事，而不是堆砌信息。
- 不允许只拿 research 主题词重新写一遍；必须把 research 中可上页的 claim、evidence 和未解决缺口落到页面级对象。
- 每页必须能说明主 claim 和 evidence 从哪里来。
- 每个 `content_blocks[n]` 都必须显式填写 `source_claim_ids` 与 `source_evidence_ids`，引用 `research-pack` 中实际存在的条目，而不是写模糊主题词。
- 缺证据时要显式记录 `unresolved_gaps`，不要假装内容已经闭环。
- `style_variant` 必须直接引用 `style-spec.json` 中已声明的 variant 映射，不要重新发明一套名字。
- `style_variant` 不要把它写成宽泛形容词；它必须是后续 `ppt-page-html` 可直接按 variant 落地的键。
- `asset_requirements` 不要只写模糊的槽位名；要用能指导后续分流的提示，例如 `svg-illustration`、`svg-icon`、`real-photo`、`qr-placeholder`。
- 资产类型判断必须先看页面语义，再看风格偏好。
- 如果页面要呈现人物、产品、空间、场景、活动现场、作品样张、环境氛围等真实对象，默认应规划为 `real-photo`，必要时可叠加 `svg-illustration` 或 `svg-icon` 做装饰。
- `插画感` 只影响装饰语法、背景氛围和前景点缀，不等于把证据型图片全部改成 `svg-illustration`。
- 不要因为风格里有插画感、手作感、童趣感，就把整套 deck 的图片需求都改写成 `svg-illustration`。
- `presenter_intent` 只表达讲述意图，不承担完整讲稿。
- 每页必须显式记录 `asset_requirements` 与 `unresolved_issues`，便于后续局部修复。

## 不要做的事

- 不要退回旧 `outline` 的松散结构。
- 不要把完整讲稿直接塞进 `storyboard.json`。
- 不要让前端需要猜字段含义。
