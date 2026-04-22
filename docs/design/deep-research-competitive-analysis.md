# Deep Research 产品竞品分析

> 更新时间：2026-04-15  
> 说明：本文基于公开资料整理，优先使用官方产品页、官方博客、帮助中心、定价页与官方 GitHub 仓库。deep research 相关功能、套餐和可用地区变化较快，阅读时请结合文末来源二次确认。

## 1. 一句话结论

deep research 正在从“聊天产品里的高级模式”演进成一层独立能力栈。闭源产品的竞争重点已经从“会不会搜”转向“能否同时接公网与私域数据、能否长任务稳定执行、能否产出可复核的工作成果”；开源产品的竞争重点则从“能不能跑”转向“能否低成本自建、可控接入企业数据、方便扩展工具和评测”。

如果只看当前成熟度：

- 闭源参考标杆是 `OpenAI ChatGPT Deep Research`，综合完成度最高。
- 速度和“搜索产品基因”最强的是 `Perplexity Deep Research`。
- 公私域混合研究能力最激进的是 `Gemini Deep Research`。
- 企业工作流贴合度最强的是 `Claude Research` 和 `Microsoft 365 Copilot Researcher`。
- 企业级深度研究专用定位最明确的是 `You.com ARI`。
- 开源里最适合做产品化底座的不是单一项目，而是三类路线：
  - 通用编排底座：`LangChain Open Deep Research`
  - 成熟研究应用：`GPT Researcher`
  - 企业私域增强：`DeepSearcher`

## 2. 什么才算 deep research 产品

我把 deep research 产品定义成同时具备下面 5 个特征的系统：

1. 能把一个复杂问题拆成多步研究计划，而不是只做一次搜索问答。
2. 能在执行中持续检索、阅读、归纳、修正路线，而不是一次性生成答案。
3. 能输出“可交付成果”，例如多页报告、表格、PDF、Slides、可追溯引用。
4. 能处理长时任务，用户不必一直盯着界面。
5. 至少部分支持证据可追溯，用户能看到来源、引用或中间计划。

基于这个定义，赛道可以粗分成三类：

| 类别 | 代表产品 | 核心价值 |
| --- | --- | --- |
| 消费级研究助手 | OpenAI、Gemini、Perplexity、Claude | 帮个人用户或轻团队快速生成研究报告 |
| 企业级研究代理 | Microsoft Researcher、You.com ARI | 把企业内部数据和公网信息合并，生成可直接用于工作的成果 |
| 开源研究框架/应用 | Open Deep Research、GPT Researcher、DeepSearcher | 让团队自建、私有化、定制化 deep research 能力 |

## 3. 市场格局判断

### 3.1 当前赛道已经进入“标配化”

从 2025 年到 2026 年，OpenAI、Google、Anthropic、Perplexity、Microsoft 都已经把 deep research 从试验能力推进到了主产品线或主工作流里。这说明 deep research 不再只是“一个炫技 demo”，而是会成为下一代 AI 助手的标准能力层。

### 3.2 差异化重点正在转移

现在真正拉开差距的点已经不是“能不能搜几百个网页”，而是：

- 能不能同时接入外部网页、企业知识库、邮件、网盘、IM、MCP 工具。
- 能不能让研究过程可中断、可继续、可审计。
- 能不能把结果做成工作产物，而不只是长文本。
- 能不能控制成本、权限、可信来源与合规边界。

### 3.3 开源与闭源的护城河不同

- 闭源产品的护城河主要在模型能力、产品体验、数据接入广度、默认可用性。
- 开源产品的护城河主要在部署可控、可改造、可与企业系统深度集成。

## 4. 闭源竞品分析

### 4.1 主竞品矩阵

