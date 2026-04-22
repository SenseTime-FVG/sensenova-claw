# Deep Research — 自治研究编排系统

## 系统定义

Deep Research 是 Sensenova-Claw 面向复杂知识任务构建的自治研究编排系统。它并不是传统意义上的“搜索增强问答”，也不是单一的长文生成 Agent，而是一套以问题建模、研究编排、证据挖掘、可信治理和结果沉淀为核心的 Research OS。

在这套体系中，系统处理的对象不再是一次性的 Prompt，而是一个需要被持续拆解、求证、修订和综合的研究任务；系统交付的结果也不再是单轮回答，而是一份具备证据约束、引用治理和结构化结论的 `Evidence-Backed Research Dossier`。

从能力边界上看，Deep Research 完成的是以下升级：

- 从信息检索升级为研究生产
- 从文本生成升级为研究工件交付
- 从单点回答升级为多阶段自治编排
- 从来源调用升级为数据源级路由与治理

---

## 设计目标

Deep Research 面向的是以下类型的问题：

- 研究目标开放，无法通过单次搜索直接收敛
- 需要跨来源、跨视角、跨阶段推进
- 对结果的可信度、可追溯性和可复核性有明确要求

围绕这类问题，系统设计聚焦于五个核心目标：

1. **Problem Formalization**  
   将自然语言问题转化为结构化研究对象、研究边界、关键维度和执行约束。

2. **Cognitive Orchestration**  
   由总控 Agent 持续驱动全局流程，根据证据密度、任务进展和信息缺口动态调整后续路径。

3. **Evidence-Centric Research**  
   以证据而非文案为中心组织研究过程，要求关键结论始终绑定来源与求证状态。

4. **Trust & Governance by Default**  
   将引用治理、质量审查、冲突识别和风险提示作为系统内生能力，而非后置补丁。

5. **Assetization of Research**  
   将研究过程沉淀为可复用、可审计、可再加工的结构化工件。

---

## 核心原则

| 原则 | 说明 |
|---|---|
| `Orchestrator-first` | 研究流程由总控 Agent 驱动，而不是由固定状态机硬编码 |
| `Research over Writing` | 系统优先完成问题建模、证据构建与结论收敛，而非优先追求文案长度 |
| `Evidence before Narrative` | 叙事必须建立在已求证证据之上，不能让写作先于研究 |
| `Path over Payload` | 跨 Agent 协作优先传递路径和结构化指令，避免上下文膨胀 |
| `Data Source over Tool` | 检索能力按数据源和路由策略组织，而非按单个工具堆叠 |
| `Governance as Infrastructure` | 引用治理与质量门控属于底层基础设施，而不是附属流程 |
| `Graceful Degradation` | 局部数据源失败不阻塞主流程，但必须显式暴露覆盖边界与可信限制 |

---

## 总体架构

### 架构分层

Deep Research 采用四层架构：

- **Cognitive Orchestration Layer**：负责目标理解、阶段推进、任务调度与结果收敛
- **Research Execution Layer**：负责侦察、规划、证据挖掘、审查和终稿综合
- **Trust & Governance Layer**：负责引用治理、可信收口和结果标准化
- **Persistence Layer**：负责研究工件沉淀与后续复用

### 架构概览

```text
User Query
    ↓
Cognitive Orchestrator
    ↓
Multi-Agent Research Fabric
    ├── Domain Recon Agent
    ├── Research Planning Agent
    ├── Evidence Mining Agent
    ├── Trust & Quality Review Agent
    └── Narrative Synthesis Agent
    ↓
Trust & Governance Layer
    ├── CitationManager
    └── prepare_report_citations
    ↓
Persistence Layer
    ├── briefing.md
    ├── plan.json
    ├── sub_reports/d*.md
    ├── report.md
    └── citations.json
```

### 分层职责

| 层级 | 核心实体 | 职责 |
|---|---|---|
| 编排层 | `Cognitive Orchestrator` | 接收用户目标，驱动全流程，执行阶段调度、回路控制与结果收敛 |
| 执行层 | `Research Fabric` | 承担问题侦察、研究规划、证据挖掘、质量审查和叙事综合 |
| 治理层 | `CitationManager` / `prepare_report_citations` | 统一处理来源映射、编号、去重、规范化与可信收口 |
| 持久层 | Research Assets | 保存中间工件与最终产物，支撑复盘、复用和审计 |

---

## Agent Fabric

### 角色拓扑

