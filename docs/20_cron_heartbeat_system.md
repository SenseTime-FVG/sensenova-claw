# Cron（定时任务）与 Heartbeat（心跳巡检）系统

> 版本: v0.8 | 日期: 2026-03-10
> 前置: [14_dual_bus_architecture.md](./14_dual_bus_architecture.md), [17_system_prompt_workspace_session.md](./17_system_prompt_workspace_session.md)

---

## 1. 概述

Cron 是定时任务调度器，Heartbeat 是周期性 Agent 巡检——两者协同实现 Agent 的主动行为能力。

### 1.1 与原始 PRD 的关键适配

原始 PRD 参考 OpenClaw（Node.js），以下为适配 AgentOS 的核心变更：

| 原始方案 | 适配决策 |
|---------|---------|
| JSON 文件持久化 | SQLite 表——复用现有 Repository |
| 独立 `CronService` / `HeartbeatRunner` | `CronRuntime` / `HeartbeatRuntime`——遵循 Runtime 生命周期 |
| 内部 `emit()` / `enqueueSystemEvent()` | 通过 PublicEventBus 发布 `cron.*` / `heartbeat.*` 事件 |
| `deliver_outbound()` 直接调用渠道 | `Gateway.deliver_to_channel()` 路由 |
| Transcript 文件截断 | 删除临时 session 的 messages |
| `~/.agentbox/` 路径 | 统一到 `{storage.root}/` + SQLite |
| HEARTBEAT.md 独立管理 | 纳入 Workspace 文件体系 |

---

## 2. Cron 数据模型

### 2.1 Schedule

```python
@dataclass
class AtSchedule:
    kind: Literal["at"] = "at"
    at: str = ""                      # ISO 8601

@dataclass
class EverySchedule:
    kind: Literal["every"] = "every"
    every_ms: int = 0
    anchor_ms: int | None = None

@dataclass
class CronSchedule:
    kind: Literal["cron"] = "cron"
    expr: str = ""
    tz: str | None = None
    stagger_ms: int | None = None

Schedule = AtSchedule | EverySchedule | CronSchedule
```

### 2.2 Payload

```python
@dataclass
class SystemEventPayload:
    kind: Literal["systemEvent"] = "systemEvent"
    text: str = ""

@dataclass
class AgentTurnPayload:
    kind: Literal["agentTurn"] = "agentTurn"
    message: str = ""
    model: str | None = None
    timeout_seconds: int | None = None
    light_context: bool = False

Payload = SystemEventPayload | AgentTurnPayload
```

### 2.3 Delivery

```python
@dataclass
class CronDelivery:
    mode: Literal["none", "announce"] = "announce"
    channel_id: str | None = None     # "feishu", "websocket" 等
    to: str | None = None
    best_effort: bool = False
```

### 2.4 CronJob

```python
@dataclass
class CronJobState:
    next_run_at_ms: int | None = None
    running_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_run_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    consecutive_errors: int = 0

@dataclass
class CronJob:
    id: str
    name: str | None = None
    description: str | None = None
    schedule: Schedule = field(default_factory=AtSchedule)
    session_target: Literal["main", "isolated"] = "isolated"
    wake_mode: Literal["now", "next-heartbeat"] = "now"
    payload: Payload = field(default_factory=AgentTurnPayload)
    delivery: CronDelivery | None = None
    enabled: bool = True
    delete_after_run: bool | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0
    state: CronJobState = field(default_factory=CronJobState)
```

约束：

| 约束 | 说明 |
|------|------|
| `session_target="main"` 搭配 `payload.kind="systemEvent"` | 主会话只注入系统事件 |
| `session_target="isolated"` 搭配 `payload.kind="agentTurn"` | 隔离会话运行完整 Turn |
| `delivery` 仅对 `isolated` 生效 | |
| `at` 类型成功后默认自动删除 | |

### 2.5 SQLite 持久化

