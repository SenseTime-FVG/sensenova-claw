# Sensenova-Claw Agent Harness SDK — 完整功能清单

- 版本：v1.0
- 日期：2026-04-29
- 维度：按**功能域**组织，不分排期
- 来源：合并 [Spec](2026-04-27-agent-harness-sdk-design.md) / [Plan 拆分](2026-04-27-plan-decomposition.md) / [PRD](2026-04-29-agent-harness-sdk-prd.md) 三份文档的全部功能项

> 排期维度参见 [PRD §5 / §7](2026-04-29-agent-harness-sdk-prd.md)。本文档**只看"做什么"，不看"什么时候做"**。

---

## 1. Harness Core（运行时内核）

### 1.1 事件系统
- `EventEnvelope` 数据结构：`event_id` / `type` / `session_id` / `turn_id` / `trace_id` / `payload` / `source`
- `PublicEventBus` 全局事件总线
- `BusRouter` 按 `session_id` 路由
- `PrivateEventBus` 每 session 物理隔离
- 事件持久化（落 SQLite，可回放）
- 事件订阅与过滤（按 type / session / turn / source）

### 1.2 编排循环（Runtime）
- `AgentRuntime`：监听 `user.input`，发布 `agent.step_*`
- `LLMRuntime`：监听 `llm.call_requested`，发布 `llm.call_completed`
- `ToolRuntime`：监听 `tool.call_requested`，发布 `tool.call_completed`
- `TitleRuntime`：自动生成会话标题
- 编排循环：`user.input → agent.step_started → llm → tool → llm → ... → agent.step_completed`
- 多步循环（直到 LLM 不再返回 tool_calls）
- Turn 取消（`turn.cancel` 方法 + 中断 LLM/tool 调用）
- Step 跨 turn 状态隔离

### 1.3 Session 与 Turn 管理
- `SessionStateStore` 内存状态（Turn / Message / 工具调用状态）
- Session 创建 / 列出 / 删除 / fork / resume
- Turn 状态机（pending / running / completed / failed / cancelled）
- Message 历史（含分页查询）
- 跨 Session 消息隔离

### 1.4 存储层
- SQLite 默认实现
- Repository 抽象接口（为 PostgreSQL 等后端预留）
- 默认表：`sessions` / `turns` / `messages` / `events` / `agent_messages` / `cron_jobs` / `cron_runs`
- 多团队字段：`team_id` 列（自动加入所有上述表）
- `plugin_kv` 表：`(team_id, plugin_id, key, value)` 复合主键
- 透明 namespace 写入（plugin 调 `ctx.storage.get/set` 自动加 team_id + plugin_id 前缀）
- DB 迁移脚本（向后兼容、可回滚）
- 替换为 PostgreSQL 实现（云端形态）

### 1.5 配置管理
- `ConfigManager` 统一配置写入入口
- YAML 配置文件 + `${ENV_VAR}` 环境变量解析
- `~/.sensenova-claw/config.yml` 用户级配置
- 项目级 `config.yml` 与 `.sensenova-claw/config.yaml` 双格式
- 配置合并优先级：DEFAULT_CONFIG < 文件 < 环境变量
- `ConfigFileWatcher` 文件变更监听（watchdog）
- `config.updated` 事件广播
- 下游模块自动刷新（LLMFactory / AgentRegistry / MemoryManager）

### 1.6 Secret 管理
- 明文 → keyring 迁移工具
- Secret 工具：`get_secret` / `write_secret`
- 配置脱敏读取（`config.get` 不返回 secret 明文）

---

## 2. Plugin 系统

### 2.1 Plugin Manifest
- `plugin.yaml` 文件格式（YAML + JSON Schema 校验）
- 顶层字段：`schema_version` / `id` / `version` / `name` / `description` / `author` / `license` / `homepage`
- 兼容性字段：`sensenova_claw.min_version` / `max_version`
- 隔离字段：`owner` / `visibility` / `allowed_teams` / `allowed_users`
- 安全字段：`permissions.network` / `filesystem` / `env`
- 配置字段：`config.schema`（JSON Schema）
- 贡献字段：`contributes.{llm_providers, tools, channels, skills, agents, hooks, commands, mcp_servers}`
- Manifest 校验流程（schema → 兼容性 → visibility → permissions → config → contributes）
- 校验失败的 plugin 进入 `disabled` 状态（不影响 core 启动）

