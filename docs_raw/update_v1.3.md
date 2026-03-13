# 实现文档：Per-Agent 目录存储体系

> 版本: v1.3
> 日期: 2026-03-12
> 状态: Draft
> 前置: v1.0（多 Agent）, v1.2（PathPolicy）

---

## 1. 问题陈述

### 1.1 现状

当前 AgentOS 的存储是**扁平的单目录结构**：

```
./SenseAssistant/
├── workspace/
│   ├── AGENTS.md           # 全局 Agent 指令
│   ├── USER.md             # 全局用户偏好
│   ├── MEMORY.md
│   ├── HEARTBEAT.md
│   ├── skills/             # 所有 skills
│   ├── skills_state.json
│   └── .agent_preferences.json  # 工具/技能偏好（全局）
├── agentos.db              # 单一 SQLite，存所有 Agent 的 sessions/messages/events
└── memory_index.db
```

**问题**：

| 问题 | 说明 |
|------|------|
| 多 Agent 无隔离 | 所有 Agent 共用一份 AGENTS.md、一份偏好文件、一个 DB |
| 路径不规范 | `./SenseAssistant/` 是相对路径，跟随工作目录变化 |
| 不可迁移 | 用户无法简单地备份/复制/迁移单个 Agent 的数据 |
| 无法独立管理 | 删除一个 Agent 时，其 session 数据散落在全局 DB 中无法干净清除 |

### 1.2 目标

- 每个 Agent 拥有独立的目录：`~/.agentos/{agent_name}/`
- 目录下包含该 Agent 的所有 Markdown 配置文件 + sessions 数据
- 删除 Agent = 删除目录，零残留
- 全局数据（config、跨 Agent 资源）集中在 `~/.agentos/` 根目录
- 向后兼容：default Agent 开箱即用

---

## 2. 目录结构设计

### 2.1 总体布局

```
~/.agentos/                              # 系统根目录（AGENTOS_HOME）
├── config.yml                           # 全局配置
├── global.db                            # 全局数据库（cron_jobs、跨 Agent 元数据）
│
├── shared/                              # 共享资源
│   ├── skills/                          # 内置 skills（只读）
│   └── tools/                           # 自定义工具配置（预留）
│
├── default/                             # default Agent 目录
│   ├── AGENTS.md                        # Agent 行为指令
│   ├── USER.md                          # 用户偏好
│   ├── MEMORY.md                        # 长期记忆（v0.6）
│   ├── HEARTBEAT.md                     # 心跳配置（v0.8）
│   ├── config.json                      # Agent 配置（序列化的 AgentConfig）
│   ├── preferences.json                 # 工具/技能启停偏好
│   ├── agent.db                         # 该 Agent 的 sessions + messages + events
│   ├── memory_index.db                  # 该 Agent 的向量索引
│   ├── workspace/                       # 文件操作安全区（PathPolicy GREEN zone）
│   ├── skills/                          # Agent 专属 skills（已安装的市场 skills）
│   └── sessions/                        # session 产出物
│       ├── sess_abc12345/
│       │   └── artifacts/               # 该 session 产出的文件（write_file 的结果等）
│       └── sess_def67890/
│           └── artifacts/
│
├── research-agent/                      # 用户创建的 Agent
│   ├── AGENTS.md
│   ├── USER.md
│   ├── config.json
│   ├── agent.db
│   ├── workspace/
│   ├── skills/
│   └── sessions/
│
└── code-reviewer/                       # 另一个自定义 Agent
    ├── AGENTS.md
    ├── config.json
    ├── agent.db
    ├── workspace/
    └── sessions/
```

### 2.2 文件职责说明

#### Markdown 文件（Agent 行为配置层）

