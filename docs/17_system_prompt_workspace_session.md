# System Prompt 模块化、Workspace 文件体系与 Session 持久化增强

> 版本: v0.5
> 日期: 2026-03-10

---

## 1. 概述

为 AgentOS 引入模块化的 System Prompt 构建、轻量级 Workspace 文件体系、以及基于现有 SQLite 的 Session 持久化增强——三者协同为 v0.6 Memory 系统铺路。

**设计原则**:
- 只实现有调用者或下一版本明确需要的 Section（YAGNI）
- Session 持久化在现有 SQLite 上扩展
- Workspace 文件仅在不存在时创建，不覆盖用户修改
- `build_system_prompt()` 是**纯函数**，不做 I/O

---

## 2. System Prompt 模块化

### 2.1 Section 清单（8 个）

```
1. Identity（必选）     — 身份声明 + 基础行为规范
2. Tooling（有工具时）   — 可用工具列表 + 调用规范
3. Skills（有 skills 时） — 可用技能列表 + 使用说明
4. Memory（有记忆时）    — 长期记忆召回结果（v0.6 填充）
5. Context Files（有时） — AGENTS.md / USER.md 内容
6. Date & Time（必选）   — 当前日期时间 + 系统信息
7. Extra Context（有时） — 用户自定义额外上下文
8. Runtime（必选）       — 运行时信息行（调试用）
```

每个 Section 是独立 builder 函数，返回 `list[str]`，空则跳过。

### 2.2 数据结构

```python
@dataclass
class SystemPromptParams:
    prompt_mode: PromptMode = "full"          # v0.5 只实现 full
    base_prompt: str = ""                      # Identity
    tool_names: list[str] = field(default_factory=list)
    tool_summaries: dict[str, str] = field(default_factory=dict)
    skills_prompt: str | None = None           # Skills
    memory_context: str | None = None          # Memory（v0.6 预留）
    context_files: list[ContextFile] = field(default_factory=list)
    extra_system_prompt: str | None = None
    runtime_info: RuntimeInfo | None = None

@dataclass
class ContextFile:
    name: str       # "AGENTS.md"
    content: str

@dataclass
class RuntimeInfo:
    host: str | None = None
    os: str | None = None
    python: str | None = None
    model: str | None = None
    channel: str | None = None
```

### 2.3 构建逻辑

```python
def build_system_prompt(params: SystemPromptParams) -> str:
    if params.prompt_mode == "none":
        return "You are a personal assistant running inside AgentOS."

    sections = [
        _build_identity(params.base_prompt),
        _build_tooling(params.tool_names, params.tool_summaries),
        _build_skills(params.skills_prompt),
        _build_memory(params.memory_context),
        _build_context_files(params.context_files),
        _build_datetime(),
        _build_extra(params.extra_system_prompt),
        _build_runtime(params.runtime_info),
    ]

    lines: list[str] = []
    for section in sections:
        if section:
            lines.extend(section)
    return "\n".join(lines)
```

### 2.4 ContextBuilder 重构

```python
class ContextBuilder:
    def build_messages(
        self,
        user_input: str,
        history: list[dict] | None = None,
        memory_context: str | None = None,     # v0.6 预留
        context_files: list[ContextFile] | None = None,
    ) -> list[dict]:
        params = SystemPromptParams(
            base_prompt=config.get("agent.system_prompt", ""),
            skills_prompt=self._build_skills_section() if self.skill_registry else None,
            memory_context=memory_context,
            context_files=context_files or [],
            runtime_info=self._collect_runtime_info(),
        )
        system_prompt = build_system_prompt(params)

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        messages.append({"role": "user", "content": f"[{current_time}] {user_input}"})
        return messages
```

### 2.5 Context Files 注入格式

```
## Project Context
The following workspace files have been loaded:
### AGENTS.md
(文件内容)
### USER.md
(文件内容)
```

截断规则：单文件 > 20000 字符截断；总计 > 50000 字符按优先级裁剪（AGENTS.md > USER.md）。

### 2.6 Runtime 行

System prompt 末尾：`Runtime: os=windows (x86_64) | python=3.12 | model=gpt-4o-mini | channel=websocket`

---

## 3. Workspace 文件体系

### 3.1 位置

默认 `{project_root}/SenseAssistant/workspace/`，可通过 `system.workspace_dir` 配置。

### 3.2 文件清单

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `AGENTS.md` | Agent 操作指令、行为规则、工具使用备注 | session 首轮 |
| `USER.md` | 用户信息、偏好、称呼方式、人格定制 | session 首轮 |

### 3.3 创建逻辑

