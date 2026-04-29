# Agent Harness SDK 功能清单

> 立项稿配图，仅列**新增**功能，不分排期。简化版，便于领导评审。
> 完整版（80 项细化）见 git 历史；本表为 30 项主功能。

## 一句话定位

把 Sensenova-Claw 从"一个 Agent 应用"升级为"业务团队都能复用的 Agent Harness SDK + 平台"，跨语言、本地云端同源、不改源码即可扩展。

---

## 新增功能总表

| # | 功能 | 业务价值（一句话） |
|---|---|---|
| 1 | **Plugin Manifest 机制** | 业务团队用一份 YAML 声明所有扩展，不需要改 sensenova-claw 源码 |
| 2 | **Plugin Loader + Registry 抽象** | core 启动时按 manifest 自动加载所有插件，支持 builtin/团队/用户多来源 |
| 3 | **Control Protocol（JSON-RPC）** | SDK 和 Core 之间的统一协议，本地与云端共用同一份语义 |
| 4 | **Python SDK（瘦客户端）** | `pip install sensenova-claw-sdk`，5 分钟跑通 hello world |
| 5 | **Node.js SDK** | TypeScript/JavaScript 业务团队接入 |
| 6 | **Go SDK** | Go 业务团队接入 |
| 7 | **Rust SDK** | Rust 业务团队接入 |
| 8 | **In-process MCP Server**（SDK 内嵌） | Python 团队写 tool 不用起独立子进程，性能与体验最佳 |
| 9 | **MCP 三路径接入**（stdio / SSE / HTTP） | 任何语言写的工具都能接入，复用业内 MCP 生态 |
| 10 | **Hook 子进程协议** | 任意语言写的 hook 脚本可在 LLM/Tool 调用前后介入（审计、脱敏、改写、缓存） |
| 11 | **Hook 9 个触发点** | OnSessionStart/End、OnUserInput、PreLLM/PostLLM、PreTool/PostTool、OnError、OnConfigUpdated |
| 12 | **Hook Decision 四态** | continue / block / mutate / replace，覆盖所有干预场景 |
| 13 | **多团队 Identity 机制** | (user_id, team_id, org_id) 三元组贯穿全链路 |
| 14 | **Plugin Visibility 隔离** | private / internal / public 三级，跨团队默认互不可见 |
| 15 | **Registry Namespace 隔离** | LLM 看到的工具名带 `team-a/plugin::tool` 前缀，绝不串调 |
| 16 | **存储 Namespace 隔离** | 数据库自动按 team_id / plugin_id 加 namespace，跨团队读不到 |
| 17 | **Permission 双向 RPC** | 高风险工具调用前 Core 反向请求业务方确认，可 allow/deny/edit |
| 18 | **Plugin 安全声明** | manifest 声明 network / filesystem / env 白名单，core 强制实施 |
| 19 | **`sensenova-claw serve` 子命令** | 与现有 run/cli 并列的 SDK 后端入口（stdio/ws/tcp 三种传输），不影响现有体验 |
| 20 | **WebSocket 传输** | Core 跑成远程服务，业务方仅切 URL 即可接入云端 |
| 21 | **Cloud Gateway** | 鉴权、路由、限流、计费，支持多租户 |
| 22 | **Core 进程池** | 一会话一进程或共享池，按 identity 隔离 |
| 23 | **PostgreSQL Repository** | 替换 SQLite 实现，支撑云端规模化 |
| 24 | **Plugin Marketplace 服务** | 注册、发现、版本管理、签名校验、跨 org 公开 |
| 25 | **前端开源仓库** | Web Dashboard + sdk-react + ui-kit + 三个示例项目 |
| 26 | **数据库迁移工具** | sessions/turns/messages/events 加 team_id 列；新 plugin_kv 表；幂等可回滚 |
| 27 | **跨语言示例集** | Python / Go / Node / Rust / Bash 各一份完整 hook + tool 示例 |
| 28 | **多团队混部审计日志** | 每条事件带 plugin_id / team_id，按团队维度可查 |
| 29 | **Plugin 热重载（开发期）** | `plugin.reload` method，本地开发时无需重启 core |
| 30 | **统一文档站** | API 参考 + 每类 contribution 0→1 教程 + 多语言对照 |

---

## 三大类归纳

| 类别 | 功能编号 | 一句话总结 |
|---|---|---|
| **扩展机制**（让业务不改源码） | 1, 2, 8, 9, 10, 11, 12, 29 | Plugin manifest + Hook + MCP，统一三类扩展协议 |
| **跨语言与跨形态**（SDK + 云端） | 3, 4, 5, 6, 7, 19, 20, 21, 22, 23, 25 | 一份 Core，N 种接入；本地与云端同协议 |
| **多团队治理**（让平台可商用） | 13, 14, 15, 16, 17, 18, 24, 26, 27, 28, 30 | Identity → Visibility → Namespace → Audit 全链路 |

---

## 与现有产品的边界

| 现状 | 本次新增 |
|---|---|
| 一个 Agent 应用，业务接入要改源码 | Plugin 机制，业务自包含 |
| 仅 Python 业务可用 | Python/Node/Go/Rust 四语言 |
| 单机 SQLite | 同时支持本地（SQLite）和云端（PostgreSQL） |
| 工具只能写 Python | MCP 三路径 + Python 快速通道 |
| 没有跨团队隔离 | Identity + Visibility + Namespace 三层隔离 |
| 终端用户视角 | **保持 100% 兼容**（详见 spec §9） |

---

## 备注

- 本表只列**新增**功能。现有 17+ tool / 24 skill / 4 LLM provider / 飞书 Channel 等不重写，由 Plugin Manifest 包装挂载（已在 spec §9.2 明确）。
- 详细 80 项功能版本见 git 历史 `docs/design/2026-04-29-agent-harness-sdk-feature-list.md` 的早期 commit。
- 完整设计：[2026-04-27-agent-harness-sdk-design.md](2026-04-27-agent-harness-sdk-design.md)
- 立项 PRD：[2026-04-29-agent-harness-sdk-prd.md](2026-04-29-agent-harness-sdk-prd.md)
- 实现拆分：[2026-04-27-plan-decomposition.md](2026-04-27-plan-decomposition.md)
