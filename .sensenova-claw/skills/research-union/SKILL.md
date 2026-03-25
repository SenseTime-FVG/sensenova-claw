---
name: research-union
description: 当用户要求深度调研、系统梳理、研究报告、竞品分析、方案对比、趋势分析或事实核查，且需要多来源检索、交叉验证并附来源依据时使用；不用于单点事实查询或快速摘要。
---

# research-union（迭代式 Deep Research 编排）

这是一个深度研究编排 skill，采用与市面 Deep Search 产品（OpenAI Deep Research、Gemini Deep Research、Perplexity Pro）相同的核心架构：**迭代式搜索-阅读-反思循环**。

核心理念：不是"搜一轮就写报告"，而是"搜 → 读 → 评估 → 不够就再搜"，循环多轮直到证据充分。

## 何时使用

优先使用：

- 用户明确要求"深度调研""全面梳理""系统研究""研究报告""deep research"
- 问题涉及多来源对比、竞品/方案比较、趋势分析、事实核验
- 问题需要拆成多个子问题才能回答
- 用户强调结果要附依据、来源和分歧说明

不要使用：

- 单条事实问题，直接搜索即可
- 只需要几个链接或一个简短摘要
- 本地文件或已有上下文就足以回答

## 路径选择

### simple path

适用于单点事实查询、少量链接、快速摘要。

执行：直接搜索 → 先结论后依据 → 完成。不走 planning，不落盘。

### complex path

当以下信号命中任意 2 条时进入：

- 需要回答多个子问题
- 需要多来源交叉验证
- 涉及竞品对比、方案比较、趋势梳理、事实核验
- 用户明确要求深入调研
- 需要明确时间/地域/样本边界

复杂路径采用 **7 阶段迭代架构**：

```
PLAN → DIVERGE → SEARCH → TRIAGE → READ → REASSESS → SYNTHESIZE
                    ↑                          |
                    └── 覆盖度不足时回到这里 ───┘
```

---

## complex path 详细流程

### 阶段 1：PLAN（研究规划 + 用户确认）
【
探索性搜索的目的：确认术语准确性、判断信息可获取性、校准研究范围。不是正式搜索。

产出一个可确认的 planning JSON：

```json
{
  "mode": "deep_research",
  "topic": "研究主题",
  "goal": "核心目标",
  "scope": {
    "time_range": "近3年",
    "region": "全球",
    "language": ["zh", "en"],
    "inclusions": [],
    "exclusions": []
  },
  "questions": [
    {
      "id": "q1",
      "question": "子问题1",
      "evidence_types": ["官方文档", "技术博客", "论文"],
      "dimensions": ["定义", "对比", "时间线"]
    }
  ],
  "search_budget": {
    "min_queries": 15,
    "max_queries": 40,
    "max_iterations": 3,
    "min_sources_per_question": 2
  },
  "success_criteria": {
    "min_total_sources": 8,
    "min_verified_claims": 5,
    "coverage_target": 0.8
  },
  "source_plan": {
    "primary": ["serper_search", "fetch_url"],
    "supplement": ["union-search-plus（仅在主链不足时启用）"]
  },
  "expected_output": {
    "format": "report",
    "sections": ["结论摘要", "关键发现", "证据与来源", "分歧与不确定点", "限制说明"]
  }
}
```

向用户展示时用简洁中文概括，只确认：范围、子问题、边界条件。

确认后写入当前 session 工作区 `research/plan.json`，作为后续阶段的统一依据。

### 阶段 2：DIVERGE（发散式 Query 生成）

这是与传统 skill 最大的区别。不是直接把子问题当搜索词，而是对每个子问题生成多维度的 query 矩阵。

对每个子问题，生成以下类型的 query：

1. **直接查询**：子问题本身的自然语言表述
2. **专业术语版**：用该领域的专业词汇重新表述（practitioner vocabulary）
3. **反面查询**：`"X 的问题"` `"X 的缺点"` `"X alternatives"` `"why not X"`
4. **对比查询**：`"X vs Y"` `"X compared to Y"`
5. **实体扩展**：通过已知实体（公司、人物、项目）做一跳关联搜索
6. **聚合器查询**：搜索目录、排行榜、awesome-list 等聚合页面

目标：每个子问题至少 3-5 个变体 query，整体 query 数量达到 `search_budget.min_queries` 以上。

同时生成中英文双语 query（如果 scope.language 包含多语言）。

将所有 query 按子问题分组，记录到 `research/queries.json`。

### 阶段 3：SEARCH（并发搜索爆发）

