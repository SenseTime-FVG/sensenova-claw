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

- `开始反馈`：说明正在把任务包和风格规格转成分页叙事，并指出会产出 `storyboard.json`。
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
    evidence_refs: list[str]
```

## 关键规则

- 消费前必须先确认 `task-pack.json` 与 `style-spec.json` 真实存在且可读。
- 如果目标文件不存在、路径不一致或关键字段缺失，先返回缺失依赖并补齐上游工件，不要猜测。
- `storyboard.json` 为默认必产。
- 页数必须严格匹配任务包要求。
- 页面自然语言内容默认与用户 query 保持一致。
- 页面顺序必须体现清晰叙事，而不是堆砌信息。
- `presenter_intent` 只表达讲述意图，不承担完整讲稿。
- 每页必须显式记录 `asset_requirements` 与 `unresolved_issues`，便于后续局部修复。

## 不要做的事

- 不要退回旧 `outline` 的松散结构。
- 不要把完整讲稿直接塞进 `storyboard.json`。
- 不要让前端需要猜字段含义。
