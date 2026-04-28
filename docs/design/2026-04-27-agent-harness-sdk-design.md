# Agent Harness SDK 设计

- 作者：sensenova-claw 团队
- 日期：2026-04-27
- 范围：harness core 抽象 + Python 参考实现 + 外部扩展协议
- 不在范围：多语言 SDK 的具体实现、云端服务的具体实现、前端开源仓库的具体切分（仅写入长期蓝图）

## 1. 背景与目标

Sensenova-Claw 当前是 Python 单体（FastAPI + asyncio + SQLite），plugin/skill/tool/hook 已有雏形，但形态各异：channel 是 plugin、tool 是 Python 子类、skill 是 Markdown 文档，没有统一的 plugin manifest，业务团队接入只能改源码。

本期目标：把现有代码抽成"harness core SDK"，让业务团队**不改源码**就能扩展。约束：

- 多团队共存，相互不可见
- 多语言：Python、Go、Node、Rust（本期只交付 Python，其他写契约）
- 同时支持 SDK（业务进程接入）和云端（托管服务）形态
- 前端只服务于展示和开源 demo

## 2. 范围与边界（已确认决策）

| 决策 | 选项 |
|---|---|
| 本期范围 | 只定 harness core 抽象 + Python 参考实现；其他写蓝图 |
| Core 边界 | 中等内核：core 管事件总线、编排循环、加载机制、存储；LLM/Tool/Channel/Skill/Agent/Hook 都是 plugin |
| 跨语言扩展 | Tool 走 MCP，Hook 走子进程 JSON，Skill/Agent 走 Markdown；Python 团队保留类继承快速通道 |
| SDK 形态 | Claude Code 模式：SDK 是瘦客户端（spawn core CLI + Control Protocol 编解码）；core CLI 是 agent 循环的唯一实现 |
| 调用协议 | 自定义 Control Protocol（JSON-RPC over stdio），独立于 MCP；MCP 仅用于业务给 core 加工具 |
| 传输层 | 默认 stdio；TCP/WebSocket 是蓝图，同一份协议语义 |

## 3. 整体架构

