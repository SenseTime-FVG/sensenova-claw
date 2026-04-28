# Agent Harness SDK 实现计划拆分

- 配套 spec：[2026-04-27-agent-harness-sdk-design.md](2026-04-27-agent-harness-sdk-design.md)
- 目的：把 spec §9.6 的 9 步迁移路径拆成 6 份独立可执行的 plan，并钉死 plan 之间的接口契约，避免并行写 plan 时各 plan 互相对不上。

## 1. 拆分原则

- 每份 plan 产出独立可测试、独立可回滚的工作软件
- 每份 plan 控制在 ~300-600 行
- plan 之间通过**冻结的接口契约**通信（本文 §3）
- 不写 plan 间的"详细实现"——那是各 plan 自己的事

## 2. 6 份 Plan 的范围与依赖

```
P1 (Loader + Registry 抽象)
  │
  └─► P2 (内置能力挂 manifest，改 Registry 走 Loader)
       │
       └─► P3 (serve --stdio + Control Protocol Server)
            │
            ├─► P4 (Python SDK)
            ├─► P5 (Identity + DB 迁移)
            └─► P6 (Hook + MCP 三路径)   ◄── P4/P5/P6 可真并行执行
```

| Plan | 标题 | 覆盖 spec 章节 | 对应 §9.6 步骤 | 依赖 |
|---|---|---|---|---|
| P1 | PluginLoader 与 Registry 抽象 | §4.1 §4.4 §4.5（manifest schema 框架）+ §7.3（namespace 抽象） | 1 | 无 |
| P2 | 内置能力包成 plugin manifest | §4.3（具体 contribution）+ §9.2（迁移映射） | 2-3 | P1 |
| P3 | serve --stdio + Control Protocol Server | §3（架构）+ §5（Control Protocol） | 4-5 | P2 |
| P4 | Python SDK 瘦客户端 | §5（SDK 侧）+ §6.2 Path C（in-process MCP） | 6 | P3 |
| P5 | 多团队 identity + DB 迁移 | §7（多团队隔离）+ §9.4（DB 迁移） | 7-8 | P4 |
| P6 | Hook 子进程协议 + MCP 三路径接入 | §6.1（Hook）+ §6.2 Path A/B（外部 MCP） | （横切，独立块） | P3 |

### 范围边界（每份 plan 写"我覆盖什么、我不覆盖什么"）

#### P1 范围
- ✓ `PluginLoader` 类（扫描、读 manifest、校验、注入 registry）
- ✓ `RegistryEntry` 数据类（带 owner_plugin / namespace / visibility 字段）
- ✓ 各 Registry 增加 `register_from_plugin(entry)` 方法
- ✓ Plugin manifest YAML schema 校验器（jsonschema 或 pydantic）
- ✓ Plugin source 抽象（builtin / marketplace / team / user，本期只实 builtin + user）
- ✗ 不实际把现有内置能力包成 plugin（P2 做）
- ✗ 不做 visibility 过滤（P5 做）
- ✗ 不做 manifest 中 mcp_servers / hooks 的执行（P6 做）

#### P2 范围
- ✓ 创建 4 个内置 plugin 目录：`core/builtin-tools` / `core/builtin-llm` / `core/builtin-skills` / `core/builtin-channels`
- ✓ 给每个内置 plugin 写完整 `plugin.yaml`，覆盖现有所有 17+ tool / 24 skill / 4 LLM provider / 1 channel
- ✓ 改 `ToolRegistry._register_builtin()` / `SkillRegistry` / `LLMFactory` 等，统一走 `PluginLoader`
- ✓ e2e 跑通——行为完全等价，前端 / TUI / 现有 e2e 不需要改
- ✗ 不引入任何新功能（hooks / identity / control protocol）

#### P3 范围
- ✓ `sensenova-claw serve --stdio` 子命令（`app/main.py` 加 `serve` 分发）
- ✓ Control Protocol Server（JSON-RPC 2.0 over stdio，行分隔）
- ✓ 实现 §5.3 Method 列表中所有 method（除 `mcp.register_server` / `mcp.invoke`，留给 P4）
- ✓ EventEnvelope 流式推送（订阅模型）
- ✓ Permission 双向 RPC
- ✓ 命令行启动后 stdout 仅走协议、日志走 stderr
- ✗ 不实现 SDK 客户端（P4 做）
- ✗ 不实现 identity 过滤（P5 做，本 plan 用占位 `local-team`）
- ✗ 不实现 WebSocket 传输（蓝图）

