# PRD: AgentBox — Cron（定时任务）与 Heartbeat（心跳巡检）系统

> 版本: 0.1.0
> 作者: shaoyuyao
> 日期: 2026-03-10
> 状态: Draft
> 前置: [prd-python-agent-framework.md](./prd-python-agent-framework.md), [prd-agentbox-system-prompt-workspace-session.md](./prd-agentbox-system-prompt-workspace-session.md)
> 参考实现: OpenClaw `src/cron/`, `src/infra/heartbeat-runner.ts`, `src/infra/heartbeat-wake.ts`, `src/agents/tools/cron-tool.ts`

---

## 1. 概述

### 1.1 一句话描述

Cron 是 AgentBox Gateway 的内置定时任务调度器，Heartbeat 是周期性 Agent 巡检机制——两者协同实现 Agent 的"主动行为能力"：Cron 负责"精确时间做精确事"，Heartbeat 负责"定期巡检找需要关注的事"。

### 1.2 解决的问题

Agent 默认是被动的——只有用户发消息才会响应。但很多场景需要 Agent 主动行动：

| 场景 | 需要的能力 |
|------|-----------|
| "每天早上 7 点给我发一份日报" | 定时触发 + 隔离执行 + 结果投递 |
| "20 分钟后提醒我开会" | 一次性定时 + 主会话事件注入 |
| "持续关注邮箱，有紧急邮件就通知我" | 周期性巡检 + 条件性推送 |
| "异步命令跑完了通知我结果" | 事件驱动唤醒 + 结果转发 |
| "Gateway 重启后恢复之前没跑完的任务" | 任务持久化 + 启动恢复 |

### 1.3 核心取舍

| 做 | 不做 |
|---|---|
| Gateway 进程内调度（`setTimeout` 链式驱动） | 不做独立调度进程或外部 Scheduler（不引入 APScheduler/Celery Beat） |
| JSON 文件持久化 Job 状态 | 不做数据库存储（不引入 SQLite/Redis） |
| 标准 cron 表达式 + 固定间隔 + 一次性定时三种调度 | 不做复杂日历调度（不做排除节假日等） |
| 主会话 / 隔离会话两种执行模式 | 不做跨 Agent 的任务编排 |
| Heartbeat 内置 HEARTBEAT_OK 协议和 transcript 修剪 | 不做通用的 Agent 轮询框架 |
| 错误指数退避 + 瞬态/永久错误分类 | 不做死信队列或任务迁移 |

### 1.4 设计原则

| 原则 | 说明 |
|------|------|
| **进程内调度** | 调度器运行在 Gateway 进程中，不依赖外部组件，零运维成本 |
| **持久化恢复** | 所有 Job 和状态持久化到磁盘，进程重启不丢失任何调度 |
| **两种执行域** | 主会话（共享上下文）和隔离会话（独立 Agent Turn）泾渭分明 |
| **静默优先** | Heartbeat 默认静默——无事可报时不打扰用户，有内容才推送 |
| **事件驱动可唤醒** | 除定时触发外，Cron 和外部事件都可以随时唤醒 Heartbeat |
| **渐进降级** | 投递失败不阻塞调度循环，单 Job 异常不影响其他 Job |

---

## 2. Cron 定时任务系统

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户接口层                             │
│  CLI (cron add/list/edit/run)  │  Agent Tool (cron)         │
│  Gateway RPC (cron.*)          │  Web UI (CronView)          │
├─────────────────────────────────────────────────────────────┤
│                        CronService                           │
│  start() │ stop() │ add() │ update() │ remove()              │
│  run()   │ enqueueRun() │ list() │ status() │ wake()        │
├─────────────────────────────────────────────────────────────┤
│                        调度内核                               │
│  Timer (arm/stop)  │  onTimer() │  collectRunnableJobs()     │
│  applyJobResult()  │  runMissedJobs()                        │
├─────────────────────────────────────────────────────────────┤
│                        执行层                                 │
│  Main Session: enqueueSystemEvent() → Heartbeat              │
│  Isolated: runIsolatedAgentJob() → cron:<jobId> session      │
├─────────────────────────────────────────────────────────────┤
│                        持久化层                               │
│  CronStore (jobs.json)  │  RunLog (runs/<jobId>.jsonl)       │
│  Session Reaper                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据模型

#### 2.2.1 Schedule（调度时间）

三种调度类型，覆盖绝大多数定时场景：

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class AtSchedule:
    """一次性定时：指定 ISO 8601 时间戳。"""
    kind: Literal["at"] = "at"
    at: str = ""                      # ISO 8601，无时区视为 UTC

@dataclass
class EverySchedule:
    """固定间隔循环。"""
    kind: Literal["every"] = "every"
    every_ms: int = 0                 # 间隔毫秒
    anchor_ms: int | None = None      # 锚点时间（用于计算对齐）

@dataclass
class CronSchedule:
    """标准 cron 表达式（5 字段或 6 字段含秒）。"""
    kind: Literal["cron"] = "cron"
    expr: str = ""                    # cron 表达式
    tz: str | None = None             # IANA 时区，None 使用主机本地时区
    stagger_ms: int | None = None     # 错峰窗口（0 精确调度）

Schedule = AtSchedule | EverySchedule | CronSchedule
```

#### 2.2.2 Payload（执行载荷）

```python
@dataclass
class SystemEventPayload:
    """主会话事件注入：将文本作为系统事件入队，等待 Heartbeat 处理。"""
    kind: Literal["systemEvent"] = "systemEvent"
    text: str = ""

@dataclass
class AgentTurnPayload:
    """隔离 Agent 执行：在独立会话中运行一次完整的 Agent Turn。"""
    kind: Literal["agentTurn"] = "agentTurn"
    message: str = ""                          # 发给 Agent 的 prompt
    model: str | None = None                   # 模型覆盖
    thinking: str | None = None                # 思考级别覆盖
    timeout_seconds: int | None = None         # 超时覆盖（0 = 不超时）
    light_context: bool = False                # 轻量 bootstrap（不注入 workspace 文件）