```text
deep-research-controller
├── recon-agent
├── planning-agent
├── mining-agent
├── review-agent
└── synthesis-agent
```

### 1. Deep Research Controller

总控 Agent 是系统唯一的研究编排中枢。它负责驱动全局流程，但不直接承担领域研究。

职责：

- 接收用户研究目标并初始化研究目录
- 按阶段调度各类专业 Agent
- 按 wave 组织并行执行和修订闭环
- 在阶段边界完成任务收敛、异常容错和结果交接
- 调用治理能力完成终稿收口

约束：

- 只负责调度，不替代子 Agent 写研究内容
- 所有跨 Agent 文件路径必须使用绝对路径
- 优先传递路径和结构化任务描述，而非大段正文
- 异常任务默认重试一次，失败则记录限制并继续主流程

### 2. Domain Recon Agent

负责完成问题初筛、领域扫描和用户意图澄清，为后续规划建立认知地基。

输出：`briefing.md`

职责：

- 提取研究对象、研究目标、隐含决策背景
- 识别关键实体、核心术语、主流叙事和争议焦点
- 判断研究边界是否清晰，是否需要补充澄清
- 输出结构化 `Research Briefing`

### 3. Research Planning Agent

负责将问题空间转化为结构化、可执行、可并行的研究蓝图。

输出：`plan.json`

职责：

- 确定总体研究策略与主研究轴
- 将问题拆解为 3 到 7 个核心研究维度
- 为维度分配来源类别、研究深度和依赖关系
- 生成可由总控执行的 `Execution Blueprint`

### 4. Evidence Mining Agent

负责围绕单个研究维度执行检索、筛选、求证、交叉验证和子报告撰写。

输出：`sub_reports/d*.md`

职责：

- 将 `key_questions` 细化为可搜索子问题
- 规划多角度检索路径与原始出处追溯路径
- 评估来源层级、偏见风险、时效性和可信边界
- 区分事实、观点与推断
- 产出带脚注引用的维度级 `Evidence Brief`

### 5. Trust & Quality Review Agent

负责对维度级输出和终稿分别进行质量门控。

职责：

- 检查关键结论是否有来源支撑
- 检查逻辑链条是否稳固
- 识别遗漏、偏差、冲突与过度推断
- 判断结果是否真正回答原始问题

输出判定：

- `pass`
- `revise`

### 6. Narrative Synthesis Agent

负责将多个维度级 `Evidence Brief` 综合为结构化研究终稿。

输出：`report.md`

职责：

- 综合而非拼接各维度研究结果
- 沿用既有 citation key
- 显式处理跨维度冲突和证据张力
- 保持结论、论证与证据的一致性

---

## 执行机制

### 研究闭环

Deep Research 采用完整的多阶段研究闭环：

```text
Stage 1  Problem Framing & Domain Recon
Stage 2  Research Blueprinting
Stage 3  Intent Calibration
Stage 4  Wavefront Evidence Acquisition
Stage 5  Dimension Review Loop
Stage 6  Narrative Synthesis
Stage 7  Global Consistency Review
Stage 8  Provenance Consolidation
```

### 阶段职责

| 阶段 | 执行主体 | 输出 | 作用 |
|---|---|---|---|
| Stage 1 | `recon-agent` | `briefing.md` | 建立问题画像、领域地图与信息地形 |
| Stage 2 | `planning-agent` | `plan.json` | 建立维度拆解、波次规划与来源类别建议 |
| Stage 3 | `controller` / `ask_user` | 用户确认 | 在边界、深度、重点不清晰时完成校准 |
| Stage 4 | `mining-agent × N` | `sub_reports/d*.md` | 按 wave 并行执行证据挖掘 |
| Stage 5 | `review-agent × N` | 修订意见或通过 | 对子报告做质量门控 |
| Stage 6 | `synthesis-agent` | `report.md` | 综合维度发现，生成终稿 |
| Stage 7 | `review-agent` | 终稿判定 | 审查全局一致性、可信性和回答完整性 |
| Stage 8 | `CitationManager` | `report.md` + `citations.json` | 完成引用编号与治理收口 |

### Wavefront Parallelism

Wavefront 是系统的核心执行机制。

- 同一 wave 内：维度任务并行执行
- wave 与 wave 之间：根据已有发现重新评估后续路径
- 当前序 wave 暴露出新的关键问题时：后续 wave 可动态调整

这使得系统具备一种更接近真实研究团队的推进方式：先探索、再校准、再加深，而不是一次性静态拆题。

### 执行样例