| 产品 | 当前定位 | 关键能力 | 商业化与接入 | 优势 | 短板 |
| --- | --- | --- | --- | --- | --- |
| OpenAI ChatGPT Deep Research | 通用型研究代理标杆 | 多步互联网研究、文件上传、引用、长任务执行；2026-02-10 更新后支持任意 MCP 或 app 连接、可信站点限制、实时进度和中断续调 | 当前已进入 ChatGPT 多档套餐；Free 为 limited，Plus/Pro/Business/Enterprise 提供更高层级 deep research 与 internal tools/app 接入 | 产品完成度高，报告形态成熟，生态连接能力最强 | 企业私域深度仍依赖连接器生态，价格与配额策略变化较快 |
| Gemini Deep Research | 强搜索基因的公私域研究助手 | 可基于网页、Gmail、Drive、Chat 做研究；支持研究计划展示、Canvas 二次加工、Audio Overview；Ultra 支持更丰富视觉化 | 官方页面显示可免费试用；Google AI Plus/Pro/Ultra 提升模型与额度，当前公开价分别约 `$7.99/$19.99/$249.99` 每月 | 谷歌搜索与 Workspace 天然联动，信息源广且适合知识工作 | 私域接入体验与 Workspace 绑定更深，对非 Google 生态企业吸引力有限 |
| Perplexity Deep Research | 搜索即研究的高速产品 | 数十次搜索、读取数百来源、2-4 分钟内生成报告；默认引用强；免费用户也可用，Pro 有更高容量 | 官方帮助中心可见 Pro `$20/月` 起，另有 Max/Enterprise；连接器能力正向企业扩展 | 速度快，搜索产品心智强，公开信息研究体验优秀 | 更像“搜索增强研究”而非企业知识工作台，私域深度和流程治理弱于企业型产品 |
| Claude Research | 面向知识工作者的研究协作模式 | 多轮 agentic search、网页搜索、Google Workspace 上下文、内联引用；2025-04-15 首发时为 beta，当前价格页已把 Research 列入 Pro/Max/Team 能力 | Pro `$20/月`、Max `$100/月` 起；Team/Enterprise 继续向组织扩展 | 和知识工作流贴合度高，叙述质量、资料组织、企业文档协作体验强 | 公开信息搜索广度与默认互联网产品体验不一定领先 OpenAI/Perplexity |
| Microsoft 365 Copilot Researcher | 企业内知识 + 外部信息的工作研究代理 | 与邮件、会议、文件、聊天等工作数据融合；Researcher 负责多步研究，Analyst 负责 Python 数据分析 | 需要 Microsoft 365 Copilot 许可；Researcher 于 2025-06-02 GA，当前页面显示可在 Copilot 许可中使用，含每月合并查询额度 | 企业治理、权限、工作数据接入、组织部署能力强 | 更偏企业已有 Microsoft 生态客户，消费级用户和轻团队门槛高 |
| You.com ARI | 企业级专业研究代理 | 2025-02 beta 时可分析 400+ sources、5 分钟内生成专业报告；后续公开材料提升到 500+ sources 与 polished PDF；强调企业私有数据融合 | 更偏 Max/Enterprise 与定制化销售；同时有面向开发者的 Research API | 企业研究定位非常明确，适合咨询、市场、金融等深研究场景 | 普通消费者心智弱于主流大模型助手，生态与默认使用路径不如 ChatGPT/Gemini 普及 |

### 4.2 逐家点评

#### OpenAI ChatGPT Deep Research

OpenAI 目前最像“deep research 标准答案”。它的优势不是单点能力最夸张，而是整体链路最完整：`提问 -> 计划 -> 长任务执行 -> 报告输出 -> 引用 -> 连接器/MCP -> 后续追问` 基本打通了。  
如果你的目标是做一个“通用 deep research 产品”，OpenAI 最值得对标的不是模型，而是它把 deep research 从单独模式逐步并入 agent mode、internal tools、apps/MCP 的产品路线。

#### Gemini Deep Research

Gemini 的差异化非常清楚：把 deep research 从纯公网研究扩展成“公网 + Workspace 私域”的混合研究，而且还强调把结果转成 Canvas、Audio Overview、交互式内容。  
如果你的产品未来想做企业知识工作台，Gemini 非常值得参考，尤其是“研究之后还要继续加工”的后链路。

#### Perplexity Deep Research

Perplexity 最大优势仍然是“搜索产品化能力”。它没有把自己做成一个过重的办公工作台，而是把 deep research 做成搜索范式的自然延伸：更快、更清楚、更强调引用和网页事实。  
如果你的目标是用户增长和搜索替代，Perplexity 路线会比企业重工作流更有参考价值。

