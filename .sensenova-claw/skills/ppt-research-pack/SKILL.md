---
name: ppt-research-pack
description: 当 `ppt-task-pack` 判定存在内容缺口、`task-pack.json.research_required` 为真时使用；上传报告、事实数据案例和长文档只是 `ppt-task-pack` 计算 `research_required` 的信号，不是独立入口。
---

# PPT 研究包

为后续 `ppt-info-pack` 提供经过结构化整理的"可上页内容池"，而非简单摘要。

## 目标

- 必须先读取 `task-pack.json`，按其中 `research_required` 字段决定是否执行研究。
- 产出 `research-pack.json`，作为 `ppt-info-pack` 的内容依据。
- research 不是摘要——它是带有稳定 ID 的结构化"可上页内容池"，先供 `ppt-info-pack` 汇总，再供 `ppt-storyboard` 的 `source_claim_ids` / `source_evidence_ids` 回指。

## 触发条件

- `task-pack.json.research_required` 为真，且 `task-pack.json` 已明确存在内容缺口。
- 由 `ppt-task-pack` 判定后进入，不可跳过 `ppt-task-pack` 直接触发。

以下情况**不是**直接触发本 skill 的入口：
- 用户上传了报告、文档、网页 —— 这些只用于帮助 `ppt-task-pack` 判断 `research_required`。
- 主题涉及事实、数据、案例 —— 这是 `research_required` 的信号，不是直接入口。
- 需要把长文档整理成可用于分页叙事的研究结果 —— 由 `ppt-task-pack` 的 `research_required` 决定是否进入。

## 输入

- `task-pack.json`：必须先读取，从中获取 `deck_dir`、`research_required`、`research_needs`、`content_gap_assessment`。
- 用户上传的原始资料（报告、文档、网页等）。

## 输出

- 输出路径：`${deck_dir}/research-pack.json`。
- 不要手写、缩写、翻译或重拼 `deck_dir`。

研究结果至少应包含：
- 核心结论
- `claims` —— 结构化论点
- `evidence_points` —— 支撑证据
- `pageworthy_chunks` —— 可上页的内容块
- `risks_or_uncertainties` —— 信息缺口与证据不确定性

## 执行规则

### 研究流程

1. 读取 `task-pack.json`，确认 `research_required` 为真。
2. 根据 `research_needs` 中的 topic、reason、scope、priority 执行定向研究，不要退化成泛化搜索。
3. 对用户上传的资料做结构化提炼，提取可上页的论点、证据和内容块。
4. 对外部检索结果交叉验证，标注不确定性。
5. 为每个 `Claim`、`EvidencePoint`、`PageworthyChunk` 分配稳定 ID。

### 稳定 ID 要求

- `Claim` 必须拥有 `claim_id`，`EvidencePoint` 必须拥有 `evidence_id`，`PageworthyChunk` 必须拥有 `chunk_id`。
- 这些稳定 ID 先供 `ppt-info-pack` 汇总，再供 `ppt-storyboard` 的 `source_claim_ids` / `source_evidence_ids` 回指，不允许只靠自然语言主题词做弱关联。

## 数据结构

```python
class Claim:
    claim_id: str
    claim: str
    importance: str
    evidence_ids: list[str]


class EvidencePoint:
    evidence_id: str
    evidence: str
    source: str
    supports_claim_ids: list[str]


class PageworthyChunk:
    chunk_id: str
    chunk: str
    why_pageworthy: str
    related_claim_ids: list[str]


class ResearchPack:
    claims: list[Claim]
    evidence_points: list[EvidencePoint]
    pageworthy_chunks: list[PageworthyChunk]
    risks_or_uncertainties: list[str]
```

## 用户回显

- **开始反馈**：说明正在补充研究或提炼上传资料，并指出会产出 `research-pack`。
- **完成反馈**：总结核心结论、仍然缺失的信息和 `下一步` 要落到哪个工件。
- 如果外部检索结果不稳定、证据不足或存在冲突，要在反馈里显式提示不确定性。

## 关键原则

- 必须先读取 `task-pack.json`；research 不是默认第一步，是否运行取决于 `task-pack.json.research_required`。
- 上传报告、事实数据案例和长文档只是 `ppt-task-pack` 计算 `research_required` 的信号，不是绕过 `ppt-task-pack` 的独立入口。
- 稳定 ID 先供 `ppt-info-pack` 汇总，再供 storyboard 的 `source_claim_ids` / `source_evidence_ids` 回指。
- research 不是摘要，而是带稳定 ID 的"可上页内容池"；`pageworthy_chunks` 是 `ppt-info-pack` 的上游输入。
- `risks_or_uncertainties` 统一承接信息缺口与证据不确定性，不再额外拆成另一套"已知信息缺口"字段。

## 禁止事项

- 不要在研究阶段先决定最终页面布局。
- 不要虚构事实、数据或案例。
- 如果外部检索结果不稳定，必须写明不确定性。
- 不要跳过 `ppt-task-pack` 直接执行研究。
- 不要只靠自然语言主题词做弱关联，必须使用稳定 ID。