### 2.2 PluginLoader
- 扫描多个 PluginSource
- 按 identity 过滤可见性
- 加载 manifest、校验、注入 Registry
- `InstallReport` 收集失败项（不抛异常）

### 2.3 PluginSource（来源）
- `BuiltinPluginSource`（随 core 分发）
- `UserPluginSource`（`~/.sensenova-claw/plugins/`）
- `TeamPluginSource`（git 仓库 / 团队私有目录）
- `OrgMarketplaceSource`（公司私有 marketplace）

### 2.4 内置 Plugin（4 个）
- `core/builtin-tools`（覆盖现有 17+ tool）
- `core/builtin-llm`（4 个 LLM provider）
- `core/builtin-skills`（24 个 bundled skill）
- `core/builtin-channels`（websocket + 飞书 channel）

### 2.5 Plugin 生命周期
- 启动期加载
- 运行时启用 / 禁用（`plugin.enable` / `plugin.disable`）
- 热重载（`plugin.reload`，开发模式专用）
- 失败回滚（plugin 加载失败不影响 core）

### 2.6 Plugin 命名空间
- 全局 ID：`{plugin_id}::{contribution_id}`
- 跨 plugin 引用：`team-a/crm-assistant::send_email`
- Core 内置引用：`core::bash_command`
- 通配引用：`core::*`
- LLM 看到的 tool name 始终带 namespace 前缀

---

## 3. Contribution 类型（八种）

### 3.1 LLM Providers
- `type: python`：继承 `LLMProvider` 类
- `type: http`：兼容 OpenAI API endpoint
- `type: mcp`：通过 MCP server 提供
- 多 model 声明（`models[]` 含 `id` / `context_window`）
- 默认 4 个 provider：openai / anthropic / gemini / mock
- 流式 token 输出（蓝图）

### 3.2 Tools（三种接入方式）
- **Python 快速通道**：`type: python`，继承 `Tool` 类
- **MCP 主路径**：`type: mcp`，引用 `mcp_servers` 中的 server
- **HTTP**：`type: http`，业务现有 REST API 直接套
- 输入 JSON Schema（反射或显式 `schema_path`）
- Tool 风险等级（low / medium / high）
- 用户确认要求（`requires_user_consent`）

#### 内置 Tool（M0 必须覆盖）
- 通用：`bash_command` / `read_file` / `write_file` / `edit_file` / `apply_patch` / `fetch_url` / `manage_todolist`
- 搜索：`serper_search` / `image_search` / `brave_search` / `baidu_search` / `tavily_search`
- 邮件（6 个）：`send_email` / `list_emails` / `read_email` / `download_attachment` / `mark_email` / `search_emails`
- Obsidian：`obsidian_locate_and_setup` / `obsidian_index` / `obsidian_list_vaults` / `obsidian_read` / `obsidian_search` / `obsidian_write`
- 编排：`create_agent` / `ask_user` / `send_message`
- Secret：`get_secret` / `write_secret`
- 条件注册：`cron_tool` / `memory_search`

### 3.3 Channels
- `type: python`：继承 `Channel` 类
- `auto_start: bool`
- 默认 channel：`WebSocketChannel` / `FeishuChannel`
- 多 channel 共存
- Channel 仅支持 Python 实现（in-process，事件总线交互密集）

### 3.4 Skills
- Markdown + YAML frontmatter 格式（`SKILL.md`）
- `name` / `description` / `metadata.sensenova-claw.requires.bins`
- Body 懒加载（LLM 选中时才读）
- `enabled_by_default: bool`
- `skills_state.json` 启用状态持久化
- 多步骤声明式编排
- 条件分支
- 内置 24 个 skill（PPT / 飞书 / 搜索 / 系统运维 / 知识管理）