Payload = SystemEventPayload | AgentTurnPayload
```

#### 2.2.3 Delivery（投递配置）

```python
@dataclass
class CronDelivery:
    """控制隔离 Job 执行结果的投递方式。"""
    mode: Literal["none", "announce", "webhook"] = "announce"
    channel: str | None = None         # 渠道 ID（如 "telegram", "feishu"）或 "last"
    to: str | None = None              # 渠道内目标（如 chat_id、webhook URL）
    account_id: str | None = None      # 多账号渠道中的账号 ID
    best_effort: bool = False          # True 时投递失败不导致 Job 失败
```

投递模式说明：

| 模式 | 行为 |
|------|------|
| `announce` | 将结果发送到目标聊天，并在主会话写入简短摘要 |
| `webhook` | 将 finished 事件 JSON POST 到 `delivery.to` URL |
| `none` | 不投递，仅内部记录 |

#### 2.2.4 CronJob（完整 Job 定义）

```python
@dataclass
class CronJobState:
    """Job 的运行时状态（可变，由调度器维护）。"""
    next_run_at_ms: int | None = None
    running_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_run_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    consecutive_errors: int = 0
    last_delivery_status: Literal["delivered", "not-delivered", "unknown", "not-requested"] | None = None

@dataclass
class CronJob:
    """一个 Cron Job 的完整定义。"""
    id: str                                     # 唯一 ID（UUID）
    name: str | None = None                     # 人类可读名称
    description: str | None = None
    schedule: Schedule = field(default_factory=AtSchedule)
    session_target: Literal["main", "isolated"] = "isolated"
    wake_mode: Literal["now", "next-heartbeat"] = "now"
    payload: Payload = field(default_factory=AgentTurnPayload)
    delivery: CronDelivery | None = None        # 仅 isolated 有效
    agent_id: str | None = None                 # 多 Agent 时绑定特定 Agent
    enabled: bool = True
    delete_after_run: bool | None = None        # at 类型默认 True
    created_at_ms: int = 0
    updated_at_ms: int = 0
    state: CronJobState = field(default_factory=CronJobState)
```

约束规则：

| 约束 | 说明 |
|------|------|
| `session_target="main"` 必须搭配 `payload.kind="systemEvent"` | 主会话只能注入系统事件 |
| `session_target="isolated"` 必须搭配 `payload.kind="agentTurn"` | 隔离会话运行完整 Agent Turn |
| `delivery` 仅对 `isolated` 生效 | 主会话的输出由 Heartbeat 统一处理 |
| `at` 类型 Job 成功后默认自动删除 | 设 `delete_after_run=False` 改为仅禁用 |

#### 2.2.5 持久化格式

```python
@dataclass
class CronStoreFile:
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
```

存储路径：`~/.agentbox/cron/jobs.json`
运行日志：`~/.agentbox/cron/runs/<jobId>.jsonl`（每行一条 JSON 运行记录）

### 2.3 调度内核

#### 2.3.1 Timer 驱动模型

调度不使用外部 Scheduler，而是基于 `asyncio` 的单定时器链式驱动：

```
arm_timer()
  │
  ├── 扫描所有 enabled job 的 next_run_at_ms
  ├── 取最小值作为下次唤醒时间
  ├── delay = min(next_wake - now, MAX_TIMER_DELAY)  # 最大 60 秒
  └── asyncio.get_event_loop().call_later(delay, on_timer)

on_timer()
  │
  ├── 如果 running（有 job 正在执行）→ 设置 60s 后重检 → return
  ├── running = True
  ├── 上锁，从磁盘重新加载 store
  ├── collect_runnable_jobs(now) → due_jobs
  │
  ├── 如果 due_jobs 为空
  │     └── maintenance recompute → persist → arm_timer
  │
  ├── 标记 due_jobs 的 running_at_ms → persist
  │
  ├── 并发执行（受 max_concurrent_runs 限制，默认 1）
  │     for job in due_jobs:
  │       result = await execute_job_core_with_timeout(job)
  │
  ├── 上锁，从磁盘重新加载 store
  ├── 对每个结果调用 apply_job_result()
  ├── persist → arm_timer
  │
  └── finally:
        session_reaper.sweep()   # 清理过期 cron session
        running = False
        arm_timer()
```

**关键设计决策**：

1. **最大定时器延迟 60 秒**：即使下个 Job 在 1 小时后，也每 60 秒醒一次，防止系统时钟漂移或进程休眠导致错过调度
2. **执行期间看门狗**：Job 执行期间持续设置 60 秒定时器，即使 Agent Turn 挂住也能重新检查
3. **最小重触发间隔 2 秒**（`MIN_REFIRE_GAP_MS`）：防止 `computeJobNextRunAtMs` 返回同一秒导致死循环
4. **先标记 running 再执行**：持久化 `running_at_ms` 后再释放锁，防止并发触发同一 Job

#### 2.3.2 Job 是否到期的判定

```python
def is_job_runnable(job: CronJob, now_ms: int, *, forced: bool = False) -> bool:
    if not job.enabled:
        return False
    if job.state.running_at_ms is not None:
        return False  # 已在运行
    if forced:
        return True

    next_run = job.state.next_run_at_ms
    if isinstance(next_run, int) and now_ms >= next_run:
        return True

    return False
```

#### 2.3.3 下次执行时间计算

```python
def compute_next_run_at_ms(job: CronJob, now_ms: int) -> int | None:
    match job.schedule:
        case AtSchedule():
            # 一次性 Job 没有"下次"
            return None

        case EverySchedule(every_ms=interval, anchor_ms=anchor):
            # 从锚点计算下一个对齐的时间槽
            if anchor is None:
                return now_ms + interval
            elapsed = now_ms - anchor
            periods = elapsed // interval
            next_ms = anchor + (periods + 1) * interval
            return max(next_ms, now_ms + 1)

        case CronSchedule(expr=expr, tz=tz, stagger_ms=stagger):
            # 使用 croniter 解析 cron 表达式
            next_ms = croniter_next(expr, now_ms, tz)
            if stagger and stagger > 0:
                # 确定性错峰：基于 job.id 的 hash 偏移
                offset = deterministic_stagger(job.id, stagger)
                next_ms += offset
            return next_ms
