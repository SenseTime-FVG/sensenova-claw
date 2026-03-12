# PRD: agentos — System Prompt 组织、Workspace 文件体系与 Session 持久化

> 版本: 0.1.0
> 作者: shaoyuyao
> 日期: 2026-03-09

---

## 1. 概述

本文档定义 agentos 的三个核心子系统的详细设计：

1. **System Prompt 组织** — 如何将固定指令、用户配置、工具列表、运行时信息等组装成最终的 system prompt
2. **Workspace 文件体系** — Agent 的"家目录"中有哪些文件、何时创建、如何注入上下文
3. **Session 持久化** — 对话元数据和历史记录的存储、维护和生命周期管理

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| **分层组装，条件裁剪** | System prompt 由独立 section 拼装，按 agent 类型/工具集/配置动态裁剪，避免冗余 token |
| **惰性创建，仅缺失时写入** | Workspace 文件只在需要且不存在时从模板创建，不覆盖用户修改 |
| **两层持久化** | Session 索引（元数据，JSON）和对话记录（transcript，JSONL）分离，各自独立维护 |
| **原子写入** | 所有持久化操作使用 tmp + rename 模式，防止并发损坏 |

---

## 2. System Prompt 组织

### 2.1 Prompt 模式

agentos 支持三种 prompt 模式，控制 system prompt 的详细程度：

| 模式 | 适用场景 | 包含的 Section |
|------|----------|----------------|
| `full` | 主 Agent（用户直接交互） | 所有 Section |
| `minimal` | 子 Agent（委托/Cron） | 仅 Tooling、Workspace、Runtime |
| `none` | 极简模式（OpenAI 兼容 API 转发） | 仅一行身份声明 |

```python
PromptMode = Literal["full", "minimal", "none"]
```

### 2.2 Section 清单与组装顺序

System prompt 由以下 Section 按顺序拼装，每个 Section 可根据条件跳过：

```
┌──────────────────────────────────────────────────────────┐
│  1. 身份声明（必选）                                       │
│     "You are a personal assistant running inside agentos." │
├──────────────────────────────────────────────────────────┤
│  2. Tooling（必选）                                        │
│     工具列表 + 摘要 + 调用规范                               │
├──────────────────────────────────────────────────────────┤
│  3. Tool Call Style（full 模式）                            │
│     何时 narrate、何时静默调用                                │
├──────────────────────────────────────────────────────────┤
│  4. Safety（full 模式）                                     │
│     安全边界、人类监督优先级                                    │
├──────────────────────────────────────────────────────────┤
│  5. Skills（有 skills 配置时）                               │
│     技能扫描 + 选择 + 加载规则                                │
├──────────────────────────────────────────────────────────┤
│  6. Memory Recall（有 memory 工具时，full 模式）             │
│     记忆搜索指令 + 引用格式                                   │
├──────────────────────────────────────────────────────────┤
│  7. Model Aliases（有别名时，full 模式）                     │
│     模型别名表                                               │
├──────────────────────────────────────────────────────────┤
│  8. Workspace（必选）                                       │
│     工作目录路径 + 使用说明                                    │
├──────────────────────────────────────────────────────────┤
│  9. Documentation（有 docs 路径时，full 模式）               │
│     文档链接 + 查阅指引                                       │
├──────────────────────────────────────────────────────────┤
│ 10. Authorized Senders（有 owner 配置时，full 模式）         │
│     允许的发送者列表                                          │
├──────────────────────────────────────────────────────────┤
│ 11. Current Date & Time（有时区时）                          │
│     用户时区                                                 │
├──────────────────────────────────────────────────────────┤
│ 12. Workspace Files — Project Context（有 context files 时） │
│     注入 AGENTS.md / SOUL.md / USER.md 等内容               │
├──────────────────────────────────────────────────────────┤
│ 13. Messaging（有 message 工具时，full 模式）                │
│     消息路由 + 跨 session 通信 + Channel 操作                │
├──────────────────────────────────────────────────────────┤
│ 14. Voice / TTS（有 TTS 配置时，full 模式）                  │
│     语音输出指引                                              │
├──────────────────────────────────────────────────────────┤
│ 15. Extra Context（有额外 prompt 时）                        │
│     群聊上下文 / 子 Agent 上下文                              │
├──────────────────────────────────────────────────────────┤
│ 16. Silent Replies（full 模式）                              │
│     无内容回复的约定 token                                    │
├──────────────────────────────────────────────────────────┤
│ 17. Heartbeats（full 模式）                                  │
│     心跳 ack 协议                                            │
├──────────────────────────────────────────────────────────┤
│ 18. Runtime（必选）                                          │
│     agent_id, host, os, model, channel, thinking 等运行时信息 │
└──────────────────────────────────────────────────────────┘
```

