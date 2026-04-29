# Sensenova-Claw Agent Harness SDK — 完整功能清单

- 版本：v1.0
- 日期：2026-04-29
- 维度：按**功能域**组织，不分排期
- 来源：合并 [Spec](2026-04-27-agent-harness-sdk-design.md) / [Plan 拆分](2026-04-27-plan-decomposition.md) / [PRD](2026-04-29-agent-harness-sdk-prd.md) 三份文档的全部功能项

> 排期维度参见 [PRD §5 / §7](2026-04-29-agent-harness-sdk-prd.md)。本文档**只看"做什么"，不看"什么时候做"**。

---

## 总表（按功能域）

| # | 功能域 | 功能项 | 用户可见 | 可用语言 | 备注 |
|---|---|---|---|---|---|
| **1. Harness Core（不可替换内核）** ||||||
| 1.1 | 编排循环 | `user.input → agent.step_started → llm.* → tool.* → step_completed` 标准循环 | 间接 | — | 现状保留 |
| 1.2 | 事件总线 | `PublicEventBus` + `EventEnvelope`（event_id / type / session_id / turn_id / trace_id / payload / source） | 间接 | — | 100% 复用现状 |
| 1.3 | Plugin Loader | 扫描 source、读 manifest、schema 校验、按 identity 过滤、注入 registry | 间接 | — | 新增 |
| 1.4 | Plugin Source 抽象 | builtin / org marketplace / team repo / user local（可见性默认值不同） | 间接 | — | builtin + user 先实，其他蓝图 |
| 1.5 | Registry 抽象 | Tool / Skill / LLMProvider / Channel / Agent / Hook / Command 七类，统一 `register_from_plugin(entry)` | 间接 | — | 新增 |
| 1.6 | RegistryEntry | 全局 ID `{plugin_id}::{contribution_id}` + owner_plugin / owner_team / visibility / impl / metadata | 间接 | — | 新增 |
| 1.7 | InstallReport | 加载失败的 contribution 不抛异常，集中报告 | 间接 | — | 新增 |
| 1.8 | 存储抽象 | `Repository` 接口（SessionRepo / TurnRepo / MessageRepo / EventRepo），SQLite 默认实现 | 间接 | — | 抽象本期、PostgreSQL 蓝图 |
| **2. Plugin Manifest（业务接入面）** ||||||
| 2.1 | YAML 顶层字段 | id / version / owner / visibility / sensenova_claw{min/max}_version / permissions / config.schema | 业务团队 | YAML | 新增 |
| 2.2 | LLM Provider contribution | `type: python / mcp / http`；models 列表 | 业务团队 | YAML + Py/MCP | 新增 |
| 2.3 | Tool contribution（Py 路径） | `type: python` + `python: file:Class` 快速通道 | 业务团队 | Python | 新增 |
| 2.4 | Tool contribution（MCP 路径） | `type: mcp` + `mcp_server` + `tool_name` | 业务团队 | 任意 | 新增 |
| 2.5 | Tool contribution（HTTP 路径） | `type: http` + url 模板 + 输入 schema | 业务团队 | YAML | 新增 |
| 2.6 | Channel contribution | `type: python`，`auto_start` | 业务团队 | Python | 现状形态保留 |
| 2.7 | Skill contribution | `path: SKILL.md`，body 懒加载 | 业务团队 | Markdown | 现状形态保留 |
| 2.8 | Agent contribution | `path: agent.md` + tools 白名单 + skills + llm.provider/model | 业务团队 | Markdown | 现状形态保留 |
| 2.9 | Hook contribution | event + matcher + type(subprocess/python) + command + timeout + blocking + on_failure | 业务团队 | YAML+任意 | 新增 |
| 2.10 | Command contribution | 斜杠命令 path + visibility(session/user/team/org) | 业务团队 | Markdown | 现状形态保留 |
| 2.11 | MCP server contribution | transport(stdio/sse/http) + command/url + env + auto_start + health_check + restart_policy | 业务团队 | YAML | 新增 |
| 2.12 | 命名空间引用规则 | local: `tool_id` / cross: `team-x/p::tool` / core: `core::bash_command` | 业务团队 | — | 新增 |
| 2.13 | Manifest 校验流程 | 7 步校验 + 失败进 disabled 状态 | 间接 | — | 新增 |
| **3. Control Protocol（SDK ↔ Core）** ||||||
| 3.1 | 协议格式 | JSON-RPC 2.0；行分隔；双向 | 间接 | — | 新增 |
| 3.2 | stdio 传输 | 每行一个 JSON | 间接 | — | M0 默认 |
| 3.3 | WebSocket 传输 | 同协议换 frame | 间接 | — | M1 |
| 3.4 | TCP 传输 | 同协议换 frame | 间接 | — | 蓝图 |
| 3.5 | initialize 握手 | protocol_version + client_info + identity + config_overrides | SDK 用户 | 多语言 | 新增 |
| 3.6 | session.create / list / get_info / fork / delete / resume | 6 个 method | SDK 用户 | 多语言 | 新增 |
| 3.7 | turn.send_input / cancel / get_messages | 3 个 method | SDK 用户 | 多语言 | 新增 |
| 3.8 | event.subscribe / unsubscribe + event 推送 | 流式事件 | SDK 用户 | 多语言 | 新增 |
| 3.9 | permission.request / respond | 双向 RPC（core 反向问 client） | SDK 用户 | 多语言 | 新增 |
| 3.10 | plugin.list / enable / disable / reload | 4 个 method | SDK 用户 | 多语言 | 新增 |
| 3.11 | tool.list / agent.list / skill.list | 3 个 capability 查询 | SDK 用户 | 多语言 | 新增 |
| 3.12 | config.get / set / subscribe | 配置读写订阅 | SDK 用户 | 多语言 | 新增 |
| 3.13 | mcp.register_server / mcp.invoke | 反向 RPC（in-process MCP） | SDK 用户 | 多语言 | 新增 |
| 3.14 | ping / pong | 健康检查 | SDK 用户 | 多语言 | 新增 |
| 3.15 | 错误码扩展 | -32000~-32006（permission_denied / plugin_not_loaded / session_not_found / ...） | SDK 用户 | 多语言 | 新增 |
| 3.16 | 进程生命周期 | EOF / SIGTERM 优雅退出；崩溃恢复（client 重起 + session.resume） | SDK 用户 | 多语言 | 新增 |
| 3.17 | 协议演进 | protocol_version 协商 + minor/major 兼容策略 | 间接 | — | 新增 |
| **4. SDK 客户端（多语言）** ||||||
| 4.1 | Python SDK | `Harness` / `query()` async iterator / `tool()` decorator / `create_sdk_mcp_server()` | 业务团队 | Python | M0 |
| 4.2 | Python in-process MCP server | 业务进程内起 MCP，core 反向调（不 spawn 子进程） | 业务团队 | Python | M0 |
| 4.3 | Node SDK | `@sensenova-claw/sdk` + TypeScript 类型 | 业务团队 | Node | M1 |
| 4.4 | Go SDK | `github.com/sensetime/sensenova-claw-go` | 业务团队 | Go | M2 |
| 4.5 | Rust SDK | `sensenova-claw-rs` | 业务团队 | Rust | M2 |
| 4.6 | hello-world 示例 | `examples/sdk_minimal.py`（≤30 行） | 业务团队 | Python | M0 |
| 4.7 | in-process tool 示例 | `examples/sdk_inprocess_tool.py`（@tool + create_sdk_mcp_server） | 业务团队 | Python | M0 |
| 4.8 | 多语言示例（5 个） | 跨 SDK 的对照示例集 | 业务团队 | 各语言 | M1+ |
| **5. Hook 子进程协议** ||||||
| 5.1 | HookPipeline | 按 event 类型查 HookRegistry → spawn 子进程 | 间接 | — | 新增 |
| 5.2 | Input envelope | hook_id / event / session_id / turn_id / trace_id / identity / context / timestamp | 业务团队 | 任意 | 新增 |
| 5.3 | Output envelope | decision / reason / mutations / replacement / diagnostics | 业务团队 | 任意 | 新增 |
| 5.4 | Decision: continue | 放行 | 业务团队 | 任意 | 新增 |
| 5.5 | Decision: block | 中止 step，turn 失败 | 业务团队 | 任意 | 新增 |
| 5.6 | Decision: mutate | 替换字段后继续（messages / tool_args / response） | 业务团队 | 任意 | 新增 |
| 5.7 | Decision: replace | 跳过原调用，直接用 replacement（mock / cache） | 业务团队 | 任意 | 新增 |
| 5.8 | Event: OnSessionStart | session 创建后；可 mutate config | 业务团队 | 任意 | 新增 |
| 5.9 | Event: OnSessionEnd | session 关闭时；审计落库 | 业务团队 | 任意 | 新增 |
| 5.10 | Event: OnUserInput | 用户输入入队后；可 mutate input | 业务团队 | 任意 | 新增 |
| 5.11 | Event: PreLLM | LLM 调用前；可 mutate messages/tools | 业务团队 | 任意 | 新增 |
| 5.12 | Event: PostLLM | LLM 返回后；可 mutate response | 业务团队 | 任意 | 新增 |
| 5.13 | Event: PreTool | tool 调用前；可 mutate args / block | 业务团队 | 任意 | 新增 |
| 5.14 | Event: PostTool | tool 返回后；可 mutate result | 业务团队 | 任意 | 新增 |
| 5.15 | Event: OnError | 任意 runtime 异常；告警/上报 | 业务团队 | 任意 | 新增 |
| 5.16 | Event: OnConfigUpdated | config 变更后；重载下游缓存 | 业务团队 | 任意 | 新增 |
| 5.17 | Matcher 过滤 | tool_name / agent_id / session_id 模式匹配 | 业务团队 | YAML | 新增 |
| 5.18 | blocking hook | 串行执行，mutation 链式传递 | 业务团队 | 任意 | 新增 |
| 5.19 | fire-and-forget hook | 并发 spawn，结果忽略 | 业务团队 | 任意 | 新增 |
| 5.20 | 失败模式 | 非 0 退出 / 超时 / 非法 JSON 走 `on_failure: block\|continue` | 业务团队 | YAML | 新增 |
| 5.21 | hook 长驻进程模式 | 每次 spawn 性能优化 | 间接 | — | 蓝图（M1+） |
| **6. MCP 三路径接入** ||||||
| 6.1 | Path A: stdio MCP server | command + args + env + working_dir，core 子进程托管 | 业务团队 | 任意 | 新增 |
| 6.2 | Path B: SSE MCP server | url + headers，HTTP 长连 | 业务团队 | 任意 | 新增 |
| 6.3 | Path B: HTTP MCP server | StreamableHTTP 双向通信 | 业务团队 | 任意 | 新增 |
| 6.4 | Path C: in-process MCP server | SDK 内启动，通过反向 RPC 调用，无子进程 | 业务团队 | Python（M0），多语言（M2+） | 新增 |
| 6.5 | auto_start: always / on_demand / never | spawn 时机控制 | 业务团队 | YAML | 新增 |
| 6.6 | health_check | method + interval_seconds | 业务团队 | YAML | 新增 |
| 6.7 | restart_policy | never / on_failure / always + max_restarts | 业务团队 | YAML | 新增 |
| 6.8 | server 进程共享 | 一个 MCP server 被同 core 内所有 session 共享 | 间接 | — | 新增 |
| 6.9 | 多 client 隔离（metadata） | core 在请求 metadata 注入 session_id / identity，server 自决 | 业务团队 | — | 新增 |
| 6.10 | 关闭与清理 | core 退出 → SIGTERM；超时 → SIGKILL | 间接 | — | 新增 |
| **7. Identity / 多团队隔离** ||||||
| 7.1 | Identity 数据类 | (user_id, team_id, org_id) + source 来源标记 | SDK 用户 | 多语言 | 新增 |
| 7.2 | Identity 来源链 | 显式 > env > ~/.sensenova-claw/identity.yaml > default | SDK 用户 | 多语言 | 新增 |
| 7.3 | 默认 identity | local-dev / local-team / local-org（仅本地开发） | SDK 用户 | 多语言 | 新增 |
| 7.4 | visibility: public | 所有 team 可见 + 可启用 | 业务团队 | YAML | 新增 |
| 7.5 | visibility: internal | 所有 team 可见 + 仅 allowed_teams 可启用 | 业务团队 | YAML | 新增 |
| 7.6 | visibility: private | 仅 owner team 可见可启用 | 业务团队 | YAML | 新增 |
| 7.7 | allowed_teams / allowed_users | 白名单 | 业务团队 | YAML | 新增 |
| 7.8 | Plugin Loader 过滤算法 | 不可见 plugin 完全不加载（不是 UI 隐藏） | 间接 | — | 新增 |
| 7.9 | Registry namespace 注入 | 全局 ID 自动加 plugin_id 前缀，LLM 看见的也是带前缀 | 间接 | — | 新增 |
| 7.10 | DB team_id 列 | sessions / turns / messages / events / agent_messages 加列 | 间接 | — | 新增 |
| 7.11 | plugin_kv 表 | 每 plugin 独立 KV 存储，PK (team_id, plugin_id, key) | 业务团队 | Python ctx.storage | 新增 |
| 7.12 | Repository 透明过滤 | 所有 SQL 自动加 team_id where 条件 | 间接 | — | 新增 |
| 7.13 | DB 迁移脚本 | `python3 -m sensenova_claw.adapters.storage.migrate up` 幂等 | 平台运维 | CLI | 新增 |
| **8. 安全 / 权限声明** ||||||
| 8.1 | permissions.network | 白名单 URL pattern | 业务团队 | YAML | 新增 |
| 8.2 | permissions.filesystem | read / write 路径白名单 | 业务团队 | YAML | 新增 |
| 8.3 | permissions.env | 透传 env 白名单 | 业务团队 | YAML | 新增 |
| 8.4 | 权限实施点 | fetch_url / read_file / write_file / bash_command / MCP server spawn | 间接 | — | 复用 platform/security |
| 8.5 | Permission RPC | tool 高风险时反向问业务（allow/deny/edit） | SDK 用户 | 多语言 | 新增 |
| **9. 配置管理** ||||||
| 9.1 | Plugin config schema | manifest 内置 JSON Schema，用户传入时校验 | 业务团队 | YAML | 新增 |
| 9.2 | Config 变量插值 | `${env.X}` / `{config.api_endpoint}` 占位符 | 业务团队 | YAML | 新增 |
| 9.3 | Secret 存储 | keyring 集成（沿用现状） | 业务团队 | CLI | 现状保留 |
| 9.4 | Config 变更事件 | `config.updated` 事件流 | 业务团队 | 多语言 | 现状保留 |
| **10. CLI 入口** ||||||
| 10.1 | `sensenova-claw run` | 前端 + backend 一键启动 | 终端用户 | CLI | 不动 |
| 10.2 | `sensenova-claw cli` | TUI 客户端 | 终端用户 | CLI | 不动 |
| 10.3 | `sensenova-claw version` | 版本 | 终端用户 | CLI | 不动 |
| 10.4 | `sensenova-claw serve --stdio` | SDK 子进程模式 | SDK 用户 | CLI | 新增 |
| 10.5 | `sensenova-claw serve --ws HOST:PORT` | WebSocket 服务模式 | SDK 用户 | CLI | M1 |
| 10.6 | `sensenova-claw serve --tcp HOST:PORT` | TCP 服务模式 | SDK 用户 | CLI | 蓝图 |
| 10.7 | `sensenova-claw migrate up/down` | DB 迁移命令 | 平台运维 | CLI | 新增 |
| **11. 兼容性承诺** ||||||
| 11.1 | 终端用户体验 100% 兼容 | run / cli / 前端 Web 体验不变 | 终端用户 | — | 验收红线 |
| 11.2 | EventEnvelope 协议 100% 复用 | 不发明新结构 | 间接 | — | 验收红线 |
| 11.3 | 现有 e2e 0 修改 | tests/e2e 全部通过 | 间接 | — | 验收红线 |
| 11.4 | 现有 17+ tool 不重写 | 包成 builtin plugin | 业务团队 | Python | M0 |
| 11.5 | 现有 24 skill 不重写 | manifest path 引用 | 业务团队 | Markdown | M0 |
| 11.6 | 现有 4 LLM provider 不重写 | 包成 builtin plugin | 业务团队 | Python | M0 |
| 11.7 | DB 加列兼容迁移 | 老数据 team_id='local-team'，可回滚 | 平台运维 | CLI | M0 |
| 11.8 | 默认 local-team identity | 现有用户感觉不到 | 终端用户 | — | M0 |
| **12. 云端服务（M3+ 蓝图）** ||||||
| 12.1 | Cloud Gateway | 鉴权 / 路由 / 限流 / 计费 | 平台运维 | — | M3 |
| 12.2 | Token / mTLS 鉴权 | 接入云端的认证方式 | SDK 用户 | 多语言 | M3 |
| 12.3 | Core 进程池 | 一会话一进程 / 进程池 | 间接 | — | M3 |
| 12.4 | PostgreSQL Repository | 替换 SQLite，接口不变 | 间接 | — | M3 |
| 12.5 | Org × Team × User 三层隔离 | 多租户隔离 | 平台运维 | — | M3 |
| 12.6 | WebSocket Auth | wss + token | SDK 用户 | 多语言 | M3 |
| **13. Marketplace（M4+ 蓝图）** ||||||
| 13.1 | Plugin 注册中心 | 注册 / 发现 / 版本管理 | 业务团队 | Web + CLI | M4 |
| 13.2 | 签名校验 | plugin 防篡改 | 间接 | — | M4 |
| 13.3 | 私有 marketplace | 按 org 分发 | 业务团队 | Web | M3-M4 |
| 13.4 | 公共 marketplace | 跨组织 / OSS | 业务团队 | Web | M4 |
| **14. 前端（开源/展示）** ||||||
| 14.1 | Web Dashboard | Next.js 14（沿用现状） | 终端用户 | Web | 不动 |
| 14.2 | sdk-react | useSession / useTurnEvents / usePermissionDialog hooks | 业务团队 | React | M1+ |
| 14.3 | ui-kit | 消息气泡 / 工具卡片等可复用组件 | 业务团队 | React | M4 |
| 14.4 | 示例：chat-minimal | 最简 chat | 开发者 | Web | M4 |
| 14.5 | 示例：plugin-showcase | 演示加载第三方 plugin | 开发者 | Web | M4 |
| 14.6 | 示例：multi-agent | 多 agent 切换 | 开发者 | Web | M4 |
| **15. 可观测 / 治理（隐性需求）** ||||||
| 15.1 | 事件日志带 plugin_id / team_id | 审计可查 | 平台运维 | — | M0 |
| 15.2 | Hook 失败计数 | OnError 事件聚合 | 平台运维 | — | M0 |
| 15.3 | Plugin 启用/禁用持久化 | settings.json 写入 | 平台运维 | CLI/UI | 现状形态 |
| 15.4 | Plugin 热重载（开发用） | `plugin.reload` method | 开发者 | 多语言 | M0（受限） |
| 15.5 | 健康检查端点 | ping/pong + MCP server health_check | 平台运维 | — | M0 |
| **16. 文档 / DX（开发体验）** ||||||
| 16.1 | 协议文档站 | mdx + 多语言示例 | 业务团队 | Web | M1 |
| 16.2 | Method 速查表 | Control Protocol 全部 method 一图速览 | 开发者 | Web | M1 |
| 16.3 | 教程：写第一个 Plugin | 0 到 1 接入文档 | 业务团队 | Web | M0 |
| 16.4 | 教程：写第一个 Hook | 任意语言 | 业务团队 | Web | M0 |
| 16.5 | 教程：跨语言 SDK 接入 | 4 语言对照 | 业务团队 | Web | M2 |
| 16.6 | API 参考 | 自动生成 | 业务团队 | Web | M0 |
| 16.7 | 迁移指南 | 现有 fork → 新 plugin manifest | 业务团队 | Web | M0 |
| 16.8 | 故障排查手册 | 常见错误 / 性能问题 | 平台运维 | Web | M1 |