| 文件 | 用途 | 注入方式 | 必须 |
|------|------|----------|:----:|
| `AGENTS.md` | Agent 行为指令（工具使用规范、回复风格等） | 注入 system prompt | ✅ |
| `USER.md` | 用户偏好（语言、称呼、代码风格等） | 注入 system prompt | ❌ |
| `MEMORY.md` | 长期记忆提取物（v0.6 MemoryManager 写入） | 注入 system prompt | ❌ |
| `HEARTBEAT.md` | 心跳巡检指令（v0.8 HeartbeatRuntime 读取） | 直接读取 | ❌ |
| `config.json` | AgentConfig 序列化（provider/model/temperature 等） | 启动时加载 | ✅ |
| `preferences.json` | 工具/技能 enable/disable 偏好 | API 读写 | ❌ |

**设计原则**：Markdown 文件是人类可编辑的——用户可以直接打开文本编辑器修改。JSON 文件是程序管理的——通过 API 或 UI 操作。

#### sessions/ 目录

```python
class SessionDir:
    """每个 session 在文件系统上的表示"""
    session_id: str          # 如 "sess_abc12345"
    artifacts_dir: Path      # sessions/{session_id}/artifacts/

    # session 的结构化数据（messages, events, turns）仍存储在 agent.db
    # sessions/ 目录只存放 session 产出的文件资产
```

**为什么不把 messages 也存成文件？**

| 方案 | 优势 | 劣势 |
|------|------|------|
| messages 存 SQLite | 查询快、索引灵活、事务安全 | 不够"可读" |
| messages 存 JSONL 文件 | 人类可读、git 友好 | 查询慢、无事务、并发写冲突 |
| **混合方案（推荐）** | SQLite 为主存储 + JSONL 导出备份 | 需要同步机制 |

推荐方案：**agent.db 为主，sessions/ 存产出物和可选的 JSONL 导出**。

具体来说：
- `agent.db` 存储 sessions、turns、messages、events 四张表（与现有 schema 一致）
- `sessions/{session_id}/artifacts/` 存储该 session 中 write_file 工具产出的文件
- 可选提供 `export_session(session_id)` 功能，将完整 session 导出为 `session.json`

#### agent.db schema

与当前 `agentos.db` 的 schema 完全一致，但范围缩小到单个 Agent：

```sql
-- 只包含该 Agent 的数据，无需 agent_id 字段
CREATE TABLE sessions (...);
CREATE TABLE turns (...);
CREATE TABLE messages (...);
CREATE TABLE events (...);
```

#### global.db schema

存放跨 Agent 的全局数据：

```sql
-- 定时任务（可能涉及多个 Agent）
CREATE TABLE cron_jobs (...);
CREATE TABLE cron_runs (...);

-- Agent 注册表索引（快速查找，权威数据在各 Agent 目录的 config.json）
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT,
    dir_path TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at REAL,
    updated_at REAL
);
```

### 2.3 路径解析规则

```python
AGENTOS_HOME = Path("~/.agentos").expanduser()  # 可通过环境变量 AGENTOS_HOME 覆盖

def agent_dir(agent_id: str) -> Path:
    """获取 Agent 根目录"""
    return AGENTOS_HOME / agent_id

def agent_db(agent_id: str) -> Path:
    """获取 Agent 数据库路径"""
    return agent_dir(agent_id) / "agent.db"

def agent_workspace(agent_id: str) -> Path:
    """获取 Agent 工作区（PathPolicy GREEN zone）"""
    return agent_dir(agent_id) / "workspace"

def agent_sessions_dir(agent_id: str) -> Path:
    """获取 Agent 的 sessions 产出目录"""
    return agent_dir(agent_id) / "sessions"

def agent_markdown(agent_id: str, filename: str) -> Path:
    """获取 Agent 的 Markdown 文件"""
    return agent_dir(agent_id) / filename

def global_db() -> Path:
    return AGENTOS_HOME / "global.db"

def shared_skills_dir() -> Path:
    return AGENTOS_HOME / "shared" / "skills"
```

---

## 3. 关键设计决策

### 3.1 为什么每个 Agent 一个 SQLite 而不是全局单库？

