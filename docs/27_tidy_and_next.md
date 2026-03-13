# AgentOS 代码整合与演进方案（v1.6）

按**运行时风险 → 代码整合 → 架构优化**排序，共 20 项变更。

---

## 一、运行时安全（第一阶段，P0/P1）

### 1.1 事件总线背压 `events/bus.py`

`PublicEventBus` / `PrivateEventBus` 使用无界 `asyncio.Queue`，慢订阅者会导致内存无限增长。

```python
class PublicEventBus:
    _DEFAULT_QUEUE_SIZE = 10000

    async def subscribe(self, maxsize: int = _DEFAULT_QUEUE_SIZE) -> AsyncIterator[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: EventEnvelope) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Queue full, dropping: type=%s session=%s", event.type, event.session_id)
                try:
                    q.get_nowait()  # 丢弃最旧事件腾出空间
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
```

不用 `await q.put()` 是因为 publish 是热路径，一个慢订阅者阻塞 publish 会级联阻塞所有事件源。

### 1.2 Gateway session 绑定泄漏 `main.py`

WebSocket 断开时只调了 `ws_channel.disconnect()`，没调 `gateway.unbind_session()`。每个断开的连接都在 `Gateway._session_bindings` 中留下永久记录。

```python
except WebSocketDisconnect:
    for sid, ws_set in list(ws_channel._session_bindings.items()):
        if websocket in ws_set:
            gateway.unbind_session(sid)
    ws_channel.disconnect(websocket)
```

### 1.3 Repository 异步化 `db/repository.py`

同步 sqlite3 阻塞事件循环。统一方案：**线程级连接复用 + 事务上下文管理器 + asyncio.to_thread**。

```python
import threading
from contextlib import contextmanager

class Repository:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or ...).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    @contextmanager
    def _tx(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        def _sync():
            with self._tx() as conn:
                conn.execute("INSERT OR IGNORE INTO sessions (...) VALUES (?, ?, ?, ?)",
                             (session_id, time.time(), time.time(), json.dumps(meta or {})))
        await asyncio.to_thread(_sync)
```

所有现有 `async def xxx` 方法都按此模式改造：内部定义 `_sync()`，用 `await asyncio.to_thread(_sync)` 执行。

### 1.4 TTL 集合 `events/router.py`, `runtime/title_runtime.py`

`BusRouter._forwarded_ids` 和 `TitleRuntime._processed_sessions` 都是无限增长的 `set[str]`。统一替换为：

```python
from collections import OrderedDict

class _TTLSet:
    def __init__(self, ttl: float = 30.0, max_size: int = 10000):
        self._data: OrderedDict[str, float] = OrderedDict()
        self._ttl = ttl
        self._max_size = max_size

    def add(self, key: str) -> None:
        self._data[key] = time.time()
        self._data.move_to_end(key)
        self._evict()

    def discard(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def _evict(self) -> None:
        now = time.time()
        while self._data:
            k, ts = next(iter(self._data.items()))
            if now - ts > self._ttl or len(self._data) > self._max_size:
                self._data.popitem(last=False)
            else:
                break
```

- `BusRouter`: `self._forwarded_ids = _TTLSet(ttl=30)`
- `TitleRuntime`: `self._processed_sessions = _TTLSet(ttl=3600)`

### 1.5 工具禁用实际生效 `tools/registry.py`, `runtime/workers/tool_worker.py`

当前 "enabled" 偏好仅影响 UI，ToolRuntime 执行时不检查。

```python
class ToolRegistry:
    def __init__(self, preferences: PreferencesService | None = None):
        self._tools: dict[str, Tool] = {}
        self._preferences = preferences
        self._register_builtin()

    def as_llm_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
            if self._is_enabled(t.name)
        ]

    def get_if_enabled(self, name: str) -> Tool | None:
        tool = self._tools.get(name)
        if tool and self._is_enabled(name):
            return tool
        return None

    def _is_enabled(self, name: str) -> bool:
        if self._preferences:
            return self._preferences.is_tool_enabled(name)
        return True
```

