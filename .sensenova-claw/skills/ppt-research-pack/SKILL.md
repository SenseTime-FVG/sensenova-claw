---
name: ppt-research-pack
description: 当 `task-pack` 判定存在内容缺口、需要进一步研究时使用；上传报告、事实数据案例和长文档只是 `task-pack` 计算 `research_required` 的信号，不是独立入口。
---

# PPT 研究包

## 目标

必须先读取 `task-pack.json`，再按 `task-pack.json.research_required` 决定是否执行研究，产出 `research-pack.md` 或 `research-pack.json`，作为内容依据。
research 不是摘要，而是“可上页内容池”。

## 用户回显要求

- `开始反馈`：说明正在补充研究或提炼上传资料，并指出会产出 `research-pack`。
- `完成反馈`：总结核心结论、仍然缺失的信息和 `下一步` 要落到哪个工件。
- 如果外部检索结果不稳定、证据不足或存在冲突，要在反馈里显式提示不确定性。

## 适用场景

- 用户上传了报告、文档、网页，需要提炼内容: 先进入 `ppt-task-pack`，这些输入只用于帮助 `task-pack` 判断 `research_required`
- 主题涉及事实、数据、案例，需要补充检索: 先进入 `ppt-task-pack`，这是 `research_required` 的信号，不是直接触发 research 的入口
- 需要把长文档整理成可用于分页叙事的研究结果: 先进入 `ppt-task-pack`，由 `research_required` 决定是否进入 research
- 上传报告、事实数据案例和长文档只是 `task-pack` 计算 `research_required` 的信号
- `task-pack.json.research_required` 为真，且 `task-pack.json` 已明确存在内容缺口

## 产出要求

研究结果至少应包含：

- 核心结论
- `claims`
- `evidence_points`
- `pageworthy_chunks`
- `risks_or_uncertainties`

建议最小结构：

```python
class Claim:
    claim: str
    importance: str
    evidence_refs: list[str]


class EvidencePoint:
    evidence: str
    source: str
    supports: list[str]


class PageworthyChunk:
    chunk: str
    why_pageworthy: str
    related_claims: list[str]


class ResearchPack:
    claims: list[Claim]
    evidence_points: list[EvidencePoint]
    pageworthy_chunks: list[PageworthyChunk]
    risks_or_uncertainties: list[str]
```

## 关键原则

- 必须先读取 `task-pack.json`。
- research 不是默认第一步。
- 是否运行 research 取决于 `task-pack.json.research_required`。
- 由 `task-pack.json.research_required` 决定是否进入 `ppt-research-pack`。
- 上传报告、事实数据案例、长文档等都只是 `task-pack` 的研究信号。
- 研究包是内容依据，不是页面大纲。
- research 不是摘要，而是“可上页内容池”。
- `pageworthy_chunks` 是 storyboard 的上游输入。
- `risks_or_uncertainties` 统一承接信息缺口与证据不确定性，不再额外拆成另一套“已知信息缺口”字段语义。
- 不要在研究阶段先决定最终页面布局。
- 不要虚构事实、数据或案例。
- 如果外部检索结果不稳定，必须写明不确定性。
