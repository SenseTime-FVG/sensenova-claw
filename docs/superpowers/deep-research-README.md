# Deep Research — 深度研究多 Agent 系统

## 概述

Deep Research 是 Sensenova-Claw 平台的深度研究功能，采用多 Agent 协作架构，从用户提交研究 query 到输出带引用的结构化报告全程自动化。支持商业调研、竞品分析、技术深挖、事实核查、学术综述等综合场景。

**核心特点**：

- **LLM 驱动编排**：流程由总控 Agent 自主调度，非硬编码状态机，可根据研究进展动态调整
- **波次并行**：按维度依赖关系分波执行，同一波次内多维度并发研究
- **双层质量审查**：子报告逐篇审查 + 终稿整合审查，审查不通过自动打回修订
- **引用全链路管理**：从子报告脚注到终稿统一编号，自动去重、URL 归一化
- **多源搜索体系**：主链搜索引擎 + 5 类专业领域搜索 Skill，按需调用

---

## 架构总览

### 三层架构

```
┌───────────────────────────────────────────────────────────────┐
│                        用户 Query                              │
│                           │                                    │
│                      ┌────▼─────┐                              │
│                      │  总控Agent │  入口、调度、结果收口        │
│                      └────┬─────┘                              │
│                           │ send_message                       │
│         ┌────────┬────────┼────────┬──────────┐                │
│         ▼        ▼        ▼        ▼          ▼                │
│     Scout    Plan    Research   Review    Report                │
│     Agent    Agent    Agent     Agent     Agent                │
│                                    ▲                           │
│                         │          │                           │
│                    Report Agent ────┘                           │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         工程治理层（透明中间件，Agent 无感知）              │  │
│  │   CitationManager  │  prepare_report_citations 工具       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                    │
│              落盘: report.md + citations.json                   │
└───────────────────────────────────────────────────────────────┘
```

### 层级职责

| 层 | 职责 | 实现方式 |
|---|---|---|
| **Agent 层** | 思考、推理、内容生成、调度决策 | 独立 AgentConfig，通过 `send_message` 委派 |
| **工程治理层** | Citation 标准化/去重/编号 | `CitationManager` + `prepare_report_citations` 工具 |
| **存储层** | 报告和引用落盘 | `write_file` 写入 workspace 报告目录 |

### 设计原则

| 原则 | 说明 |
|---|---|
| 总控 Agent 驱动 | 流程由 LLM 自主决策推进，非 Python 状态机硬编码 |
| 零新增工具 | 完全复用现有 `send_message` / `ask_user` / `write_file` 等 |
| 治理层透明 | CitationManager 自动运作，Agent 无需感知 |
| Skill 扩展来源 | 特定领域搜索通过 Skill 接入，不硬编码到 Agent |

---

## Agent 团队

### 团队总览

```
deep-research-controller (总控)
├── scout-agent        侦察 — 领域地形扫描 + 用户需求澄清
├── plan-agent         规划 — 维度拆解 + 波次编排
├── research-agent     研究 — 按维度搜集证据 + 输出子报告
├── review-agent       审查 — 证据/逻辑/完整性审查
└── report-agent       报告 — 综合子报告生成结构化终稿
```

### 各 Agent 详细说明

#### 1. Deep Research Controller（总控 Agent）

**职责**：
- 接收用户研究需求，依次调度各专家 Agent
- 管理报告目录结构和文件路径（所有路径为绝对路径）
- 分波并行调度 research-agent，控制修订循环
- 调用 `prepare_report_citations` 完成引用后处理
- 只做调度，不做研究

**关键规则**：
- 所有跨 Agent 的文件路径必须使用绝对路径
- 文件由 Agent 自行写入，总控不替代其写入操作
- 传递文件路径而非大段文本
- 异常处理：重试一次，失败则跳过并说明

#### 2. Scout Agent（侦察 Agent）

**职责**：快速侦察研究领域地形，建立领域认知，通过预研和用户澄清为后续规划提供认知基础。

**工作流程**：
1. **意图解析**：从 query 中提取研究对象、研究类型、隐含决策背景
2. **快速扫描**（2-3 轮搜索）：
   - 第 1 轮：核心关键词搜索 → 关键实体、领域结构、术语
   - 第 2 轮：实体与争议搜索 → 关系、核心分歧
   - 第 3 轮（可选）：补盲搜索