| 全局单库 | Per-Agent 库 |
|----------|-------------|
| 查询方便（一次 JOIN 查所有 Agent 的 session） | 每次需指定 Agent |
| 删除 Agent 需要逐表清理 | **删除 Agent = rm -rf 目录** |
| DB 文件越来越大 | 单库文件小，可独立备份 |
| 并发写锁冲突（多 Agent 同时写一个 DB） | **无锁冲突（各写各的）** |
| 迁移/备份需整体导出再过滤 | **直接 cp 目录** |

**结论**：Per-Agent SQLite 更符合"Agent = 独立实体"的语义。代价是跨 Agent 查询需要遍历多个 DB——但实际需求中几乎不需要跨 Agent 查询。

### 3.2 config.yml 放在哪里？

```
优先级（高 → 低）：
1. 环境变量（OPENAI_API_KEY 等）
2. 项目级 config.yml（当前工作目录或 git repo 根目录的 config.yml）
3. ~/.agentos/config.yml（全局默认配置）
4. 代码内 DEFAULT_CONFIG
```

**改动**：Config 类增加多路径搜索。全局 `~/.agentos/config.yml` 是 fallback，项目级 config 优先。

### 3.3 shared/skills 和 Agent 专属 skills 的关系

```
skills 加载顺序：
1. 内置 skills（代码内 backend/app/skills/builtin/）
2. 共享 skills（~/.agentos/shared/skills/）
3. Agent 专属 skills（~/.agentos/{agent_id}/skills/）

优先级：Agent 专属 > 共享 > 内置（同名覆盖）
```

这意味着用户可以在 Agent 目录下放置定制化的 skill，覆盖全局版本。

### 3.4 workspace 和 sessions/artifacts 的区别

| | workspace/ | sessions/{sid}/artifacts/ |
|---|---|---|
| 用途 | Agent 的通用文件操作区 | 特定 session 的产出物 |
| 生命周期 | 持久，跨 session | 随 session 存在 |
| PathPolicy | GREEN zone，自由读写 | GREEN zone（子目录） |
| 典型文件 | 用户项目文件、笔记 | LLM 生成的代码、报告 |

**默认行为**：write_file 工具默认写入 `workspace/`。如果启用 session 隔离，可以改为写入 `sessions/{current_session_id}/artifacts/`。

---

## 4. 代码改动方案

### 4.1 新增 AgentHome 管理类