`ToolSessionWorker._handle_tool_requested` 中将 `self.rt.registry.get(tool_name)` 改为 `self.rt.registry.get_if_enabled(tool_name)`。

### 1.6 SQL 列名白名单 `db/repository.py`

`update_cron_job` / `update_cron_run` 用 f-string 拼接列名。

```python
_CRON_JOB_MUTABLE_COLUMNS = frozenset({
    "name", "description", "schedule_json", "session_target",
    "wake_mode", "payload_json", "delivery_json", "enabled",
    "delete_after_run", "updated_at_ms", "next_run_at_ms",
    "running_at_ms", "last_run_at_ms", "last_run_status",
    "last_error", "last_duration_ms", "consecutive_errors",
})

async def update_cron_job(self, job_id: str, updates: dict[str, Any]) -> None:
    invalid = set(updates.keys()) - _CRON_JOB_MUTABLE_COLUMNS
    if invalid:
        raise ValueError(f"Invalid column names: {invalid}")
    ...
```

---

## 二、代码整合（第二阶段）

### 2.1 提取 PreferencesService `app/services/preferences.py`

`api/agents.py` 和 `api/tools.py` 各自实现了完全相同的 `_prefs_path` / `_load_prefs` / `_save_prefs`。

```python
class PreferencesService:
    def __init__(self, workspace_dir: Path):
        self._path = workspace_dir / ".agent_preferences.json"

    def load(self) -> dict[str, Any]:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def save(self, prefs: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_tool_enabled(self, name: str) -> bool:
        return self.load().get("tools", {}).get(name, True)

    def set_tool_enabled(self, name: str, enabled: bool) -> None:
        prefs = self.load()
        prefs.setdefault("tools", {})[name] = enabled
        self.save(prefs)
```

在 `lifespan` 中初始化，挂到 `app.state.preferences`，同时注入到 `ToolRegistry`。

优先级链：`AgentConfig.tools 白名单 → Preferences 运行时覆盖 → 默认启用`。

### 2.2 提取 WorkerManagerRuntime `runtime/base.py`

`AgentRuntime`、`LLMRuntime`、`ToolRuntime` 的 start/stop/create_worker/on_destroy 逻辑完全相同。

```python
class WorkerManagerRuntime(ABC):
    def __init__(self, bus_router: BusRouter):
        self.bus_router = bus_router
        self._workers: dict[str, SessionWorker] = {}

    @abstractmethod
    async def _build_worker(self, session_id: str, private_bus: PrivateEventBus) -> SessionWorker: ...

    async def start(self) -> None:
        self.bus_router.register_worker_factory(self._create_worker)
        self.bus_router.on_destroy(self._on_session_destroy)

    async def stop(self) -> None:
        for w in self._workers.values():
            await w.stop()
        self._workers.clear()

    async def _create_worker(self, session_id: str, bus: PrivateEventBus) -> None:
        worker = await self._build_worker(session_id, bus)
        self._workers[session_id] = worker
        await worker.start()

    async def _on_session_destroy(self, session_id: str) -> None:
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
```

三个 Runtime 变为：
```python
class AgentRuntime(WorkerManagerRuntime):
    def __init__(self, bus_router, repo, context_builder, ...):
        super().__init__(bus_router)
        self.repo = repo; self.context_builder = context_builder; ...

    async def _build_worker(self, session_id, bus):
        agent_config = await self._resolve_agent_config(session_id)
        return AgentSessionWorker(session_id, bus, runtime=self, agent_config=agent_config)
```

### 2.3 SessionWorker 事件上下文追踪 `runtime/workers/base.py`

Worker 中大量重复的 EventEnvelope 构造。让 Worker 追踪 `_current_event`，自动继承 turn_id/session_id/source：

```python
class SessionWorker:
    _default_source: str = "system"

    async def _loop(self) -> None:
        async for event in self.bus.subscribe():
            self._current_event = event
            try:
                await self._handle(event)
            except Exception:
                logger.exception(...)
            finally:
                self._current_event = None

    def _envelope(self, event_type: str, payload: dict, trace_id: str | None = None) -> EventEnvelope:
        return EventEnvelope(
            type=event_type,
            session_id=self.session_id,
            turn_id=self._current_event.turn_id if self._current_event else None,
            trace_id=trace_id,
            source=self._default_source,
            payload=payload,
        )
```