```

**Top-of-hour 错峰**：对于 `0 * * * *` 这类整点表达式，自动应用最多 5 分钟的确定性偏移，避免多实例同时触发。固定小时表达式（如 `0 7 * * *`）保持精确。

#### 2.3.4 并发控制

```python
MAX_CONCURRENT_RUNS = 1  # 默认值，可通过 cron.max_concurrent_runs 配置

# 执行时使用 worker 池模式
async def execute_batch(state, due_jobs):
    concurrency = min(state.max_concurrent_runs, len(due_jobs))
    cursor = 0

    async def worker():
        nonlocal cursor
        while cursor < len(due_jobs):
            idx = cursor
            cursor += 1
            results[idx] = await run_due_job(due_jobs[idx])

    await asyncio.gather(*[worker() for _ in range(concurrency)])
```

### 2.4 执行模式

#### 2.4.1 主会话执行（System Event）

```
CronJob (session_target="main", payload.kind="systemEvent")
  │
  ├── enqueue_system_event(text, agent_id=job.agent_id)
  │     → 将文本注入系统事件队列
  │
  └── wake_mode == "now"?
        ├── Yes → run_heartbeat_once(reason="cron:<jobId>")
        │         → 立即触发一次 Heartbeat，Prompt 中包含 cron 事件文本
        └── No  → request_heartbeat_now(reason="cron:<jobId>")
                  → 等待下一次自然 Heartbeat 周期
```

主会话 Job 的特点：
- 事件文本会被 Heartbeat 的 `buildCronEventPrompt()` 包装为专门的 Prompt
- 执行结果直接在主会话上下文中产出
- 适合需要主会话完整上下文的任务（如"检查一下日程"）

#### 2.4.2 隔离执行（Agent Turn）

```
CronJob (session_target="isolated", payload.kind="agentTurn")
  │
  ├── 创建独立会话 session_key="cron:<jobId>:run:<uuid>"
  ├── Prompt 前缀: "[cron:<jobId> <name>]"
  ├── 每次 run 全新 session（无上下文继承）
  │
  ├── run_isolated_agent_job(job, message, abort_signal)
  │     → 完整的 Agent Turn，可用工具、可调用 API
  │
  └── 执行完成后根据 delivery.mode 投递：
        ├── "announce" → 发送结果到目标渠道 + 主会话写入摘要
        ├── "webhook"  → HTTP POST finished 事件到 delivery.to
        └── "none"     → 仅记录，不投递
```

隔离 Job 的特点：
- 每次运行创建全新会话 ID，无前置对话上下文
- Prompt 标注来源 `[cron:<jobId> <name>]` 便于追踪
- HEARTBEAT_OK 类回复不投递（无事可报）
- 已通过消息工具发送过的结果不重复投递

#### 2.4.3 Announce 投递流程

```python
async def deliver_announce(job: CronJob, run_result: RunResult):
    """将隔离 Job 的输出通过渠道投递给用户。"""
    # 1. 无实质内容（HEARTBEAT_OK 等）→ 跳过
    if is_heartbeat_ok_only(run_result.text):
        return

    # 2. 如果 run 中已经通过消息工具发送过 → 跳过（防重复）
    if run_result.already_sent_to_target:
        return

    # 3. 解析投递目标
    channel = job.delivery.channel or "last"
    to = job.delivery.to

    # 4. 发送到目标渠道
    await deliver_outbound(channel=channel, to=to, payloads=run_result.payloads)

    # 5. 在主会话写入简短摘要（供后续 Heartbeat 可见）
    summary = truncate(run_result.text, 200)
    enqueue_system_event(f"[cron:{job.id}] completed: {summary}")
    if job.wake_mode == "now":
        request_heartbeat_now(reason=f"cron:{job.id}")
```

### 2.5 错误处理与重试

#### 2.5.1 错误分类

```python
TRANSIENT_PATTERNS = {
    "rate_limit": r"(rate[_ ]limit|too many requests|429|resource.*exhausted)",
    "overloaded": r"(\b529\b|overloaded|high demand|capacity exceeded)",
    "network":    r"(network|econnreset|econnrefused|fetch failed|socket)",
    "timeout":    r"(timeout|etimedout)",
    "server_error": r"\b5\d{2}\b",
}

def is_transient_error(error: str) -> bool:
    """瞬态错误可重试；非瞬态为永久错误。"""
    return any(re.search(pattern, error, re.I) for pattern in TRANSIENT_PATTERNS.values())
```

#### 2.5.2 重试策略

**一次性 Job（`at` 类型）**：

```
瞬态错误 → 最多重试 3 次，指数退避：
  第 1 次重试: 30 秒后
  第 2 次重试: 1 分钟后
  第 3 次重试: 5 分钟后
  超过 3 次  → 禁用 Job

永久错误 → 立即禁用 Job
成功     → 删除 Job（或禁用，如果 delete_after_run=False）
```

**循环 Job（`cron` / `every` 类型）**：

```
任何错误 → 指数退避叠加到自然调度：
  连续第 1 次: 30 秒
  连续第 2 次: 1 分钟
  连续第 3 次: 5 分钟
  连续第 4 次: 15 分钟
  连续第 5+ 次: 60 分钟

next_run = max(自然下次执行时间, 上次结束 + 退避时间)
成功后 → consecutive_errors 重置，退避消失
```

#### 2.5.3 `apply_job_result` 状态更新

```python
def apply_job_result(job: CronJob, result: RunResult) -> bool:
    """更新 Job 状态，返回 True 表示应删除此 Job。"""
    job.state.running_at_ms = None
    job.state.last_run_at_ms = result.started_at
    job.state.last_run_status = result.status
    job.state.last_error = result.error
    job.state.last_duration_ms = result.ended_at - result.started_at

    if result.status == "error":
        job.state.consecutive_errors += 1
        # 连续失败告警（可选）
        maybe_emit_failure_alert(job)
    else:
        job.state.consecutive_errors = 0

    # 一次性 Job 成功后删除
    should_delete = (
        job.schedule.kind == "at"
        and job.delete_after_run is True
        and result.status == "ok"
    )
    if not should_delete:
        job.state.next_run_at_ms = compute_next_with_backoff(job, result)

    return should_delete
