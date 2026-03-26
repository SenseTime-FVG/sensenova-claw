# PPT 内容充实度与确认优先流程改造设计

## 背景

当前 PPT skill 链路已经基本具备以下能力：

- 以 `ppt-superpower` 作为统一入口
- 输出 `task-pack.json`、`style-spec.json`、`storyboard.json`
- 逐页生成 HTML，并导出为 PPTX
- 支持阶段回显、图片规划、装饰层约束与 review 守卫

但从近期生成结果看，仍有三类系统性问题：

1. 正文页内容偏少
2. 实际执行顺序偶尔出现“search 先于 task”的漂移
3. 默认仍偏 `fast`，而不是“逐步汇报并等待用户确认”

这三类问题彼此相关，但不能一次性混改，否则很难判断是哪一层真正起效。因此需要先写出一份实验驱动的改造设计。

## 目标

本轮设计的目标不是立刻实现所有优化，而是确定一套可验证的试验顺序，使后续改动具备可解释性。

核心目标：

1. 提升正文页的内容充实度，优先改善：
   - `A`：论点太薄、像提纲
   - `B`：事实 / 数据 / 证据支撑不足
   - `D`：页面承载偏稀，看起来不完整
2. 纠正总控逻辑，使 `ppt-superpower` 先收敛任务边界，再决定是否 research
3. 将默认交互模式改成“逐步汇报、等待确认”，只有用户明确要求时才直通快路径

## 非目标

本轮不把以下内容作为第一优先级：

- 修改主画布分辨率
- 大规模重做视觉风格系统
- 调整 PPTX 导出能力
- 推翻现有 skill 架构

分辨率相关问题只作为对照观察项，不作为第一刀。

## 核心判断

### 1. “内容少”优先被视为内容链路问题，而不是分辨率问题

从用户反馈看，当前问题排序为 `A > B > D`。这意味着：

- 主问题是内容组织与证据支撑不足
- 页面“看起来空”更像结果，而不是唯一根因

因此，不建议先动 `1280x720` 画布约束。只有在后续诊断中证明“内容本身足够，但字号 / 间距 / 版面尺度导致容纳不下”时，才应单独开启分辨率或尺度实验。

### 2. `search` 顺序问题不仅影响内容，也影响总控设计是否成立

当前设计理念应是：

1. 先明确任务边界
2. 再判断是否存在内容缺口
3. 有缺口才进入 research

如果实际运行出现“先 search 再 task”，问题就不只是内容不足，而是 `ppt-superpower` 的控制职责被破坏。此问题必须作为优先修复项，而不是只当作“可能会增内容”的一个试验变量。

### 3. 默认 mode 的修改必须放在内容实验之后

将默认模式从 `fast` 改为“确认优先”会同时影响：

- 用户体验
- 链路节奏
- 中间工件稳定性
- 耗时感知

因此它不应与内容充实度试验混在第一轮一起做，否则会干扰对内容质量的判断。

## 试验总顺序

按以下顺序推进：

1. `实验 0：基线诊断`
2. `实验 1：总控顺序纠偏 + 内容前置增强`
3. `实验 2：正文页内容密度按主题自适应`
4. `实验 3：默认模式改为确认优先`

这样可以保证每一轮的结论都可解释。

---

## 实验 0：基线诊断

### 目标

不改实现，先建立“内容充实度”的诊断口径，判断当前问题主要少在哪里。

### 诊断维度

每个正文页按以下维度记录：

1. `论点密度`
   - 是否有清晰主结论
   - 是否存在“观点 - 解释 - takeaway”闭环
2. `证据密度`
   - 是否有数据、事实、案例、时间点、方法说明、对比支撑
3. `结构密度`
   - 是否有 2 到 4 个具有功能差异的内容块
4. `视觉承载密度`
   - 是否有图表、对比块、流程块、摘要条、标签组等结构化承载
5. `空白感`
   - 是风格性留白，还是“本来还可以放内容但没有放”

### 分辨率观察规则

保持主画布 `1280x720` 不变，只作为诊断时的旁路观察项：

- 如果原始 HTML 的内容块数量就很少，分辨率不是主因
- 如果内容较多但因为字号 / 间距 / 容器比例过松导致塞不下，再考虑后续单开版面尺度实验