```python
async def ensure_workspace(workspace_dir: str) -> None:
    """确保 workspace 存在，创建缺失的核心文件（不覆盖已有）"""
    dir_path = Path(workspace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    for filename, content in {"AGENTS.md": DEFAULT_AGENTS_MD, "USER.md": DEFAULT_USER_MD}.items():
        file_path = dir_path / filename
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
```

### 3.4 加载逻辑

```python
async def load_workspace_files(workspace_dir: str) -> list[ContextFile]:
    """读取引导文件，缺失或空文件自动跳过"""
    files = []
    for name in ["AGENTS.md", "USER.md"]:
        path = Path(workspace_dir) / name
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                files.append(ContextFile(name=name, content=content))
    return files
```

### 3.5 默认内容

**AGENTS.md**: Agent 操作规则（工具使用规范、回复风格）

**USER.md**: 用户个人信息模板（称呼、语言偏好、工作环境）

---

## 4. Session 持久化增强

### 4.1 新增 messages 表

当前 `SessionStateStore._session_history` 纯内存，重启丢失。新增：

```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    tool_name TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);
```

### 4.2 sessions 表扩展

```sql
ALTER TABLE sessions ADD COLUMN channel TEXT;
ALTER TABLE sessions ADD COLUMN model TEXT;
ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0;
```

### 4.3 会话历史恢复

```python
class SessionStateStore:
    async def load_session_history(self, session_id: str, repo: Repository) -> list[dict]:
        """从 SQLite 加载会话历史到内存（惰性加载）"""
        if session_id in self._session_history:
            return self._session_history[session_id]
        messages = await repo.get_session_messages(session_id)
        self._session_history[session_id] = messages
        return messages
```

### 4.4 生命周期管理

```python
class SessionMaintenance:
    async def prune_expired(self, repo: Repository, max_age_days: int = 30) -> int:
        """清理超期未活跃的会话及关联数据"""
    async def cap_sessions(self, repo: Repository, max_count: int = 500) -> int:
        """限制会话总数，淘汰最旧的"""
```

配置：`session.maintenance.prune_after_days: 30`，`session.maintenance.max_sessions: 500`

---

## 5. 集成变更

### 5.1 AgentSessionWorker 修改

```python
async def _handle_user_input(self, event: EventEnvelope) -> None:
    content = str(event.payload.get("content", ""))
    turn_id = event.turn_id or f"turn_{uuid.uuid4().hex[:12]}"
    # ... 现有 session/turn 创建 ...

    # v0.5: 首轮加载 workspace 文件
    context_files = None
    if self.rt.state_store.is_first_turn(self.session_id):
        context_files = await load_workspace_files(config.get("system.workspace_dir", ...))
        self.rt.state_store.mark_first_turn_done(self.session_id)

    # v0.6 预留: memory_context = await self.rt.memory_service.recall(content)

    history = self.rt.state_store.get_session_history(self.session_id)
    messages = self.rt.context_builder.build_messages(
        content, history, context_files=context_files,
    )
    # ... 后续不变 ...
```

### 5.2 修改文件清单

| 文件 | 修改 |
|------|------|
| `runtime/context_builder.py` | 拆出 `build_system_prompt()` + Section builders，新增参数 |
| `runtime/workers/agent_worker.py` | 首轮加载 workspace files |
| `runtime/state.py` | context_files 缓存 |
| `db/repository.py` | messages 表 + 消息持久化方法 |
| `core/config.py` | `session.maintenance` 配置段 |
| `main.py` | lifespan 中 `ensure_workspace()` |

### 5.3 新增文件

| 文件 | 说明 |
|------|------|
| `runtime/prompt_builder.py` | `build_system_prompt()` + Section builder 函数 |
| `workspace/manager.py` | `ensure_workspace()` + `load_workspace_files()` |

---

## 6. 实现计划

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | `prompt_builder.py`: 8 个 Section builder | 1 天 |
| 2 | `ContextBuilder` 重构 + 新增参数 | 0.5 天 |
| 3 | `workspace/manager.py` + 默认内容 | 0.5 天 |
| 4 | `AgentSessionWorker` 集成 workspace 加载 | 0.5 天 |
| 5 | SQLite: messages 表 + 历史恢复 | 1 天 |
| 6 | Session 生命周期管理 | 0.5 天 |
| 7 | 测试 | 1 天 |

**总计：5 天**

---

## 7. 验收标准

1. system prompt 包含 Identity / Tooling / Skills / Time / Runtime 等 Section
2. 编辑 workspace 文件后新会话 system prompt 反映变更
3. `build_messages(memory_context=...)` 接口可用（v0.6 预留）
4. 对话历史存入 messages 表，重启后可恢复
5. 超 30 天未活跃的会话被清理
6. 不配置 workspace 时行为与 v0.4 一致
7. `build_system_prompt()` 纯函数，可独立单测