以“深度分析 Tesla 2026 年竞争格局和挑战”为例：

1. Recon Agent 识别核心业务、主要竞争者、争议焦点与边界问题
2. Planning Agent 将任务拆解为财务表现、产品技术、市场格局、战略风险等维度
3. Controller 视情况向用户确认是否覆盖中国市场、Robotaxi、能源业务等边界
4. Mining Agent 按 wave 并行研究各维度，并产出子报告
5. Review Agent 对每份子报告做可信性和完整性审查
6. Synthesis Agent 综合各维度输出终稿，并显式处理支持关系与潜在冲突
7. Review Agent 对终稿做全局一致性审查
8. CitationManager 完成统一编号、参考文献生成与元数据导出

---

## 数据源接入与检索编排

### 抽象层次

Deep Research 不将 `serper_search`、`fetch_url`、`arxiv_search.py` 视为同一层级能力。

系统中的检索能力被拆分为三个抽象层：

- **Data Source**：信息来自哪里
- **Access Mode**：系统如何访问它
- **Routing Policy**：系统在当前任务中为什么选择它

这意味着系统组织的不是“工具列表”，而是一套面向研究任务的数据源路由体系。

### 数据源分类

| 类别 | 典型对象 | 主要价值 |
|---|---|---|
| `official` | 官网、财报、监管文件、政策文本 | 一次来源、权威边界、制度口径 |
| `news` | 主流媒体、行业媒体、事件报道 | 时效信息、事件线索、外部观察 |
| `academic` | arXiv、Semantic Scholar、PubMed | 学术证据、方法论、前沿研究 |
| `code` | GitHub、Hugging Face、Stack Overflow | 技术实现、生态成熟度、开发者反馈 |
| `social_media` | Reddit、YouTube、微博、知乎、小红书 | 用户感知、社区讨论、实践经验 |
| `forum` | Hacker News、垂直论坛 | 早期讨论、专家意见、社区信号 |
| `analyst` | 行业报告、投研文章 | 结构化观点、市场框架、竞争视角 |
| `review` | 产品测评、用户评测 | 使用体验、横向对比、口碑信号 |

### 接入方式

| 接入方式 | 说明 | 代表能力 |
|---|---|---|
| `Search` | 基于搜索引擎做发现与召回 | `serper_search`、`brave_search`、`tavily_search` |
| `Fetch` | 对已发现页面做正文抓取与原始出处追溯 | `fetch_url` |
| `Site Adapter` | 面向特定平台封装的查询脚本或 Skill | `search-academic`、`search-code`、`search-social-*` |
| `Direct Source` | 直接命中特定权威来源或已知 URL | 官方页面、论文详情页、仓库页 |

### 默认主链

系统默认优先走通用发现链：

```text
serper_search / brave_search / tavily_search
    ↓
候选来源发现
    ↓
fetch_url
    ↓
原始出处追溯与证据提取
```

主链适合覆盖大多数通用研究问题，也是最低耦合、最稳定的默认路径。

### 专业增强层

当主链覆盖不足、用户显式指定来源，或任务天然依赖特定专业语境时，系统会按需调用专业 Skill：

- `search-academic`
- `search-code`
- `search-social-cn`
- `search-social-en`

这些 Skill 的定位不是“默认入口”，而是特定数据源簇的增强型适配层。

### 路由原则

- 通用搜索始终优先
- 专业 Skill 作为增强层按需触发
- 遇到二次引用时优先回溯原始出处
- 社交和社区信号用于补充视角，不替代一次来源
- 特定数据源失败不阻塞主流程，但必须显式记录限制

---

## Trust & Governance

### 治理目标

Deep Research 的终稿可信性并不来自“写得像”，而来自一套可检查、可追踪、可规范化的治理流程。

治理层承担的核心目标包括：

- 保证关键结论与来源之间存在明确映射
- 保证引用格式、编号与别名关系的一致性
- 保证子报告与终稿都经过质量门控
- 保证冲突、不确定性和边界条件被显式暴露

### 引用流转模型

```text
Evidence Mining Agent
    ↓ 写入 [^key]
sub_reports/d*.md
    ↓ 复用同一组 key
report.md
    ↓ CitationManager 统一处理
report.md（编号格式） + citations.json
```

### CitationManager

实现路径：`sensenova_claw/capabilities/deep_research/citation_manager.py`

处理职责：

1. 收集所有脚注定义
2. 统一规范 URL
3. 合并同源引用与别名 key
4. 按终稿首次出现顺序分配编号
5. 将正文中的 `[^key]` 替换为编号引用
6. 生成 `## 参考文献` 与 `citations.json`