```python
# backend/app/core/agent_home.py

"""Per-Agent 目录管理器

负责创建/加载/清理 Agent 目录结构。
是 Agent 存储体系的唯一入口。
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENTOS_HOME_ENV = "AGENTOS_HOME"
DEFAULT_HOME = "~/.agentos"


class AgentHome:
    """管理单个 Agent 的目录结构"""

    def __init__(self, agent_id: str, base_dir: Path | None = None):
        self.agent_id = agent_id
        self._base = base_dir or _get_agentos_home()
        self.root = self._base / agent_id

    # ── 目录 ──

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    # ── 文件 ──

    @property
    def db_path(self) -> Path:
        return self.root / "agent.db"

    @property
    def memory_db_path(self) -> Path:
        return self.root / "memory_index.db"

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def preferences_path(self) -> Path:
        return self.root / "preferences.json"

    # ── Markdown 文件 ──

    def markdown_path(self, name: str) -> Path:
        """AGENTS.md / USER.md / MEMORY.md / HEARTBEAT.md"""
        return self.root / name

    # ── Session 产出目录 ──

    def session_artifacts(self, session_id: str) -> Path:
        return self.sessions_dir / session_id / "artifacts"

    # ── 生命周期 ──

    def ensure(self) -> None:
        """确保目录结构存在，创建缺失的目录和默认文件"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)

        # 创建默认 Markdown 文件（不覆盖已有）
        _ensure_default_md(self.root / "AGENTS.md", DEFAULT_AGENTS_MD)
        _ensure_default_md(self.root / "USER.md", DEFAULT_USER_MD)

    def destroy(self) -> None:
        """删除整个 Agent 目录（慎用）"""
        import shutil
        if self.root.exists():
            shutil.rmtree(self.root)

    # ── 配置读写 ──

    def load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text("utf-8"))
        return {}

    def save_config(self, data: dict[str, Any]) -> None:
        self.config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load_preferences(self) -> dict:
        if self.preferences_path.exists():
            return json.loads(self.preferences_path.read_text("utf-8"))
        return {}

    def save_preferences(self, prefs: dict) -> None:
        self.preferences_path.write_text(
            json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8"
        )


class AgentHomeRegistry:
    """管理所有 Agent 的 Home 目录"""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or _get_agentos_home()
        self._homes: dict[str, AgentHome] = {}

    @property
    def base_dir(self) -> Path:
        return self._base

    @property
    def global_db_path(self) -> Path:
        return self._base / "global.db"

    @property
    def shared_skills_dir(self) -> Path:
        return self._base / "shared" / "skills"

    @property
    def config_path(self) -> Path:
        return self._base / "config.yml"

    def get(self, agent_id: str) -> AgentHome:
        """获取或创建 AgentHome 实例（惰性缓存）"""
        if agent_id not in self._homes:
            self._homes[agent_id] = AgentHome(agent_id, self._base)
        return self._homes[agent_id]

    def list_agents(self) -> list[str]:
        """扫描磁盘，返回所有存在的 Agent ID"""
        if not self._base.exists():
            return []
        agents = []
        skip = {"shared"}
        for p in self._base.iterdir():
            if p.is_dir() and p.name not in skip and not p.name.startswith("."):
                config_file = p / "config.json"
                if config_file.exists():
                    agents.append(p.name)
        return sorted(agents)

    def ensure_base(self) -> None:
        """确保系统根目录和共享目录存在"""
        self._base.mkdir(parents=True, exist_ok=True)
        self.shared_skills_dir.mkdir(parents=True, exist_ok=True)


# ── 内部辅助 ──

def _get_agentos_home() -> Path:
    env = os.environ.get(AGENTOS_HOME_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return Path(DEFAULT_HOME).expanduser().resolve()


def _ensure_default_md(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


DEFAULT_AGENTS_MD = """\
# Agent Instructions

## 工具使用规范
- 在需要时主动调用工具，不要猜测结果
- 优先使用 bash_command 执行系统命令
- 使用 serper_search 获取最新信息
- 文件操作前先用 read_file 确认内容

## 回复风格
- 简洁明了，避免冗余
- 代码块使用正确的语言标记
- 默认使用中文回复，除非用户使用其他语言
- 对不确定的内容如实说明，不要编造
"""

DEFAULT_USER_MD = """\
# User Profile

## 基本信息
- 称呼: （请填写你希望 AI 如何称呼你）
- 语言偏好: 中文

## 工作环境
- 操作系统: （自动检测）
- 常用工具: （请填写）

## 偏好设置
- 回复详细程度: 适中
- 代码风格: （请填写偏好的代码风格）
"""
```

### 4.2 改造 Repository（Per-Agent 数据库）

```python
# 核心变化：Repository 不再是全局单例，而是 per-Agent 实例

class Repository:
    def __init__(self, db_path: Path):
        """接收明确的 db_path，不再从 config 读取"""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # schema 不变，但移除 agent_id 字段（因为数据库本身就是按 Agent 隔离的）
    # sessions 表不再需要 agent_id 列

    # ... 其他方法签名不变 ...


class GlobalRepository:
    """全局数据库，管理 cron_jobs 和 Agent 索引"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # cron_jobs、cron_runs 相关方法从 Repository 迁移到这里
    # 新增 agents 表管理
```

### 4.3 改造 Config