```

### 2.6 启动恢复（Missed Jobs）

Gateway 重启时，可能有 Job 在停机期间到期但未执行。

```python
MAX_MISSED_JOBS_PER_RESTART = 5
MISSED_JOB_STAGGER_MS = 5000  # 5 秒间隔

async def run_missed_jobs(state: CronServiceState):
    """启动时检查并执行错过的 Job。"""
    # 1. 清除 stale running 标记（上次崩溃残留）
    for job in state.store.jobs:
        if job.state.running_at_ms is not None:
            job.state.running_at_ms = None

    # 2. 收集所有到期的 Job（包括通过 last_run 推断错过的 cron Job）
    missed = collect_runnable_jobs(state, now_ms, allow_missed_by_last_run=True)

    # 3. 前 N 个立即执行，其余错开
    immediate = missed[:MAX_MISSED_JOBS_PER_RESTART]
    deferred = missed[MAX_MISSED_JOBS_PER_RESTART:]

    # 4. 执行 immediate
    for job in immediate:
        await execute_job(state, job)

    # 5. 为 deferred 设置错开时间
    offset = MISSED_JOB_STAGGER_MS
    for job in deferred:
        job.state.next_run_at_ms = now_ms + offset
        offset += MISSED_JOB_STAGGER_MS
```

### 2.7 维护机制

#### 2.7.1 Session 清理

隔离 Job 每次运行创建新 session，需要定期清理：

```python
DEFAULT_SESSION_RETENTION = "24h"  # 可配置

async def sweep_cron_run_sessions(config: CronConfig, now_ms: int):
    """清理过期的 cron run session 条目和 transcript 文件。"""
    retention_ms = parse_duration(config.session_retention)
    # 在每次 on_timer 的 finally 块中运行（自节流：每 5 分钟最多一次）
    for session in cron_sessions:
        if now_ms - session.created_at > retention_ms:
            archive_transcript(session)
            remove_session_entry(session)
```

#### 2.7.2 运行日志裁剪

```python
DEFAULT_RUN_LOG_MAX_BYTES = 2_000_000  # 2 MB
DEFAULT_RUN_LOG_KEEP_LINES = 2000

async def prune_run_log(job_id: str, config: CronConfig):
    """运行日志超过大小限制时只保留最新 N 行。"""
    log_path = f"~/.agentbox/cron/runs/{job_id}.jsonl"
    if file_size(log_path) > config.run_log.max_bytes:
        keep_newest_lines(log_path, config.run_log.keep_lines)
```

### 2.8 配置

```python
@dataclass
class CronRetryConfig:
    max_attempts: int = 3
    backoff_ms: list[int] = field(default_factory=lambda: [60_000, 120_000, 300_000])
    retry_on: list[str] | None = None  # None 表示所有瞬态错误

@dataclass
class CronRunLogConfig:
    max_bytes: int = 2_000_000
    keep_lines: int = 2000

@dataclass
class CronConfig:
    enabled: bool = True
    store: str = "~/.agentbox/cron/jobs.json"
    max_concurrent_runs: int = 1
    retry: CronRetryConfig = field(default_factory=CronRetryConfig)
    session_retention: str = "24h"       # duration 字符串或 "false" 禁用
    run_log: CronRunLogConfig = field(default_factory=CronRunLogConfig)
    webhook_token: str | None = None     # webhook 模式的 Bearer token
```

### 2.9 用户接口

#### 2.9.1 CLI 命令

```bash
# 一次性提醒（主会话，立即唤醒）
agentbox cron add \
  --name "提醒开会" \
  --at "20m" \
  --session main \
  --system-event "提醒：20 分钟后有产品评审会议" \
  --wake now \
  --delete-after-run

# 循环任务（隔离会话，结果发到飞书）
agentbox cron add \
  --name "早间日报" \
  --cron "0 7 * * *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "总结昨天的工作和今天的待办事项" \
  --announce \
  --channel feishu \
  --to "oc_xxxxxxxxxxxx"

# 管理
agentbox cron list
agentbox cron edit <jobId> --message "更新后的 prompt" --model opus
agentbox cron run <jobId>             # 立即执行
agentbox cron runs --id <jobId>       # 查看运行历史
```

#### 2.9.2 Agent Tool（cron）

Agent 可以通过 `cron` 工具自主管理定时任务：

```python
@dataclass
class CronToolParams:
    action: Literal["status", "list", "add", "update", "remove", "run", "runs", "wake"]
    job_id: str | None = None         # update/remove/run/runs 需要
    job: dict | None = None           # add 需要（CronJob 结构）
    patch: dict | None = None         # update 需要（部分更新）
    text: str | None = None           # wake 需要
    mode: str | None = None           # wake/run 的模式
    include_disabled: bool = False    # list 时是否包含已禁用的
```

工具描述（注入到 LLM）：

> Manage Gateway cron jobs (status/list/add/update/remove/run/runs) and send wake events.
> Default: prefer isolated agentTurn jobs unless the user explicitly wants a main-session system event.

#### 2.9.3 Gateway RPC

| 方法 | 说明 |
|------|------|
| `cron.status` | 调度器状态（enabled、job 数量、下次唤醒时间） |
| `cron.list` | Job 列表（分页、搜索、排序） |
| `cron.add` | 创建 Job |
| `cron.update` | 更新 Job（部分 patch） |
| `cron.remove` | 删除 Job |
| `cron.run` | 手动触发 Job（force 或 due） |
| `cron.runs` | 查看 Job 运行历史 |

### 2.10 事件系统

Cron 调度器对外发出事件，供 UI、日志和监控消费：

```python
@dataclass
class CronEvent:
    job_id: str
    action: Literal["added", "updated", "removed", "started", "finished"]
    run_at_ms: int | None = None
    duration_ms: int | None = None
    status: str | None = None         # ok / error / skipped
    error: str | None = None
    summary: str | None = None
    delivered: bool | None = None
    next_run_at_ms: int | None = None
    model: str | None = None
    provider: str | None = None
    usage: dict | None = None         # token 用量