子类设置 `_default_source`：`AgentSessionWorker._default_source = "agent"`，`ToolSessionWorker._default_source = "tool"` 等。

### 2.4 版本号统一 `app/core/version.py`

```python
__version__ = "1.6.0"
```

`main.py` 的 `FastAPI(version=__version__)`、`health_check` 的返回值、`README.md` 统一引用。

### 2.5 API 字段命名统一 `api/agents.py`

`AgentConfigUpdate` 中 `systemPrompt`(camelCase) 和 `can_delegate_to`(snake_case) 混用。统一用 Pydantic alias：

```python
class AgentConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    max_tokens: int | None = Field(None, alias="maxTokens")
    system_prompt: str | None = Field(None, alias="systemPrompt")
    can_delegate_to: list[str] | None = Field(None, alias="canDelegateTo")
    max_delegation_depth: int | None = Field(None, alias="maxDelegationDepth")
    # name/description/provider/model/temperature/tools/skills 保持原样
```

### 2.6 LLM 错误双通道处理 `runtime/workers/agent_worker.py`

当前 LLM 失败时错误消息被当作正常 assistant 回复处理，污染消息历史。

```python
async def _handle_llm_result(self, event: EventEnvelope) -> None:
    ...
    finish_reason = event.payload.get("finish_reason", "stop")
    if finish_reason == "error":
        error_msg = response.get("content", "发生未知错误")
        state.final_response = error_msg
        # 不加入 LLM 上下文历史，但通过 step_completed 告知用户
        await self.bus.publish(self._envelope(
            AGENT_STEP_COMPLETED,
            {"step_type": "error", "result": {"content": error_msg}, "next_action": "end", "error": True},
            trace_id=event.trace_id,
        ))
        return
    ...
```

---

## 三、架构优化（第三阶段）

### 3.1 拆分 main.py

```
backend/app/
├── main.py              # FastAPI 创建 + 路由注册（<50 行）
├── bootstrap.py         # lifespan 服务编排
├── api/sessions.py      # 从 main.py 抽出的 /api/sessions 路由
└── gateway/ws_handler.py  # WebSocket 消息分派
```

`ws_handler.py` 使用字典分派替代 if/elif 链：

```python
class WebSocketHandler:
    def __init__(self, services: Services):
        self.services = services
        self._handlers = {
            "create_session": self._handle_create_session,
            "user_input": self._handle_user_input,
            "cancel_turn": self._handle_cancel_turn,
            ...
        }

    async def handle_message(self, ws: WebSocket, message: dict) -> None:
        handler = self._handlers.get(message.get("type"))
        if handler:
            await handler(ws, message)
        else:
            await self._send_error(ws, "InvalidMessage", f"unsupported: {message.get('type')}")
```

### 3.2 Tool execute() 引入 ToolContext `tools/base.py`

当前 `_path_policy`、`_session_id` 混入 `**kwargs`，工具需要 `kwargs.pop` 清理。

```python
@dataclass
class ToolContext:
    session_id: str
    path_policy: PathPolicy | None = None
    workspace_dir: str | None = None

class Tool(ABC):
    ...
    @abstractmethod
    async def execute(self, ctx: ToolContext, **kwargs: Any) -> Any: ...
```

`ToolSessionWorker` 构造 `ToolContext` 后传入，所有内置工具从 `ctx.path_policy` 读取而非 `kwargs.pop("_path_policy")`。

### 3.3 数据库版本迁移 `db/repository.py`

替换当前 `_migrate_sessions_table` 的手动列检查：

```python
_MIGRATIONS = [
    (1, "ALTER TABLE sessions ADD COLUMN channel TEXT"),
    (2, "ALTER TABLE sessions ADD COLUMN model TEXT"),
    (3, "ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0"),
    (4, "ALTER TABLE sessions ADD COLUMN agent_id TEXT DEFAULT 'default'"),
]

def _run_migrations(self, conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] else 0
    for version, sql in _MIGRATIONS:
        if version > current:
            try:
                conn.execute(sql)
                conn.execute("INSERT INTO schema_version VALUES (?)", (version,))
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
    conn.commit()
```

