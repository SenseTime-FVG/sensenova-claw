# AgentOS 工作目录与文件路径全景分析

## 一、整体目录结构

当前系统在项目根目录下的运行时目录布局如下：

```
项目根/
├── config.yml                    # 主配置文件
├── .agentos/config.yaml          # 新格式配置（可选）
├── workspace/                    # Agent 工作区
│   ├── AGENTS.md                 # Agent 行为指令
│   ├── USER.md                   # 用户偏好
│   ├── MEMORY.md                 # 长期记忆（memory 启用时）
│   ├── memory/**/*.md            # 分块记忆文件
│   ├── agents/{agent_id}.json    # Agent 个性化配置
│   └── skills/                   # Skills 目录
├── var/
│   └── data/
│       ├── agentos.db            # 主数据库（sessions/turns/messages/events）
│       └── memory_index.db       # 记忆向量索引
├── logs/
│   └── system.log                # 系统日志（RotatingFileHandler）
└── var/skills/                   # 安装的第三方 skills
```

---

## 二、各路径详细分析

### 1. 配置文件读取 (`config.yml`)

**核心代码**：`agentos/platform/config/config.py`

```python
# agentos/platform/config/config.py -> 往上 3 层到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
```

**两种加载模式**：

| 模式 | 搜索路径 | 使用场景 |
|------|---------|---------|
| **传统模式** (`Config()`) | `PROJECT_ROOT/config.yml` 单文件 | 当前 Gateway 使用 |
| **新模式** (`Config(project_root=...)`) | 从 project_root 向上遍历，收集所有 `config.yml` + `.agentos/config.yaml` | 测试/新架构 |

**优先级**：环境变量 > `.agentos/config.yaml` > `config.yml` > `DEFAULT_CONFIG`

**详细说明**：
- `config` 是模块级全局单例（第 399 行 `config = Config()`），在 import 时即加载
- 路径基于源码位置推导（`Path(__file__).resolve().parents[3]`）而非 cwd
- 新模式从 `project_root` 向上遍历到文件系统根，沿途收集：
  - `config.yml`（遗留格式）
  - `.agentos/config.yaml`（新格式）
  - 合并顺序：从远到近，近的覆盖远的
- 遗留 key 映射：`OPENAI_API_KEY` → `llm_providers.openai.api_key`，`SERPER_API_KEY` → `tools.serper_search.api_key`

### 2. 数据库路径

**配置项**：`system.database_path`

```python
DEFAULT_CONFIG = {
    "system": {
        "workspace_dir": "./workspace",
        "database_path": "./var/data/agentos.db",
    },
}
```

**实际解析**（`agentos/adapters/storage/repository.py`）：

```python
def __init__(self, db_path: str | None = None):
    self.db_path = Path(db_path or config.get("system.database_path", "./SenseAssistant/agentos.db")).expanduser()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
```

- 使用 `Path(db_path).expanduser()` 解析
- 自动创建父目录 `mkdir(parents=True, exist_ok=True)`
- **相对路径基于进程 cwd**，不是 PROJECT_ROOT

**关联数据库**：

| 数据库 | 路径 | 内容 |
|--------|------|------|
| 主库 `agentos.db` | `./var/data/agentos.db` | sessions、turns、messages、events、users 表 |
| 记忆索引 `memory_index.db` | `{主库目录}/memory_index.db` | memory_chunks 向量分块 |

**用户表与主库共用同一 SQLite 文件**：`UserRepository(db_path=str(repo.db_path))`

### 3. Session 对话记录

所有对话数据存储在 **SQLite 主库** 中，表结构：

| 表 | 主要字段 | 说明 |
|----|---------|------|
| `sessions` | session_id, agent_id, channel, model, status, created_at, last_active, meta, message_count | 会话元数据 |
| `turns` | turn_id, session_id, status, started_at, ended_at, user_input, agent_response | 对话轮次 |
| `messages` | session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name, created_at | 完整消息链 |
| `events` | event_id, session_id, turn_id, event_type, timestamp, source, trace_id, payload_json | 事件流全量记录 |
| `agent_messages` | 多 Agent 间消息记录 | send_message 等 |