```sql
CREATE TABLE IF NOT EXISTS cron_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    schedule_json TEXT NOT NULL,
    session_target TEXT NOT NULL DEFAULT 'isolated',
    wake_mode TEXT NOT NULL DEFAULT 'now',
    payload_json TEXT NOT NULL,
    delivery_json TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    delete_after_run INTEGER,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    next_run_at_ms INTEGER,
    running_at_ms INTEGER,
    last_run_at_ms INTEGER,
    last_run_status TEXT,
    last_error TEXT,
    last_duration_ms INTEGER,
    consecutive_errors INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cron_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    status TEXT,
    error TEXT,
    duration_ms INTEGER,
    session_id TEXT,
    delivery_status TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_job ON cron_runs(job_id);
```

---

## 3. Cron 调度内核

### 3.1 Timer 驱动

```
arm_timer()
  ├── 查询所有 enabled job 的 next_run_at_ms
  ├── delay = min(next_wake - now, 60s)
  └── call_later(delay, on_timer)

on_timer()
  ├── running? → 60s 后重检 → return
  ├── running = True
  ├── 从 SQLite 加载 job 列表
  ├── collect_runnable_jobs(now) → due_jobs
  ├── 空? → recompute → arm_timer
  ├── 标记 running_at_ms → 更新 DB
  ├── 依次执行（max_concurrent_runs 限制）
  ├── apply_job_result() → 更新 DB → arm_timer
  └── finally: session_reaper.sweep(); running = False; arm_timer()
```

关键决策：最大延迟 60 秒、最小重触发 2 秒、先标记 running 再执行。

### 3.2 到期判定 & 下次执行

```python
def is_job_runnable(job: CronJob, now_ms: int, *, forced: bool = False) -> bool:
    if not job.enabled or job.state.running_at_ms is not None:
        return False
    if forced:
        return True
    return isinstance(job.state.next_run_at_ms, int) and now_ms >= job.state.next_run_at_ms

def compute_next_run_at_ms(job: CronJob, now_ms: int) -> int | None:
    match job.schedule:
        case AtSchedule():
            return None
        case EverySchedule(every_ms=interval, anchor_ms=anchor):
            if anchor is None:
                return now_ms + interval
            periods = (now_ms - anchor) // interval
            return max(anchor + (periods + 1) * interval, now_ms + 1)
        case CronSchedule(expr=expr, tz=tz, stagger_ms=stagger):
            next_ms = croniter_next(expr, now_ms, tz)
            if stagger and stagger > 0:
                next_ms += deterministic_stagger(job.id, stagger)
            return next_ms
```

### 3.3 执行模式

**主会话（systemEvent）**：

```
CronJob(session_target="main")
  ├── 发布 cron.system_event 到 PublicEventBus
  └── wake_mode=="now" → 发布 heartbeat.wake_requested
```

**隔离（agentTurn）**：

```
CronJob(session_target="isolated")
  ├── 创建 session: cron_{job_id}_{uuid}
  ├── BusRouter → PrivateEventBus → AgentRuntime.ensure_worker()
  ├── 发布 ui.user_input（source="cron"）
  ├── Worker 完成 Agent Turn → agent.step_completed
  └── 根据 delivery 投递：Gateway.deliver_to_channel()
```

### 3.4 Announce 投递

```python
async def deliver_announce(job: CronJob, run_result: RunResult, gateway: Gateway):
    if is_heartbeat_ok_only(run_result.text):
        return
    channel_id = job.delivery.channel_id
    if not channel_id:
        return
    delivery_event = EventEnvelope(
        type=CRON_DELIVERY_REQUESTED,
        session_id=run_result.session_id,
        source="cron",
        payload={"job_id": job.id, "content": run_result.text,
                 "channel_id": channel_id, "to": job.delivery.to},
    )
    await gateway.deliver_to_channel(delivery_event, channel_id)
```

### 3.5 错误处理

```python
TRANSIENT_PATTERNS = {
    "rate_limit": r"(rate[_ ]limit|too many requests|429)",
    "overloaded": r"(\b529\b|overloaded)",
    "network":    r"(network|econnreset|econnrefused|fetch failed)",
    "timeout":    r"(timeout|etimedout)",
    "server_error": r"\b5\d{2}\b",
}
```

- **at 类型**：瞬态最多 3 次退避（30s→60s→300s），永久立即禁用
- **循环类型**：`next_run = max(自然下次, 上次结束 + 退避)`，成功后重置

### 3.6 启动恢复