```python
# backend/app/core/config.py

# 配置文件搜索路径（优先级从高到低）
CONFIG_SEARCH_PATHS = [
    Path.cwd() / "config.yml",              # 当前工作目录
    Path(__file__).resolve().parents[3] / "config.yml",  # 项目根目录
    _get_agentos_home() / "config.yml",      # 全局配置
]

DEFAULT_CONFIG = {
    "system": {
        "home_dir": "~/.agentos",            # AGENTOS_HOME
        # 移除 workspace_dir 和 database_path（现在由 AgentHome 管理）
        "log_level": "DEBUG",
        "max_concurrent_sessions": 10,
    },
    # ... 其余不变 ...
}
```

### 4.4 改造 main.py（lifespan 初始化）

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # 初始化 AgentHome 体系
    home_registry = AgentHomeRegistry()
    home_registry.ensure_base()

    # 确保 default Agent 存在
    default_home = home_registry.get("default")
    default_home.ensure()

    # Per-Agent 数据库
    default_repo = Repository(default_home.db_path)
    await default_repo.init()

    # 全局数据库
    global_repo = GlobalRepository(home_registry.global_db_path)
    await global_repo.init()

    # 加载 workspace 文件（从 Agent 目录）
    context_files = await load_workspace_files(str(default_home.root))

    # Skills 加载（合并 shared + Agent 专属）
    shared_skills_dir = home_registry.shared_skills_dir
    agent_skills_dir = default_home.skills_dir

    # AgentRegistry 从 Agent 目录加载
    agent_registry = AgentRegistry(home_registry=home_registry)
    agent_registry.load_from_config(config.data)
    agent_registry.load_from_homes()  # 扫描所有 Agent 目录

    # PathPolicy 使用 Agent workspace
    path_policy = PathPolicy(workspace=default_home.workspace)

    # ... 其余初始化逻辑 ...

    app.state.home_registry = home_registry
```

### 4.5 改造 AgentRegistry

```python
class AgentRegistry:
    """管理 Agent 配置注册表

    配置来源优先级：
    1. ~/.agentos/{agent_id}/config.json（持久化配置）
    2. config.yml 的 agents 节（静态配置）
    3. config.yml 的 agent 节（default Agent 向后兼容）
    """

    def __init__(self, home_registry: AgentHomeRegistry):
        self._agents: dict[str, AgentConfig] = {}
        self._home_registry = home_registry

    def load_from_homes(self) -> None:
        """从 AgentHome 目录扫描加载所有 Agent"""
        for agent_id in self._home_registry.list_agents():
            home = self._home_registry.get(agent_id)
            data = home.load_config()
            if data:
                agent = AgentConfig.from_dict(data)
                self.register(agent)

    def save(self, agent: AgentConfig) -> None:
        """保存 Agent 配置到其 Home 目录"""
        home = self._home_registry.get(agent.id)
        home.ensure()
        home.save_config(agent.to_dict())

    def delete(self, agent_id: str) -> bool:
        """删除 Agent：注销 + 删除目录"""
        if agent_id == "default":
            return False
        self._agents.pop(agent_id, None)
        home = self._home_registry.get(agent_id)
        home.destroy()
        return True
```

### 4.6 改造 workspace/manager.py

```python
async def ensure_workspace(agent_home: AgentHome) -> None:
    """确保 Agent Home 目录结构完整"""
    agent_home.ensure()  # 创建目录 + 默认 Markdown 文件

async def load_workspace_files(agent_home: AgentHome) -> list[ContextFile]:
    """从 Agent Home 读取 Markdown 文件注入 system prompt"""
    files: list[ContextFile] = []
    for name in ["AGENTS.md", "USER.md", "MEMORY.md"]:
        path = agent_home.markdown_path(name)
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                files.append(ContextFile(name=name, content=content))
    return files
```

### 4.7 改造 workspace API

```python
# backend/app/api/workspace.py

def _agent_home(request: Request, agent_id: str = "default") -> AgentHome:
    home_registry = request.app.state.home_registry
    return home_registry.get(agent_id)