### 3.5 Agents
- Markdown + YAML frontmatter（`agent.md`）
- 三种来源：builtin / plugin / user-project-policy（覆盖优先级）
- `tools[]` 白名单（agent 实际可见的 tool）
- `skills[]` 白名单
- `llm.provider` + `llm.model`
- 多 Agent 配置
- Agent 私有 tool / skill（`agents/<id>/tools/`、`agents/<id>/skills/`）
- Agent-to-Agent 消息（`send_message` 工具）
- 动态创建 Agent（`create_agent` 工具）

### 3.6 Hooks（在编排循环触发的子进程）
- 9 个 event：`OnSessionStart` / `OnSessionEnd` / `OnUserInput` / `PreLLM` / `PostLLM` / `PreTool` / `PostTool` / `OnError` / `OnConfigUpdated`
- Matcher 过滤：`tool_name` / `agent_id` / `session_id` 模式匹配
- 两种类型：`subprocess`（任意语言）/ `python`（in-process）
- 4 种 decision：`continue` / `block` / `mutate` / `replace`
- Input envelope schema（含 `hook_id` / `event` / `session_id` / `turn_id` / `trace_id` / `identity` / `context` / `timestamp`）
- Output envelope schema（`decision` / `reason` / `mutations` / `replacement` / `diagnostics`）
- 串行 blocking 模式（mutation chain）
- 并行 fire-and-forget 模式
- 失败模型：`on_failure: block | continue`，超时 kill，bad JSON 等同超时
- Hook 长驻进程模式（性能优化，蓝图）

### 3.7 Commands
- 斜杠命令（`/foo`）
- Markdown + YAML frontmatter
- `visibility: session | user | team | org`

### 3.8 MCP Servers
- 三种 transport：`stdio` / `sse` / `streamable-http`
- `auto_start: always | on_demand | never`
- `health_check` 健康探测
- `restart_policy` 重启策略 + `max_restarts`
- `permissions` 收敛 server 进程能力
- 环境变量透传（按 manifest 声明白名单）

---

## 4. 协议层

### 4.1 Control Protocol（SDK ↔ Core）
- JSON-RPC 2.0
- 双向（SDK→Core request / Core→SDK notification + reverse request）
- 行分隔 JSON（stdio）
- 协议版本协商（`protocol_version` 握手字段）
- 错误码：JSON-RPC 标准 + 自定义扩展（`-32000` 起）

#### Method 列表
- **Session 域**：`session.create` / `session.list` / `session.get_info` / `session.fork` / `session.delete` / `session.resume`
- **Turn 域**：`turn.send_input` / `turn.cancel` / `turn.get_messages`
- **Event 域**：`event.subscribe` / `event.unsubscribe` / `event`（S→C notification）
- **Permission 域**：`permission.request`（S→C）/ `permission.respond`（C→S）
- **Plugin 域**：`plugin.list` / `plugin.enable` / `plugin.disable` / `plugin.reload`
- **Capability 域**：`tool.list` / `agent.list` / `skill.list`
- **Config 域**：`config.get` / `config.set` / `config.subscribe`
- **MCP 反向 RPC 域**：`mcp.register_server`（C→S）/ `mcp.invoke`（S→C，反向调业务进程内 MCP tool）
- **健康域**：`ping` / `pong`

#### 传输形态
- stdio（默认，本地）
- WebSocket（云端 / 远程）
- TCP（蓝图）

### 4.2 MCP 协议（Core ↔ 业务工具 server）
- 复用业内标准 MCP（`@modelcontextprotocol/sdk` 等）
- stdio / SSE / Streamable HTTP
- in-process（SDK 反向 RPC 注入业务进程内 server）
- Tool 调用穿过 `PreTool`/`PostTool` hook（与 Python tool 一致）

### 4.3 Hook 子进程协议（Core ↔ 业务 hook）
- 子进程 + stdin/stdout JSON
- input envelope / output envelope schema
- 见 §3.6

---