#### Claude Research

Claude Research 的优势不是“能搜更多网页”，而是“把研究变成知识工作的一部分”。和 Google 一样，它在主动把私域上下文纳入 deep research，但表达方式更偏“工作协作伙伴”而不是“搜索助手”。  
对 B 端产品来说，Claude 路线说明一个趋势：未来 deep research 一定会与日历、邮件、文档、组织知识结合，而不是长期停留在公网问答。

#### Microsoft 365 Copilot Researcher

Microsoft 的 Researcher 本质上是把 deep research 做成“企业 reasoning agent 组件”。它和 Analyst 组合后，形成了 `研究 + 数据分析` 的双代理结构，这比单纯报告生成更接近真实办公任务。  
如果你的目标客户是企业，Microsoft 证明了一个关键点：企业愿意为 deep research 付费的前提，不是“更聪明”，而是“接组织数据、带治理、能落进既有工作流”。

#### You.com ARI

ARI 的公开定位一直很明确：不是大众聊天入口，而是专业研究代理。它强调处理更多 sources、更正式的 PDF 报告、更强的企业数据集成能力。  
如果你的目标不是做“所有人都能聊”的产品，而是做面向分析师、研究员、咨询团队的高价值工具，ARI 的定位非常值得研究。

### 4.3 闭源侧的共同趋势

- 都在把研究范围从开放网页扩到私域数据。
- 都在从“答案”转向“工作成果”，例如报告、图表、音频、演示稿。
- 都在强化长任务和异步执行。
- 都在补连接器、MCP、组织级治理能力。

## 5. 开源竞品分析

### 5.1 主竞品矩阵

> GitHub Star 为抓取时快照，仅用于判断社区热度，不建议作为唯一决策依据。

| 项目 | GitHub / 协议 / 热度 | 定位 | 关键能力 | 适合场景 | 主要不足 |
| --- | --- | --- | --- | --- | --- |
| LangChain `open_deep_research` | MIT，约 `11.1k` stars | 通用开源 deep research 底座 | 支持多模型、多搜索工具、MCP server；默认 Tavily，可接 OpenAI/Anthropic 原生 web search；可用 LangGraph Studio 直接调试 | 想快速搭可配置研究代理原型或二次开发平台 | 更偏框架模板，产品层体验和企业权限治理需要自己补 |
| `GPT Researcher` | Apache-2.0，约 `26.5k` stars | 最成熟的开源 deep research 应用之一 | 支持多 LLM provider、MCP、递归式 deep research、报告生成、文档导出与较完整文档站 | 想直接落一个可用研究产品，或把研究能力嵌进现有系统 | 默认形态偏单人研究助手，复杂组织治理需二次建设 |
| ByteDance `DeerFlow` | MIT，约 `61.6k` stars | 从 deep research 扩展到 super agent harness | 多代理、sandbox、memory、skills、subagents、MCP server；能研究、编码、内容创作 | 想做“研究 + 执行 + 产物”的综合型 agent 平台 | 范围更广，若只做纯研究，系统复杂度偏高 |
| Alibaba `Tongyi DeepResearch` | Apache-2.0，约 `18.7k` stars | 模型驱动的开源 deep research 代理家族 | 提供 deep research agent 家族、论文与模型体系，研究积累深 | 想参考前沿研究路线、强化长程 web agent 能力 | 更偏研究与模型路线，产品落地和工程整合门槛较高 |
| Zilliz `DeepSearcher` | 开源，约 `7.8k` stars | 私域数据增强的 deep research 替代方案 | 面向 private data；结合 LLM + vector DB；支持 Milvus/Zilliz Cloud/Qdrant 等 | 企业知识库、内网研究、RAG + deep research 混合场景 | 公网页面研究与完整产品体验不如专门的通用研究助手 |
| LangChain `local-deep-researcher` | MIT，约 `9k` stars | 完全本地化 deep research | 基于 Ollama / LMStudio，本地执行搜索总结反思循环并产出 markdown 报告 | 强隐私、本地部署、低外部依赖场景 | 本地模型质量与速度受限，默认能力上限通常低于闭源云产品 |