```

---

## 3. Heartbeat 心跳巡检系统

### 3.1 架构总览

Heartbeat 由三层组成：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: runHeartbeatOnce()   — 单次执行逻辑               │
│  前置检查 → Prompt 构建 → Agent 调用 → 回复处理 → 消息投递    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: HeartbeatRunner      — 多 Agent 调度循环           │
│  per-agent 定时器 │ scheduleNext() │ updateConfig()         │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: HeartbeatWake        — 唤醒调度与合并               │
│  requestHeartbeatNow() │ 合并窗口 │ 优先级 │ 忙碌重试        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Layer 1: Wake 唤醒调度层

这是最底层的调度基础设施，管理"何时真正执行心跳"。

#### 3.2.1 唤醒来源（Reason）

```python
class HeartbeatReasonKind(Enum):
    RETRY = "retry"              # 上次被跳过后的自动重试
    INTERVAL = "interval"        # Runner 定时器到期
    MANUAL = "manual"            # 用户手动触发
    EXEC_EVENT = "exec-event"    # 异步命令完成
    WAKE = "wake"                # Cron wake、系统事件
    CRON = "cron"                # Cron Job 触发
    HOOK = "hook"                # 外部 Hook（如 Gmail）
    OTHER = "other"              # 其他
```

优先级排序：`RETRY(0) < INTERVAL(1) < DEFAULT(2) < ACTION(3)`

ACTION 级别包括 `manual`、`exec-event`、`hook`——这些是"有明确事件要处理"的唤醒，优先级最高。

#### 3.2.2 合并与调度机制

```python
DEFAULT_COALESCE_MS = 250    # 合并窗口
DEFAULT_RETRY_MS = 1_000     # 忙碌重试间隔

class HeartbeatWakeState:
    handler: HeartbeatWakeHandler | None = None
    pending_wakes: dict[str, PendingWakeReason] = {}  # key = "agentId::sessionKey"
    running: bool = False
    timer: asyncio.TimerHandle | None = None
    timer_kind: Literal["normal", "retry"] | None = None

def request_heartbeat_now(
    reason: str = "requested",
    coalesce_ms: int = DEFAULT_COALESCE_MS,
    agent_id: str | None = None,
    session_key: str | None = None,
):
    """任何组件都可以调用此函数唤醒 Heartbeat。"""
    # 1. 将 wake reason 加入 pending（同一 target 只保留最高优先级）
    queue_pending_wake_reason(reason, agent_id, session_key)
    # 2. 调度定时器（合并窗口内多次调用只执行一次）
    schedule(coalesce_ms, kind="normal")
```

定时器触发时的流程：

```python
async def on_wake_timer():
    if running:
        # 上一次还在跑 → 标记 scheduled，等结束后重调度
        scheduled = True
        schedule(delay, kind)
        return

    # 批量提取 pending wakes
    batch = list(pending_wakes.values())
    pending_wakes.clear()
    running = True

    try:
        for wake in batch:
            result = await handler(reason=wake.reason, agent_id=wake.agent_id, ...)
            if result.status == "skipped" and result.reason == "requests-in-flight":
                # 主队列忙 → 1 秒后重试
                queue_pending_wake_reason(wake.reason, ...)
                schedule(DEFAULT_RETRY_MS, kind="retry")
    finally:
        running = False
        if pending_wakes or scheduled:
            schedule(delay, kind="normal")
```

**关键设计**：
- **retry 定时器不可被抢占**：防止 0ms 的 reschedule 击穿退避
- **批量处理**：一次 tick 处理所有 pending 请求，减少执行次数
- **同一 target 合并**：相同 `agentId::sessionKey` 的多次唤醒只保留最高优先级

### 3.3 Layer 2: HeartbeatRunner 调度循环

Runner 管理多 Agent 的心跳调度，维护每个 Agent 的独立定时状态。

```python
@dataclass
class HeartbeatAgentState:
    agent_id: str
    heartbeat: HeartbeatConfig | None
    interval_ms: int          # 心跳间隔
    last_run_ms: int | None   # 上次执行时间
    next_due_ms: int          # 下次到期时间

class HeartbeatRunner:
    agents: dict[str, HeartbeatAgentState]
    timer: asyncio.TimerHandle | None
    stopped: bool

    def start(self, config: AgentBoxConfig):
        """初始化所有 Agent 的心跳状态，注册 wake handler。"""
        for agent in resolve_heartbeat_agents(config):
            interval_ms = parse_duration(agent.heartbeat.every)
            self.agents[agent.id] = HeartbeatAgentState(
                agent_id=agent.id,
                heartbeat=agent.heartbeat,
                interval_ms=interval_ms,
                next_due_ms=now + interval_ms,
            )
        set_heartbeat_wake_handler(self._run)
        self._schedule_next()

    def _schedule_next(self):
        """设置定时器到最近一个 Agent 的到期时间。"""
        next_due = min(a.next_due_ms for a in self.agents.values())
        delay = max(0, next_due - now)
        self.timer = call_later(delay, lambda: request_heartbeat_now(reason="interval"))

    async def _run(self, reason: str, agent_id: str | None, ...):
        """被 wake handler 调用，执行到期的 Agent 心跳。"""
        is_interval = reason == "interval"

        for agent in self.agents.values():
            if is_interval and now < agent.next_due_ms:
                continue  # 未到期的 Agent 跳过

            result = await run_heartbeat_once(
                config=self.config,
                agent_id=agent.agent_id,
                heartbeat=agent.heartbeat,
                reason=reason,
            )

            if result.status == "skipped" and result.reason == "requests-in-flight":
                return result  # 不推进调度，wake 层会重试

            # 推进调度
            agent.last_run_ms = now
            agent.next_due_ms = now + agent.interval_ms

        self._schedule_next()
