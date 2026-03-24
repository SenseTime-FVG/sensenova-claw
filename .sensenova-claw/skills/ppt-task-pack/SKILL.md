---
name: ppt-task-pack
description: 当需要把用户意图、页数、受众、语言、限制、交付物和信息缺口统一收束为一个稳定任务包时使用。
---

# PPT 任务包

## 目标

产出 `task-pack.json`，为后续所有技能提供统一的任务边界。

## 用户回显要求

- `开始反馈`：说明正在整理任务包，并告知会固定 `deck_dir`、页数假设和 mode。
- `完成反馈`：总结主题、受众、总页数、当前 mode、`deck_dir` 和 `下一步`。
- 如果 query 中存在必须依赖假设的边界条件，要在反馈里明确写出假设项或待确认项，不要静默带过。

## 必须覆盖

- 主题
- 受众
- 演示目标
- 目标页数
- 默认语言
- 必须覆盖的章节
- 约束条件
- 当前交付物需求
- 已知缺口
- 当前建议模式

## 建议结构

```python
from typing import Literal

Mode = Literal["fast", "guided", "surgical"]
OutputPolicy = Literal["user-provided", "reuse-existing", "auto-generated"]

class TaskPack:
    schema_version: str
    topic: str
    audience: str
    goal: str
    language: str
    total_pages: int
    mode: Mode
    deliverables: list[str]
    must_have_sections: list[str]
    constraints: list[str]
    known_gaps: list[str]
    available_sources: list[str]
    deck_dir: str
    output_policy: OutputPolicy
```

## 关键原则

- 面向用户阅读的自然语言内容默认与用户 query 保持一致。
- 如果页数没有明确给出，需要在任务包中写明合理假设。
- 如果讲稿是交付物，必须在 `deliverables` 中显式声明。
- `deck_dir` 是本轮任务的 canonical 输出根目录。
- `deck_dir` 必须在这里被明确固定，后续所有 skill 都复用同一个输出目录。
- 后续 skill 只能直接复制这个值，不要自行改写、缩写、翻译或重拼目录名。
- 如果用户没有指定输出地点，`deck_dir` 应使用 `query概述 + 时间戳` 自动创建，而不是把产物直接写到当前目录顶层。
