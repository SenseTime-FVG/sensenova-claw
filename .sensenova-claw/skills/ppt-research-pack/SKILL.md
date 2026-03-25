---
name: ppt-research-pack
description: 当内容素材不足、主题涉及真实事实、或需要把报告与外部资料整理成可直接支持 PPT 叙事的研究结果时使用。
---

# PPT 研究包

## 目标

必须先读取 `task-pack.json`，再按 `task-pack.json.research_required` 决定是否执行研究，产出 `research-pack.md` 或 `research-pack.json`，作为内容依据。

## 用户回显要求

- `开始反馈`：说明正在补充研究或提炼上传资料，并指出会产出 `research-pack`。
- `完成反馈`：总结核心结论、仍然缺失的信息和 `下一步` 要落到哪个工件。
- 如果外部检索结果不稳定、证据不足或存在冲突，要在反馈里显式提示不确定性。

## 适用场景

- 用户上传了报告、文档、网页，需要提炼内容
- 主题涉及事实、数据、案例，需要补充检索
- 需要把长文档整理成可用于分页叙事的研究结果
- `task-pack.json.research_required` 为真，且 `task-pack.json` 已明确存在内容缺口

## 产出要求

研究结果至少应包含：

- 核心结论
- 关键论点
- 证据摘要
- 可用于分页的章节建议
- 已知信息缺口

## 关键原则

- 必须先读取 `task-pack.json`。
- research 不是默认第一步。
- 是否运行 research 取决于 `task-pack.json.research_required`。
- 研究包是内容依据，不是页面大纲。
- 不要在研究阶段先决定最终页面布局。
- 不要虚构事实、数据或案例。
- 如果外部检索结果不稳定，必须写明不确定性。