```
═══════════════════════════════════════════════════════════════════════════════
  ① 业务接入层（业务进程，任意语言；也可以是终端用户的 CLI/前端）
═══════════════════════════════════════════════════════════════════════════════

   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │ Python 业务     │  │ Go/Node/Rust    │  │ 终端用户        │
   │  app.py         │  │  business app   │  │  CLI / Web 前端 │
   │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │
   │  │ sn-claw   │  │  │  │ sn-claw   │  │  │  │ sn-claw   │  │
   │  │  -sdk(py) │  │  │  │  -sdk(*)  │  │  │  │ CLI 命令  │  │
   │  └─────┬─────┘  │  │  └─────┬─────┘  │  │  └─────┬─────┘  │
   └────────┼────────┘  └────────┼────────┘  └────────┼────────┘
            │                    │                    │
            │      Control Protocol（JSON-RPC）        │
            │      ┌───────────────────────────┐       │
            │      │ 默认：stdio                │       │
            │      │ 蓝图：TCP / WebSocket      │       │
            │      └───────────────────────────┘       │
            ▼                    ▼                    ▼

═══════════════════════════════════════════════════════════════════════════════
  ② Core CLI 进程（Python；本期参考实现；也是云端容器化形态的同一份代码）
═══════════════════════════════════════════════════════════════════════════════

   ┌─────────────────────────────────────────────────────────────────────┐
   │  Control Server（Control Protocol 解码 → 派发到 core）              │
   │  - session.start / session.fork / session.list                      │
   │  - turn.send_input / turn.cancel                                    │
   │  - event.subscribe（向 SDK 流式推送 EventEnvelope）                 │
   │  - permission.request / permission.respond                          │
   └────────────────────────────────┬────────────────────────────────────┘
                                    │
   ┌────────────────────────────────▼────────────────────────────────────┐
   │  Harness Core（写死，业务不可换）                                    │
   │                                                                      │
   │  ┌─ Identity / Tenancy ─────────────────────────────────────┐       │
   │  │ user_id, team_id, org_id（来自 SDK 启动参数 / 环境变量） │       │
   │  │ → 用于 plugin 可见性过滤和存储 namespace                  │       │
   │  └──────────────────────────────────────────────────────────┘       │
   │                                                                      │
   │  ┌─ Plugin Loader ──────────────────────────────────────────┐       │
   │  │ 1. 扫描 source（builtin / marketplace / team / local）   │       │
   │  │ 2. 按 identity 过滤 visibility（private/internal/public） │       │
   │  │ 3. 加载 manifest，校验 schema                             │       │
   │  │ 4. 把贡献注入到下面各个 registry                          │       │
   │  └──────────────────────────────────────────────────────────┘       │
   │                                                                      │
   │  ┌──────────────────────  PublicEventBus ─────────────────────┐     │
   │  │  EventEnvelope（event_id, type, session_id, turn_id, ...） │     │
   │  └──┬──────────────┬──────────────┬──────────────┬────────────┘     │
   │     │              │              │              │                  │
   │  ┌──▼─────────┐ ┌──▼─────────┐ ┌──▼─────────┐ ┌──▼─────────┐       │
   │  │ Agent      │ │ LLM        │ │ Tool       │ │ Title /    │       │
   │  │ Runtime    │ │ Runtime    │ │ Runtime    │ │ Memory ... │       │
   │  └──┬─────────┘ └──┬─────────┘ └──┬─────────┘ └────────────┘       │
   │     │              │              │                                 │
   │     │     编排循环：user.input → llm → tool → step_completed        │
   │     │                                                                │
   │  ┌──▼──────────────────────────────────────────────────────────┐   │
   │  │ Hook Pipeline（在循环关键节点触发）                          │   │
   │  │  PreLLM / PostLLM / PreTool / PostTool / OnSessionStart / …  │   │
   │  └─────────────────────────┬───────────────────────────────────┘   │
   │                            │                                        │
   │  ┌─ Storage（SQLite，本期不暴露替换接口） ─────────────────────┐    │
   │  │ sessions / turns / messages / events / agent_messages       │    │
   │  │ 写入时按 plugin_id / team_id 自动加 namespace                │    │
   │  └──────────────────────────────────────────────────────────────┘   │
   │                                                                      │
   │  ┌─ Registries（运行期 plugin 注入的能力） ──────────────────┐       │
   │  │ LLMProviderRegistry │ ToolRegistry │ ChannelRegistry      │       │
   │  │ SkillRegistry       │ AgentRegistry │ HookRegistry        │       │
   │  │ CommandRegistry                                            │       │
   │  │  └─ 每个条目带 owner_plugin / visibility / namespace        │       │
   │  └────────────────────────────────────────────────────────────┘       │
   └──────────────────────────────────────────────────────────────────────┘
                       │              │              │
       ┌───────────────┘              │              └────────────────┐
       │                              │                                │
       │ MCP 协议                     │ 子进程 + JSON                  │ in-process
       │ (stdio/SSE/HTTP)             │ stdin/stdout                   │ Python 调用
       ▼                              ▼                                ▼

═══════════════════════════════════════════════════════════════════════════════
  ③ 扩展层（业务团队的代码，任意语言；都通过协议或 Python plugin 接入）
═══════════════════════════════════════════════════════════════════════════════

   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
   │ MCP Servers      │   │ Hook Scripts     │   │ Python Plugins   │
   │（Tool 扩展主路） │   │（任意语言可执行）│   │（快速通道）      │
   │                  │   │                  │   │                  │
   │ • crm_lookup     │   │ • PreTool        │   │ • Tool 子类      │
   │ • db_query       │   │   audit.sh       │   │ • LLMProvider    │
   │ • internal_api   │   │ • PostLLM        │   │ • Channel        │
   │ • ...            │   │   redact.py      │   │ • ...            │
   │                  │   │ • OnSessionStart │   │                  │
   │ 任何语言 + MCP   │   │   bootstrap.go   │   │ 仅 Python        │
   └──────────────────┘   └──────────────────┘   └──────────────────┘

═══════════════════════════════════════════════════════════════════════════════
  ④ Plugin 分发（哪里来的）
═══════════════════════════════════════════════════════════════════════════════

   ┌────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌─────────────┐
   │ Builtin    │  │ Org Marketplace │  │ Team Repo    │  │ User Local  │
   │（随 core） │  │（公司私有库）   │  │（git 仓库）  │  │（本地目录） │
   │            │  │                 │  │              │  │             │
   │ visibility:│  │ visibility:     │  │ visibility:  │  │ visibility: │
   │ public     │  │ internal        │  │ private      │  │ session     │
   └─────┬──────┘  └────────┬────────┘  └──────┬───────┘  └──────┬──────┘
         │                  │                  │                  │
         └──────────────────┴──────────────────┴──────────────────┘
                                    │
                                    ▼
                          Plugin Loader（在 ② 中）
```

### 3.1 协议分工（强化）

| 协议 | 谁和谁说话 | 形态 | 实现来源 |
|---|---|---|---|
| Control Protocol | 业务 SDK ↔ Core CLI | 自定义 JSON-RPC over stdio（默认）/ TCP+WS（蓝图） | 我们定 schema，每语言写瘦客户端 |
| MCP | Core ↔ 业务工具 server | 标准 MCP（stdio / SSE / HTTP） | 复用 `@modelcontextprotocol/sdk` 等 |
| Hook 子进程协议 | Core ↔ 业务 hook 脚本 | 子进程 + stdin/stdout JSON | 我们定 envelope schema，业务自己写脚本 |

### 3.2 一次请求的完整数据流

```
SDK.run_turn("帮我查客户")
   │
   │ ① Control Protocol（stdio JSON-RPC）
   │    {"method":"turn.send_input", "session_id":"...", "text":"..."}
   ▼
Control Server（解码）
   │
   ▼
Harness Core 发布事件: user.input → PublicEventBus
   │
   ├──► HookPipeline.run("OnUserInput") ──► 子进程（任意语言）
   │
   ▼
AgentRuntime: 编排循环开始
   │
   ├──► HookPipeline.run("PreLLM")
   ├──► LLMRuntime: 调 LLM provider plugin（OpenAI / 内部模型 / ...）
   ├──► HookPipeline.run("PostLLM")
   │
   ├──► 如果 LLM 返回 tool_calls：
   │       ├──► HookPipeline.run("PreTool")
   │       ├──► ToolRuntime.dispatch(tool_name)
   │       │      ├──► Python 直接调用（快速通道）
   │       │      └──► 或 MCP 调用 ──► MCP Server（任意语言子进程）
   │       └──► HookPipeline.run("PostTool")
   │       回到 LLMRuntime 继续循环
   │
   ▼
agent.step_completed
   │
   │ ② Control Protocol（向 SDK 流式回推）
   │    {"method":"event", "envelope":{...}}
   ▼
SDK 把事件 yield 给业务代码
```