```

### 3.4 Layer 3: 单次执行逻辑 (`run_heartbeat_once`)

这是心跳系统最核心的函数，完整流程如下：

```
run_heartbeat_once(config, agent_id, heartbeat, reason)
  │
  ├─── Phase 1: 前置检查（Guard Checks）
  │     ├── 全局开关 heartbeats_enabled?
  │     ├── Agent 级别 is_heartbeat_enabled_for_agent()?
  │     ├── 间隔合法 resolve_heartbeat_interval_ms()?
  │     ├── 活跃时段 is_within_active_hours()?
  │     └── 主队列空闲 get_queue_size(CommandLane.Main) == 0?
  │
  ├─── Phase 2: Preflight（预飞检查）
  │     ├── 解析 reason 类型 → isExecEvent / isCronEvent / isWake
  │     ├── 解析 session → main session key + store + entry
  │     ├── 检查 pending system events（cron 事件、exec 完成事件）
  │     └── 检查 HEARTBEAT.md 文件
  │           ├── 文件有内容 → 继续
  │           ├── 文件为空（仅标题/空行）→ skip("empty-heartbeat-file")
  │           ├── 文件不存在 → 继续（模型自行判断）
  │           └── cron/exec/wake 原因 → 绕过文件检查
  │
  ├─── Phase 3: 构建 Prompt
  │     ├── exec completion → "异步命令已完成，结果在系统消息中..."
  │     ├── cron events → "定时提醒已触发，内容是：\n{事件文本}"
  │     └── 普通心跳 → 配置的 heartbeat.prompt（默认引导读 HEARTBEAT.md）
  │
  ├─── Phase 4: 执行 Agent Turn
  │     ├── 记录 transcript 当前大小（用于后续修剪）
  │     ├── ctx = { Body: prompt, From: sender, SessionKey: ..., Provider: "heartbeat" }
  │     └── reply = await get_reply_from_config(ctx, is_heartbeat=True)
  │
  ├─── Phase 5: 处理回复
  │     │
  │     ├── 空回复（无文本无媒体）
  │     │     → 恢复 session.updatedAt（不算"新活动"）
  │     │     → 修剪 transcript（截断回心跳前大小）
  │     │     → 可选发送 HEARTBEAT_OK 消息（showOk=true 时）
  │     │     → emit("ok-empty")
  │     │
  │     ├── HEARTBEAT_OK 回复
  │     │     → strip_heartbeat_token(text, max_ack_chars=300)
  │     │     → 剩余内容 ≤ ackMaxChars → 视为"无事可报"
  │     │     → 恢复 updatedAt + 修剪 transcript
  │     │     → emit("ok-token")
  │     │
  │     ├── 重复消息（24h 内相同文本）
  │     │     → 恢复 updatedAt + 修剪 transcript
  │     │     → emit("skipped", reason="duplicate")
  │     │
  │     └── 有实质内容
  │           → 进入投递流程
  │
  └─── Phase 6: 投递
        ├── delivery target 缺失 → emit("skipped", reason="no-target")
        ├── visibility.showAlerts == false → emit("skipped", reason="alerts-disabled")
        ├── channel plugin 未就绪 → emit("skipped", reason=readiness.reason)
        └── 投递成功
              → deliver_outbound_payloads(channel, to, payloads)
              → 记录 lastHeartbeatText + lastHeartbeatSentAt（用于去重）
              → emit("sent")
```

### 3.5 HEARTBEAT_OK 协议

这是 Heartbeat 系统的核心设计——模型通过特殊 token 表达"无事可报"：

```python
HEARTBEAT_TOKEN = "HEARTBEAT_OK"
DEFAULT_ACK_MAX_CHARS = 300

def strip_heartbeat_token(text: str, max_ack_chars: int) -> StripResult:
    """
    规则：
    1. HEARTBEAT_OK 出现在回复的开头或末尾时才被识别
    2. 出现在中间位置不做特殊处理
    3. 去除 token 后，剩余内容 ≤ max_ack_chars → should_skip=True
    4. exec completion 事件时强制不跳过
    """
```

**为什么需要这个协议**：

- Heartbeat 每 30 分钟运行一次，大多数时候"没什么事"
- 如果每次都发消息，用户会被淹没
- `HEARTBEAT_OK` 让模型明确表达"我检查过了，没什么需要关注的"
- 系统据此跳过投递、恢复时间戳、修剪 transcript，极大减少噪音

### 3.6 Transcript 修剪

HEARTBEAT_OK 的对话轮次对后续上下文毫无信息量。如果不清理，每 30 分钟就会累积一轮无用的 user+assistant 对话。

```python
async def prune_heartbeat_transcript(transcript_path: str, pre_heartbeat_size: int):
    """将 transcript 文件截断回心跳前的大小，移除无信息量的对话轮次。"""
    current_size = file_size(transcript_path)
    if current_size > pre_heartbeat_size:
        truncate(transcript_path, pre_heartbeat_size)
```

实现方式：在 Agent Turn 之前记录 transcript 文件大小，如果结果是 HEARTBEAT_OK，直接截断回原来的大小。

### 3.7 重复消息去重

```python
def is_duplicate_heartbeat(
    current_text: str,
    prev_text: str,
    prev_sent_at: int | None,
    now: int,
) -> bool:
    """24 小时内相同文本视为重复，不再投递。"""
    if not prev_text.strip():
        return False
    if current_text.strip() != prev_text.strip():
        return False
    if prev_sent_at is None:
        return False
    return now - prev_sent_at < 24 * 60 * 60 * 1000
```

防止模型在连续多次心跳中重复发送相同的提醒（"你有一封未读邮件" × N 次）。

### 3.8 Visibility 可见性控制

三层配置优先级：per-account > per-channel > channel-defaults > global defaults

```python
@dataclass
class HeartbeatVisibility:
    show_ok: bool = False         # HEARTBEAT_OK 时是否发送消息（默认静默）
    show_alerts: bool = True      # 有内容时是否发送（默认发送）
    use_indicator: bool = True    # 是否发出 UI 状态指示事件
```

| 场景 | 配置 |
|------|------|
| 默认（静默 OK，告警发送） | 无需配置 |
| 全部静默（仅日志） | `show_ok: false, show_alerts: false, use_indicator: false` |
| 仅状态指示（不发消息） | `show_ok: false, show_alerts: false, use_indicator: true` |
| 某渠道显示 OK | `channels.telegram.heartbeat: { show_ok: true }` |

### 3.9 Active Hours（活跃时段）

```python
@dataclass
class ActiveHoursConfig:
    start: str = "08:00"     # HH:MM 格式
    end: str = "24:00"       # 支持 24:00 表示午夜
    timezone: str = "user"   # "user" | "local" | IANA 时区