**可选的 JSONL 导出**：
- 实现：`agentos/adapters/storage/session_jsonl.py`
- 目录结构：`{base_dir}/{agent_id}/{session_id}.jsonl`
- 当前 Gateway **未启用**（未传入 `jsonl_writer`）

### 4. Agent 个性化文件

**来源一：config.yml 中的 agent/agents 配置**

```python
"agent": {
    "provider": "mock",
    "default_model": "mock-agent-v1",
    "default_temperature": 0.2,
    "max_turns_per_session": 50,
    "system_prompt": "你是一个有工具能力的AI助手，请在必要时调用工具。",
},
"agents": {},  # v1.0: 多 Agent 配置
```

- `agent.*` → 生成 `default` Agent
- `agents.{agent_id}.*` → 生成其他 Agent

**来源二：workspace/agents/ 目录下的 JSON 文件**
- 路径：`{workspace_dir}/agents/{agent_id}.json`
- `AgentRegistry.load_from_dir()` 扫描加载

**AgentConfig 字段**（`agentos/capabilities/agents/config.py`）：
- `id`, `name`, `description`
- `provider`, `model`, `temperature`, `max_tokens`
- `system_prompt`
- `tools`, `skills`
- `can_delegate_to`, `max_delegation_depth`, `max_pingpong_turns`

**当前状态：没有 per-agent 独立工作目录**。所有 Agent 共用同一个 `workspace_dir`，仅通过 `sessions.agent_id` 区分会话归属。

### 5. workspace 引导文件 (AGENTS.md / USER.md)

**核心代码**：`agentos/platform/config/workspace.py`

```python
async def ensure_workspace(workspace_dir: str) -> None:
    """确保 workspace 存在，创建缺失的核心文件（不覆盖已有）"""
    dir_path = Path(workspace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    defaults = {
        "AGENTS.md": DEFAULT_AGENTS_MD,
        "USER.md": DEFAULT_USER_MD,
    }
    for filename, content in defaults.items():
        file_path = dir_path / filename
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
```

**加载逻辑**（`agentos/platform/config/workspace.py`）：

```python
async def load_workspace_files(workspace_dir: str) -> list[ContextFile]:
    """读取引导文件，缺失或空文件自动跳过"""
    files: list[ContextFile] = []
    dir_path = Path(workspace_dir)
    for name in ["AGENTS.md", "USER.md"]:
        path = dir_path / name
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                files.append(ContextFile(name=name, content=content))
    return files
```

**注入时机**：仅在 **session 首轮对话** (`is_first_turn`) 时注入 system prompt
- `agentos/kernel/runtime/workers/agent_worker.py` 中 `is_first_turn` 时调用 `load_workspace_files`
- 作为 `context_files` 传给 `ContextBuilder.build_messages`
- `prompt_builder._build_context_files` 将内容放入 system prompt 的 "Project Context" 段

### 6. 日志文件

**核心代码**：`agentos/platform/logging/setup.py`

```python
def setup_logging() -> None:
    level_name = str(config.get("system.log_level", "DEBUG")).upper()
    level = getattr(logging, level_name, logging.DEBUG)

    workspace = Path(config.get("system.workspace_dir", "./SenseAssistant/workspace")).expanduser()
    root_dir = workspace.parent
    log_dir = root_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "system.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding="utf-8"
    )
```

**路径推导逻辑**：
- `workspace_dir` 默认为 `"./workspace"`
- `log_dir = workspace_dir 的父目录 / "logs"`
- 即：`./logs/system.log`

**配置**：
- 日志级别：`system.log_level`，默认 `"DEBUG"`
- RotatingFileHandler：单文件最大 10MB，保留 3 个备份
- 同时输出到 stdout（StreamHandler）

### 7. 记忆系统 (Memory)