### case 选择

建议至少覆盖：

- 分析 / 汇报类 2 个
- 方案 / 活动类 2 个

### 产出

形成一张基线诊断表，回答：

1. 主要缺的是论点、证据，还是承载
2. 哪类主题更容易空
3. 分辨率是否值得进入后续实验

---

## 实验 1：总控顺序纠偏 + 内容前置增强

### 目标

同时解决两个问题：

1. `ppt-superpower` 的实际执行顺序与设计理念不一致
2. research 没有真正变成可上页的内容池

### 新的主流程

应严格收敛为：

1. 固定 `deck_dir`
2. 生成 `task-pack.json`
3. 根据 `task-pack` 判断是否存在内容缺口
4. 如有缺口，进入 `ppt-research-pack`
5. 生成 `style-spec.json`
6. 生成 `storyboard.json`
7. 后续才进入资产、HTML、review、export

### 行为约束

- 不允许在 `task-pack` 之前做外部 research 决策
- 允许在前面做 `ppt-source-analysis` 来识别输入来源
- 但 `source-analysis` 只是理解来源，不等于已经进入 research
- `task-pack` 必须成为 research 的输入前提，而不是 research 的副产物

### `ppt-task-pack` 需要新增的控制面

建议增加以下语义字段：

```python
from typing import Literal


ResearchScope = Literal["data", "cases", "definitions", "comparisons", "risks", "trends"]
Priority = Literal["high", "medium", "low"]


class ResearchNeed:
    topic: str
    reason: str
    scope: list[ResearchScope]
    priority: Priority


class TaskPack:
    # 既有字段省略
    content_gap_assessment: list[str]
    research_required: bool
    research_needs: list[ResearchNeed]
```

语义要求：

- `content_gap_assessment` 记录哪些章节或主题存在内容缺口
- `research_required` 作为是否进入 `ppt-research-pack` 的直接依据
- `research_needs` 作为 research 的边界清单，而不是泛化地“去搜一下”

### `ppt-research-pack` 的定位调整

research 不再只是摘要，而是“可直接上页的内容池”。

建议最小结构：

```python
from typing import Optional


class EvidencePoint:
    id: str
    statement: str
    evidence_type: str  # data / fact / case / quote / comparison
    source_note: str
    uncertainty: Optional[str]


class Claim:
    id: str
    statement: str
    supporting_evidence_ids: list[str]


class PageworthyChunk:
    id: str
    title: str
    claim_ids: list[str]
    evidence_ids: list[str]
    recommended_usage: str  # overview / comparison / risk / strategy / timeline


class ResearchPack:
    claims: list[Claim]
    evidence_points: list[EvidencePoint]
    pageworthy_chunks: list[PageworthyChunk]
    risks_or_uncertainties: list[str]
```

要求：

- 输出要尽量短、可引用、可分页
- research 不是写一篇报告，而是为 storyboard 提供拼页面的砖

### `ppt-storyboard` 的消费契约

storyboard 必须显式消费 research，而不是只拿主题词重新写一遍。

建议新增以下语义：

```python
class ContentBlock:
    block_id: str
    block_type: str
    source_claim_ids: list[str]
    source_evidence_ids: list[str]
    unresolved_gaps: list[str]
```

要求：

- 每页至少能说明其主 claim 来自哪些 research 条目
- 支撑 evidence 来自哪些 research 条目
- 哪些内容仍缺支撑，不能硬写成确定结论

### 本轮不改

- 不改 `style-spec` 视觉系统
- 不改 `page-html` 的密度承载策略
- 不改默认 mode
- 不改导出链路
- 不改画布尺寸

### 验收标准

只看三件事：

1. `task-pack` 是否稳定先于 research 产生
2. research 是否真的产出可上页内容块
3. storyboard 是否显式消费这些内容块

---

## 实验 2：正文页内容密度按主题自适应

### 目标

在实验 1 让内容变厚后，进一步解决“页面仍然显得空”的问题。

### 核心思路

不是所有页面都更满，而是给不同主题默认不同的正文承载策略。

建议新增统一语义：