3. **用户澄清**：提出 2-5 个针对性问题（研究边界、目标受众、时间焦点、深度期望等）
4. **输出 Research Briefing**，包含：
   - 问题画像（研究类型、确认的约束）
   - 领域地图（关键实体、核心术语、领域阶段、子领域划分）
   - 认知缺口（已有共识、核心争议、信息空白）
   - 信息地形（高价值来源、时效敏感度、获取障碍）

**研究类型适配**：

| 类型 | 侧重点 |
|---|---|
| 学术研究 | 研究脉络、关键论文/作者、方法学派、前沿 |
| 商业调研 | 市场结构、主要玩家、竞争格局、商业模式 |
| 金融投资 | 基本面、估值、关键指标、风险 |
| 医疗健康 | 疾病机制、治疗方案、临床阶段、监管、证据等级 |
| 法律政策 | 监管框架、范围、政策演进、合规 |
| 热点事件 | 时间线、各方立场、影响范围、信息可靠性 |
| 技术评估 | 技术原理、社区、成熟度、应用场景 |
| 人物画像 | 背景、成就、关系网络、公众评价 |

#### 3. Plan Agent（规划 Agent）

**职责**：基于 Research Briefing，拆解研究维度，规划数据源和执行顺序。

**工作流程**：
1. **确定研究策略**：根据研究类型选择总体策略
2. **维度拆解**（3-7 个维度）：
   - 可用维度类型：`topic`, `entity_comparison`, `timeline`, `perspective`, `cause_chain`, `evidence_types`, `geography`, `value_chain`, `depth_layers`, `process_stages`
   - 流程：识别相关维度 → 选择主维度 → 设计切片 → 验证覆盖 → 验证可行性
3. **来源类别匹配**（指定类别而非具体工具）：
   - `official` / `news` / `social_media` / `github` / `academic` / `forum` / `analyst` / `review`
4. **波次编排**：按维度依赖关系分波，无依赖的维度同一波并行
5. **深度分配**：
   - `skim`：可靠来源 + 关键结论
   - `moderate`：主要来源覆盖，关键数据核实
   - `thorough`：多源交叉验证，对立观点，详细数据

**输出格式**（严格 JSON）：
```json
{
  "strategy": {
    "relevant_dimensions": ["by_topic", "by_entity"],
    "primary_dimension": "by_topic",
    "rationale": "..."
  },
  "dimensions": [
    {
      "id": "d1",
      "name": "维度名称",
      "description": "该维度回答什么问题",
      "key_questions": ["问题1", "问题2"],
      "focus": "方向性证据指引",
      "context_from_briefing": "Briefing 中的已知背景",
      "sources": [
        {"category": "official", "description": "具体来源说明"}
      ],
      "depth": "thorough",
      "wave": 1,
      "depends_on": []
    }
  ]
}
```

#### 4. Research Agent（研究 Agent）

**职责**：按指定维度搜集证据，输出带引用的子报告。

**工作流程**：
1. **搜索策略规划**：将 key_questions 拆解为可搜索的子问题，设计多角度搜索（正反面证据、不同信息主体、中英文）
2. **搜索-评估循环**：
   - 来源层级：一次来源（原始数据/论文/财报）> 二次来源（媒体/分析）> 三次来源（摘要/聚合）
   - 信息类型区分：事实 / 观点 / 推断
   - 线索追踪：发现原始报告/数据源引用时，用 `fetch_url` 追溯原始出处
   - 停止条件根据深度要求而定（`skim` 可靠来源 / `moderate` 完整回答 / `thorough`  独立来源交叉验证）
3. **子报告写入**：使用脚注引用格式

**子报告引用格式**：
```markdown
## 关键问题回答

某个有证据支撑的数据点 [^citation_key]。进一步分析 [^another_key]。

## 额外发现
{超出 key_questions 但可能重要的发现}

[^citation_key]: [来源标题](URL)
[^another_key]: [来源标题](URL)
```

citation_key 命名规则：`{来源缩写}_{主题关键词}_{年份}`，全小写下划线连接。

#### 5. Review Agent（审查 Agent）

**职责**：审查子报告和终稿的证据充分性、来源冲突和逻辑问题。

**审查维度**：