## 4. Plugin Manifest 与 Contribution Schema

每个 plugin 是一个目录，根有 `plugin.yaml`（必需）。所有贡献必须在 manifest 里**显式列出**（白名单），core 不靠扫目录猜。

### 4.1 plugin.yaml 顶层字段

```yaml
schema_version: "1"               # manifest schema 版本，用于演进
id: team-a/crm-assistant          # 全局唯一，{owner}/{name} 格式
version: 1.2.0                    # SemVer
name: CRM Assistant
description: 客服 CRM 工具集
author: team-a@company.com
license: Apache-2.0
homepage: https://...

# ── 隔离与可见性 ────────────────────────────────────────────────
owner: team-a                     # 所属 team
visibility: private               # private | internal | public
allowed_teams: []                 # internal 时填白名单；其他时忽略
allowed_users: []                 # 可选，更细粒度

# ── 兼容性 ────────────────────────────────────────────────────────
sensenova_claw:
  min_version: "1.2.0"
  max_version: "2.0.0"

# ── 安全声明（plugin 自报需要的能力，core 启动时按声明限制） ────
permissions:
  network:
    - "https://api.crm.internal/**"
  filesystem:
    - read: ["./data/**"]
    - write: ["./cache/**"]
  env:
    - CRM_API_TOKEN

# ── 配置 schema（业务接入时填，core 校验） ──────────────────────
config:
  schema:                         # JSON Schema
    type: object
    required: [api_endpoint]
    properties:
      api_endpoint: { type: string }
      timeout_seconds: { type: integer, default: 30 }

# ── 贡献：白名单显式列出 ──────────────────────────────────────────
contributes:
  llm_providers: [...]
  tools:         [...]
  channels:      [...]
  skills:        [...]
  agents:        [...]
  hooks:         [...]
  commands:      [...]
  mcp_servers:   [...]
```

### 4.2 目录约定

```
sensenova-claw-plugin/
├── plugin.yaml                  # 总清单（声明所有贡献）
├── agents/
│   └── support/
│       ├── agent.md             # agent 定义
│       ├── tools/               # 这个 agent 私有 tool
│       └── skills/              # 这个 agent 私有 skill
├── tools/                       # plugin 公共 tool（多 agent 共享）
├── skills/                      # plugin 公共 skill
├── channels/                    # plugin 提供的 channel
├── llm-providers/               # plugin 提供的 LLM provider
├── commands/                    # 斜杠命令
├── hooks/                       # hook 脚本
├── mcp/                         # MCP server 实现
└── README.md
```

**层次约定**：plugin 顶层贡献 = 整个 plugin 共享；agent 子目录贡献 = 单个 agent 私有。

### 4.3 各 Contribution Schema

#### 4.3.1 `llm_providers`

```yaml
contributes:
  llm_providers:
    - id: internal-model
      type: python                # python | mcp | http
      python: providers/internal.py:InternalProvider   # 类路径
      models:                     # 这个 provider 支持的 model 列表
        - id: internal-7b
          context_window: 32000
        - id: internal-70b
          context_window: 128000
```

`type: http` 时表示一个兼容 OpenAI API 的 endpoint，由 manifest 的 `config` 提供 `base_url`/`api_key`。

#### 4.3.2 `tools`（三种接入方式）

```yaml
contributes:
  tools:
    # 方式 1：Python 快速通道（in-process）
    - id: send_email
      type: python
      python: tools/email.py:SendEmailTool
      schema_path: tools/email.schema.json   # 可选，否则从类反射

    # 方式 2：MCP（跨语言主路径）
    - id: crm_lookup
      type: mcp
      mcp_server: crm-server      # 引用下方 mcp_servers 中的 id
      tool_name: lookup_customer  # MCP server 暴露的工具名

    # 方式 3：HTTP（业务已有 REST API 直接套）
    - id: order_query
      type: http
      method: POST
      url: "{config.api_endpoint}/orders/query"
      input_schema_path: tools/order.schema.json
```

#### 4.3.3 `channels`

```yaml
contributes:
  channels:
    - id: slack
      type: python
      python: channels/slack.py:SlackChannel
      auto_start: true            # core 启动时自动连接
```

Channel 仅支持 `python` 类型（本期）——它和 core 的事件总线交互密集，跨进程不划算。

#### 4.3.4 `skills`

```yaml
contributes:
  skills:
    - id: refund-flow
      path: skills/refund-flow/SKILL.md   # Markdown + frontmatter
      enabled_by_default: true
```

Skill body 懒加载：core 只在 LLM 真要选这个 skill 时读 body。

#### 4.3.5 `agents`

```yaml
contributes:
  agents:
    - id: customer-support
      path: agents/support/agent.md       # Markdown + frontmatter
      tools:                              # 这个 agent 可见的 tool（白名单）
        - send_email                      # 引用本 plugin 的 tool
        - crm_lookup
        - "core::bash_command"            # 可显式引用 core 内置 tool
      skills:
        - refund-flow
      llm:
        provider: internal-model          # 这个 agent 用哪个 provider
        model: internal-70b
```

`agent.tools` 白名单 = 这个 agent **实际能调用**的范围；plugin 顶层 `tools` = "我贡献了什么"。两者解耦。

#### 4.3.6 `hooks`