@router.get("/{agent_id}/files/{filename}")
async def read_file(agent_id: str, filename: str, request: Request):
    home = _agent_home(request, agent_id)
    path = home.markdown_path(filename)
    if not path.exists():
        raise HTTPException(404)
    return {"filename": filename, "content": path.read_text("utf-8")}

@router.put("/{agent_id}/files/{filename}")
async def write_file(agent_id: str, filename: str, body: FileContent, request: Request):
    home = _agent_home(request, agent_id)
    path = home.markdown_path(filename)
    path.write_text(body.content, encoding="utf-8")
    return {"status": "saved"}
```

### 4.8 Session 创建时的目录关联

```python
# 在 WebSocket 创建 session 时，关联到当前 Agent 的目录
session_id = f"sess_{uuid.uuid4().hex[:12]}"
agent_id = payload.get("agent_id", "default")

# 确保 session 产出目录存在
home = home_registry.get(agent_id)
artifacts_dir = home.session_artifacts(session_id)
artifacts_dir.mkdir(parents=True, exist_ok=True)

# session 存入 Agent 的数据库
agent_repo = get_agent_repo(agent_id)
await agent_repo.create_session(session_id=session_id, meta={...})
```

---

## 5. 与 PathPolicy（v1.2）的整合

### 5.1 每个 Agent 独立的 PathPolicy

```python
# PathPolicy 的 workspace 指向 Agent 的 workspace 目录
agent_home = home_registry.get(agent_id)
path_policy = PathPolicy(
    workspace=agent_home.workspace,    # ~/.agentos/{agent_id}/workspace
    granted_paths=config.get("system.granted_paths", []),
)
```

### 5.2 GREEN zone 范围

每个 Agent 的 GREEN zone 是其自己的 `workspace/` 和 `sessions/` 目录：

```python
def classify(self, target: Path) -> PathZone:
    resolved = target.expanduser().resolve()
    # Agent workspace 是 GREEN
    if _is_within(resolved, self.workspace):
        return PathZone.GREEN
    # Agent sessions 目录也是 GREEN
    if _is_within(resolved, self.workspace.parent / "sessions"):
        return PathZone.GREEN
    # ...
```

---

## 6. 迁移策略

### 6.1 自动迁移（首次启动检测）

```python
async def migrate_to_per_agent_home(
    old_workspace: Path,       # ./SenseAssistant/workspace
    old_db: Path,              # ./SenseAssistant/agentos.db
    home_registry: AgentHomeRegistry,
) -> None:
    """一次性迁移：旧的扁平结构 → Per-Agent 目录"""
    default_home = home_registry.get("default")

    # 1. 迁移 Markdown 文件
    for md_name in ["AGENTS.md", "USER.md", "MEMORY.md", "HEARTBEAT.md"]:
        old_path = old_workspace / md_name
        new_path = default_home.markdown_path(md_name)
        if old_path.exists() and not new_path.exists():
            shutil.copy2(old_path, new_path)

    # 2. 迁移偏好文件
    old_prefs = old_workspace / ".agent_preferences.json"
    if old_prefs.exists() and not default_home.preferences_path.exists():
        shutil.copy2(old_prefs, default_home.preferences_path)

    # 3. 迁移数据库
    if old_db.exists() and not default_home.db_path.exists():
        shutil.copy2(old_db, default_home.db_path)

    # 4. 迁移 workspace 内容
    if old_workspace.exists():
        for item in old_workspace.iterdir():
            if item.name.startswith(".") or item.name in ["AGENTS.md", "USER.md", "MEMORY.md", "HEARTBEAT.md"]:
                continue
            dest = default_home.workspace / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

    # 5. 迁移 skills
    old_skills = old_workspace / "skills"
    if old_skills.exists():
        # 内置 skills -> shared/skills/
        # 已安装 skills -> default/skills/
        for skill_dir in old_skills.iterdir():
            if skill_dir.is_dir():
                dest = default_home.skills_dir / skill_dir.name
                if not dest.exists():
                    shutil.copytree(skill_dir, dest)

    # 6. 迁移已有的 Agent 配置
    old_agents_dir = old_workspace.parent / "agents"  # 如果有的话
    if old_agents_dir and old_agents_dir.exists():
        for fp in old_agents_dir.glob("*.json"):
            data = json.loads(fp.read_text("utf-8"))
            agent_id = data.get("id")
            if agent_id and agent_id != "default":
                agent_home = home_registry.get(agent_id)
                agent_home.ensure()
                agent_home.save_config(data)

    logger.info("迁移完成：%s -> %s", old_workspace, home_registry.base_dir)