def is_within_active_hours(config, heartbeat, now_ms) -> bool:
    """活跃时段外自动跳过心跳。"""
    # 支持跨午夜窗口（如 22:00 - 06:00）
    if end > start:
        return current >= start and current < end
    else:
        return current >= start or current < end
```

### 3.10 Heartbeat 配置

```python
@dataclass
class HeartbeatConfig:
    every: str = "30m"                          # 间隔（0m 禁用）
    model: str | None = None                    # 模型覆盖
    target: str = "none"                        # none | last | <channel>
    to: str | None = None                       # 渠道内目标
    account_id: str | None = None               # 多账号渠道 ID
    prompt: str = (
        "Read HEARTBEAT.md if it exists (workspace context). "
        "Follow it strictly. Do not infer or repeat old tasks from prior chats. "
        "If nothing needs attention, reply HEARTBEAT_OK."
    )
    ack_max_chars: int = 300                    # HEARTBEAT_OK 后允许的最大字符数
    light_context: bool = False                 # 仅注入 HEARTBEAT.md
    include_reasoning: bool = False             # 投递 Reasoning: 消息
    direct_policy: str = "allow"                # allow | block（DM 投递策略）
    active_hours: ActiveHoursConfig | None = None
    session: str | None = None                  # 指定 session（默认 main）
    suppress_tool_error_warnings: bool = False
```

### 3.11 HEARTBEAT.md

`HEARTBEAT.md` 是放在 Agent workspace 中的可选文件，作为心跳的"巡检清单"：

```markdown
# Heartbeat checklist

- 快速扫描：邮箱里有紧急事项吗？
- 白天时段，如果没有其他待办，做一次轻量问候
- 如果有任务被阻塞，记录缺少什么，下次和用户确认
```

行为规则：

| HEARTBEAT.md 状态 | 行为 |
|-------------------|------|
| 有内容 | 正常运行心跳，Prompt 引导读取此文件 |
| 存在但为空（仅标题/空行） | **跳过心跳**（节省 API 调用） |
| 不存在 | 正常运行心跳，模型自行判断要做什么 |
| Cron/Exec/Wake 触发 | **绕过**文件检查，一定执行 |

---

## 4. Cron 与 Heartbeat 的协同

### 4.1 交互关系

```
                    ┌─────────────────┐
                    │   Cron Service   │
                    │  (定时任务调度器)  │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   Main Session Job    Isolated Job       wake() 命令
   (systemEvent)       (agentTurn)
          │                  │                  │
          │                  │                  │
          ▼                  │                  ▼
  enqueueSystemEvent()       │        enqueueSystemEvent()
          │                  │                  │
          ▼                  │                  ▼
  ┌───────────────┐          │        ┌───────────────┐
  │ Heartbeat     │          │        │ Heartbeat     │
  │ Wake Layer    │◀─────────┼────────│ Wake Layer    │
  │               │  wake_mode="now"  │               │
  └───────┬───────┘          │        └───────────────┘
          │                  │
          ▼                  ▼
  ┌───────────────┐   ┌──────────────────┐
  │ Heartbeat     │   │ Isolated Agent   │
  │ runOnce()     │   │ Turn             │
  │               │   │ cron:<jobId>     │
  │ Prompt 中包含  │   │                  │
  │ cron 事件文本  │   │ delivery →       │
  └───────────────┘   │ announce/webhook │
                      └──────────────────┘
```

### 4.2 各组件的职责边界

| 组件 | 职责 | 不做 |
|------|------|------|
| **Cron** | 精确时间调度、Job 持久化、执行和投递 | 不做"巡检决策"（那是 Heartbeat 的事） |
| **Heartbeat** | 周期性 Agent 巡检、回复处理、智能静默 | 不做精确定时（那是 Cron 的事） |
| **Wake Layer** | 唤醒合并、优先级调度、忙碌重试 | 不做业务逻辑判断 |
| **System Events** | 跨组件的事件传递队列 | 不做持久化 |

### 4.3 典型场景流转

**场景 1：用户说"20 分钟后提醒我开会"**

```
1. Agent 调用 cron tool: add(at="20m", session="main", systemEvent="提醒开会", wake="now")
2. CronService 创建 Job，计算 next_run_at_ms → 持久化 → arm_timer
3. 20 分钟后 on_timer() 触发
4. execute_job_core: enqueue_system_event("提醒开会") + run_heartbeat_once(reason="cron:xxx")
5. Heartbeat Prompt: "定时提醒已触发，内容是：\n提醒开会\n请用友好的方式转达给用户"
6. Agent 回复: "该开会啦！你 20 分钟前设的提醒 🕐"
7. Heartbeat 投递到用户的聊天渠道
8. Job 成功 → delete_after_run=true → 删除 Job
```

**场景 2：循环日报任务**

```
1. CLI: agentbox cron add --name "早间日报" --cron "0 7 * * *" --session isolated ...
2. 每天 7:00, on_timer() 触发
3. execute_job_core: run_isolated_agent_job(session="cron:xxx:run:uuid")
4. Agent 在隔离会话中执行，可调用工具、读取数据
5. 执行完成 → delivery.mode="announce" → 发送到目标渠道
6. 同时在主会话注入摘要 "[cron:xxx] completed: ..."
7. Job 状态更新 → 计算下次执行时间 → persist → arm_timer
```

**场景 3：心跳巡检发现紧急邮件**

```
1. HeartbeatRunner 定时器到期 → requestHeartbeatNow(reason="interval")
2. Wake 层合并，调用 handler
3. runHeartbeatOnce: 读取 HEARTBEAT.md → Prompt: "检查邮箱有无紧急事项..."
4. Agent 调用 gmail 工具 → 发现紧急邮件
5. Agent 回复: "你有一封来自 CEO 的紧急邮件，主题是..."
6. normalize: 非 HEARTBEAT_OK → 有实质内容
7. deliver_outbound: 发送到用户的 Telegram
8. 记录 lastHeartbeatText（下次如果相同内容则去重）
```

---

## 5. 事件系统

### 5.1 Heartbeat 事件

```python
@dataclass
class HeartbeatEvent:
    ts: int                                  # 时间戳
    status: Literal["sent", "ok-empty", "ok-token", "skipped", "failed"]
    to: str | None = None                    # 投递目标
    channel: str | None = None               # 投递渠道
    account_id: str | None = None
    preview: str | None = None               # 回复预览（前 200 字）
    duration_ms: int | None = None           # 执行耗时
    has_media: bool = False
    reason: str | None = None                # 跳过原因
    silent: bool = False                     # 是否静默抑制
    indicator_type: Literal["ok", "alert", "error"] | None = None  # UI 状态