```yaml
contributes:
  hooks:
    - event: PreTool              # 触发时机
      matcher:                    # 可选过滤条件
        tool_name: ["send_email", "crm_lookup"]
      type: subprocess            # subprocess | python
      command: ["bash", "hooks/audit.sh"]
      timeout_seconds: 5
      blocking: true              # true=阻塞循环；false=fire-and-forget
      on_failure: block           # block | continue（默认 block）

    - event: PostLLM
      type: python
      python: hooks/redact.py:redact_pii
```

可选 event 列表：`OnSessionStart`、`OnSessionEnd`、`OnUserInput`、`PreLLM`、`PostLLM`、`PreTool`、`PostTool`、`OnError`、`OnConfigUpdated`。

#### 4.3.7 `commands`

```yaml
contributes:
  commands:
    - id: analyze
      path: commands/analyze.md   # 斜杠命令，Markdown + frontmatter
      visibility: team            # session | user | team | org
```

#### 4.3.8 `mcp_servers`

```yaml
contributes:
  mcp_servers:
    - id: crm-server
      transport: stdio            # stdio | sse | http
      command: ["node", "mcp/crm-server.js"]
      args: []
      env:
        CRM_API_TOKEN: "${env.CRM_API_TOKEN}"
      working_dir: ./mcp
      auto_start: on_demand       # always | on_demand | never
      health_check:
        method: tools/list
        interval_seconds: 30
      restart_policy: on_failure  # never | on_failure | always
      max_restarts: 3
      permissions:
        network: ["https://crm.internal/**"]

    - id: ext-search
      transport: sse
      url: "https://mcp.search.internal/sse"
      headers:
        Authorization: "Bearer ${env.SEARCH_TOKEN}"
```

### 4.4 命名空间和引用规则

| 引用形态 | 含义 |
|---|---|
| `crm_lookup` | 当前 plugin 内部的本地引用 |
| `team-a/crm-assistant::crm_lookup` | 跨 plugin 引用（带前缀） |
| `core::bash_command` | core 内置的 |
| `core::*` | core 内置全部（agent.tools 中可用） |

LLM 看到的工具列表是**带 namespace 前缀的全局 ID**，避免跨团队工具同名。

### 4.5 Manifest 校验流程

```
plugin 加载
  │
  ├─ 1. 读 plugin.yaml
  ├─ 2. 用 schema_version 选 schema 校验
  ├─ 3. 校验 sensenova_claw.min_version 兼容性
  ├─ 4. 按 identity 检查 visibility / allowed_teams → 不通过则跳过
  ├─ 5. 校验 permissions（声明的网络/路径/env）
  ├─ 6. 校验 config（用户传入的 config 是否符合 schema）
  ├─ 7. 解析 contributes，每条 contribution 注册到对应 Registry
  └─ 8. 失败任一步：plugin 进入 disabled 状态，不影响 core 启动
```

## 5. Control Protocol（SDK ↔ Core）

### 5.1 协议形态

- 格式：JSON-RPC 2.0
- 传输：默认 stdio（每行一个 JSON 对象，行分隔）；蓝图支持 TCP / WebSocket
- 方向：双向。SDK → Core 是 request；Core → SDK 既有 notification（事件流）也有 request（permission 询问、`mcp.invoke` 反向调用）
- 会话模型：一个连接 = 一个 client；一个 client 可管理多个 session

### 5.2 启动握手

```
client 启动 core CLI 子进程
  │ spawn: sensenova-claw serve --stdio
  │
  ▼
client → core: { "method": "initialize", "params": {
                   "protocol_version": "1",
                   "client_info": { "name": "py-sdk", "version": "0.1.0" },
                   "identity": { "user_id": "...", "team_id": "...", "org_id": "..." },
                   "config_overrides": { ... }
                 } }
core → client: { "result": {
                   "core_version": "1.2.0",
                   "protocol_version": "1",
                   "capabilities": { "streaming": true, "permissions": true, ... },
                   "available_plugins": [ ... ],
                   "available_agents":  [ ... ],
                   "available_models":  [ ... ]
                 } }
```

握手后 core 已经按 identity 加载完 plugin，且只暴露该 identity 可见的能力。身份不可在 session 中途切换——切换需要新连接。

### 5.3 Method 列表

#### Session 域

| Method | 方向 | 用途 |
|---|---|---|
| `session.create` | C→S | 新建会话，返回 `session_id` |
| `session.list` | C→S | 列出当前 client 的会话 |
| `session.get_info` | C→S | 拿元数据（agent、turn 数、token 数） |
| `session.fork` | C→S | 从某个 turn 分叉一个新 session |
| `session.delete` | C→S | 删除（含数据） |
| `session.resume` | C→S | 用已有 session_id 接着上轮对话 |

#### Turn 域

| Method | 方向 | 用途 |
|---|---|---|
| `turn.send_input` | C→S | 发用户输入；core 异步回推事件 |
| `turn.cancel` | C→S | 取消当前 turn |
| `turn.get_messages` | C→S | 拿历史消息（分页） |

#### Event 域

| Method | 方向 | 用途 |
|---|---|---|
| `event.subscribe` | C→S | 订阅某些 session 的事件流 |
| `event.unsubscribe` | C→S | 取消订阅 |
| `event` | S→C notification | core 推送 EventEnvelope |

`EventEnvelope` 沿用 sensenova-claw 现有定义（`event_id, type, session_id, turn_id, trace_id, payload, source`），不发明新结构。