### 2.3 数据结构

```python
@dataclass
class SystemPromptParams:
    workspace_dir: str
    prompt_mode: PromptMode = "full"

    # Tooling
    tool_names: list[str] = field(default_factory=list)
    tool_summaries: dict[str, str] = field(default_factory=dict)

    # Identity & Auth
    owner_ids: list[str] = field(default_factory=list)
    owner_display: Literal["raw", "hash"] = "raw"

    # Time
    user_timezone: str | None = None

    # Context files (workspace bootstrap files)
    context_files: list[ContextFile] = field(default_factory=list)

    # Skills
    skills_prompt: str | None = None

    # Memory
    memory_citations_mode: Literal["on", "off"] = "on"

    # Model
    default_think_level: Literal["off", "low", "medium", "high"] = "off"
    reasoning_level: Literal["off", "on", "stream"] = "off"
    model_alias_lines: list[str] = field(default_factory=list)

    # Messaging
    message_channel_options: str = ""
    inline_buttons_enabled: bool = False

    # Voice
    tts_hint: str | None = None

    # Docs
    docs_path: str | None = None

    # Extra
    extra_system_prompt: str | None = None
    workspace_notes: list[str] = field(default_factory=list)

    # Runtime
    runtime_info: RuntimeInfo | None = None


@dataclass
class ContextFile:
    path: str
    content: str


@dataclass
class RuntimeInfo:
    agent_id: str | None = None
    host: str | None = None
    os: str | None = None
    arch: str | None = None
    python: str | None = None
    model: str | None = None
    default_model: str | None = None
    shell: str | None = None
    channel: str | None = None
    capabilities: list[str] = field(default_factory=list)
```

### 2.4 构建逻辑

```python
def build_agent_system_prompt(params: SystemPromptParams) -> str:
    """
    按 Section 顺序组装 system prompt。
    每个 Section 是一个独立的 builder 函数，返回 list[str]。
    空 Section（返回 []）自动跳过。
    """
    if params.prompt_mode == "none":
        return "You are a personal assistant running inside agentos."

    is_minimal = params.prompt_mode == "minimal"
    available_tools = set(t.lower() for t in params.tool_names)

    sections = [
        _build_identity(),
        _build_tooling(params.tool_names, params.tool_summaries),
        _build_tool_call_style(is_minimal),
        _build_safety(is_minimal),
        _build_skills(params.skills_prompt),
        _build_memory_recall(is_minimal, available_tools, params.memory_citations_mode),
        _build_model_aliases(is_minimal, params.model_alias_lines),
        _build_workspace(params.workspace_dir, params.workspace_notes),
        _build_docs(is_minimal, params.docs_path),
        _build_authorized_senders(is_minimal, params.owner_ids, params.owner_display),
        _build_time(params.user_timezone),
        _build_context_files(params.context_files),
        _build_messaging(is_minimal, available_tools, params.message_channel_options),
        _build_voice(is_minimal, params.tts_hint),
        _build_extra_context(params.extra_system_prompt, params.prompt_mode),
        _build_silent_replies(is_minimal),
        _build_heartbeats(is_minimal),
        _build_runtime(params.runtime_info, params.default_think_level, params.reasoning_level),
    ]

    lines: list[str] = []
    for section in sections:
        if section:
            lines.extend(section)

    return "\n".join(line for line in lines if line is not None)
```