| 类别 | 审查点 |
|---|---|
| **A. 证据审查** | 充分性（每个结论有来源）、质量（来源层级/偏见/时效）、真实性（抽查引用可访问且准确） |
| **B. 逻辑审查** | 逻辑跳跃、选择性证据、因果混淆、过度推断 |
| **C. 完整性审查**（子报告） | 问题覆盖与深度、多视角、不确定性标注 |
| **D. 整合审查**（终稿） | 跨维度一致性、叙事流畅、综合结论是否有支撑、是否回答原始问题 |

**输出格式**：
```
## 审查结论
VERDICT: pass / revise

## 问题清单
### 🔴 硬伤 (必须修复)
1. [位置] 问题 → 修复建议

### 🟡 改进建议 (建议修复)
1. [位置] 建议 → 修复方向

## 审查说明
{整体质量评估和判断理由}
```

**判定规则**：存在任何 🔴 硬伤 → `revise`；仅有 🟡 建议 → `pass`。

#### 6. Report Agent（报告 Agent）

**职责**：综合所有子报告，生成结构化研究终稿。

**工作要求**：
- **综合而非拼接**：整合发现，跨维度交叉引用，避免重复
- **引用纪律**：复用子报告的 `[^key]` 脚注格式和原有 citation_key，不引入子报告之外的新事实
- **矛盾处理**：发现跨维度矛盾时必须讨论，不隐藏
- **深度适配**：overview → 简洁结论导向；deep_analysis → 均衡；expert_level → 详尽
- 不写 `## 参考文献` 章节（由引用后处理自动生成）

---

## 执行流程

### 完整流程图

```
用户 Query
    │
    ▼
┌──────────────────┐
│  Stage 1: 侦察    │  scout-agent
│  领域扫描 + 澄清   │  → briefing.md
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Stage 2: 规划    │  plan-agent
│  维度拆解 + 波次   │  → plan.json
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Stage 3: 确认    │  ask_user（可选）
│  用户审批研究方案   │
└────────┬─────────┘
         ▼
┌──────────────────────────────────────┐
│  Stage 4: 分波研究 + 审查              │
│                                       │
│  Wave 1:  research-agent × N (并行)   │
│           → sub_reports/d1.md ...      │
│           review-agent × N (并行)      │
│           → pass / revise (最多重试2次) │
│                                       │
│  Wave 间回顾: 评估已有发现，调整后续波次  │
│                                       │
│  Wave 2:  research-agent × M (并行)   │
│           → sub_reports/dN.md ...      │
│           review-agent × M (并行)      │
│           ...                         │
└────────┬─────────────────────────────┘
         ▼
┌──────────────────┐
│  Stage 5: 生成终稿 │  report-agent
│  综合子报告        │  → report.md
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Stage 6: 终稿审查 │  review-agent
│  整合质量检查      │  → pass / revise
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Stage 7: 引用处理 │  prepare_report_citations
│  脚注→编号+参考文献 │  → report.md (覆写) + citations.json
└──────────────────┘
```

### 执行示例

**用户输入**：*"深度分析 Tesla 2026 年竞争格局和挑战"*

1. **侦察**：scout-agent 快速搜索 2-3 轮，了解 Tesla 当前状况、主要竞争对手、行业趋势；向用户确认研究边界（是否包含中国市场？聚焦哪些业务线？）；输出 `briefing.md`
2. **规划**：plan-agent 读取 briefing，拆解为 4 个维度 —— d1: 财务与经营、d2: 产品与技术、d3: 市场地位、d4: 竞争威胁；规划为 2 波执行，输出 `plan.json`
3. **确认**：总控向用户展示研究方案，用户确认或调整
4. **Wave 1 研究**：4 个 research-agent 并行研究 d1-d4，各自输出子报告 → 4 个 review-agent 并行审查 → 通过/打回修订
5. **波间回顾**：总控评估 Wave 1 成果，判断是否需要补充维度或调整后续波次
6. **终稿生成**：report-agent 读取所有子报告，交叉引用发现，生成结构化终稿
7. **终稿审查**：review-agent 检查跨维度一致性、叙事逻辑、结论是否有证据支撑
8. **引用处理**：`prepare_report_citations` 汇总所有脚注，统一编号 `[1]` `[2]` ...，生成参考文献列表

---

## 报告目录结构

```
{workspace}/.sensenova-claw/workdir/deep-research-controller/reports/
└── YYYY-MM-DD-{topic}/
    ├── briefing.md          # Scout Agent 的 Research Briefing
    ├── plan.json            # Plan Agent 的研究计划
    ├── sub_reports/
    │   ├── d1.md            # 维度 1 子报告（脚注引用格式）
    │   ├── d2.md            # 维度 2 子报告
    │   └── ...
    ├── report.md            # 终稿（经引用处理后，[N] 编号 + 参考文献）
    └── citations.json       # 引用元数据
```