### 5.2 开源侧分层

开源赛道其实不是一个层次：

| 层次 | 代表项目 | 价值 |
| --- | --- | --- |
| 研究产品模板 | GPT Researcher、open_deep_research | 快速得到一个能跑、能改的 deep research 系统 |
| 平台型 super agent | DeerFlow | 不止研究，还能继续编码、制作内容、串联多代理 |
| 私域知识增强 | DeepSearcher | 让 deep research 更适合企业内部知识体系 |
| 本地化/隐私优先 | local-deep-researcher | 降低对外部云服务依赖 |
| 学术/模型路线 | Tongyi DeepResearch | 更适合作为方法论和模型能力参考 |

### 5.3 开源与闭源的本质差别

闭源产品赢在“默认体验”，开源产品赢在“可控性”。  
如果你要服务的是标准化用户，闭源产品通常更强；如果你要服务的是企业、垂直行业、特殊数据环境，开源底座更有价值。

## 6. 闭源与开源的能力拆解对比

| 维度 | 闭源主流产品 | 开源主流项目 | 结论 |
| --- | --- | --- | --- |
| 默认效果 | 高 | 中 | 闭源即开即用优势明显 |
| 结果稳定性 | 高 | 中 | 闭源在模型、搜索、产品链路联调上更成熟 |
| 私域集成 | 中到高 | 高 | 开源更容易接企业自有系统，但需要工程投入 |
| 连接器/MCP | 正快速补齐 | 高 | 开源更开放，闭源在补生态 |
| 审计与治理 | 企业版较强 | 取决于自建 | 企业级落地时，自建方案反而更可控 |
| 成本结构 | 订阅或 seat 制 | 工程成本 + 模型/搜索成本 | 开源不一定便宜，但更可控 |
| 本地部署 | 弱 | 强 | 涉及隐私和合规时，开源明显占优 |
| 产物体验 | 强 | 中 | 闭源更擅长 polished report/UI |

## 7. 相邻赛道：哪些产品相关但不该直接混为一谈

下面这些产品和 deep research 高度相关，但更准确地说，它们是“执行型超代理”而不是“报告型研究代理”：

- `Manus Wide Research`
  - 核心卖点是把大规模研究拆成并行子任务，由大量子代理同时处理。
  - 更适合“研究 100 个对象、整理成结构化结果”这类宽任务。
- `Genspark Super Agent`
  - 核心卖点是一条 prompt 覆盖 research、content、data analysis、phone calls、emails、MCP integrations 等复杂流程。
  - 本质上是超代理工作台，而不是纯 deep research 报告器。

这类产品值得关注，因为它们代表了 deep research 的下一步演化方向：研究能力最终会变成“更大 agent 操作系统”的一个子模块。

## 8. 关键趋势与机会点

### 8.1 真正的竞争点是“数据接入”

2026 年最重要的变化不是谁能搜更多网页，而是谁能更好地统一：

- 公网网页
- 企业知识库
- 邮件/IM/文档
- 文件上传
- MCP / SaaS / API 工具

### 8.2 真正的产品壁垒是“研究过程可治理”

企业越来越在意：

- 研究过程能否回放
- 来源能否白名单限制
- 中间步骤能否人工纠偏
- 是否有配额、权限、审计日志

### 8.3 输出形态正在从“长答案”升级为“工作成品”

领先产品都在朝这些方向走：

- 报告
- PDF
- 表格
- 图表
- Slides
- Audio overview
- 可继续编辑的 workspace / canvas

### 8.4 纯 deep research 产品会被更大的 agent 平台吸收

从 OpenAI 的 agent mode、Gemini 的 Agent 化、Microsoft 的 reasoning agents、DeerFlow/Manus/Genspark 的超代理路径来看，deep research 很可能不会长期作为孤立功能存在，而会成为上层 agent 平台的一个标准工作模式。

## 9. 对我们做产品的启示

如果要做自己的 deep research 能力，我建议优先做下面 7 件事，而不是一开始卷“更强模型”：

1. `研究计划可见且可编辑`
   让用户能在开始前修改计划，减少长任务跑偏。