```

| status | 含义 | indicator |
|--------|------|-----------|
| `sent` | 有内容并已投递 | `alert` |
| `ok-empty` | 空回复，无事可报 | `ok` |
| `ok-token` | HEARTBEAT_OK 回复 | `ok` |
| `skipped` | 未执行（各种原因） | — |
| `failed` | 执行出错 | `error` |

### 5.2 Cron 事件

```python
@dataclass
class CronEvent:
    job_id: str
    action: Literal["added", "updated", "removed", "started", "finished"]
    # finished 时附带:
    status: str | None = None
    error: str | None = None
    summary: str | None = None
    delivered: bool | None = None
    duration_ms: int | None = None
    next_run_at_ms: int | None = None
    model: str | None = None
    usage: dict | None = None
```

事件消费者：Web UI、CLI 状态显示、日志系统、监控告警。

---

## 6. 实现优先级

### Phase 1: MVP（最小可用）

| 模块 | 范围 |
|------|------|
| CronService 核心 | Timer 驱动、Job CRUD、持久化、at/every/cron 三种调度 |
| 主会话执行 | systemEvent + requestHeartbeatNow |
| Heartbeat Runner | 单 Agent 定时循环、HEARTBEAT_OK 协议 |
| Wake 层 | requestHeartbeatNow + 合并窗口 + 忙碌重试 |
| CLI | `cron add/list/run`, `system event` |

### Phase 2: 完善

| 模块 | 范围 |
|------|------|
| 隔离执行 | runIsolatedAgentJob + delivery (announce) |
| 错误重试 | 瞬态/永久分类 + 指数退避 |
| 启动恢复 | runMissedJobs + stagger |
| Agent Tool | cron tool 全部 action |
| 多 Agent | per-agent heartbeat + agent_id binding |

### Phase 3: 生产级

| 模块 | 范围 |
|------|------|
| Webhook delivery | delivery.mode="webhook" + Bearer token |
| Active Hours | 活跃时段 + 时区支持 |
| Session Reaper | cron session 清理 + run log 裁剪 |
| Failure Alert | 连续失败通知 + cooldown |
| Visibility | 三层可见性配置 + per-channel/per-account |
| Transcript 修剪 | HEARTBEAT_OK 时截断 transcript |
| 重复去重 | 24h 同文本去重 |
| 并发控制 | max_concurrent_runs |
| 错峰 | top-of-hour stagger |

---

## 7. 附录

### 7.1 与 OpenClaw 实现的对照

| AgentBox 概念 | OpenClaw 对应文件 | 说明 |
|---------------|-------------------|------|
| `CronService` | `src/cron/service.ts` | 入口类 |
| `CronServiceState` | `src/cron/service/state.ts` | 依赖注入 + 运行时状态 |
| Timer / onTimer | `src/cron/service/timer.ts` | 调度内核 (~1260 行) |
| CRUD ops | `src/cron/service/ops.ts` | add/update/remove/run (~570 行) |
| Job 工具函数 | `src/cron/service/jobs.ts` | 创建/计算/查找 |
| Cron 类型 | `src/cron/types.ts` | 数据模型 |
| 隔离执行 | `src/cron/isolated-agent/` | 独立 Agent Turn |
| 投递 | `src/cron/delivery.ts` | announce/webhook |
| Session 清理 | `src/cron/session-reaper.ts` | 过期 session 清理 |
| Cron Tool | `src/agents/tools/cron-tool.ts` | Agent 工具 |
| HeartbeatRunner | `src/infra/heartbeat-runner.ts` | 心跳调度 (~1239 行) |
| HeartbeatWake | `src/infra/heartbeat-wake.ts` | 唤醒层 |
| HeartbeatReason | `src/infra/heartbeat-reason.ts` | 原因分类 |
| HeartbeatEvents | `src/infra/heartbeat-events.ts` | 事件发射 |
| ActiveHours | `src/infra/heartbeat-active-hours.ts` | 活跃时段 |
| Visibility | `src/infra/heartbeat-visibility.ts` | 可见性控制 |
| EventsFilter | `src/infra/heartbeat-events-filter.ts` | Prompt 构建 |

### 7.2 关键设计约束

1. **单进程安全**：所有调度和执行在同一个 asyncio event loop 中，通过 `asyncio.Lock` 保证串行化（OpenClaw 使用 Promise 链式锁 `locked()`）
2. **磁盘是唯一事实来源**：每次 on_timer 都从磁盘 reload store，保证外部修改（CLI、RPC）可见
3. **不做跨进程调度**：Gateway 是唯一调度者，不支持多实例分布式调度
4. **Token 开销可控**：Heartbeat 默认 30 分钟间隔，HEARTBEAT_OK 轮次修剪 transcript，避免上下文膨胀

### 7.3 术语表

| 术语 | 定义 |
|------|------|
| **Job** | Cron 中的一个定时任务记录 |
| **Schedule** | 调度规则（at/every/cron） |
| **Payload** | 执行载荷（systemEvent/agentTurn） |
| **Delivery** | 执行结果的投递配置 |
| **Main Session** | 用户主对话会话 |
| **Isolated Session** | Cron Job 创建的独立执行会话 |
| **Heartbeat** | 周期性 Agent 巡检机制 |
| **HEARTBEAT_OK** | 模型回复 token，表示"无事可报" |
| **Wake** | 唤醒 Heartbeat 执行一次心跳 |
| **System Event** | 注入到会话的系统级事件文本 |
| **Announce** | 将隔离 Job 结果发送到聊天渠道 |
| **Stagger** | 错峰机制，避免多 Job 同时触发 |