将 DIVERGE 阶段生成的所有 query 尽可能并发执行。

执行策略：

- 在单次 LLM 响应中，尽可能多地并发调用 `serper_search`（利用 tool_calls 并发能力）
- 如果 query 数量超过单次并发上限，分 2-3 批执行，每批尽量打满
- 每个 query 记录：query 文本、搜索引擎、返回结果数、top 结果标题和 URL

搜索源优先级：

1. `serper_search`（主链，始终优先）
2. 内置搜索工具（`brave_search`、`tavily_search` 等，如果可用）
3. `union-search-plus`（仅在主链覆盖不足时启用，不是默认选项）

本阶段目标：收集尽可能多的候选 URL 和摘要，不做深度阅读。

### 阶段 4：TRIAGE（结果筛选与去重）

对 SEARCH 阶段收集的所有结果进行质量筛选。

筛选规则：

1. **去重**：完全相同的 URL 去重；同一内容的不同镜像/转载去重（保留原始来源）
2. **域名限制**：同一域名最多保留 3 条结果，防止单一来源主导
3. **视角多样性**：确保结果覆盖不同立场（支持方、反对方、中立方）
4. **可信度分级**（5 级）：
   - L1 官方文档/原始公告/一手数据
   - L2 权威媒体/知名研究机构/peer-reviewed
   - L3 行业博客/技术社区/知名个人
   - L4 一般媒体/聚合站/二手报道
   - L5 论坛评论/社交媒体/未验证来源
5. **相关性评分**：与子问题的匹配度（高/中/低）

产出：按子问题分组的优先阅读列表，每个子问题选出 top 3-5 个高价值 URL。

### 阶段 5：READ（深度阅读与证据提取）

对 TRIAGE 筛选出的高价值 URL 进行全文抓取和精读。

执行策略：

- 小批量抓取：每批 2-3 个 URL，使用 `fetch_url` 获取全文
- 小批量的原因：避免超时影响扩散，单个失败不阻塞其他
- 对每个页面提取：
  - 与子问题相关的关键事实和数据
  - 直接引用（带原文）
  - 来源的发布时间和作者
  - 页面中提到的其他有价值的链接（可选：一跳跟踪）

证据记录格式：

```
子问题 ID | 证据摘要 | 原文引用 | 来源 URL | 可信度等级 | 是否需要交叉验证
```

如果某个 URL 抓取失败，标记为 FAILED 并在 REASSESS 阶段考虑补充。

### 阶段 6：REASSESS（覆盖度评估 + 迭代决策）

**这是整个 skill 的核心阶段，也是与传统线性 skill 最大的区别。**

对每个子问题逐一评估：

1. **来源充分性**：是否达到 `min_sources_per_question`（默认 2 个独立来源）？
2. **证据强度**：关键结论是否有 L1-L2 级来源支撑？
3. **交叉验证**：重要事实是否被 2+ 个独立来源确认？
4. **视角覆盖**：是否只有单一立场的来源？是否缺少反面证据？
5. **新发现**：阅读过程中是否发现了新的子问题、新术语、新角度？

对每条关键结论标注验证状态：

- **CONFIRMED**：2+ 个独立来源交叉确认
- **LIKELY**：1 个可靠来源支撑，无矛盾信息
- **DISPUTED**：来源之间存在矛盾
- **UNVERIFIED**：仅有低可信度来源或单一来源
- **GAP**：该子问题缺乏有效证据

**迭代决策逻辑**：

```
IF 任何子问题标记为 GAP:
    → 必须回到 DIVERGE，为该子问题生成补充 query
IF 关键结论标记为 UNVERIFIED 且可信度 < L3:
    → 应该回到 SEARCH，尝试交叉验证
IF 发现新的重要子问题:
    → 评估是否在原始 scope 内
    → 如果在 scope 内：添加子问题，回到 DIVERGE
    → 如果超出 scope：记录但不追踪，在报告中提及
IF 所有子问题达到 min_sources 且关键结论均为 CONFIRMED/LIKELY:
    → 进入 SYNTHESIZE
IF 已达到 max_iterations:
    → 即使覆盖不足也进入 SYNTHESIZE，但在报告中明确标注不足之处
```

**迭代约束**：

- 最多迭代 `search_budget.max_iterations` 轮（默认 3 轮）
- 每轮迭代的补充 query 数量递减（第 2 轮 ≤ 10，第 3 轮 ≤ 5）
- 补充搜索优先使用不同的搜索词和搜索引擎，避免重复
- 如果连续 2 轮迭代没有发现新的有效信息，提前终止

**迭代时需要用户确认的情况**：