### 2.5 工具列表规范

工具按固定顺序排列（核心工具在前，扩展在后），每个工具附带一行摘要：

```python
CORE_TOOL_SUMMARIES: dict[str, str] = {
    "bash": "Execute shell commands",
    "file_read": "Read file contents",
    "file_write": "Create or overwrite files",
    "web_search": "Search the web",
    "http_request": "Make HTTP requests",
    "memory_search": "Search long-term memory",
    "memory_write": "Write to long-term memory",
    "message": "Send messages and channel actions",
    "cron": "Manage cron jobs and reminders",
    "delegate": "Synchronously delegate to another agent",
    "notify": "Asynchronously notify another agent",
}

TOOL_ORDER = [
    "bash", "file_read", "file_write", "web_search",
    "http_request", "memory_search", "memory_write",
    "message", "cron", "delegate", "notify",
]
```

输出格式：
```
## Tooling
Tool availability (filtered by policy):
- bash: Execute shell commands
- file_read: Read file contents
- web_search: Search the web
- custom_tool: (user-provided summary)
```

### 2.6 Runtime 行

System prompt 的最后一行是压缩的运行时信息，用于调试和上下文感知：

```
Runtime: agent=main | host=my-server | os=linux (x86_64) | python=3.12 | model=claude-sonnet-4-20250514 | channel=feishu | thinking=off
```

### 2.7 Context Files 注入

Workspace 引导文件（AGENTS.md、SOUL.md 等）的内容被注入到 system prompt 的 "Project Context" 段：

```
# Project Context

The following project context files have been loaded:
If SOUL.md is present, embody its persona and tone.

## AGENTS.md
(file content)

## SOUL.md
(file content)

## USER.md
(file content)
```

注入规则：
- 空文件跳过
- 单文件超过 `bootstrap_max_chars`（默认 20000）时截断，附加截断标记
- 所有文件总计超过 `bootstrap_total_max_chars`（默认 150000）时截断
- 缺失的文件注入 "missing file" 标记行

---

## 3. Workspace 文件体系

### 3.1 默认位置

```
~/.agentos/workspace/
```

如果设置了 `agentos_PROFILE`（且不为 `"default"`），则为：
```
~/.agentos/workspace-{profile}/
```

可通过配置覆盖：
```yaml
agents:
  main:
    workspace: "~/my-agent-workspace"
```

### 3.2 文件清单

#### 引导文件（Bootstrap Files）

每次新 session 第一个 turn 时读取并注入 system prompt：

| 文件 | 用途 | 每次 session 加载 | 模板默认值 |
|------|------|:-:|:-:|
| `AGENTS.md` | Agent 操作指令、行为规则 | ✓ | ✓ |
| `SOUL.md` | 人格、语气、边界 | ✓ | ✓ |
| `USER.md` | 用户信息、称呼方式 | ✓ | ✓ |
| `IDENTITY.md` | Agent 名字、风格 | ✓ | ✓ |
| `TOOLS.md` | 工具使用备注（不控制可用性） | ✓ | ✓ |
| `HEARTBEAT.md` | 心跳检查清单（保持简短） | ✓ | ✓ |
| `BOOTSTRAP.md` | 一次性首次运行仪式，完成后删除 | ✓ | 仅全新工作区 |

#### 可选文件

| 文件/目录 | 用途 | 加载时机 |
|-----------|------|----------|
| `MEMORY.md`（或 `memory.md`） | 长期记忆（持久事实/偏好） | 仅主 session |
| `memory/YYYY-MM-DD.md` | 每日记忆日志 | session 开始时读取今天 + 昨天 |
| `skills/` | 自定义 skill 文件 | 按需读取 |