#### Permission 域

| Method | 方向 | 用途 |
|---|---|---|
| `permission.request` | S→C request | core 反向问业务："要执行 send_email，许可吗" |
| `permission.respond` | C→S | 业务回 allow / deny / edit |

#### Plugin / Capability 域

| Method | 方向 | 用途 |
|---|---|---|
| `plugin.list` | C→S | 列出已加载 plugin |
| `plugin.enable` / `plugin.disable` | C→S | 运行时开关 |
| `plugin.reload` | C→S | 热重载（开发用） |
| `tool.list` | C→S | 列出当前 session 可见的 tool |
| `agent.list` | C→S | 列出可用 agent |
| `skill.list` | C→S | 列出可用 skill |

#### Config 域

| Method | 方向 | 用途 |
|---|---|---|
| `config.get` | C→S | 读 config（脱敏 secret） |
| `config.set` | C→S | 写 config（持久化 + 触发 `config.updated` 事件） |
| `config.subscribe` | C→S | 订阅 config 变更通知 |

#### MCP 域（业务用 SDK 注册 in-process MCP server）

| Method | 方向 | 用途 |
|---|---|---|
| `mcp.register_server` | C→S | 业务进程内的 MCP server 句柄注册到 core |
| `mcp.invoke` | S→C request | core 反向调业务进程内的 MCP tool |

### 5.4 错误模型

```
-32700 ~ -32603   JSON-RPC 标准错误
-32000            permission_denied
-32001            plugin_not_loaded
-32002            session_not_found
-32003            tool_execution_failed
-32004            config_validation_failed
-32005            identity_mismatch（visibility 拒绝）
-32006            capability_unavailable
```

### 5.5 一次完整调用的协议级追踪

```
[1]  C→S  initialize { protocol_version, identity }
[2]  S→C  result { core_version, capabilities, available_* }
[3]  C→S  session.create { agent_id: "team-a/crm-assistant::customer-support" }
[4]  S→C  result { session_id: "s-abc" }
[5]  C→S  event.subscribe { session_id: "s-abc" }
[6]  C→S  turn.send_input { session_id: "s-abc", text: "查客户 12345" }
[7]  S→C  result { turn_id: "t-1" }
[8]  S→C  event { type: "user.input", ... }
[9]  S→C  event { type: "agent.step_started", ... }
[10] S→C  event { type: "llm.call_completed", payload: { tool_calls: [...] } }
[11] S→C  request permission.request { tool: "crm_lookup", args: {...} }
[12] C→S  permission.respond { decision: "allow" }
[13] S→C  event { type: "tool.call_completed", ... }
[14] S→C  event { type: "agent.step_completed", final_text: "..." }
```

### 5.6 进程生命周期

| 信号 | 行为 |
|---|---|
| stdin EOF | core 优雅退出（先 flush 事件、关闭 session） |
| SIGTERM | 同上 |
| 健康检查 | `ping` method（C→S），`pong` 立即返回 |
| 崩溃恢复 | client 检测到子进程退出 → 起新进程 → `session.resume` |

### 5.7 协议演进

- `protocol_version` 字段在握手时双方协商
- 新增 method = minor 版本（向后兼容）
- 改 method 签名 = major 版本（同时维护两个版本一段时间）
- 字段新增允许；字段删除走 deprecated → 下个 major 移除

## 6. 扩展协议

### 6.1 Hook 子进程协议

#### 触发模型

```
core 编排循环跑到关键节点
    │
    ▼
HookPipeline 按 event 类型查 HookRegistry
    │
    ├─ matcher 过滤（tool_name / agent_id / session_id 模式匹配）
    │
    ▼
对每个匹配 hook：spawn 子进程
    │
    ├─ stdin: 写 input envelope（一行 JSON）
    ├─ wait timeout（manifest 声明，默认 5s）
    ├─ stdout: 读 output envelope（一行 JSON）
    ├─ exit code: 0=正常 / 非 0=hook 失败
    │
    ▼
按 output 决定：continue / block / mutate / replace
```

#### Event 列表（与 §4.3.6 对齐）

| Event | 触发时机 | 可否 mutate | 典型用途 |
|---|---|---|---|
| `OnSessionStart` | 新 session 创建后 | mutate config | 注入身份、加载团队预设 |
| `OnSessionEnd` | session 关闭时 | 不可 mutate | 审计落库 |
| `OnUserInput` | 用户输入入队后 | mutate input | 输入脱敏、敏感词过滤 |
| `PreLLM` | LLM 调用前 | mutate messages/tools | prompt 注入、tool 白名单收敛 |
| `PostLLM` | LLM 返回后 | mutate response | 输出脱敏、PII 检测 |
| `PreTool` | tool 调用前 | mutate args / block | 审计、权限校验、参数改写 |
| `PostTool` | tool 返回后 | mutate result | 结果裁剪、缓存 |
| `OnError` | 任意 runtime 异常 | 不可 mutate | 告警、上报 |
| `OnConfigUpdated` | config 变更后 | 不可 mutate | 重载下游缓存 |

#### Input envelope（core → hook stdin）

```json
{
  "hook_id": "team-a/crm-assistant::audit",
  "event": "PreTool",
  "session_id": "s-abc",
  "turn_id": "t-1",
  "trace_id": "tool-call-xyz",
  "identity": { "user_id": "u-1", "team_id": "team-a" },
  "context": {
    "tool_name": "send_email",
    "tool_args": { "to": "x@y.com", "subject": "..." },
    "agent_id": "customer-support"
  },
  "timestamp": "2026-04-27T08:00:00Z"
}
```

