# Sensenova-Claw Agent Harness SDK — 产品需求文档（PRD）

- 版本：v1.0
- 日期：2026-04-29
- 状态：立项评审稿
- 配套技术文档：[Spec](2026-04-27-agent-harness-sdk-design.md) / [Plan 拆分](2026-04-27-plan-decomposition.md)

---

## 1. 一句话定位

把 Sensenova-Claw 从"一个 AI Agent 应用"升级为"业务团队都能复用的 Agent Harness SDK + 平台"——业务团队不改源码就能扩展 LLM、工具、Skill、Hook，跨语言、跨部署形态（本地 SDK / 云端服务）。

## 2. 问题陈述

### 2.1 现状痛点

| 问题 | 谁受影响 | 现在的代价 |
|---|---|---|
| 业务团队接入 = 改 Sensenova-Claw 源码 | 所有想用 Sensenova-Claw 能力的兄弟团队 | PR 排队、版本耦合、回归风险大；中央仓库变成所有人的"垃圾桶"，迭代越来越慢 |
| 只支持 Python 业务 | Go / Node / Rust 业务团队 | 无法接入，要么放弃，要么自己造一套 Agent harness（重复造轮子） |
| 多团队共享一份 SQLite + 工具列表 | 多业务团队混部时 | 工具污染、数据混淆、审计困难、安全风险 |
| 工具 / Skill / LLM 扩展三套不同协议 | 想做扩展的工程师 | 学习曲线陡，每加一类扩展都要改不同地方 |
| SDK 和云端是两套独立架构假设 | 平台团队 | 云化时要二次重构，浪费已有投入 |

### 2.2 业务侧信号（非完整）

- 已有 ≥3 个内部团队在私下 fork sensenova-claw 改源码加自己的 tool；
- 多次出现"我能不能不要 Python，用 Go 接你"的请求被搁置；
- 云端形态的产品需求（多租户托管 Agent 服务）已在路线图，但没有协议层支撑；
- Claude Code、LangChain、Anthropic Agent SDK 都已经选择"瘦客户端 + 协议"的形态，市场已验证。

### 2.3 不做这件事的代价

继续维持现状 6-12 个月后：
- 内部 fork 数量持续增长，"哪个 fork 是真的 sensenova-claw" 的问题会频繁出现
- 每接入一个新业务团队，平台团队需要 2-4 周配合改造
- 云端立项被技术债阻塞，至少推迟一个季度
- 多语言团队彻底放弃 sensenova-claw，平台失去 50%+ 潜在用户

## 3. 用户与场景

### 3.1 用户画像

| 用户 | 角色 | 核心诉求 | 当前替代方案 |
|---|---|---|---|
| **业务团队工程师**（主要） | 给业务做 Agent 的开发者 | 不改源码、用熟悉的语言、5 分钟跑通 hello world | 自研 / fork / LangChain |
| **平台运维** | sensenova-claw 平台维护者 | 业务团队互不影响、可观测、可审计 | 改源码后被反复打扰 |
| **业务团队架构师** | 决定团队选型 | 对齐内部技术栈、长期可维护、可上云 | 拒绝接入或独立造轮子 |
| **终端用户**（间接） | 用业务团队 Agent 产品的人 | 体验稳定，跟现状一致 | — |

### 3.2 核心场景

#### 场景 A：业务团队 0 到 1 接入（M0 必须支持）

> 客服团队工程师小李想给客服系统加一个 AI 助理：能查 CRM、查订单、发邮件。

```
1. 团队工程师 pip install sensenova-claw-sdk
2. 写一个 plugin.yaml + 1 个 Python 文件（继承 Tool）/ 或写一个 MCP server
3. async with Harness() as h: async for ev in h.query("..."): print(ev)
4. 跑通 hello world：5 分钟内完成
5. 接入业务系统：~1 天
```

**关键体验**：完全不需要触碰 sensenova-claw 源码。

#### 场景 B：跨语言团队接入（M2 必须支持）

> 数据团队用 Go 做数据流水线，希望调 Sensenova-Claw 跑批量 Agent 推理。

```
1. go get github.com/sensetime/sensenova-claw-go
2. 用 Go SDK 连接同一份 Core
3. Tool 用 Go 写 MCP server，跨语言透明接入
```

**关键体验**：Go/Node/Rust 工程师无需懂 Python。

#### 场景 C：多团队混部（M0+ 渐进支持）