#### P4 范围
- ✓ `sensenova-claw-sdk` Python 包（独立子包 `sdk/`）
- ✓ `Harness` 门面类（spawn core CLI 子进程 + 协议编解码）
- ✓ `query()` async iterator API
- ✓ `tool()` / `create_sdk_mcp_server()` 装饰器（in-process MCP server 注册）
- ✓ `mcp.register_server` / `mcp.invoke` 反向 RPC
- ✓ 提供 hello-world 示例（`examples/sdk_minimal.py`）
- ✗ 不打包发布到 PyPI（独立任务）
- ✗ 不做多语言客户端

#### P5 范围
- ✓ `Identity` 数据类 + 来源链解析（spec §7.1）
- ✓ `Harness(identity=...)` 接受 identity，握手时传给 core
- ✓ PluginLoader 按 visibility 过滤
- ✓ Registry 注入时打 namespace 前缀
- ✓ DB 迁移脚本：sessions/turns/messages/events/agent_messages 加 `team_id` 列；新 `plugin_kv` 表
- ✓ Repository 层透明加 `team_id` 过滤
- ✓ 默认 identity（`local-dev / local-team / local-org`）
- ✗ 不做 PostgreSQL（蓝图）
- ✗ 不做 marketplace（蓝图）

#### P6 范围
- ✓ `HookPipeline` 类（按 event 类型查 HookRegistry → spawn 子进程）
- ✓ Hook input/output envelope schema（spec §6.1）
- ✓ Hook Decision 处理（continue / block / mutate / replace）
- ✓ blocking / fire-and-forget 两种模式
- ✓ MCP server 配置（spec §4.3.8）→ McpSessionManager 接入（已有）
- ✓ 在编排循环关键节点接入 hook 触发
- ✗ 不做 in-process MCP（P4 做）
- ✗ 不做 hook 长驻进程优化（蓝图）

## 3. 接口契约（冻结）

以下接口签名由本文档钉死，所有 6 份 plan 必须按此引用。**plan 不能擅自改这些签名**——如有需要变更，更新本文档后同步所有 plan。

### 3.1 PluginManifest（P1 定义；P2~P6 引用）

```python
# sensenova_claw/platform/plugins/manifest.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Visibility = Literal["public", "internal", "private"]

@dataclass
class PluginPermissions:
    network: list[str] = field(default_factory=list)
    filesystem_read: list[str] = field(default_factory=list)
    filesystem_write: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)

@dataclass
class PluginManifest:
    schema_version: str            # "1"
    id: str                        # e.g. "team-a/crm-assistant"
    version: str                   # SemVer
    name: str
    description: str
    owner: str                     # team id
    visibility: Visibility
    allowed_teams: list[str] = field(default_factory=list)
    allowed_users: list[str] = field(default_factory=list)
    min_core_version: str = "1.2.0"
    max_core_version: str | None = None
    permissions: PluginPermissions = field(default_factory=PluginPermissions)
    config_schema: dict | None = None
    contributes: dict = field(default_factory=dict)   # 各类 contribution 的字典
    root_path: Path = field(default_factory=Path)     # plugin 目录
```

### 3.2 RegistryEntry（P1 定义；所有 Registry 用）

```python
# sensenova_claw/platform/plugins/registry_entry.py
from dataclasses import dataclass
from typing import Any

@dataclass
class RegistryEntry:
    id: str                 # 全局：f"{plugin.id}::{contribution.id}"
    short_id: str           # plugin 内部短名
    owner_plugin: str       # plugin id
    owner_team: str
    visibility: str         # public | internal | private
    impl: Any               # 实际实现引用（Tool 实例 / LLMProvider 实例 / Skill / ...）
    metadata: dict          # 各 Registry 自定义
```

### 3.3 PluginLoader 接口（P1 定义；P2~P6 调用）