```python
from typing import Literal


ContentDensityProfile = Literal["analysis-heavy", "balanced", "showcase-light"]


class PayloadBudget:
    claim_count: int
    evidence_count: int
    structure_block_count: int
    require_comparison_or_summary: bool
```

含义：

- `analysis-heavy`
  - 适合金融、行业分析、方法论、复盘、评估
- `balanced`
  - 适合一般汇报、培训、项目介绍
- `showcase-light`
  - 适合品牌、活动、展示、发布型页面

### 落点分工

#### `ppt-task-pack`

- 根据用户任务判断默认 `content_density_profile`
- 允许用户显式覆盖

#### `ppt-style-spec`

- 将 profile 翻译成页面承载规则
- 例如允许多少结构块、是否鼓励摘要条、对比块、小表格、标签组

#### `ppt-storyboard`

- 每页增加 `payload_budget`
- 说明这一页应承载多少主 claim、多少 evidence、多少结构块

#### `ppt-page-html`

- 必须按 budget 落地
- 不允许把可承载 3 块内容的页面做成“一个标题 + 一个大卡片”

### 本轮不改

- 不改 research 顺序
- 不改默认 mode
- 不改画布尺寸

### 验收标准

- 分析 / 汇报类正文页更扎实
- 品牌 / 活动 / 方案类正文页保持呼吸感，但不再像提纲
- 页面块数与类型更合理，而不是机械加字

---

## 实验 3：默认模式改成确认优先

### 目标

让默认体验从“静默跑到底”变成“逐步汇报、用户确认后继续”。

### 模式策略调整

不是删除 `fast`，而是修改 mode 选择策略：

1. 默认进入接近 `guided` 的确认优先路径
2. 只有用户明确说“直接执行 / 不要确认 / 一口气跑完”时，才进入显式 `fast`
3. `surgical` 保持现有局部修复语义不变

### 默认停点

默认确认优先路径至少在以下工件后等待确认：

- `task-pack.json`
- `style-spec.json`
- `storyboard.json`

必要时，在以下阶段也允许显式确认：

- `asset-plan.json`
- `review.md` / `review.json`

### 典型触发语义

#### 默认

- 用户说“帮我做一份 PPT”
- 用户说“先做一下这个题目”
- 用户没有明确授权自动跑完

此时应进入确认优先路径。

#### 显式快路径

只有当用户明确表达以下意图时，才直通 `fast`：

- “直接生成”
- “不要确认”
- “自动继续”
- “一口气跑完”

### 改动范围

- `ppt-superpower`
- 设计文档与契约测试
- 必要时补 mode 选择回归测试

### 本轮不改

- 不改内容研究逻辑
- 不改页面密度规则
- 不改导出链路

---

## 试验执行建议

按以下顺序逐步落地：

1. 先完成 `实验 0`，形成可复用诊断表
2. 再完成 `实验 1`，确认总控顺序与 research 内容池是否成立
3. 如果 `A/B` 明显改善，再进入 `实验 2`
4. 最后再做 `实验 3`

这样每一轮都能回答一个清晰问题：

1. 现在到底少在哪里
2. 顺序纠偏是否让内容变厚
3. 页面承载是否跟上了内容
4. 默认交互模式是否需要整体转为确认优先

## 风险与控制

### 风险 1：实验 1 改太多，难以判断效果

控制方式：

- 实验 1 只动 `superpower / task-pack / research-pack / storyboard`
- 不碰视觉层与页面承载策略

### 风险 2：实验 2 把所有主题都做成高密度

控制方式：

- 通过 `content_density_profile` 做主题级分流
- 明确保留 `showcase-light`

### 风险 3：实验 3 改默认 mode 后，流程明显变慢

控制方式：

- 保留显式 `fast`
- 只有默认值切换，不删除快路径

## 最终建议

推荐按照如下顺序实施：

1. 先修主流程逻辑
2. 再补 research 到 storyboard 的内容消费
3. 再做正文页内容密度自适应
4. 最后把默认交互模式切到确认优先

原因是：

- 这最符合 `ppt-superpower` 的设计理念
- 也最能解释用户当前观察到的现象
- 并且能把“内容不足”和“体验不稳”分开验证