> Team-A 和 Team-B 的 Agent 同时跑在同一个平台实例上。

```
- Team-A 看不到 Team-B 的 plugin（visibility 隔离）
- 数据库写入按 team_id 自动分隔
- 审计日志按 team 维度可查
```

**关键体验**：业务团队感觉是"独享"的，平台运维知道是"共享"的。

#### 场景 D：云端托管（M3 必须支持）

> 兄弟事业部不想自部署，希望调云端服务。

```
- 同一份 Control Protocol，传输层从 stdio 换成 wss://
- 业务方代码（Python/Go/Node）一行改 URL 即可切换本地/云端
```

**关键体验**：本地开发 = 云端使用，零迁移成本。

## 4. 核心价值主张

### 4.1 一句话

**业内首个"统一协议、跨语言、本地云端同源"的 Agent Harness——同时是 SDK，同时是平台。**

### 4.2 三个支点

| 支点 | 含义 | 对比 |
|---|---|---|
| **1. 协议优先** | 业务通过 Control Protocol（JSON-RPC over stdio/WS）调 Core；通过 MCP（业内标准）扩展工具；通过子进程 JSON 写 Hook | LangChain：纯 Python 库，无协议层 / Anthropic Agent SDK：单语言、闭源 / MCP 单点：只解决工具扩展 |
| **2. 一份 Core，N 种接入** | Python core 是唯一实现；Python/Go/Node/Rust 都是几百行的瘦客户端；本地是 stdio，云端是 WebSocket，**协议完全一致** | 大多数 SDK 多语言 = N 份重复实现，迭代时永远有语言落后 |
| **3. 不改源码即可扩展** | Plugin manifest 白名单声明所有贡献：LLM、Tool、Skill、Agent、Channel、Hook、Command。多团队共存有 visibility 隔离 | 现状只能 fork 主仓库 |

### 4.3 不是什么（边界声明）

- **不是 LangChain 的 Python 包**：LangChain 是组件库；Sensenova-Claw 是带运行时和协议的 harness
- **不是裸 MCP**：MCP 只解决"AI ↔ Tool"；Sensenova-Claw 还包括"业务 ↔ Agent 会话"的协议层
- **不是 Claude Code**：Claude Code 是个人开发者工具；Sensenova-Claw 是企业多团队平台

## 5. 功能清单

按 Roadmap 维度展开。每个 M 都是可独立交付、可对外宣布的版本。

### M0：Harness Core + Python SDK + 协议（本期，4-6 周）

| 模块 | 功能 | 用户可见性 |
|---|---|---|
| Harness Core | 编排循环、事件总线、存储、PluginLoader、Registry 抽象（保留现有运行时行为 100% 兼容） | 不可见（基础设施） |
| Plugin Manifest | YAML 声明：LLM/Tool/Channel/Skill/Agent/Hook/Command/MCP_servers 八种贡献 | 业务团队主要接触面 |
| Control Protocol | JSON-RPC 2.0 over stdio；30+ method（session/turn/event/permission/plugin/tool/agent/skill/config/mcp） | 协议契约 |
| Python SDK | `Harness` / `query()` / `tool()` / `create_sdk_mcp_server()`；瘦客户端 spawn core CLI | `pip install sensenova-claw-sdk` |
| Hook 子进程协议 | PreLLM/PostLLM/PreTool/PostTool/OnSession*/OnError/OnConfigUpdated；continue/block/mutate/replace | 任意语言可写 hook |
| MCP 三路径 | stdio / SSE / HTTP / in-process（SDK 反向 RPC） | 工具跨语言扩展 |
| 多团队基础 | Identity 来源链、visibility 过滤、namespace、DB team_id 列、plugin_kv 表 | 业务团队透明享受 |

**对外承诺：终端用户体验、事件协议、现有 e2e 100% 兼容。**

### M1：Node SDK + WebSocket 传输（4-6 周）

| 模块 | 功能 |
|---|---|
| WebSocket 传输 | 同一份 Control Protocol，从 stdio 升级为 WS frame；多客户端支持 |
| Node SDK | `@sensenova-claw/sdk`：spawn core CLI 或连远程 WS；TypeScript 类型定义 |
| 现有 TUI 重构（可选） | 现有 `cli_client.py` 改为基于 Python SDK 的客户端（dogfood） |
| 文档站 | 多语言 API 参考 + 5 个完整示例 |

