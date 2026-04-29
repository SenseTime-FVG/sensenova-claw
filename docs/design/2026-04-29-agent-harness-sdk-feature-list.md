# Agent Harness SDK 功能清单（问题驱动版）

> 立项稿配图。把所有新增功能按"问题 → 解决方案"组织，便于领导一眼看清"为什么要做"。

## 一句话定位

把 Sensenova-Claw 从"一个 Agent 应用"升级为"业务团队都能复用的 Agent Harness SDK + 平台"——跨语言、本地云端同源、不改源码即可扩展。

---

## 6 大问题与解决方案

### 问题 1：业务团队接入要改 Sensenova-Claw 源码

**现状代价**：PR 排队、版本耦合、回归风险大；多团队私下 fork 主仓库，迭代越来越慢。

**解决方案：Plugin 机制**

| 功能 | 解决了什么 |
|---|---|
| Plugin Manifest（YAML 声明） | 业务一份 yaml 自包含所有扩展 |
| Plugin Loader + Registry 抽象 | core 启动时自动加载；不动源码 |
| 8 类 contribution（LLM/Tool/Channel/Skill/Agent/Hook/Command/MCP） | 所有扩展点统一一种声明方式 |

---

### 问题 2：只支持 Python 业务，Go/Node/Rust 团队接不进来

**现状代价**：跨语言团队放弃接入或自己造轮子，平台失去 50%+ 潜在用户。

**解决方案：协议优先 + 多语言瘦客户端**

| 功能 | 解决了什么 |
|---|---|
| Control Protocol（JSON-RPC over stdio/WS） | 一份协议，所有语言都能消费 |
| Python SDK（瘦客户端） | Python 团队 5 分钟跑通 |
| Node.js / Go / Rust SDK | 其他三大语言全覆盖 |
| MCP 三路径（stdio/SSE/HTTP） | 工具任何语言可写，复用业内 MCP 生态 |

---

### 问题 3：多团队混部时相互污染、数据混淆、审计困难

**现状代价**：工具串调风险、跨团队读到对方数据、出事查不清谁干的。

**解决方案：Identity → Visibility → Namespace 三层隔离**

| 功能 | 解决了什么 |
|---|---|
| Identity 三元组（user/team/org） | 全链路身份贯穿 |
| Plugin Visibility（private/internal/public） | 跨团队默认互不可见 |
| Registry Namespace（`team-a/plugin::tool`） | LLM 看到的工具名带前缀，绝不串调 |
| 存储 Namespace（team_id 列 + plugin_kv 表） | 跨团队物理读不到 |
| 多团队混部审计日志 | 每条事件带 plugin_id / team_id |

---

### 问题 4：扩展协议碎片化，工程师学习曲线陡

**现状代价**：tool 是 Python 类、skill 是 Markdown、hook 没有统一形态，每加一类扩展都要改不同地方。

**解决方案：三协议各司其职 + 干预节点统一**

| 功能 | 解决了什么 |
|---|---|
| Hook 子进程协议（任意语言） | 一种协议覆盖审计、脱敏、改写、缓存所有干预场景 |
| Hook 9 个触发点 | OnSession*/OnUserInput/PreLLM/PostLLM/PreTool/PostTool/OnError/OnConfigUpdated |
| Hook Decision 四态（continue/block/mutate/replace） | 单一返回值表达所有干预意图 |
| In-process MCP（Python 快速通道） | 性能体验最佳，业务代码无感 |
| Permission 双向 RPC | 高风险调用前业务方可拦截/改写 |
| Plugin 安全声明（network/fs/env 白名单） | 业务自报 capability，core 强制实施 |

---

### 问题 5：SDK 和云端是两套架构假设，云化时要二次重构

**现状代价**：云端立项被技术债阻塞至少一个季度。

**解决方案：本地与云端同协议、同 Core**

| 功能 | 解决了什么 |
|---|---|
| `sensenova-claw serve` 子命令（stdio/ws/tcp） | 同一个 Core，三种传输 |
| WebSocket 传输 | 远程接入；业务方仅切 URL |
| Cloud Gateway（多租户鉴权/路由/限流/计费） | 商业化所需基础 |
| Core 进程池 + identity 隔离 | 单实例多租户的运行时基础 |
| PostgreSQL Repository | 替换 SQLite，支撑规模化 |
| 数据库迁移工具（幂等可回滚） | 本地数据无损升级到云端 |

---

### 问题 6：缺乏开发者生态与可发现性

**现状代价**：好 plugin 散落各 fork，无人能复用；外部贡献者无入口。

**解决方案：Marketplace + 前端开源 + 文档**

| 功能 | 解决了什么 |
|---|---|
| Plugin Marketplace 服务 | 注册/发现/版本/签名校验，跨 org 公开 |
| 前端开源仓库（Dashboard + sdk-react + ui-kit） | 社区可见、可二开 |
| 三个示例项目（chat/plugin-showcase/multi-agent） | 0→1 上手 |
| 跨语言示例集（Python/Go/Node/Rust/Bash） | 各语言团队"抄作业"即可接入 |
| 统一文档站（API + 教程 + 多语言对照） | 评估、上手、深入有清晰路径 |
| Plugin 热重载 | 开发期体验流畅 |

---

## 核心承诺（一行）

**终端用户视角 100% 兼容**：现有 `sensenova-claw run / cli / version`、前端 Web、所有现有 e2e 完全不变，业务团队和现有用户无感升级（详见 spec §9）。

---

## 关联文档

- 完整设计：[2026-04-27-agent-harness-sdk-design.md](2026-04-27-agent-harness-sdk-design.md)
- 立项 PRD：[2026-04-29-agent-harness-sdk-prd.md](2026-04-29-agent-harness-sdk-prd.md)
- 实现拆分：[2026-04-27-plan-decomposition.md](2026-04-27-plan-decomposition.md)