- 研究范围需要明显扩大
- 需要启用 `union-search-plus` 进行补充搜索
- 发现原始问题的前提假设可能有误

### 阶段 7：SYNTHESIZE（综合报告）

将所有经过验证的证据整合为最终报告。

报告结构：

#### 1. 结论摘要（Executive Summary）
- 用 3-5 句话回答用户的核心问题
- 标注整体置信度（高/中/低）

#### 2. 关键发现（Key Findings）
- 按子问题组织
- 每个发现附验证状态标签：`[CONFIRMED]` `[LIKELY]` `[DISPUTED]` `[UNVERIFIED]`
- 关键数据和事实用原文引用

#### 3. 证据与来源（Evidence & Sources）
- 每条关键结论附来源链接
- 标注来源可信度等级（L1-L5）
- 多来源交叉确认的结论明确标注

#### 4. 分歧与不确定点（Disagreements & Uncertainties）
- 来源之间的矛盾信息，列出各方观点和来源
- 标记为 DISPUTED 的结论，说明分歧原因
- 无法确认的信息，说明为什么无法确认

#### 5. 研究限制（Limitations）
- 未覆盖的子问题及原因
- 搜索受限的领域（如付费墙、语言限制）
- 补充搜索未执行/失败的说明
- 建议的后续研究方向

#### 6. 附录：来源清单（Source Appendix）
- 所有引用来源的完整列表
- 格式：`[编号] 标题 | URL | 可信度等级 | 访问时间`

报告同时生成两个版本：
- Markdown 格式的完整报告（给用户阅读）
- 结构化 YAML/JSON 附录（给后续处理使用），写入 `research/report_meta.json`

---

## 与 union-search-plus 的衔接

`union-search-plus` 定位不变：补充来源，不是默认主链。

启用条件（必须满足至少一条）：

- REASSESS 阶段发现主链搜索覆盖不足（某子问题 0 有效来源）
- 用户在 PLAN 阶段明确要求使用补充来源
- 主链搜索引擎对特定领域（如中文社区、视频平台）覆盖差

启用顺序：先 `preferred` 来源 → 必要时升级到 `all`。

补充搜索失败时：继续使用已有结果，在报告中明确说明限制。不得因补充失败而阻塞整个研究。

---

## 执行纪律

### 必须做到

- 每次 SEARCH 阶段至少并发 5+ 个 query（不是一个一个搜）
- REASSESS 阶段必须逐子问题评估，不能笼统说"差不多够了"
- 关键结论必须有 2+ 独立来源交叉确认才能标记 CONFIRMED
- 每个 SEARCH → READ → REASSESS 循环结束后，明确输出当前覆盖度状态
- 迭代决策必须基于具体的 GAP/UNVERIFIED 标记，不能凭感觉

### 禁止事项

- 不得在简单问题上强行走复杂流程
- 不得在 PLAN 未确认前进入大规模搜索
- 不得把 `union-search-plus` 当成默认主链
- 不得编造来源或伪造引用
- 不得把"搜索到"写成"已验证"
- 不得省略关键结论的来源链接
- 不得把 planning 只放在上下文里而不落盘
- 不得在 REASSESS 阶段跳过迭代检查直接进入 SYNTHESIZE
- 不得在单次搜索后就声称"覆盖充分"（除非确实所有子问题都有 2+ 来源）

### 进度透明

在每个阶段转换时，向用户简要报告：

- 当前阶段和进度
- 已搜索 query 数 / 已阅读页面数 / 已确认证据数
- 下一步计划
- 如果需要迭代，说明原因和补充方向

---

## 执行检查清单

结束前确认：

- [ ] 是否先判断了 simple path 还是 complex path
- [ ] 如果是复杂路径，是否生成并确认了 planning JSON
- [ ] planning 是否写入 `research/plan.json`
- [ ] DIVERGE 阶段是否为每个子问题生成了 3+ 变体 query（含反面查询）
- [ ] SEARCH 阶段是否并发执行了 15+ 个 query
- [ ] TRIAGE 阶段是否做了去重、域名限制和可信度分级
- [ ] READ 阶段是否对 top 结果做了全文精读
- [ ] REASSESS 阶段是否逐子问题评估了覆盖度
- [ ] 关键结论是否标注了验证状态（CONFIRMED/LIKELY/DISPUTED/UNVERIFIED）
- [ ] 覆盖不足的子问题是否触发了迭代回搜
- [ ] 最终报告是否包含来源链接、分歧说明和限制声明
- [ ] 来源清单是否完整且标注了可信度等级