`context` 字段按 event 类型不同：`PreLLM` 给 messages，`PostTool` 给 result，等等。schema 由 core 提供 JSON Schema，业务可生成本地类型。

#### Output envelope（hook stdout → core）

```json
{
  "decision": "continue",
  "reason": "audit passed",
  "mutations": {
    "tool_args": { "to": "x@y.com", "subject": "[REDACTED]" }
  },
  "replacement": {
    "tool_result": { "ok": true, "stub": true }
  },
  "diagnostics": [
    { "level": "warn", "message": "...", "code": "..." }
  ]
}
```

#### Decision 语义

| decision | 行为 |
|---|---|
| `continue` | 放行，core 继续原流程 |
| `block` | 中止当前 step，core 抛 `HookRejected` 事件，turn 失败 |
| `mutate` | 用 `mutations` 替换对应字段后继续 |
| `replace` | 跳过原调用（如 LLM/tool），直接用 `replacement` 当结果 |

`replace` 可以让 hook 完全代理掉 LLM 或 tool 调用（本地 mock、缓存命中）。

#### 串行 vs 并行

- blocking hook（`blocking: true`）按 manifest 声明顺序串行，前一个的 mutation 喂给下一个
- fire-and-forget hook（`blocking: false`）并发 spawn，结果忽略，超时也不阻塞主循环（用于审计/监控）
- 一个 event 上多个 blocking hook 时：插件加载顺序 = 执行顺序；同一 plugin 内按 manifest 顺序

#### 失败模型

| 失败类型 | core 行为 |
|---|---|
| 子进程非 0 退出 | 默认 `block`（保守）；manifest 可声明 `on_failure: continue` |
| 超时 | kill 子进程，按 `on_failure` 处理 |
| stdout 不是合法 JSON | 同超时 |
| hook 自己崩溃 | 不影响 core；失败计数到 `OnError` 事件 |

#### Hook 跨语言示例

```bash
#!/bin/bash
# hooks/audit.sh
read INPUT
TOOL=$(echo "$INPUT" | jq -r '.context.tool_name')
echo "{\"decision\":\"continue\",\"reason\":\"audit ok: $TOOL\"}"
```

```go
// hooks/redact.go
func main() {
    var in HookInput
    json.NewDecoder(os.Stdin).Decode(&in)
    out := HookOutput{
        Decision: "mutate",
        Mutations: map[string]any{
            "llm_response": redactPII(in.Context["llm_response"]),
        },
    }
    json.NewEncoder(os.Stdout).Encode(out)
}
```

任何语言只要能读 stdin / 写 stdout / 输出 JSON，就能写 hook。

### 6.2 MCP 接入约定

#### 三种接入路径

```
Path A: 外部 stdio MCP server
  ─────────────────────────────────
  plugin.yaml 声明 command + args
  core 在第一次用到时 spawn
  通信走 MCP 标准 stdio

Path B: 外部 SSE / HTTP MCP server
  ─────────────────────────────────
  plugin.yaml 声明 url
  core 通过 HTTP 长连
  适合远程 / 已有微服务

Path C: SDK 内 in-process MCP server
  ─────────────────────────────────
  业务进程用 SDK 起 MCP server
  通过 Control Protocol 反向 RPC（mcp.register_server / mcp.invoke）
  core 不 spawn 子进程，直接调业务进程
  Python 业务团队的快速通道
```

#### 生命周期与隔离

| 维度 | 行为 |
|---|---|
| Spawn 时机 | `auto_start: always` → 启动即 spawn；`on_demand` → 第一次调用 tool 时 spawn |
| 进程归属 | 一个 MCP server 进程被同一 core 进程内所有 session 共享 |
| 多 client 隔离 | server 不感知 client；core 在请求 metadata 里注入 `session_id`、`identity`，由 server 自行决定是否做隔离 |
| 关闭 | core 退出时 `SIGTERM`；超时 `SIGKILL` |
| 错误传播 | server 崩溃 → tool 调用返回 `tool_execution_failed`；按 `restart_policy` 重启 |

#### 权限/审计

每次 MCP tool 调用都过 `PreTool` hook，所以 §6.1 的所有审计/拦截能力对 MCP tool 也适用。Tool 是 Python 还是 MCP，hook 看到的接口一致。

### 6.3 协议层关系图

```
┌─────────────────────────── core 编排循环 ─────────────────────────┐
│                                                                  │
│  user.input ──► PreLLM hook ──► LLM ──► PostLLM hook             │
│                                          │                       │
│                                          ▼                       │
│                                   PreTool hook                   │
│                                          │                       │
│                          ┌───────────────┼───────────────┐       │
│                          │               │               │       │
│                          ▼               ▼               ▼       │
│                   Python tool      MCP tool        in-proc MCP   │
│                   (in-process)    (子进程)         (经 SDK 反向) │
│                          │               │               │       │
│                          └───────────────┼───────────────┘       │
│                                          ▼                       │
│                                   PostTool hook                  │
│                                          │                       │
│                                          ▼                       │
│                                   step_completed                 │
└──────────────────────────────────────────────────────────────────┘
```

## 7. 多团队隔离实现

### 7.1 Identity 来源链