---

## 维度交叉视图

### 按"业务团队接触面"

业务团队真正会写、会读的东西，不超过这 5 类：

1. **Plugin manifest（YAML）**：声明所有贡献（§2 全部）
2. **Tool 实现**：Python 类 / MCP server / HTTP（§2.3-2.5、§6 全部）
3. **Hook 脚本**：任意语言子进程（§5 全部）
4. **SDK 调用代码**：Python/Go/Node/Rust（§4 全部）
5. **Skill / Agent / Command Markdown**：现状形态（§2.7、§2.8、§2.10）

### 按"内核 vs 扩展"

| 类型 | 数量级 | 说明 |
|---|---|---|
| 内核（业务不可换） | §1（8 项）+ §3（17 项 Control Protocol method）+ §10（CLI）= ~30 项 | 这是 SDK 的"骨头" |
| 扩展（业务可写） | §2 manifest（13 项）+ §5 Hook（21 项）+ §6 MCP（10 项）= ~44 项 | 这是 SDK 的"肉" |
| 兼容承诺 | §11（8 项）| 这是不能动的红线 |
| 蓝图（M1+） | §4（多语言）+ §12（云端）+ §13（marketplace）+ §14.2-14.6（前端开源）= ~25 项 | 后续 spec |

### 按"必交付 vs 渐进交付"

**M0 必须交付（验收红线）：** §1 全部 + §2 全部（schema + 8 类 contribution） + §3.1-3.2、3.5-3.16 + §4.1-4.2、4.6-4.7 + §5 全部 + §6.1-6.10 + §7 全部 + §8 全部 + §9 全部 + §10.4、10.7 + §11 全部 + §15.1-15.5 + §16.3-16.4、16.6-16.7

**M1 起渐进交付：** §3.3 WS / §4.3 Node / §10.5 / §16.1-16.2、16.5、16.8

**M2 起渐进交付：** §4.4 Go / §4.5 Rust / §6.4 多语言 in-process / §16.5

**M3 起渐进交付：** §12 云端全部 / §13.3 私有 marketplace

**M4 起渐进交付：** §13 marketplace / §14.2-14.6 前端开源

---

## 总数

| 范围 | 项数 |
|---|---|
| 全部功能项 | **≈ 130** |
| M0 必交付项 | **≈ 90** |
| M0 之后渐进项 | **≈ 40** |