## 5. SDK（多语言）

### 5.1 Python SDK（`sensenova-claw-sdk`）
- `Harness` 门面类（spawn core CLI + 协议编解码）
- `query()` async iterator API
- `tool()` 装饰器
- `create_sdk_mcp_server()` 工厂
- in-process MCP server 注册（`mcp.register_server` / `mcp.invoke` 反向 RPC）
- Permission handler 接口
- 错误类型映射（`PermissionDenied` / `PluginNotLoaded` / `SessionNotFound` / ...）
- Identity 传入（`Harness(identity=...)`）
- 进程崩溃恢复 + session resume
- Hello world 示例（`examples/sdk_minimal.py`）
- in-process tool 示例（`examples/sdk_inprocess_tool.py`）

### 5.2 Node SDK（`@sensenova-claw/sdk`）
- 同 Python SDK 的 API 对等（spawn / query / tool / mcp）
- TypeScript 类型定义
- 远程连接（WebSocket）

### 5.3 Go SDK（`github.com/sensetime/sensenova-claw-go`）
- 同 API 对等
- channel-based event stream

### 5.4 Rust SDK（`sensenova-claw-rs`）
- 同 API 对等
- async-stream-based event API

### 5.5 跨语言通用约束
- 所有 SDK 共享同一份 Control Protocol（无方言）
- 每个 SDK 是几百行的瘦客户端
- 协议 schema 版本协商
- 同一份 examples 在每语言都有对照实现

---

## 6. CLI

### 6.1 现有命令（保留不变）
- `sensenova-claw run`（一键起前后端）
- `sensenova-claw cli`（TUI 客户端）
- `sensenova-claw version`

### 6.2 新增命令
- `sensenova-claw serve --stdio`（SDK 子进程模式）
- `sensenova-claw serve --ws HOST:PORT`（WebSocket 模式）
- `sensenova-claw serve --tcp HOST:PORT`（TCP，蓝图）

### 6.3 CLI 行为约束
- `--stdio` 模式：stdout 仅协议；日志走 stderr / file；不起 HTTP/WS server
- `--ws` 模式：复用 `interfaces/ws/` 传输层
- 现有 e2e 测试不需修改

---

## 7. 多团队隔离

### 7.1 Identity
- `Identity` 数据类：`(user_id, team_id, org_id)` + `source` 诊断字段
- 来源链：explicit > env > file > default
- `Identity.default_local()`（local-dev / local-team / local-org）
- `Identity.from_env()`（`SENSENOVA_CLAW_USER_ID` / `TEAM_ID` / `ORG_ID`）
- `Identity.from_file(~/.sensenova-claw/identity.yaml)`
- `Identity.resolve()` 走全链
- 云端启动强制要求显式 identity（拒绝 default）

### 7.2 Plugin 可见性
- `visibility: public`（所有人可见）
- `visibility: internal`（`allowed_teams` 白名单）
- `visibility: private`（仅 owner team）
- 不可见 plugin **不进内存**（不是 UI 隐藏）

### 7.3 数据隔离
- 数据库行按 `team_id` 过滤
- Plugin storage API namespace（`(team_id, plugin_id, key)`）
- 跨 plugin / 跨 team 数据互不可见（底层强制）

### 7.4 网络 / 文件系统隔离
- `permissions.network`：URL 白名单（fetch_url / HTTP tool / MCP server spawn 前校验）
- `permissions.filesystem.read` / `.write`：路径白名单
- `permissions.env`：env 透传白名单（spawn MCP server 时屏蔽未声明 env）
- 复用现有 `platform/security/` 路径策略 + 拒绝列表

### 7.5 跨团队协作
- internal visibility + allowed_teams 显式授权
- Fork 路径（plugin_id 改名，自维护）
- 不存在"隐式跨团队可见"

---

## 8. 云端形态

### 8.1 Cloud Gateway
- 鉴权（Token / mTLS）
- 路由（按 org / team / user）
- 限流
- 计费集成