```
client 启动 SDK → SDK 收集 identity 信息（按优先级）
  │
  ├─ 1. SDK 调用方显式传入（最高）：
  │      sdk = Harness(identity={user_id, team_id, org_id})
  │
  ├─ 2. 环境变量：
  │      SENSENOVA_CLAW_USER_ID / TEAM_ID / ORG_ID
  │
  ├─ 3. ~/.sensenova-claw/identity.yaml
  │
  └─ 4. 默认 identity（local-dev / local-team / local-org）
       → 仅本地开发使用，云端/CI 环境必须显式传
  │
  ▼
SDK 在 initialize 握手时通过 Control Protocol 传给 core
  │
  ▼
core 把 identity 存进 SessionContext，整个 session 生命周期都带着
```

### 7.2 Plugin Loader 过滤算法

```python
def load_plugins(identity, plugin_sources):
    visible_plugins = []
    for source in plugin_sources:           # builtin / org / team / user
        for manifest in source.list():
            if not is_visible(manifest, identity):
                continue                    # 静默跳过，不进内存
            visible_plugins.append(manifest)
    return visible_plugins

def is_visible(manifest, identity):
    if manifest.visibility == "public":
        return True
    if manifest.visibility == "internal":
        return identity.team_id in manifest.allowed_teams
    if manifest.visibility == "private":
        return identity.team_id == manifest.owner
    return False
```

**关键不变量**：不可见的 plugin 在 core 内存中**完全不存在**——不是 UI 隐藏。审计日志、tool 列表、agent 列表，都看不到。

### 7.3 Registry 注册时打 namespace

```python
RegistryEntry(
    id=f"{plugin.id}::{contribution.id}",   # 全局唯一 ID
    short_id=contribution.id,                # plugin 内部短名
    owner_plugin=plugin.id,
    owner_team=plugin.owner,
    visibility=plugin.visibility,
    impl=...
)
```

LLM 看到的工具名都带 namespace 前缀，绝不可能跨团队误调。

### 7.4 存储 namespace

`Repository` 层透明加 `plugin_id` 和 `team_id` 列：

```sql
CREATE TABLE plugin_kv (
  team_id    TEXT NOT NULL,
  plugin_id  TEXT NOT NULL,
  key        TEXT NOT NULL,
  value      BLOB,
  PRIMARY KEY (team_id, plugin_id, key)
);
```

plugin 调 `ctx.storage.get(key)` 时 core 自动用 `(team_id, plugin_id)` 过滤——底层强制，不是约定。

`sessions` / `turns` / `messages` 表也加 `team_id` 列。

### 7.5 网络/文件系统隔离

复用 `platform/security/` 现有路径策略 + 拒绝列表，扩展三类约束：

| 资源 | 声明位置 | 实施位置 |
|---|---|---|
| 网络 | `permissions.network` | core 在 `fetch_url` / HTTP tool / MCP server spawn 前校验 URL |
| 文件 | `permissions.filesystem` | `read_file` / `write_file` / `bash_command` cwd 校验 |
| Env | `permissions.env` | spawn MCP server 时只透传声明的 env，其他屏蔽 |

声明之外的访问 → 直接 `permission_denied`，事件流可观测。

### 7.6 跨团队协作的兜底

team-b 想用 team-a 的 plugin：
- team-a 把 `visibility` 改成 `internal` 并加 team-b 到 `allowed_teams`
- 或 team-b fork 自己维护一份（plugin_id 改 `team-b/...`）

不存在"跨团队隐式可见"的灰色地带。

## 8. 长期蓝图

### 8.1 多语言 SDK 路线

| 语言 | 形态 | 状态 |
|---|---|---|
| Python | `sensenova-claw-sdk`：瘦客户端 + in-process MCP server 快捷 | 本期参考实现 |
| Node | `@sensenova-claw/sdk`：spawn core CLI + Control Protocol | 蓝图（独立 spec） |
| Go | `github.com/sensetime/sensenova-claw-go`：同上 | 蓝图 |
| Rust | `sensenova-claw-rs`：同上 | 蓝图 |

每个客户端只实现：spawn / 连接 core CLI；JSON-RPC 编解码；Control Protocol method 的语言友好封装；Event stream → async iterator / channel / Stream。预估每个客户端 ~500-1000 行。**协议是一份，客户端是 N 份薄壳。**

### 8.2 云端形态

```
                ┌─────────────────────────────────────┐
                │  云端 Sensenova-Claw Service        │
                │                                      │
   多租户 ────► │  ┌─ Gateway（鉴权、路由、限流） ─┐ │
                │  └────────────┬───────────────────┘ │
                │               │                      │
                │  ┌────────────▼───────────────────┐ │
                │  │ Control Protocol over WebSocket│ │
                │  └────────────┬───────────────────┘ │
                │               │                      │
                │  ┌────────────▼───────────────────┐ │
                │  │ Core 进程池                     │ │
                │  │ - 一会话一进程 / 进程池         │ │
                │  │ - 按 identity 隔离 plugin       │ │
                │  └────────────┬───────────────────┘ │
                │               │                      │
                │  ┌────────────▼───────────────────┐ │
                │  │ 持久化：PostgreSQL 替代 SQLite │ │
                │  │（Repository 接口换实现）        │ │
                │  └────────────────────────────────┘ │
                └─────────────────────────────────────┘
                          ▲
                          │ wss://
                          │
              ┌───────────┴────────────┐
              │ 任意语言 SDK           │
              │（同一份协议，换 URL）  │
              └────────────────────────┘
```