### `prepare_report_citations`

参数：

- `report_path`
- `sub_report_paths`

行为：

- 扫描所有子报告与终稿中的脚注定义
- 完成引用映射、编号与正文替换
- 覆写 `report.md`
- 输出 `citations.json`

---

## 研究工件模型

### 目录结构

```text
{workspace}/.sensenova-claw/workdir/deep-research-controller/reports/
└── YYYY-MM-DD-{topic}/
    ├── briefing.md
    ├── plan.json
    ├── sub_reports/
    │   ├── d1.md
    │   ├── d2.md
    │   └── ...
    ├── report.md
    └── citations.json
```

### 工件语义

| 文件 | 语义 |
|---|---|
| `briefing.md` | 问题建模结果，定义问题空间与信息地形 |
| `plan.json` | 研究蓝图，定义维度、深度、依赖、波次和来源类别 |
| `sub_reports/d*.md` | 维度级证据简报，保存事实、判断与引用 |
| `report.md` | 最终研究终稿，在治理前为脚注格式，治理后为统一编号格式 |
| `citations.json` | 引用元数据，支撑后续分析、导出和审计 |

这些工件共同构成了 Deep Research 的研究资产层，使系统天然具备复盘、复用和二次加工能力。

---

## 工程映射

### Skill 结构

```text
~/.sensenova-claw/skills/
├── _search-common/
│   └── search_utils.py
├── search-academic/
│   ├── SKILL.md
│   └── scripts/
├── search-code/
│   ├── SKILL.md
│   └── scripts/
├── search-social-cn/
│   ├── SKILL.md
│   └── scripts/
├── search-social-en/
│   ├── SKILL.md
│   └── scripts/
└── research-union/
    └── SKILL.md
```

### 配置入口

在 `~/.sensenova-claw/config.yml` 中配置基础搜索能力：

```yaml
tools:
  serper_search:
    api_key: ${SERPER_API_KEY}
  brave_search:
    api_key: ${BRAVE_API_KEY}
  tavily_search:
    api_key: ${TAVILY_API_KEY}
```

平台认证通过环境变量配置，例如：

- `ZHIHU_COOKIE`
- `XHS_COOKIE`
- `WEIBO_COOKIE`
- `DOUYIN_COOKIE`
- `TIKHUB_TOKEN`
- `YOUTUBE_API_KEY`
- `GITHUB_TOKEN`

### 关键代码路径

```text
sensenova_claw/
├── capabilities/
│   ├── agents/
│   │   ├── config.py
│   │   └── registry.py
│   ├── deep_research/
│   │   └── citation_manager.py
│   └── tools/
│       ├── citation_tool.py
│       └── send_message_tool.py
├── kernel/
│   └── runtime/
│       └── agent_runtime.py

docs/superpowers/
├── specs/
│   └── 2026-04-08-deep-research-agent-design.md
└── plans/
    └── 2026-04-08-deep-research-agent.md
```

### 关键技术决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 编排方式 | 总控 Agent 驱动 | 支持动态调度与阶段性重规划 |
| 工具策略 | 零新增核心工具 | 复用现有 `send_message`、`ask_user`、`write_file` 能力 |
| 工件模型 | 文件化沉淀 | 便于复核、调试、审计与二次加工 |
| 引用格式 | 脚注 `[^key]` | 便于模型生成，也便于后处理解析 |
| 编号时机 | 终稿统一编号 | 保持子报告独立性，减少中间扰动 |
| 检索扩展 | Skill 化接入 | 与现有能力体系一致，便于逐步演进 |
| 路由策略 | Plan 定类别，Mining 选路径 | 将策略层与执行层解耦 |
| 审查机制 | 双层质量门控 | 同时保证局部可信与全局一致 |
| 并发机制 | Wavefront | 兼顾依赖感知与吞吐效率 |

---

## 总结

Deep Research 的本质，不是一个“更会搜索、更会写报告”的 Agent，而是一套面向复杂问题求解的自治研究系统。

它通过 Cognitive Orchestrator、Agent Fabric、Data Source Routing 和 Trust & Governance 四类核心能力，将研究过程从一次性文本生成提升为一条可编排、可求证、可治理、可沉淀的研究流水线。

最终，系统交付的不是一篇看起来完整的生成文本，而是一份真正具备证据约束、逻辑闭环和工程可复用性的 `Evidence-Backed Research Dossier`。