```python
async def run_missed_jobs(repo: Repository):
    await repo.clear_stale_cron_running()
    missed = await repo.get_runnable_cron_jobs(now_ms, include_missed=True)
    for i, job in enumerate(missed):
        if i < 5:
            await execute_job(job)
        else:
            job.state.next_run_at_ms = now_ms + (i - 4) * 5000
            await repo.update_cron_job_state(job)
```

---

## 4. Heartbeat 心跳系统

### 4.1 三层架构

```
Layer 3: run_heartbeat_once()   — 前置检查 → Prompt → Agent Turn → 回复处理 → 投递
Layer 2: HeartbeatRuntime       — 定时器 + 事件监听
Layer 1: Wake 调度              — 合并窗口 + 忙碌重试
```

### 4.2 HeartbeatRuntime

```python
class HeartbeatRuntime:
    def __init__(self, bus, publisher, agent_runtime, repo, gateway, config):
        self._bus = bus
        self._publisher = publisher
        self._agent_runtime = agent_runtime
        self._repo = repo
        self._gateway = gateway
        self._config = config
        self._timer: asyncio.TimerHandle | None = None
        self._task: asyncio.Task | None = None
        self._pending_system_events: list[str] = []

    async def start(self):
        self._task = asyncio.create_task(self._event_loop())
        self._schedule_next()

    async def stop(self):
        if self._timer: self._timer.cancel()
        if self._task: self._task.cancel()

    async def _event_loop(self):
        async for event in self._bus.subscribe():
            if event.type == CRON_SYSTEM_EVENT:
                self._pending_system_events.append(event.payload.get("text", ""))
            elif event.type == HEARTBEAT_WAKE_REQUESTED:
                await self._handle_wake_request(event)
```

### 4.3 单次执行流程

```
run_heartbeat_once(reason)
  ├── Phase 1: 检查 enabled / active_hours
  ├── Phase 2: 构建 Prompt（pending events 或读 HEARTBEAT.md）
  ├── Phase 3: 创建临时 session → Worker → Agent Turn
  ├── Phase 4: 空回复/HEARTBEAT_OK → 清理 session
  │            重复(24h) → 跳过
  │            有内容 → 投递
  └── Phase 5: Gateway → Channel 投递，发布 heartbeat.completed
```

### 4.4 HEARTBEAT_OK 协议

```python
HEARTBEAT_TOKEN = "HEARTBEAT_OK"

def strip_heartbeat_token(text: str, max_ack_chars: int = 300) -> StripResult:
    """开头或末尾的 HEARTBEAT_OK 被识别；去除后剩余 ≤ max_ack_chars → skip"""
```

HEARTBEAT_OK 轮次的临时 session 直接删除（含 messages），无需截断逻辑。

### 4.5 去重

```python
def is_duplicate_heartbeat(current: str, prev: str, prev_sent_at: int | None, now: int) -> bool:
    return (prev.strip() == current.strip()
            and prev_sent_at is not None
            and now - prev_sent_at < 86_400_000)
```

### 4.6 HEARTBEAT.md

纳入 Workspace 文件体系：

```python
# workspace/manager.py
WORKSPACE_FILES = {
    "AGENTS.md": DEFAULT_AGENTS_MD,
    "USER.md": DEFAULT_USER_MD,
    "HEARTBEAT.md": DEFAULT_HEARTBEAT_MD,
}
```

| 状态 | 行为 |
|------|------|
| 有内容 | 正常心跳 |
| 存在但空 | 跳过（省 API） |
| 不存在 | 正常心跳 |
| Cron 触发 | 绕过检查，一定执行 |

---

## 5. 事件类型

`events/types.py` 新增：

```python
CRON_JOB_ADDED = "cron.job_added"
CRON_JOB_UPDATED = "cron.job_updated"
CRON_JOB_REMOVED = "cron.job_removed"
CRON_JOB_STARTED = "cron.job_started"
CRON_JOB_FINISHED = "cron.job_finished"
CRON_SYSTEM_EVENT = "cron.system_event"
CRON_DELIVERY_REQUESTED = "cron.delivery_requested"

HEARTBEAT_WAKE_REQUESTED = "heartbeat.wake_requested"
HEARTBEAT_CHECK_STARTED = "heartbeat.check_started"
HEARTBEAT_COMPLETED = "heartbeat.completed"
```

