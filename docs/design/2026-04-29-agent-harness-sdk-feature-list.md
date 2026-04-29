# Agent Harness SDK — 完整功能清单（不分排期）

> 配套 PRD：[2026-04-29-agent-harness-sdk-prd.md](2026-04-29-agent-harness-sdk-prd.md)
>
> 本表把 PRD §5 中 M0-M4 所有**新增**功能拍平到一张大表，方便横向看清整个产品形态。
> 仅列新增；现有 sensenova-claw 已有能力（编排循环、事件总线、SQLite、24 个 skill 等）不重复列出。

## 完整功能清单

| # | 功能域 | 功能 | 描述 | 用户可见性 |
|---|---|---|---|---|
| 1 | **Harness Core** | PluginLoader | 扫描 plugin source、读 manifest、校验 schema、注入 Registry；按 identity 过滤可见性 | 内部基础设施 |
| 2 | Harness Core | RegistryEntry 抽象 | 所有 Registry 条目带 `owner_plugin / owner_team / visibility / namespace` | 内部基础设施 |
| 3 | Harness Core | 7 类 Registry 统一接口 | Tool / Skill / LLMProvider / Channel / Agent / Hook / Command 全部支持 `register_from_plugin(entry)` | 内部基础设施 |
| 4 | Harness Core | InstallReport | Plugin 加载失败不抛异常，进入 failures 列表，可观测 | 内部基础设施 |
| 5 | Harness Core | PluginSource 抽象 | builtin / marketplace / team / user 四种来源；本期实现 builtin + user | 平台运维 |
| 6 | **Plugin Manifest** | plugin.yaml schema | YAML 声明式清单：id / version / owner / visibility / permissions / config_schema | 业务团队主接触面 |
| 7 | Plugin Manifest | 8 类 contribution | llm_providers / tools / channels / skills / agents / hooks / commands / mcp_servers | 业务团队主接触面 |
| 8 | Plugin Manifest | Tool 三种接入方式 | python / mcp / http；Python 类、MCP server 引用、HTTP API 包装 | 业务团队 |
| 9 | Plugin Manifest | LLM Provider 三种接入 | python / mcp / http；包含 model 列表声明 | 业务团队 |
| 10 | Plugin Manifest | Hook 声明 | event 类型 + matcher + subprocess/python + blocking 策略 + on_failure | 业务团队 |
| 11 | Plugin Manifest | MCP Server 声明 | transport（stdio/sse/http）+ command + auto_start + restart_policy + health_check | 业务团队 |
| 12 | Plugin Manifest | Manifest 校验流程 | 读取 → schema → 兼容性 → visibility → permissions → config → 注入 Registry | 内部基础设施 |
| 13 | Plugin Manifest | 命名空间引用规则 | 本地 short_id / 跨 plugin `owner/name::id` / 内置 `core::id` | 业务团队 |
| 14 | **Control Protocol** | JSON-RPC 2.0 协议层 | Request / Response / Notification 编解码；id 关联 | 协议契约 |
| 15 | Control Protocol | stdio 传输 | 行分隔 JSON over stdin/stdout；EOF 优雅退出 | 协议契约 |
| 16 | Control Protocol | WebSocket 传输 | 同协议换 frame 格式；多 client 并发 | 云端 / 远程 |
| 17 | Control Protocol | initialize 握手 | 协议版本协商、client info、identity 注入、capabilities 返回 | 协议契约 |
| 18 | Control Protocol | Session 域 method | session.create / list / get_info / fork / delete / resume | 业务团队 |
| 19 | Control Protocol | Turn 域 method | turn.send_input / cancel / get_messages | 业务团队 |
| 20 | Control Protocol | Event 域 method | event.subscribe / unsubscribe；S→C `event` notification 流 | 业务团队 |
| 21 | Control Protocol | Permission 双向 RPC | S→C permission.request / C→S permission.respond（allow/deny/edit） | 业务团队 |
| 22 | Control Protocol | Plugin / Capability 域 | plugin.list/enable/disable/reload；tool.list / agent.list / skill.list | 业务团队 |
| 23 | Control Protocol | Config 域 | config.get / set / subscribe；触发 config.updated 事件 | 业务团队 |
| 24 | Control Protocol | MCP 反向 RPC | mcp.register_server（C→S）/ mcp.invoke（S→C） | SDK 内部 |
| 25 | Control Protocol | 错误码体系 | -32000 ~ -32006 自定义错误码（permission_denied / plugin_not_loaded / ...） | 协议契约 |
| 26 | Control Protocol | 进程生命周期 | EOF / SIGTERM 优雅退出；ping/pong 健康检查；崩溃恢复 + session.resume | 协议契约 |
| 27 | Control Protocol | 协议版本演进 | protocol_version 协商；新增 method 走 minor；签名变更走 major | 协议契约 |
| 28 | **Hook 子进程协议** | HookPipeline | 按 event 类型查 HookRegistry → matcher 过滤 → spawn 子进程 | 内部基础设施 |
| 29 | Hook 子进程协议 | 9 个 hook event | OnSessionStart / OnSessionEnd / OnUserInput / PreLLM / PostLLM / PreTool / PostTool / OnError / OnConfigUpdated | 业务团队 |
| 30 | Hook 子进程协议 | Input/Output envelope | hook_id / event / session_id / context / mutations / replacement / diagnostics | 业务团队 |
| 31 | Hook 子进程协议 | 4 种 Decision | continue / block / mutate / replace | 业务团队 |
| 32 | Hook 子进程协议 | Blocking vs fire-and-forget | 串行链式 mutation vs 并发不阻塞 | 业务团队 |
| 33 | Hook 子进程协议 | 失败模型 | 非 0 退出 / 超时 / 非法 JSON / 子进程崩溃 + on_failure 策略 | 业务团队 |
| 34 | Hook 子进程协议 | 跨语言 hook | 任何语言可读 stdin / 写 stdout JSON；bash/Go/Node/Rust 示例 | 业务团队 |
| 35 | **MCP 三路径** | Path A: stdio MCP server | manifest 声明 command/args/env；spawn 子进程 | 业务团队 |
| 36 | MCP 三路径 | Path B: SSE / HTTP MCP server | manifest 声明 url；HTTP 长连 | 业务团队 |
| 37 | MCP 三路径 | Path C: in-process MCP server | SDK 起 server；通过 mcp.register_server / mcp.invoke 反向 RPC | Python 业务团队快速通道 |
| 38 | MCP 三路径 | MCP 生命周期管理 | auto_start（always/on_demand/never）+ restart_policy + max_restarts + health_check | 平台运维 |
| 39 | MCP 三路径 | 进程隔离与共享 | 单 server 进程被同 core 内多 session 共享；metadata 注入 session_id/identity | 内部基础设施 |
| 40 | **Python SDK** | sensenova-claw-sdk 包 | `pip install sensenova-claw-sdk`；瘦客户端 | 业务团队 |
| 41 | Python SDK | Harness 门面类 | spawn core CLI + Control Protocol 编解码；async with 上下文管理 | 业务团队 |
| 42 | Python SDK | query() async iterator | `async for event in h.query("...")` 流式拿事件 | 业务团队 |
| 43 | Python SDK | tool() 装饰器 | 业务用 Python 写 tool，自动包成 in-process MCP | 业务团队 |
| 44 | Python SDK | create_sdk_mcp_server() | 一组 tool 打包成 in-process MCP server，通过反向 RPC 注册 | 业务团队 |
| 45 | Python SDK | hello-world 示例 | `examples/sdk_minimal.py`，30 行跑通 | 业务团队 |
| 46 | Python SDK | in-process tool 示例 | `examples/sdk_inprocess_tool.py`，演示自定义 tool 端到端 | 业务团队 |
| 47 | **Node SDK** | @sensenova-claw/sdk 包 | npm 安装；TypeScript 类型定义齐全 | 业务团队（JS/TS） |
| 48 | Node SDK | spawn / 远程双模式 | 本地 spawn core CLI 或远程连 wss:// | 业务团队（JS/TS） |
| 49 | Node SDK | React hooks 封装 | sdk-react 子包：useSession / useTurnEvents / usePermissionDialog | 前端开发者 |
| 50 | **Go SDK** | sensenova-claw-go 包 | `go get`；channel 风格事件流 | 业务团队（Go） |
| 51 | **Rust SDK** | sensenova-claw-rs crate | crates.io；async Stream 事件流 | 业务团队（Rust） |
| 52 | **多团队隔离** | Identity 三元组 | (user_id, team_id, org_id) 数据类 + 来源链解析 | 平台运维 |
| 53 | 多团队隔离 | Identity 来源优先级 | 显式 > 环境变量 > ~/.sensenova-claw/identity.yaml > 默认 local | 平台运维 |
| 54 | 多团队隔离 | Visibility 过滤 | public / internal+allowed_teams / private→owner-only | 平台运维 |
| 55 | 多团队隔离 | Registry namespace 注入 | LLM 看到的 tool 名为 `team-a/plugin::tool` 全限定 | 平台运维 |
| 56 | 多团队隔离 | DB team_id 列 | sessions/turns/messages/events/agent_messages 加列 + Repository 透明过滤 | 平台运维 |
| 57 | 多团队隔离 | plugin_kv 表 | 按 (team_id, plugin_id, key) 隔离的 KV 存储 API | 业务团队 |
| 58 | 多团队隔离 | 网络/文件/env 权限 | manifest permissions 声明 → core 强制校验 → permission_denied 错误 | 业务团队 |
| 59 | 多团队隔离 | DB 迁移脚本 | `python3 -m sensenova_claw.adapters.storage.migrate up`；幂等 | 平台运维 |
| 60 | **CLI 子命令** | sensenova-claw serve --stdio | SDK 用的 headless 后端；stdout 仅协议、日志走 stderr | 业务团队 / SDK |
| 61 | CLI 子命令 | sensenova-claw serve --ws | WebSocket 模式；远程接入 | 云端 / 远程 |
| 62 | CLI 子命令 | sensenova-claw serve --tcp | TCP 模式；保留蓝图 | 蓝图 |
| 63 | **TUI 重构（可选）** | cli_client 改走 SDK | 现有 TUI 用 Python SDK 接 core，dogfood SDK | 平台运维 / 用户透明 |
| 64 | **云端服务** | Cloud Gateway | 多租户鉴权（Token / mTLS）+ 路由 + 限流 + 计费 | 终端业务 |
| 65 | 云端服务 | Core 进程池 | 一会话一进程或共享池；按 identity 隔离 | 平台运维 |
| 66 | 云端服务 | PostgreSQL Repository | 替换 SQLite 实现；Repository 接口不变 | 平台运维 |
| 67 | 云端服务 | 多租户三层隔离 | Org × Team × User 三层身份 + 数据分库 | 终端业务 |
| 68 | 云端服务 | 计费 / 配额 | 按租户、按调用计量 | 商业化 |
| 69 | **Plugin Marketplace** | 私有 Marketplace（基础） | 按 org 分发 plugin；签名校验 | 平台运维 |
| 70 | Plugin Marketplace | Marketplace 服务化 | 注册、发现、版本管理、跨 org 公开 plugin | 业务团队 / 第三方 |
| 71 | Plugin Marketplace | 协议开放 | 任何人可建私有 marketplace（开源协议） | 生态 |
| 72 | **前端开源** | sensenova-claw-web 仓库 | 独立仓库或 monorepo 子包；Next.js 14 Dashboard | 开发者社区 |
| 73 | 前端开源 | sdk-react 包 | React hooks + Provider | 前端开发者 |
| 74 | 前端开源 | ui-kit 包 | 消息气泡、工具卡片等可复用组件 | 前端开发者 |
| 75 | 前端开源 | 三个示例项目 | chat-minimal / plugin-showcase / multi-agent | 开发者社区 |
| 76 | 前端开源 | 商业 vs 开源 Dashboard 区分 | 闭源云端 Dashboard 与开源 Dashboard 切分 | 商业化 |
| 77 | **文档** | API 参考 | 每个 Control Protocol method 都有示例 | 业务团队 |
| 78 | 文档 | Hook envelope schema | JSON Schema + 各语言类型生成 | 业务团队 |
| 79 | 文档 | 接入教程 | 每类 contribution 都有 0→1 教程 | 业务团队 |
| 80 | 文档 | 多语言 API 对照表 | 同一概念在 Python/Node/Go/Rust 中的写法对照 | 业务团队 |

## 按功能域汇总

| 功能域 | 数量 |
|---|---|
| Harness Core | 5 |
| Plugin Manifest | 8 |
| Control Protocol | 14 |
| Hook 子进程协议 | 7 |
| MCP 三路径 | 5 |
| Python SDK | 7 |
| Node SDK | 3 |
| Go / Rust SDK | 2 |
| 多团队隔离 | 8 |
| CLI 子命令 | 3 |
| TUI 重构 | 1 |
| 云端服务 | 5 |
| Plugin Marketplace | 3 |
| 前端开源 | 5 |
| 文档 | 4 |
| **合计** | **80** |