**对外承诺：Node 业务团队可接入；本地 / 远程同协议无缝切换。**

### M2：Go / Rust SDK（6-8 周）

| 模块 | 功能 |
|---|---|
| Go SDK | `github.com/sensetime/sensenova-claw-go` |
| Rust SDK | `sensenova-claw-rs` |
| 跨语言 Hook 示例 | Go/Node/Rust 写的 hook 直接被 core 调用，文档化 |

**对外承诺：四语言全覆盖业内最广。**

### M3：云端托管服务（8-12 周）

| 模块 | 功能 |
|---|---|
| Cloud Gateway | 鉴权（Token / mTLS）、路由、限流、计费 |
| Core 进程池 | 一会话一进程或进程池；按 identity 隔离 |
| PostgreSQL Repository | 替换 SQLite 实现，Repository 接口不变 |
| 多租户 | Org × Team × User 三层隔离 |
| Plugin Marketplace（基础） | 私有 marketplace，按 org 分发 plugin |

**对外承诺：业务团队只需切 URL 即可从本地切到云端。**

### M4：Plugin Marketplace 服务化 + 前端开源（6-8 周）

| 模块 | 功能 |
|---|---|
| Marketplace 服务 | 注册、发现、版本管理、签名校验、跨 org 公开 plugin |
| 前端开源仓库 | Web Dashboard + sdk-react + ui-kit + 三个示例项目 |
| 商业化界面 | 闭源云端 Dashboard 与开源 Dashboard 区分 |

**对外承诺：开发者社区可形成。**

## 6. 成功指标

### 6.1 北极星指标

> **接入到首个有效工具调用的中位时间（Time-to-First-Tool-Call, TTFTC）**

- M0 目标：≤ 30 分钟（从 0 配置到跑通自定义 tool）
- M1 目标：≤ 20 分钟（含跨语言）
- M3 目标：≤ 10 分钟（云端零部署）

### 6.2 业务指标

| 指标 | M0 目标 | M2 目标 | M4 目标 |
|---|---|---|---|
| 接入业务团队数 | 3 | 8 | 20 |
| 跨语言 SDK 用户占比 | 0% | 30% | 50% |
| 内部 fork 数（应下降） | -50% | -90% | 0 |
| 平台团队"配合改造工时"占比 | <30% | <15% | <10% |
| 云端 MAU（M3 上线后） | — | — | 500+ |

### 6.3 工程指标（质量门）

| 指标 | 验收要求 |
|---|---|
| 现有 e2e 兼容性 | 100% 通过，零修改 |
| Control Protocol 单元测试覆盖 | ≥ 90% |
| Hook 子进程性能开销（PreTool） | P50 ≤ 5ms / P99 ≤ 20ms |
| Plugin 隔离失败率（跨团队可见漏洞） | 0 |
| 文档完整性 | 每个 method 都有示例；每类 contribution 都有从 0 到 1 教程 |

### 6.4 反指标（不允许的退化）

- 终端用户感知到的延迟变化 > 10%（拒绝合并）
- 任何破坏现有 SQLite 数据的迁移（拒绝合并）
- 任何让现有 4 个 LLM provider 行为变化的改动（拒绝合并）

## 7. 里程碑与计划

### 7.1 时间表

```
2026
 04 ─┬─ M0 启动（本期）
     │  P1 PluginLoader → P2 builtin manifest → P3 Control Protocol →
     │  P4 Python SDK + P5 Identity/DB + P6 Hook/MCP（并行）
 05 ─┤
 06 ─┴─ M0 GA：内部 3 个业务团队接入
 07 ─┬─ M1 启动（Node SDK + WS）
 08 ─┤
 09 ─┴─ M1 GA：跨语言首发
 10 ─┬─ M2 启动（Go/Rust SDK）
 11 ─┤
 12 ─┴─ M2 GA：四语言齐全
2027
 01 ─┬─ M3 启动（云端服务 + PostgreSQL）
 02 ─┤
 03 ─┤
 04 ─┴─ M3 GA：云端首发
 05 ─┬─ M4 启动（Marketplace + 前端开源）
 06 ─┤
 07 ─┴─ M4 GA：生态成型
```

### 7.2 资源估算（粗算）