### 3.3 模板系统

模板文件位于代码仓库的 `templates/` 目录：

```
templates/
├── AGENTS.md
├── SOUL.md
├── USER.md
├── IDENTITY.md
├── TOOLS.md
├── HEARTBEAT.md
└── BOOTSTRAP.md
```

模板解析顺序：
1. 包安装路径下的 `templates/`
2. 当前工作目录下的 `templates/`
3. 源码相对路径 fallback

模板支持 YAML front matter（`---`...`---`），注入时自动剥离。

### 3.4 文件创建逻辑

核心函数 `ensure_agent_workspace()`：

```python
async def ensure_agent_workspace(
    workspace_dir: str | None = None,
    ensure_bootstrap_files: bool = False,
) -> WorkspaceInfo:
    """
    确保 workspace 目录存在。
    如果 ensure_bootstrap_files=True，从模板创建缺失的引导文件。
    """
    dir = resolve_workspace_dir(workspace_dir)
    os.makedirs(dir, exist_ok=True)

    if not ensure_bootstrap_files:
        return WorkspaceInfo(dir=dir)

    # 判断是否全新工作区（所有核心文件都不存在）
    core_files = [AGENTS, SOUL, TOOLS, IDENTITY, USER, HEARTBEAT]
    is_brand_new = all(not (dir / f).exists() for f in core_files)

    # 从模板创建缺失文件（flag="x" 仅在不存在时写入）
    for filename in core_files:
        template = load_template(filename)
        write_if_missing(dir / filename, template)

    # BOOTSTRAP.md 的特殊逻辑
    handle_bootstrap_lifecycle(dir, is_brand_new)

    # 全新工作区初始化 git
    if is_brand_new:
        init_git_repo(dir)

    return WorkspaceInfo(dir=dir, ...)
```

关键行为：
- **`write_if_missing`**：使用 `open(path, "x")` 模式，仅在文件不存在时写入，绝不覆盖用户修改
- **BOOTSTRAP.md 生命周期**：
  - 仅全新工作区创建
  - 用户删除 → 标记 onboarding 完成 → 不再重新创建
  - 如果 `USER.md` / `IDENTITY.md` 已被修改（与模板不同），视为已完成 onboarding

### 3.5 Onboarding 状态跟踪

在 `{workspace}/.agentos/workspace-state.json` 中记录：

```python
@dataclass
class WorkspaceOnboardingState:
    version: int = 1
    bootstrap_seeded_at: str | None = None      # BOOTSTRAP.md 首次创建时间
    onboarding_completed_at: str | None = None  # 用户完成首次运行仪式的时间
```

状态转换：
```
全新工作区 → bootstrap_seeded_at 设定 → 用户删除 BOOTSTRAP.md → onboarding_completed_at 设定
```

### 3.6 文件加载与注入

加载函数 `load_workspace_bootstrap_files()`：

```python
async def load_workspace_bootstrap_files(workspace_dir: str) -> list[BootstrapFile]:
    """
    从 workspace 读取所有引导文件。
    缺失的文件标记为 missing=True（不报错）。
    使用 mtime 缓存避免重复读取。
    """
```

```python
@dataclass
class BootstrapFile:
    name: str          # e.g. "AGENTS.md"
    path: str          # 完整路径
    content: str | None
    missing: bool
```

Session 类型过滤：