| 文件 | 路径 | 说明 |
|------|------|------|
| MEMORY.md | `{workspace_dir}/MEMORY.md` | 长期记忆主文件 |
| memory/*.md | `{workspace_dir}/memory/**/*.md` | 按主题组织的记忆分块 |
| memory_index.db | `{database_path 父目录}/memory_index.db` | 向量索引 SQLite |

- 记忆系统默认**关闭**（`memory.enabled: false`）
- 启用后首轮加载 `MEMORY.md` 内容注入 system prompt
- `MemoryManager` 负责同步索引、检索相关记忆
- 向量索引库路径：`repo.db_path.parent / "memory_index.db"`

---

## 三、关键配置项汇总

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `system.workspace_dir` | `./workspace` | Agent 工作区根目录 |
| `system.database_path` | `./var/data/agentos.db` | 主数据库路径 |
| `system.log_level` | `DEBUG` | 日志级别 |
| `system.granted_paths` | `[]` | 预授权目录列表 |
| `memory.enabled` | `false` | 是否启用记忆系统 |

---

## 四、关键代码文件索引

| 文件路径 | 职责 |
|----------|------|
| `agentos/platform/config/config.py` | 配置加载主逻辑、DEFAULT_CONFIG、PROJECT_ROOT |
| `agentos/platform/config/workspace.py` | workspace 引导文件创建与加载 |
| `agentos/platform/logging/setup.py` | 日志系统初始化 |
| `agentos/adapters/storage/repository.py` | 数据库初始化、表创建、CRUD |
| `agentos/adapters/storage/user_repository.py` | 用户表存储 |
| `agentos/adapters/storage/session_jsonl.py` | JSONL 会话导出（可选） |
| `agentos/capabilities/agents/config.py` | AgentConfig 数据结构 |
| `agentos/capabilities/memory/manager.py` | 记忆系统管理 |
| `agentos/capabilities/memory/index.py` | 记忆向量索引 |
| `agentos/capabilities/skills/registry.py` | Skills 注册（含用户级 ~/.agentos/skills） |
| `agentos/app/gateway/main.py` | Gateway 启动入口，串联所有组件 |
| `agentos/kernel/runtime/workers/agent_worker.py` | Agent 运行时，首轮加载 workspace 文件 |

---

## 五、发现的问题

| 编号 | 问题 | 详情 |
|------|------|------|
| **1** | **日志路径 fallback 与默认值不一致** | `setup.py` 第 14 行 fallback 是 `"./SenseAssistant/workspace"`，但 `DEFAULT_CONFIG` 里 `workspace_dir` 是 `"./workspace"`。当 config 正常加载时不影响，但如果 config 异常则日志会写到意外位置 |
| **2** | **Repository fallback 与默认值不一致** | `repository.py` 的 fallback 是 `"./SenseAssistant/agentos.db"`，而 `DEFAULT_CONFIG` 是 `"./var/data/agentos.db"`，两者不一致 |
| **3** | **相对路径依赖 cwd** | `database_path` 和 `workspace_dir` 都是相对路径，依赖进程 cwd 而非 `PROJECT_ROOT`，如果从不同目录启动后端会导致路径错乱 |
| **4** | **无 per-agent 独立工作目录** | 所有 Agent 共享一个 workspace 和一个数据库，无法隔离不同 Agent 的文件和对话数据 |
| **5** | **JSONL 会话导出未启用** | `session_jsonl.py` 已实现但 Gateway 未传入 `jsonl_writer`，对话记录仅存 SQLite |
| **6** | **日志路径间接推导** | 日志目录从 `workspace_dir` 父目录推算，不够直观，也不支持独立配置 |

---

## 六、规划中但未实现的设计

根据 `docs_raw/update_v1.3.md` 中的规划：

- 每个 Agent 独立目录：`~/.agentos/{agent_name}/`
  - 内含 `AGENTS.md`, `USER.md`, `MEMORY.md`
  - 独立数据库：`agent.db`, `memory_index.db`
  - 独立 workspace 和 skills 目录
- `AGENTOS_HOME` 环境变量支持
- `~/.agentos/config.yml` 作为全局配置

这些设计目前尚未在代码中实现。