### 3.4 消息历史窗口管理 `runtime/context_builder.py`

```python
def build_messages(self, user_input, history, ...) -> list[dict]:
    ...
    max_context_messages = config.get("agent.max_context_messages", 40)
    if history and len(history) > max_context_messages:
        summary_note = {"role": "system", "content": f"[已省略 {len(history) - max_context_messages} 条较早的消息]"}
        history = [summary_note] + history[-max_context_messages:]
    ...
```

### 3.5 健康检查增强 `main.py`

```python
@app.get("/health")
async def health_check() -> dict:
    services: Services = app.state.services
    db_ok = True
    try:
        with services.repo._tx() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "version": __version__,
        "timestamp": time.time(),
    }
```

### 3.6 BashCommand 审计日志 `tools/builtin.py`

不用黑名单（轻易绕过），改为结构化审计 + timeout 调优：

```python
async def execute(self, **kwargs: Any) -> Any:
    ...
    logger.info("BASH_AUDIT | session=%s cmd=%r cwd=%s", kwargs.get("_session_id"), command, cwd)
    ...
```

将 `BashCommandTool` 默认 timeout 从 300s 降至 60s。

### 3.7 TitleRuntime 共享 LLMFactory `runtime/title_runtime.py`

当前 TitleRuntime 自己 `LLMFactory()` 创建新实例，与 LLMRuntime 不一致。改为构造函数注入：

```python
class TitleRuntime:
    def __init__(self, bus: PublicEventBus, repo: Repository, llm_factory: LLMFactory):
        ...
        self.llm_factory = llm_factory  # 共享实例
```

### 3.8 EventPublisher 增加验证 `runtime/publisher.py`

```python
class EventPublisher:
    def __init__(self, bus: PublicEventBus):
        self.bus = bus

    async def publish(self, event: EventEnvelope) -> None:
        if not event.session_id:
            raise ValueError("EventEnvelope must have session_id")
        if not event.type:
            raise ValueError("EventEnvelope must have type")
        await self.bus.publish(event)
```

---

## 四、实施路线图

### 第一阶段：运行时安全

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 1 | 事件总线背压 | `events/bus.py` | 1h |
| 2 | Gateway 绑定泄漏 | `main.py` | 0.5h |
| 3 | Repository 异步化 | `db/repository.py` | 2h |
| 4 | TTL 集合 | `events/router.py`, `title_runtime.py` | 1h |
| 5 | 工具禁用生效 | `tools/registry.py`, `tool_worker.py` | 1h |
| 6 | SQL 列名白名单 | `db/repository.py` | 0.5h |

### 第二阶段：代码整合

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 7 | PreferencesService | `services/preferences.py`, `api/*.py` | 0.5h |
| 8 | WorkerManagerRuntime 基类 | `runtime/*.py` | 1h |
| 9 | SessionWorker._envelope | `workers/base.py`, 3 个 Worker | 1h |
| 10 | 版本号统一 | `core/version.py`, `main.py` | 0.5h |
| 11 | API 命名统一 | `api/agents.py` | 0.5h |
| 12 | LLM 错误双通道 | `workers/agent_worker.py` | 1h |

### 第三阶段：架构优化

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 13 | 拆分 main.py | `main.py`, `bootstrap.py`, `ws_handler.py` | 2h |
| 14 | Session API 迁移 | `api/sessions.py` | 0.5h |
| 15 | ToolContext | `tools/base.py`, 所有 Tool | 2h |
| 16 | DB 版本迁移 | `db/repository.py` | 1h |
| 17 | 消息历史窗口 | `context_builder.py` | 1h |
| 18 | 健康检查增强 | `main.py` | 0.5h |
| 19 | Bash 审计日志 | `tools/builtin.py` | 0.5h |
| 20 | TitleRuntime 共享 LLMFactory | `title_runtime.py` | 0.5h |