```

### 6.2 迁移触发时机

在 `lifespan()` 中，在初始化 AgentHomeRegistry 之后、创建 Repository 之前：

```python
# 检测是否需要迁移
old_workspace = Path(config.get("system.workspace_dir", "./SenseAssistant/workspace"))
old_db = Path(config.get("system.database_path", "./SenseAssistant/agentos.db"))
if old_db.exists() and not home_registry.get("default").db_path.exists():
    await migrate_to_per_agent_home(old_workspace, old_db, home_registry)
```

---

## 7. 数据流变化

### 7.1 创建 Agent

```
用户: POST /api/agents {id: "research-agent", name: "Research Agent", ...}
  → AgentRegistry.create()
  → AgentHome("research-agent").ensure()
    → 创建 ~/.agentos/research-agent/
    → 创建 AGENTS.md, workspace/, sessions/, skills/
  → AgentHome.save_config(agent.to_dict())
    → 写入 config.json
  → Repository(agent_home.db_path).init()
    → 创建 agent.db + schema
```

### 7.2 创建 Session

```
WebSocket: {type: "create_session", payload: {agent_id: "research-agent"}}
  → agent_home = home_registry.get("research-agent")
  → repo = Repository(agent_home.db_path)
  → repo.create_session(session_id)
  → agent_home.session_artifacts(session_id).mkdir()
    → 创建 ~/.agentos/research-agent/sessions/sess_xxx/artifacts/
```

### 7.3 Agent 的文件操作（write_file）

```
Agent 调用 write_file(file_path="report.md", content="...")
  → PathPolicy.check_write("report.md")
  → safe_resolve("report.md")
    → ~/.agentos/research-agent/workspace/report.md  (GREEN zone)
  → 写入成功
```

### 7.4 删除 Agent

```
用户: DELETE /api/agents/research-agent
  → AgentRegistry.delete("research-agent")
  → AgentHome("research-agent").destroy()
    → rm -rf ~/.agentos/research-agent/
    → 所有数据（DB、Markdown、sessions、skills）一次性清除
```

---

## 8. 改动清单

| 文件 | 改动 | 优先级 |
|------|------|:------:|
| **新增** `backend/app/core/agent_home.py` | AgentHome + AgentHomeRegistry | P0 |
| `backend/app/core/config.py` | 移除 workspace_dir/database_path，新增 home_dir，多路径搜索 config.yml | P0 |
| `backend/app/db/repository.py` | 接收 db_path 参数，拆分 GlobalRepository | P0 |
| `backend/app/main.py` | lifespan 用 AgentHomeRegistry 初始化，per-Agent repo | P0 |
| `backend/app/agents/registry.py` | 改用 AgentHomeRegistry 持久化 | P0 |
| `backend/app/workspace/manager.py` | 接收 AgentHome 而非 workspace_dir 字符串 | P0 |
| `backend/app/api/workspace.py` | 按 agent_id 读写 Markdown | P1 |
| `backend/app/api/agents.py` | 偏好文件从 AgentHome 读写 | P1 |
| `backend/app/runtime/workers/agent_worker.py` | 从 AgentHome 加载上下文文件 | P1 |
| `backend/app/runtime/context_builder.py` | 传入 agent_home 获取路径 | P1 |
| `backend/app/memory/manager.py` | db_path 从 AgentHome 获取 | P1 |
| `backend/app/skills/registry.py` | 合并 shared + Agent 专属 skills 目录 | P2 |
| **新增** 迁移脚本 | 旧结构一键迁移到 ~/.agentos/ | P1 |

---

## 9. 测试要点

### 9.1 单元测试

```python
def test_agent_home_paths():
    """验证 AgentHome 各路径正确"""
    home = AgentHome("test-agent", base_dir=Path("/tmp/.agentos"))
    assert home.root == Path("/tmp/.agentos/test-agent")
    assert home.workspace == Path("/tmp/.agentos/test-agent/workspace")
    assert home.db_path == Path("/tmp/.agentos/test-agent/agent.db")
    assert home.sessions_dir == Path("/tmp/.agentos/test-agent/sessions")
    assert home.markdown_path("AGENTS.md") == Path("/tmp/.agentos/test-agent/AGENTS.md")

