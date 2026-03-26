---
name: ppt-speaker-notes
description: 当用户明确要求讲稿，或任务场景属于汇报、路演、培训、答辩、演讲，需要把 storyboard 和最终页面转成逐页讲稿时使用。
---

# PPT 讲稿

这是可选交付物，不进入默认最小路径。

## 输入

- `storyboard.json`
- 可选的 `pages/page_XX.html`

## 目标

产出 `speaker-notes.json` 或 `speaker-notes.md`，为演讲者提供逐页讲稿。

## 用户回显要求

- `开始反馈`：说明当前正在为哪些页面生成讲稿，并指出输出格式。
- `完成反馈`：总结讲稿覆盖页数、语气方向和 `下一步`。

## 关键原则

- 它是可选交付物，不要默认塞进 `storyboard.json`。
- 如果 `pages/page_XX.html` 已经稳定，应优先参考最终页面结果。
- 如果页面还未稳定，可以先基于 `storyboard.json` 生成基础版讲稿。
- 讲稿语气应与场景匹配，例如汇报、路演、培训、答辩。

## 建议结构

```python
class SpeakerNotes:
    schema_version: str
    language: str
    notes: list["SpeakerNotePage"]
```