| 角色 | M0 | M1 | M2 | M3 | M4 |
|---|---|---|---|---|---|
| 后端工程师 | 3 | 2 | 4 | 4 | 2 |
| 前端工程师 | 0 | 1 | 0 | 1 | 2 |
| 测试 / DevOps | 1 | 1 | 1 | 2 | 1 |
| TPM / PM | 0.5 | 0.5 | 0.5 | 1 | 0.5 |

### 7.3 关键依赖与风险

| 项 | 类型 | 缓解 |
|---|---|---|
| 现有 e2e 测试覆盖度不足 | 工程风险 | M0 P2 阶段补 e2e；P5 之前不允许加新功能 |
| Hook 子进程在高并发下性能 | 性能风险 | 提供长驻进程模式作为 M1 优化项 |
| 多语言 SDK 维护成本 | 长期风险 | 协议是单一来源；客户端只是薄壳；自动化测试覆盖每语言 |
| 云端立项受 PostgreSQL 迁移延迟阻塞 | 排期风险 | M0 即留好 Repository 接口，M3 只换实现 |
| 内部已有 fork 的回流 | 治理风险 | M0 GA 时与各 fork 团队对齐迁移路径，提供 1:1 映射文档 |

### 7.4 验收标准（M0）

M0 GA 必须同时满足：

- [ ] 6 份 plan（P1-P6）全部执行完成、e2e 全绿
- [ ] 现有 `sensenova-claw run / cli / version` 行为完全不变
- [ ] 终端用户视角无任何感知差异
- [ ] 至少 1 个业务团队（非平台团队）独立完成接入并跑通生产用例
- [ ] `pip install sensenova-claw-sdk && python examples/sdk_minimal.py` 能在 ≤ 30 分钟内跑通
- [ ] PluginLoader / Control Protocol / Hook / MCP 三路径文档完整
- [ ] 多团队 identity / namespace / 存储隔离的安全测试全过

## 8. 不在范围（明确不做）

| 项 | 说明 | 何时考虑 |
|---|---|---|
| 自研 LLM 推理框架 | 永远复用 OpenAI/Anthropic/Gemini | 无 |
| 替代 LangChain 全部组件 | 只做 harness，不做 chain / RAG 库 | 无 |
| 实时流式 token 输出 | 当前架构按 turn 维度推送事件，不切到 token 级 | M1 后视需要 |
| 沙箱执行 | 进程隔离已足够；不做 gVisor/firecracker 级别 | M3 云端再考虑 |
| 移动端 SDK | iOS/Android 用户量不足以支撑 | 看市场 |
| 商业模式（计费、订阅） | 平台核心先成型 | M3 后由 PM 团队定 |

## 9. 决策事项

需要立项评审会确认的开放问题：

1. **资源调配**：M0 需 3 后端 + 1 测试 + 0.5 TPM，是否到位？
2. **OSS 边界**：M4 前端 + Python SDK 开源，云端服务闭源——是否同意此切分？
3. **品牌定位**：对外是 "sensenova-claw" 还是另起一个面向开发者的品牌名？
4. **Marketplace 商业模式**：私有 marketplace 是否计费？开源 plugin 是否走我们的注册中心？
5. **协议许可**：Control Protocol schema 是否走 OSS（如 Apache-2.0）？决定生态可走多远。

## 10. 附录

- 技术 Spec：[2026-04-27-agent-harness-sdk-design.md](2026-04-27-agent-harness-sdk-design.md)
- 实现 Plan 拆分：[2026-04-27-plan-decomposition.md](2026-04-27-plan-decomposition.md)
- 现有架构总览：[architecture/overview.md](../architecture/overview.md)

### 10.1 术语

| 术语 | 含义 |
|---|---|
| **Harness Core** | 编排循环 + 事件总线 + 加载机制的不可替换内核 |
| **Plugin** | 业务团队的扩展单元；通过 manifest 声明 contribution |
| **Contribution** | Plugin 贡献给 core 的能力（tool / skill / agent / hook / channel / llm / command / mcp_server） |
| **Control Protocol** | SDK ↔ Core 之间的 JSON-RPC 协议 |
| **MCP** | Model Context Protocol，业内 AI ↔ Tool 标准 |
| **Identity** | (user_id, team_id, org_id) 三元组，决定 plugin 可见性 |
| **Hook** | 在编排循环关键节点触发的子进程脚本，可 mutate/block/replace |

### 10.2 修订历史

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-04-29 | sensenova-claw 团队 | 立项稿 |