### 8.2 Core 进程池
- 一会话一进程 / 进程池
- 按 identity 隔离 plugin
- 进程崩溃自动恢复 + session resume

### 8.3 持久化
- PostgreSQL Repository（替代 SQLite）
- Repository 接口与 SQLite 完全一致

### 8.4 多租户
- Org / Team / User 三层隔离
- 数据分库 / 分 schema
- 配额 / 限速按 org

### 8.5 同源协议
- 与本地 100% 共享 Control Protocol
- SDK 切换本地/云端只换连接 URL（`stdio:./` ↔ `wss://...`）

---

## 9. Plugin Marketplace

### 9.1 注册中心
- Plugin 包注册（manifest + 代码包）
- 版本管理（SemVer）
- 签名校验（防篡改）
- 公开 / 私有 marketplace

### 9.2 分发渠道
- 内置（随 core 发布）
- Org 私有 marketplace
- Team 仓库
- 用户本地

### 9.3 发现与安装
- 搜索 / 浏览
- 一键安装到指定 source
- 依赖解析（`sensenova_claw.min_version` / plugin 间依赖）

### 9.4 商业化（可选）
- 付费 plugin
- 订阅模型
- 计费集成

---

## 10. 前端与开源

### 10.1 Web Dashboard
- Next.js 14 + TypeScript
- 通过 Control Protocol over WebSocket 连 core
- 沿用现有前端代码

### 10.2 SDK-React 包
- React hooks 封装 Node SDK
- `useSession()` / `useTurnEvents()` / `usePermissionDialog()`
- 与 Node SDK 同步演进

### 10.3 UI Kit
- 可复用组件（消息气泡、工具卡片、permission 弹窗、agent 切换器）
- 开源、文档化

### 10.4 示例项目
- `chat-minimal`（最简 chat）
- `plugin-showcase`（演示加载第三方 plugin）
- `multi-agent`（多 agent 切换）

### 10.5 OSS 边界
- 开源：core CLI + Python SDK + Web Dashboard + UI Kit + Marketplace 协议
- 闭源：商业云端服务

---

## 11. 可观测性与运维

### 11.1 日志
- DEBUG 模式输出完整 LLM 调用输入
- 工具执行详情
- 事件流转追踪
- stderr / 文件双输出（serve --stdio 模式必须）

### 11.2 事件审计
- 每个事件含 `plugin_id` / `team_id`
- 按 team / plugin 维度查询
- 失败事件 `OnError` 收集

### 11.3 健康检查
- `ping` / `pong` 协议级
- MCP server 健康探测
- Plugin 加载状态查询（`plugin.list` 含状态字段）

### 11.4 性能指标
- Hook 子进程开销（P50 / P99）
- LLM 调用耗时
- 工具调用耗时
- Turn 端到端延迟

---

## 12. 安全

### 12.1 权限模型
- Plugin manifest 自报 `permissions`（network / filesystem / env）
- Core 启动时按声明限制
- 声明之外的访问 → `permission_denied` + 事件流可观测

### 12.2 用户确认
- Tool 高风险等级触发 `permission.request` 反向 RPC
- 用户回 allow / deny / edit
- 默认拒绝（保守）

### 12.3 沙箱（蓝图）
- gVisor / firecracker 级别（M3 云端再考虑）
- 当前只用进程隔离

### 12.4 拒绝列表
- 现有 `platform/security/denylist.py` 复用
- Plugin 不能突破 deny 规则

---

## 13. 兼容性承诺

### 13.1 终端用户体验 100% 兼容
- `sensenova-claw run` / `cli` / `version` 不动
- 前端 Dashboard 不动
- 现有 e2e 测试零修改通过

### 13.2 现有扩展代码兼容
- 17+ 内置 tool 不重写（外挂 manifest）
- 24 个 skill 不重写
- 4 个 LLM provider 不重写
- 飞书 Channel 最小改动

### 13.3 EventEnvelope 协议 100% 复用
- Control Protocol 不发明新 event 结构
- 现有事件类型不变
- 前端 WebSocket 协议不变