```python
# sensenova_claw/platform/plugins/loader.py
class PluginLoader:
    def __init__(self, sources: list["PluginSource"]) -> None: ...

    def load_all(self, identity: "Identity | None" = None) -> list[PluginManifest]:
        """扫描所有 source，返回（按 identity 过滤后的）可见 plugin manifest。
        identity=None 时不过滤（P1/P2/P3 用），P5 接入后传真实 identity。"""

    def install_into_registries(
        self,
        manifests: list[PluginManifest],
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        llm_registry: "LLMProviderRegistry",
        channel_registry: "ChannelRegistry",
        agent_registry: "AgentRegistry",
        hook_registry: "HookRegistry",
        command_registry: "CommandRegistry",
    ) -> "InstallReport":
        """把每个 manifest 的 contributes 解析成 RegistryEntry 注入到对应 Registry。
        失败的 contribution 进入 InstallReport.failures，不抛异常。"""
```

### 3.4 Identity（P5 定义；P3/P4 占位实现）

```python
# sensenova_claw/platform/identity/identity.py
from dataclasses import dataclass

@dataclass
class Identity:
    user_id: str
    team_id: str
    org_id: str

    @classmethod
    def default_local(cls) -> "Identity":
        return cls(user_id="local-dev", team_id="local-team", org_id="local-org")
```

P3 / P4 在 P5 上线前用 `Identity.default_local()` 作占位。

### 3.5 Control Protocol message 形状（P3 定义；P4 引用）

JSON-RPC 2.0 over stdio，每行一个 JSON 对象。

```jsonc
// Request (C→S 或 S→C)
{ "jsonrpc": "2.0", "id": <int|str>, "method": "<name>", "params": { ... } }

// Response
{ "jsonrpc": "2.0", "id": <same>, "result": { ... } }
{ "jsonrpc": "2.0", "id": <same>, "error": { "code": <int>, "message": "...", "data": { ... } } }

// Notification (S→C 推送事件)
{ "jsonrpc": "2.0", "method": "event", "params": { "envelope": { ... EventEnvelope ... } } }
```

P3 实现 server，P4 实现 client，**双方都引用本节作为 wire 格式权威定义**。

### 3.6 Hook envelope 形状（P6 定义；其他 plan 不直接用）

按 spec §6.1 已定。P6 实现时按 spec 落地。

## 4. 命名与目录约定

所有 6 份 plan 必须遵守的命名：

| 项 | 命名 |
|---|---|
| 平台层目录（plugin 基础设施） | `sensenova_claw/platform/plugins/` |
| Identity | `sensenova_claw/platform/identity/` |
| Hook Pipeline | `sensenova_claw/kernel/hooks/` |
| Control Protocol Server | `sensenova_claw/interfaces/control/` |
| Python SDK 包 | `sensenova_claw/sdk/`（与 core 同 monorepo，发布时切包） |
| 内置 plugin（P2 创建） | `sensenova_claw/builtin_plugins/{tools,llm,skills,channels}/plugin.yaml` |
| 内置 plugin id 前缀 | `core/builtin-*` |
| 测试 | `tests/unit/platform/plugins/` 等对应路径 |

## 5. 测试策略

每份 plan 都按 TDD：

- **P1**：单元测试覆盖 manifest schema 校验、loader 扫描、registry 注入
- **P2**：用现有 e2e 验证行为等价（`tests/e2e/`）
- **P3**：单元 + 集成测试（mock stdio，跑完整握手 + send_input + event 推送）
- **P4**：用 P3 真起 core CLI 子进程跑端到端测试
- **P5**：单元覆盖 visibility 过滤；集成覆盖 DB 迁移
- **P6**：单元覆盖 Hook decision 各分支；集成覆盖 hook spawn

## 6. 并行执行注意事项

写 plan 时（本期）：
- 6 份 plan 可全并行写，每份 plan 一个 worktree
- subagent prompt 必须包含本文档作为共享上下文
- 6 份 plan markdown 文件名都不冲突（按 P 序号命名）

执行 plan 时（未来）：
- P1 → P2 → P3 必须串行
- P4 / P5 / P6 在 P3 完成后可三路并行（用各自 worktree）

## 7. 跨 plan 风险与对策

| 风险 | 对策 |
|---|---|
| P3 实现 Control Protocol 时发现 P1 的 Registry 接口不够用 | 先回到本文档加字段，再同步通知所有未完成 plan 的写者 |
| P5 引入 visibility 过滤后 P2 的内置 plugin 不可见 | 内置 plugin manifest 全部声明 `visibility: public`，永远可见 |
| P6 的 hook 改变了 LLM/Tool 调用的事件链 | 通过 Hook 机制扩展事件，不删/改既有事件类型 |
| P4 的 SDK 接口和 P3 的协议不一致 | 共同引用本文档 §3.5 的 wire 格式 |