---

## 引用管理系统

### 引用流转

```
子报告写入阶段                    终稿写入阶段                    后处理阶段
research-agent                  report-agent                  CitationManager
    │                               │                              │
    │  [^reuters_tesla_q4]          │  复用相同 [^key]              │  收集所有 [^key] 定义
    │  [^bloomberg_ev_2026]         │  不引入新事实                  │  URL 归一化去重
    │                               │                              │  按出现顺序编号 [1][2]...
    ▼                               ▼                              ▼
  d1.md (脚注格式)               report.md (脚注格式)           report.md (编号格式)
                                                               citations.json
```

### CitationManager 核心逻辑

**实现路径**：`sensenova_claw/capabilities/deep_research/citation_manager.py`

1. **收集定义**：解析所有 `[^key]: [title](url)` 脚注定义
2. **URL 归一化**：scheme/host 小写、去尾部斜杠，相同 URL 合并为同一引用
3. **统一编号**：按首次出现顺序分配 `[1]`, `[2]`, ...，多个 key 指向同一 URL 共享编号
4. **替换**：正文中 `[^key]` → `[N]`，移除脚注定义，追加 `## 参考文献` 列表
5. **导出**：生成 `citations.json`，保留 key/url/title/alias_keys 元数据

### prepare_report_citations 工具

**参数**：
- `report_path`：终稿绝对路径
- `sub_report_paths`：所有子报告绝对路径列表

**执行**：扫描所有子报告 + 终稿的脚注定义 → 处理终稿 → 覆写 report.md → 生成 citations.json

---

## 搜索体系

### 主链搜索

Agent 直接调用的搜索工具，为所有研究的默认首选：

| 工具 | 说明 |
|---|---|
| `serper_search` | Google SERP 搜索（主力） |
| `brave_search` | Brave 搜索引擎 |
| `tavily_search` | Tavily AI 搜索 |
| `fetch_url` | 网页深度抓取 |
| `image_search` | 图片搜索 |

### 专业领域 Skill（补充来源）

仅在主链搜索不足时按需调用，非默认使用：

#### search-academic — 学术搜索

| 脚本 | 来源 | 特点 |
|---|---|---|
| `arxiv_search.py` | arXiv | 30+ 学科分类，按领域/作者筛选 |
| `semantic_scholar_search.py` | Semantic Scholar | 全学科论文，引用影响力指标 |
| `pubmed_search.py` | PubMed | 生物医学文献，结构化摘要 |
| `wikipedia_search.py` | Wikipedia | 多语言百科 |

#### search-code — 开发者搜索

| 脚本 | 来源 | 特点 |
|---|---|---|
| `github_search.py` | GitHub | 仓库/代码/Issue 搜索 |
| `stackoverflow_search.py` | Stack Overflow | 技术问答，按标签/投票筛选 |
| `hackernews_search.py` | Hacker News | 技术新闻与讨论 |
| `huggingface_search.py` | HuggingFace | 模型/数据集/Spaces |

#### search-social-cn — 中文社交平台

| 脚本 | 来源 | 需要认证 |
|---|---|---|
| `bilibili_search.py` | B站 | 可选 Cookie |
| `zhihu_search.py` | 知乎 | 需要 ZHIHU_COOKIE |
| `xiaohongshu_search.py` | 小红书 | 需要 XHS_COOKIE |
| `weibo_search.py` | 微博 | 需要 WEIBO_COOKIE |
| `douyin_search.py` | 抖音 | 需要 DOUYIN_COOKIE |

> 注：中文社交平台无稳定公开 API，稳定性中等偏低。

#### search-social-en — 英文社交平台

| 脚本 | 来源 | 需要认证 |
|---|---|---|
| `reddit_search.py` | Reddit | 无需认证 |
| `twitter_search.py` | Twitter/X | 需要 TIKHUB_TOKEN |
| `youtube_search.py` | YouTube | 需要 YOUTUBE_API_KEY |


### Skill 调用策略

- 主链搜索（`serper_search` + `fetch_url`）**始终优先**
- Skill 仅在以下情况使用：
  - 主链对某子问题搜索结果不足（0 个有效来源）
  - 用户明确要求特定来源
  - 特定领域主链覆盖弱（如中文社区讨论、学术论文、代码仓库）