### 13.4 数据库轻量迁移
- 加 `team_id` 列（默认 `local-team`）
- 新 `plugin_kv` 表
- 老数据自动填默认值
- 可回滚

### 13.5 Roadmap 兼容承诺
- M0 → M1：协议不变，传输层加 WebSocket
- M1 → M2：协议不变，加多语言客户端
- M2 → M3：协议不变，core 端从 SQLite 换 PostgreSQL
- M3 → M4：Marketplace 服务化，前端切独立仓

---

## 14. 测试

### 14.1 单元测试
- 每个 Registry / Loader / Protocol codec 独立单元
- Plugin manifest schema 校验
- Hook decision 各分支

### 14.2 集成测试
- 完整握手 → send_input → event 流
- Permission 双向 RPC
- Hook 子进程 spawn 真子进程
- MCP 三路径各跑通一个端到端示例

### 14.3 端到端测试
- 现有 e2e 套件（兼容性闸门）
- 跨语言 SDK e2e（每语言至少一个 hello-world）
- 多团队隔离 e2e（两个 identity 互不可见）
- 云端连接 e2e

### 14.4 性能测试
- Hook 开销基准（P50 ≤ 5ms / P99 ≤ 20ms）
- 高并发 Turn 吞吐
- LLM 调用延迟回归

### 14.5 反指标守门
- 终端用户感知延迟变化 > 10% → 拒绝合并
- 任何破坏 SQLite 数据的迁移 → 拒绝合并
- 任何让现有 LLM provider 行为变化 → 拒绝合并

---

## 15. 文档

### 15.1 用户文档（业务团队工程师）
- 5 分钟快速开始
- Plugin 开发指南（按 contribution 类型分章）
- Hook 编写指南（含跨语言示例：bash / Go / Python / Node）
- MCP server 接入指南
- 多团队 identity 配置
- 故障排查

### 15.2 协议文档（生态合作）
- Control Protocol 完整 method 列表 + JSON Schema
- Hook envelope 各 event 的 context schema
- MCP 接入约定

### 15.3 平台文档（运维）
- 部署
- 监控指标
- 多租户配置
- 升级路径

### 15.4 设计文档（贡献者）
- 架构总览
- 事件流转
- 数据库 schema
- 关键决策记录（ADR）

---

## 16. 现有功能的迁移与保留

### 16.1 Skills 系统（保留）
- 24 个内置 skill（PPT / 飞书 / 搜索 / 知识管理 / 系统运维）
- SkillRegistry / skills_state.json
- Skill body 懒加载

### 16.2 多 Agent（保留）
- AgentRegistry
- Agent-to-Agent 消息
- 动态 create_agent

### 16.3 飞书 Channel（保留）
- 现有 plugin 形态最小改动迁移到新 manifest

### 16.4 Cron + Heartbeat（保留）
- `cron_tool` 工具
- 定时任务表（`cron_jobs` / `cron_runs`）
- 心跳巡检

### 16.5 记忆系统（保留）
- `memory_search` 工具
- MemoryManager
- 记忆配置（`memory.enabled`）

### 16.6 上下文压缩（保留）
- Turn 级压缩
- 合并压缩

### 16.7 Setup 流程（保留）
- 必配清单检查 API
- system-admin 自动配置（含 Obsidian vault 定位）
- LLM 页面单项编辑

### 16.8 不再保留 / 已删除
- Workflow 模块（v0.5 已删，不复活）

---

## 17. 暂不支持（明确不做）

- 自研 LLM 推理框架
- LangChain 全部组件替代品（chain / RAG）
- 实时流式 token 输出（M1+ 视需要）
- 移动端 SDK（iOS / Android）
- 商业模式细化（计费、订阅）
- 沙箱执行（gVisor / firecracker）

---

## 索引

- [PRD](2026-04-29-agent-harness-sdk-prd.md) — 立项与 Roadmap
- [Spec](2026-04-27-agent-harness-sdk-design.md) — 技术设计
- [Plan 拆分](2026-04-27-plan-decomposition.md) — 6 份独立 plan + 接口契约