2. `公私域统一检索`
   至少打通网页、文件、知识库、MCP/内部工具四类来源。
3. `可信来源治理`
   支持站点白名单、来源优先级、引用去重、证据追踪。
4. `长任务编排`
   支持暂停、恢复、中断追问、失败重试、进度展示。
5. `工作产物输出`
   不止生成 markdown 长文，还要能落成表格、PPT、PDF、摘要版。
6. `评测与回放`
   建立问题集、来源命中率、引用完整性、任务耗时、人工偏好评测。
7. `企业权限与日志`
   deep research 一旦接内部数据，权限和审计会比“回答质量”更重要。

## 10. 建议的对标优先级

如果我们后续要持续跟踪，我建议重点盯这 6 个对象：

| 优先级 | 对象 | 原因 |
| --- | --- | --- |
| P0 | OpenAI Deep Research | 综合完成度最高，是最强基线 |
| P0 | Gemini Deep Research | 公私域融合路径最激进 |
| P0 | Microsoft Researcher | 企业治理与工作流价值最高 |
| P1 | Perplexity Deep Research | 搜索产品化速度最快 |
| P1 | Claude Research | 知识工作协作体验强 |
| P1 | GPT Researcher / Open Deep Research | 开源实现最值得拆解 |

## 11. 参考资料

### 闭源产品

- OpenAI Introducing deep research  
  https://openai.com/index/introducing-deep-research/
- OpenAI Deep research FAQ  
  https://help.openai.com/en/articles/10500283-deep-research-faq
- OpenAI ChatGPT Pricing  
  https://chatgpt.com/pricing
- Gemini Deep Research overview  
  https://gemini.google/overview/deep-research/
- Gemini Help: Use Deep Research in Gemini Apps  
  https://support.google.com/gemini/answer/15719111
- Gemini subscriptions  
  https://gemini.google/subscriptions/
- Perplexity blog: Introducing Perplexity Deep Research  
  https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research
- Perplexity Help: What is Perplexity Pro  
  https://www.perplexity.ai/help-center/en/articles/10352901-what-is-perplexity-pro
- Perplexity Help: Using the Connector for Slack  
  https://www.perplexity.ai/help-center/en/articles/12167980-using-the-connector-for-slack
- Anthropic blog: Claude takes research to new places  
  https://claude.com/blog/research
- Anthropic pricing  
  https://claude.com/pricing
- Microsoft blog: Introducing Researcher and Analyst in Microsoft 365 Copilot  
  https://www.microsoft.com/en-us/microsoft-365/blog/2025/03/25/introducing-researcher-and-analyst-in-microsoft-365-copilot/
- Microsoft blog: Researcher and Analyst are now generally available  
  https://www.microsoft.com/en-us/microsoft-365/blog/2025/06/02/researcher-and-analyst-are-now-generally-available-in-microsoft-365-copilot/
- Microsoft 365 Copilot pricing  
  https://www.microsoft.com/en-us/microsoft-365-copilot/pricing
- You.com ARI launch  
  https://you.com/resources/introducing-ari-the-first-professional-grade-research-agent-for-business
- You.com ARI product page  
  https://you.com/ari
- You.com platform upgrade / feature comparison  
  https://you.com/platform/upgrade
- You.com API pricing  
  https://you.com/pricing

### 开源项目

- LangChain Open Deep Research  
  https://github.com/langchain-ai/open_deep_research
- GPT Researcher  
  https://github.com/assafelovic/gpt-researcher
- ByteDance DeerFlow  
  https://github.com/bytedance/deer-flow
- Alibaba Tongyi DeepResearch  
  https://github.com/Alibaba-NLP/DeepResearch
- Zilliz DeepSearcher  
  https://github.com/zilliztech/deep-searcher
- LangChain Local Deep Researcher  
  https://github.com/langchain-ai/local-deep-researcher

### 相邻赛道

- Manus Wide Research  
  https://manus.im/docs/features/wide-research
- Manus Help: What is Wide Research  
  https://help.manus.im/en/articles/11960169-what-is-wide-research
- Genspark Help Center / Super Agent  
  https://www.genspark.ai/helpcenter