def test_agent_home_ensure():
    """验证 ensure() 创建目录和默认文件"""
    with tempfile.TemporaryDirectory() as tmp:
        home = AgentHome("default", base_dir=Path(tmp))
        home.ensure()
        assert home.workspace.exists()
        assert home.sessions_dir.exists()
        assert (home.root / "AGENTS.md").exists()

def test_agent_home_registry_list():
    """验证 list_agents 只返回有 config.json 的目录"""
    with tempfile.TemporaryDirectory() as tmp:
        registry = AgentHomeRegistry(base_dir=Path(tmp))
        # 创建有 config.json 的 Agent
        home = registry.get("agent-a")
        home.ensure()
        home.save_config({"id": "agent-a", "name": "A"})
        # 创建没有 config.json 的目录（不应被识别为 Agent）
        (Path(tmp) / "not-an-agent").mkdir()
        assert registry.list_agents() == ["agent-a"]

def test_agent_home_destroy():
    """验证 destroy 完全清除 Agent 目录"""
    with tempfile.TemporaryDirectory() as tmp:
        home = AgentHome("test", base_dir=Path(tmp))
        home.ensure()
        home.save_config({"id": "test"})
        assert home.root.exists()
        home.destroy()
        assert not home.root.exists()
```

### 9.2 集成测试

- 创建 Agent → 验证目录结构完整
- 创建 Session → 验证 session 数据写入 Agent 专属 DB
- 删除 Agent → 验证目录完全清除、全局 DB 无残留
- 迁移测试 → 旧结构迁移后数据完整可用

### 9.3 E2E 测试

- 通过 WebSocket 创建 session，选择不同 Agent → 验证数据隔离
- Agent A 的 write_file 不影响 Agent B 的 workspace
- 前端 Agent 配置页面正确显示每个 Agent 的 Markdown 文件

---

## 10. 不做的事

| 不做 | 原因 |
|------|------|
| 分布式 Agent 存储（S3 / 远程 FS） | 当前是单机部署，本地文件系统足够 |
| Agent 间共享 session | 违反隔离原则，如需跨 Agent 通信走事件总线 |
| 自动同步 Markdown 文件到远端 | 复杂度高，可通过 git 管理 Agent 目录实现 |
| 按 session 分库（每个 session 一个 SQLite） | 过度拆分，查询复杂度增加，per-Agent 粒度已足够 |

---

## 11. 后续迭代

- **Agent 模板**：`agentos create-agent --template research` → 从模板目录复制预设的 AGENTS.md + skills
- **Agent 导出/导入**：`agentos export research-agent --output research-agent.tar.gz` → 打包整个 Agent 目录
- **Agent 版本控制**：Agent 目录可以是 git repo，支持回滚 Markdown 和配置变更
- **多用户隔离**：`~/.agentos/` → `~/.agentos/users/{user_id}/` → 每个用户独立的 Agent 集合