---

## 6. 配置

```yaml
cron:
  enabled: true
  max_concurrent_runs: 1
  retry:
    max_attempts: 3
    backoff_ms: [60000, 120000, 300000]
  session_retention: "24h"
  run_log_max_entries: 2000

heartbeat:
  enabled: false
  every: "30m"
  target: "none"               # none | <channel_id>
  to: null
  prompt: >
    Read HEARTBEAT.md if it exists. Follow it strictly.
    If nothing needs attention, reply HEARTBEAT_OK.
  ack_max_chars: 300
  light_context: false
  active_hours:
    start: "08:00"
    end: "24:00"
    timezone: "local"
```

---

## 7. 集成变更

### 7.1 新增文件

```
backend/app/
├── cron/
│   ├── __init__.py
│   ├── runtime.py       # CronRuntime
│   ├── models.py        # Schedule / Payload / CronJob
│   ├── executor.py      # 执行逻辑
│   ├── backoff.py       # 错误分类 + 退避
│   └── tool.py          # cron Agent Tool
├── heartbeat/
│   ├── __init__.py
│   ├── runtime.py       # HeartbeatRuntime
│   ├── protocol.py      # HEARTBEAT_OK + 去重
│   └── config.py        # HeartbeatConfig
```

### 7.2 修改文件

| 文件 | 修改 |
|------|------|
| `main.py` | lifespan 初始化 CronRuntime + HeartbeatRuntime |
| `events/types.py` | 新增 cron.* / heartbeat.* 事件 |
| `db/repository.py` | 新增 cron_jobs / cron_runs 表操作 |
| `gateway/gateway.py` | 新增 `deliver_to_channel(event, channel_id)` |
| `core/config.py` | DEFAULT_CONFIG 新增 cron / heartbeat 段 |
| `workspace/manager.py` | 新增 HEARTBEAT.md |

### 7.3 main.py 集成

```python
# gateway.start() 之后
cron_runtime = CronRuntime(publisher, repo, agent_runtime, bus_router, gateway, cron_config)
heartbeat_runtime = HeartbeatRuntime(bus, publisher, agent_runtime, repo, gateway, heartbeat_config)
await cron_runtime.start()
await heartbeat_runtime.start()
# 关闭顺序：cron → heartbeat → 其他
```

### 7.4 Gateway 新增

```python
class Gateway:
    async def deliver_to_channel(self, event: EventEnvelope, channel_id: str) -> bool:
        channel = self._channels.get(channel_id)
        if not channel:
            return False
        try:
            await channel.send_event(event)
            return True
        except Exception as exc:
            logger.error("Delivery to %s failed: %s", channel_id, exc)
            return False
```

### 7.5 新增依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| `croniter` | `>=2.0.0` | cron 表达式解析 |

---

## 8. 实现优先级

### Phase 1: MVP

- SQLite 表（cron_jobs / cron_runs）
- CronRuntime 核心（Timer + at/every/cron 调度 + CRUD）
- 主会话执行（systemEvent + heartbeat.wake_requested）
- HeartbeatRuntime（单次执行 + HEARTBEAT_OK）
- cron Tool（add / list / remove）

### Phase 2: 完善

- 隔离执行（BusRouter → Worker → announce 投递）
- 错误重试（瞬态/永久 + 退避）
- 启动恢复（missed jobs + stagger）
- HEARTBEAT.md workspace 集成

### Phase 3: 生产级

- Active Hours + 时区
- Session 清理 + run 记录裁剪
- 去重 / 并发控制 / 错峰

---

## 9. 验收标准

1. at Job 到期正确触发
2. cron 表达式 Job 按计划周期执行
3. systemEvent Job 文本出现在 Heartbeat Prompt 中
4. isolated Job 创建独立 session 完整执行
5. HEARTBEAT_OK 时不投递、清理临时 session
6. 重启后 Job 状态恢复，错过的 Job 补执行
7. 连续失败退避递增，成功后重置
8. cron.* / heartbeat.* 事件正确发布到 PublicEventBus
9. announce 通过 Gateway → Channel 投递
10. cron/heartbeat 关闭时不影响现有功能