| Session 类型 | 加载的文件 |
|-------------|-----------|
| 主 session（用户交互） | 全部引导文件 + MEMORY.md + memory/*.md |
| 子 Agent / Cron | 仅 AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md |

### 3.7 调用时机

`ensure_agent_workspace()` 在以下时机被调用：

| 时机 | `ensure_bootstrap_files` | 说明 |
|------|:-:|------|
| `agentos setup` 命令 | ✓ | 显式初始化 |
| `agentos run` 启动 | ✓ | Gateway 启动时 |
| 收到消息（`agent.run()`） | ✓ | 每次处理消息前 |
| Cron 任务触发 | ✓ | 隔离 agent 运行前 |
| 添加/更新 Agent 配置 | ✓ | Gateway API 操作 |
| CLI `agent --message` | ✓ | CLI 直接调用 |

---

## 4. Session 持久化

### 4.1 两层存储架构

```
~/.agentos/
└── agents/
    └── {agent_id}/
        └── sessions/
            ├── sessions.json              ← Session 元数据索引（Layer 1）
            ├── sessions.json.bak.*        ← 轮转备份
            ├── {session_id}.jsonl         ← 对话 transcript（Layer 2）
            ├── {session_id}-topic-*.jsonl ← 带 topic 的 transcript
            └── .archived/                 ← 已归档的 transcript
```

### 4.2 Layer 1: Session 元数据索引

**文件**: `sessions.json`

**格式**: `dict[session_key, SessionEntry]`

```python
@dataclass
class SessionEntry:
    session_id: str
    session_file: str | None = None      # transcript 文件路径
    updated_at: float | None = None      # Unix timestamp (ms)
    channel: str | None = None           # 最后使用的消息渠道
    last_channel: str | None = None
    last_to: str | None = None           # 投递目标
    last_account_id: str | None = None
    last_thread_id: str | None = None
    delivery_context: DeliveryContext | None = None
    model: str | None = None             # 当前使用的模型
    group_channel: str | None = None
```

**Session Key 规则**:

| 场景 | Key 格式 | 示例 |
|------|----------|------|
| 用户私聊 | `{channel}:{sender_id}` | `feishu:ou_abc123` |
| 用户群聊 | `{channel}:group:{group_id}` | `feishu:group:oc_xyz789` |
| Agent 间 | `pair:{sorted(a,b)}` | `pair:main,researcher` |
| Cron 触发 | `system:{trigger}:{run_id}` | `system:daily_summary:run_42` |
| 子 Agent | `subagent:{parent}:{child}:{id}` | `subagent:main:coder:s1` |

Key 归一化：`key.strip().lower()`

### 4.3 Layer 2: 对话 Transcript

**文件**: `{session_id}.jsonl`

**格式**: JSON Lines，每行一个 JSON 对象。

第一行为 session header：
```json
{"type": "session", "version": 1, "id": "abc123", "timestamp": "2026-03-09T10:00:00Z", "cwd": "/home/user"}
```

后续行为对话消息（由 SessionManager 追加）：
```json
{"role": "user", "content": [{"type": "text", "text": "你好"}], "timestamp": 1741500000000}
{"role": "assistant", "content": [{"type": "text", "text": "你好！有什么可以帮你的？"}], "model": "claude-sonnet-4-20250514", "usage": {...}, "timestamp": 1741500001000}
```

### 4.4 读写机制

#### 读取 — `load_session_store()`

```python
def load_session_store(store_path: str, skip_cache: bool = False) -> dict[str, SessionEntry]:
    """
    同步读取 sessions.json。
    带内存缓存（TTL 45s + mtime 校验）。
    """
```

缓存策略：
- TTL: 45 秒（可通过 `agentos_SESSION_CACHE_TTL_MS` 环境变量调整）
- mtime 校验：文件修改时间不变则命中缓存
- 写入时主动 invalidate 缓存

#### 写入 — `save_session_store()`

```python
async def save_session_store(
    store_path: str,
    store: dict[str, SessionEntry],
    opts: SaveOptions | None = None,
) -> None:
    """
    原子写入 sessions.json。
    1. 获取写锁
    2. 执行维护（prune / cap / rotate）
    3. 序列化为 JSON
    4. 写入临时文件
    5. rename 覆盖目标
    6. 释放锁
    """
```

写入流程：

```
save_session_store()
  │
  ├── 获取 per-file 写锁（asyncio queue + file lock）
  │
  ├── 维护（可选）
  │   ├── prune_stale_entries()   # 删除过期 entry
  │   ├── cap_entry_count()       # 限制总数
  │   ├── rotate_session_file()   # 文件过大时轮转
  │   └── enforce_disk_budget()   # 磁盘预算
  │
  ├── 原子写入
  │   ├── write tmp file
  │   └── rename tmp → target
  │
  └── 释放锁
```

#### 并发安全

写锁实现：内存队列 + 文件锁双保险。

```python
class SessionStoreLockQueue:
    """
    Per-storePath 的串行化写入队列。
    同一个 storePath 的写操作按 FIFO 顺序执行。
    不同 storePath 完全并行。
    """
    running: bool
    pending: list[LockTask]
```

- `timeout_ms`: 默认 10 秒
- `stale_ms`: 默认 30 秒（超时的锁视为 stale，可被抢占）

### 4.5 Session 维护策略

| 策略 | 配置项 | 默认值 | 说明 |
|------|--------|--------|------|
| **过期清理** | `session.maintenance.prune_after` | `30d` | `updated_at` 超过此时间的 entry 被移除 |
| **数量上限** | `session.maintenance.max_entries` | `500` | 超出后按 `updated_at` 从旧到新淘汰 |
| **文件轮转** | `session.maintenance.rotate_bytes` | `10MB` | `sessions.json` 超过此大小时 rename 为 `.bak.*`，保留最近 3 个备份 |
| **磁盘预算** | `session.maintenance.max_disk_bytes` | 不限 | transcript 文件总占用上限 |
| **归档清理** | `session.maintenance.reset_archive_retention` | 跟随 `prune_after` | `.archived/` 目录中过期 transcript 的清理 |

维护模式（`session.maintenance.mode`）：

| 模式 | 行为 |
|------|------|
| `warn`（默认） | 检测到需维护时仅日志告警，不自动执行 |
| `enforce` | 每次 save 时自动执行维护 |

配置示例：
```yaml
session:
  maintenance:
    mode: enforce
    prune_after: "30d"
    max_entries: 500
    rotate_bytes: "10MB"
    max_disk_bytes: "500MB"
```

### 4.6 Session 归档

被删除或 reset 的 transcript 不是立即删除，而是移入 `.archived/` 子目录：

```
sessions/
├── .archived/
│   ├── deleted.{session_id}.{timestamp}.jsonl
│   └── reset.{session_id}.{timestamp}.jsonl
├── sessions.json
└── active-session.jsonl
```

归档文件在 `reset_archive_retention` 到期后由维护任务清理。

### 4.7 路径解析

```python
def resolve_session_transcript_path(
    session_id: str,
    agent_id: str | None = None,
    topic_id: str | int | None = None,
) -> str:
    """
    解析 transcript 文件路径。
    普通: ~/.agentos/agents/{agent_id}/sessions/{session_id}.jsonl
    带 topic: ~/.agentos/agents/{agent_id}/sessions/{session_id}-topic-{topic_id}.jsonl
    """

def resolve_store_path(
    store: str | None = None,
    agent_id: str | None = None,
) -> str:
    """
    解析 sessions.json 路径。
    支持 {agentId} 占位符和 ~ 展开。
    默认: ~/.agentos/agents/{agent_id}/sessions/sessions.json
    """
```

路径安全校验：
- transcript 路径必须在 sessions 目录内（防止路径穿越）
- session_id 校验：`/^[a-z0-9][a-z0-9._-]{0,127}$/i`
- 绝对路径自动转换为相对路径（兼容旧版本存储的绝对路径）

---

## 5. 完整目录结构

```
~/.agentos/
├── agentos.yaml                                 # 主配置
├── agents/
│   ├── main/                                     # 默认 Agent
│   │   ├── agent/
│   │   │   └── auth.json                        # 认证缓存
│   │   └── sessions/
│   │       ├── sessions.json                    # session 元数据索引
│   │       ├── sessions.json.bak.1741500000000  # 轮转备份
│   │       ├── feishu-ou_abc123.jsonl           # 对话 transcript
│   │       ├── system-daily_summary-run_42.jsonl
│   │       └── .archived/
│   │           └── deleted.old-session.1741400000000.jsonl
│   └── researcher/                               # 第二个 Agent
│       └── sessions/
│           └── ...
├── credentials/                                   # Provider 凭证
│   └── feishu/
│       └── tenant_token.json
└── workspace/                                     # Agent 工作区（独立于 session）
    ├── .agentos/
    │   └── workspace-state.json                  # onboarding 状态
    ├── .git/
    ├── AGENTS.md
    ├── SOUL.md
    ├── USER.md
    ├── IDENTITY.md
    ├── TOOLS.md
    ├── HEARTBEAT.md
    ├── MEMORY.md
    ├── memory/
    │   ├── 2026-03-08.md
    │   └── 2026-03-09.md
    └── skills/
        └── my-skill/
            └── SKILL.md
```

---

## 6. 实现计划

### Phase 1（融入主 PRD Phase 1，3 周）

- [ ] `SystemPromptParams` 数据结构
- [ ] `build_agent_system_prompt()` 核心逻辑 + 所有 Section builder
- [ ] 模板系统 + `templates/` 目录
- [ ] `ensure_agent_workspace()` + `write_if_missing()`
- [ ] `load_workspace_bootstrap_files()` + mtime 缓存
- [ ] `SessionEntry` + `sessions.json` 读写
- [ ] JSONL transcript 追加
- [ ] 原子写入（tmp + rename）

### Phase 2（融入主 PRD Phase 2，3 周）

- [ ] Session 写锁（queue + file lock）
- [ ] Session 维护（prune / cap / rotate）
- [ ] Onboarding 状态跟踪
- [ ] BOOTSTRAP.md 生命周期
- [ ] Context files 截断与 token 控制
- [ ] Web UI 展示 workspace 文件和 session 列表

### Phase 3（融入主 PRD Phase 3，3 周）

- [ ] Memory 文件 (`MEMORY.md` / `memory/*.md`) 的 session 注入
- [ ] Skills prompt 构建
- [ ] Session 归档与清理
- [ ] 磁盘预算执行
- [ ] `minimal` prompt mode（子 Agent 支持）

---

## 7. 与 OpenClaw 的对比

| 维度 | OpenClaw | agentos |
|------|----------|----------|
| 语言 | TypeScript | Python |
| System Prompt 构建 | 字符串数组拼接 + filter(Boolean) | Section builder 函数返回 `list[str]` |
| Prompt Mode | `full` / `minimal` / `none` | 相同 |
| Workspace 模板 | `docs/reference/templates/*.md` | `templates/*.md` |
| 文件创建 | `fs.writeFile(flag: "wx")` | `open(path, "x")` |
| Session 索引 | `sessions.json`（JSON） | 相同 |
| Session Transcript | `.jsonl`（JSONL） | 相同 |
| 写入方式 | tmp + rename + retry（Windows 特化） | tmp + rename |
| 写锁 | 内存 queue + file lock | 相同 |
| 缓存 | TTL 45s + mtime | 相同 |
| 维护 | prune / cap / rotate / disk budget | 相同 |

### 简化决策

| OpenClaw 功能 | agentos 处理 | 理由 |
|---------------|---------------|------|
| Sandbox 信息注入 | 不实现 | 个人项目不需要 Docker sandbox |
| Owner ID hash 显示 | 不实现 | 不暴露到公开渠道 |
| Reply Tags | 不实现 | 飞书用交互卡片代替 |
| Reaction Guidance | 不实现 | 飞书暂不支持 |
| Reasoning Tag Hint | 保留 | 对 thinking 模型有用 |
| Bootstrap file 缓存（per-session key） | 简化为全局缓存 | 单进程，不需要 per-session 隔离 |
| Windows 特化重试 | 不实现 | 主要跑 Linux |