**关键设计选择**：本地和云端共享 100% Control Protocol。SDK 代码不区分本地还是云端——只是 `connect("stdio:./sensenova-claw")` 还是 `connect("wss://cloud.../client")` 的差别。

云端独立 spec 时要补：租户隔离（一个 org 一个 core 进程池 / 数据分库）、Plugin marketplace 服务化、计费/配额、WebSocket 鉴权（Token / mTLS）、持久化层从 SQLite 换 PostgreSQL（**Repository 抽象本期就要留好接口**）。

### 8.3 前端开源形态

前端只做展示和开源 demo，不内置业务能力。

```
sensenova-claw-web/
├── apps/
│   └── dashboard/                          # Next.js 14（沿用现有）
│       └── 通过 Control Protocol over WS 连 core
├── packages/
│   ├── sdk-react/                          # Node SDK 的 React hooks 封装
│   │   - useSession() / useTurnEvents() / usePermissionDialog()
│   └── ui-kit/                             # 可复用组件
└── examples/
    ├── chat-minimal/                       # 最简 chat
    ├── plugin-showcase/                    # 演示加载第三方 plugin
    └── multi-agent/                        # 多 agent 切换 demo
```

OSS 范围：core CLI + Python SDK + Web Dashboard。
闭源：商业云端服务。
开放：Plugin marketplace 协议（任何人可建私有 marketplace）。

### 8.4 演进顺序

```
M0（本期）：
  ├─ Core 重构出 harness 抽象 + Plugin Loader + 编排循环（保留现有语义）
  ├─ Control Protocol v1（stdio）
  ├─ ★ 新增 sensenova-claw serve --stdio 子命令（复用现有 main.py 分发）
  ├─ Python SDK（瘦客户端）
  ├─ Hook 子进程协议
  ├─ MCP 三路径接入
  ├─ 多团队隔离的 identity / namespace / 存储分隔
  └─ Repository 接口抽出（为 PostgreSQL 后续替换留口子）

M1：Node SDK + Control Protocol over WebSocket
  ├─ ★ sensenova-claw serve --ws 子命令（复用 interfaces/ws/ 传输层）
  ├─ Node SDK 瘦客户端
  └─ （可选）TUI 客户端重构走 Python SDK，dogfood 验证

M2：Go / Rust SDK

M3：云端服务 + PostgreSQL Repository

M4：Plugin Marketplace 服务化 + 前端开源仓库切出
```

### 8.5 现有 CLI 命令复用

新增 `serve` 子命令，与现有 `run`（前端开发体验）/ `cli`（终端用户体验）/ `version` 并列：

```
sensenova-claw run                    # 不动（前端 + backend）
sensenova-claw cli                    # 不动（TUI 客户端）
sensenova-claw serve --stdio          # ★ M0 新增：SDK 子进程模式
sensenova-claw serve --ws  HOST:PORT  # ★ M1 新增：WebSocket 模式
sensenova-claw serve --tcp HOST:PORT  # 蓝图
```

`serve --stdio` 模式约束：不起 HTTP/WS server；stdout 只走 Control Protocol；日志改走 stderr 或 file。

| 现有资产 | M0/M1 怎么用 |
|---|---|
| `interfaces/ws/` Gateway 代码 | M1：WS 传输层直接复用，换上层协议（前端 WS protocol → Control Protocol） |
| `interfaces/http/` REST 端点 | 保留给前端 Web 用，不进 Control Protocol |
| `app/cli/cli_client.py` TUI | M1 可重构成 Python SDK 客户端（dogfood） |
| `app/main.py` 子命令分发 | 直接加 `serve` 子命令 |
| `platform/config/` `platform/secrets/` | 全部复用 |

## 9. 不在范围

以下不在本期 spec 中，需独立 spec：

- 多语言 SDK 的具体实现（Node/Go/Rust）
- 云端服务架构（Gateway、租户隔离、计费、PostgreSQL 迁移）
- Plugin marketplace 服务（注册、发现、版本管理、签名）
- 前端开源仓库切出方案
- 现有 sensenova-claw 各模块到新 plugin manifest 的迁移细节（builtin plugin 怎么定义、tool/skill/agent 怎么改造）
- Control Protocol 的完整 JSON Schema 文件（本 spec 给字段，schema 文件在实现时落 `docs/protocols/`）
- Hook input envelope 各 event 的 `context` 详细 schema（同上）

## 10. 风险与开放问题

- **Control Protocol 和 MCP 双协议**的认知成本：业务团队既要懂"用 MCP 加工具"，又要懂"用 Python SDK 调 core"。文档要清晰区分两者职责。
- **Hook 子进程性能**：每次 LLM/tool 调用都 spawn 一个进程开销不低。M0 先不做优化，必要时引入 hook 长驻进程模式（保留扩展空间，本期不做）。
- **Plugin 热重载**：开发体验需要，但生产环境不应允许。`plugin.reload` method 可能要按 identity / 环境限权。
- **Repository 抽象的颗粒度**：本期为云端 PostgreSQL 留口子，但抽象太早可能错；建议本期只抽出最小必要接口（`SessionRepo`、`TurnRepo` 等），不试图覆盖所有未来场景。
- **Identity 默认值的安全性**：本地 `local-dev / local-team / local-org` 默认便利但有风险（误把生产环境当本地）。需要明确规则：云端启动必须显式传 identity，否则拒绝启动。