- Skill 调用失败不阻塞主流程，报告中说明限制即可

---

### send_message 工具

Deep Research 的 Agent 间通信完全基于 `send_message` 工具：

**单目标模式**：
```python
send_message(target_agent="plan-agent", message="...", mode="sync")
```

**多目标并行模式**（同一波次研究使用）：
```python
send_message(targets=[
    {"target_agent": "research-agent", "message": "维度 1 任务..."},
    {"target_agent": "research-agent", "message": "维度 2 任务..."},
    {"target_agent": "research-agent", "message": "维度 3 任务..."},
])
```

### 委派权限

| Agent | 可委派给 | 说明 |
|---|---|---|
| deep-research-controller | scout, plan, research, review, report | 全权调度 |
| scout-agent | 无 | 只做侦察 |
| plan-agent | 无 | 只做规划 |
| research-agent | 无 | 只做研究 |
| review-agent | 无 | 只做审查 |
| report-agent | 无 | 只做报告 |

### 文件共享协议

- 每个 Agent 有独立的工作目录
- 总控通过绝对路径指定输出位置
- 子 Agent 将结果写入总控指定的路径
- 总控通过 `read_file` 验证写入完成后，传递文件路径给下一个 Agent


### Skill 配置文件位置

```
~/.sensenova-claw/skills/
├── _search-common/          # 搜索通用工具库
│   └── search_utils.py
├── search-academic/         # 学术搜索
│   ├── SKILL.md
│   └── scripts/
├── search-code/             # 代码/开发者搜索
│   ├── SKILL.md
│   └── scripts/
├── search-social-cn/        # 中文社交搜索
│   ├── SKILL.md
│   └── scripts/
├── search-social-en/        # 英文社交搜索
│   ├── SKILL.md
│   └── scripts/
└── research-union/          # 一体化研究流程
    └── SKILL.md
```

### 搜索 API Key 配置

在 `~/.sensenova-claw/config.yml` 中配置：

```yaml
tools:
  serper_search:
    api_key: ${SERPER_API_KEY}     # Google SERP（主力搜索）
  brave_search:
    api_key: ${BRAVE_API_KEY}      # Brave 搜索
  tavily_search:
    api_key: ${TAVILY_API_KEY}     # Tavily 搜索
```

社交平台 Cookie 通过环境变量配置：`ZHIHU_COOKIE`, `XHS_COOKIE`, `WEIBO_COOKIE`, `DOUYIN_COOKIE`, `TIKHUB_TOKEN`, `YOUTUBE_API_KEY`, `GITHUB_TOKEN`。

---

## 关键代码路径

```
sensenova_claw/
├── capabilities/
│   ├── agents/
│   │   ├── config.py              # AgentConfig 数据类
│   │   └── registry.py            # AgentRegistry — Agent 发现、注册、运行时更新
│   ├── deep_research/
│   │   └── citation_manager.py    # CitationManager — 引用收集/去重/编号
│   └── tools/
│       ├── citation_tool.py       # prepare_report_citations 工具
│       └── send_message_tool.py   # send_message 工具（单目标/多目标并行）
├── kernel/
│   └── runtime/
│       └── agent_runtime.py       # AgentRuntime — 会话管理、Worker 工厂

docs/superpowers/
├── specs/
│   └── 2026-04-08-deep-research-agent-design.md   # 设计规格文档
└── plans/
    └── 2026-04-08-deep-research-agent.md          # 实现计划文档
```

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 编排方式 | LLM 驱动总控 | 灵活，动态调整无需改代码 |
| 新增工具 | 零（复用现有） | 降低复杂度，`send_message` + `write_file` 已足够 |
| 引用格式 | 脚注 `[^key]` | LLM 自然生成，解析无歧义 |
| 引用编号时机 | 终稿后处理统一编号 | 保持子报告独立性，Report Agent 只管综合 |
| 引用存储 | 内存 dict + 最终 JSON | 10-50 条引用无需数据库 |
| 搜索扩展 | 通过 Skill | 灵活，与现有 Skill 体系一致 |
| 来源规划 | Plan 指定类别，Research 选工具 | 策略与执行分离，Research 思维更自由 |
| 审查策略 | 双层（子报告 + 终稿） | 更严格的质量控制 |
| 并发模式 | 波次并行 | 感知依赖关系，最大化并行效率 |
