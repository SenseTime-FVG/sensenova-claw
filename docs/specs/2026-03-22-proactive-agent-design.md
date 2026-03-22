# Proactive Agent 设计文档

## 概述

为 AgentOS 内置一个 Proactive Agent，支持定时执行任务和结合 Memory 为用户做信息整理推送。Proactive Agent 作为独立 agent 存在，通过 ProactiveRuntime 管理触发、执行和投递。

## 核心场景

1. Agent 按计划定期执行任务（如每日邮件摘要、定时数据报告）
2. Agent 结合 Memory 给用户做信息整理推送（如根据用户兴趣推送新闻）

## 架构方案：混合模式（事件驱动 + 协调循环）

### 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 与现有模块关系 | 新建独立 ProactiveRuntime | 职责清晰，不污染 CronRuntime/HeartbeatRuntime 语义 |
| 触发方式 | 时间 + 事件 + 条件 | 三种触发统一在一个 Runtime |
| 与 CronRuntime 关系 | 函数级复用，Runtime 级独立 | 共享 cron 解析逻辑，各自独立运行 |
| 执行方式 | 独立会话 + 推送结果 | 不干扰用户当前对话 |
| 执行派发 | proactive-agent LLM 推理决策 | agent 自主判断是否委派其他 agent，支持多 agent 协作 |
| 推送渠道 | Web + 飞书 | 覆盖主要用户触达渠道 |
| Memory 集成 | 按任务可选 | `use_memory` 字段控制，定时任务不需要，兴趣推送需要 |
| 安全控制 | 工具级别控制 | 白名单/黑名单 + 调用限制 + 自动禁用 |
| 任务创建 | 配置文件 + 对话式 | 两种方式并存 |

### 架构图

```
ProactiveRuntime
  ├── EventListener (订阅 PublicEventBus) → 实时匹配事件触发器
  ├── TimerLoop (asyncio timer) → 处理时间触发 + 条件评估
  ├── _evaluate_and_execute(job)
  │     ├── 检查 enabled + 非 running
  │     ├── 条件评估（可选，LLM 轻量调用）
  │     └── _spawn_session → 创建 proactive-agent 隔离会话
  ├── _spawn_session(job)
  │     ├── 创建 proactive-agent 会话
  │     ├── 注入 task.prompt + memory（可选）+ safety 约束
  │     ├── proactive-agent LLM 推理，决定是否 send_message 给其他 agent
  │     └── 监听 AGENT_STEP_COMPLETED 等待完成
  ├── _deliver_result(job, result)
  │     ├── Web: 通过 WebSocketChannel 推送 proactive.result 事件
  │     └── 飞书: 通过 FeishuChannel 发送卡片消息
  └── stop() → 取消 timer，清理运行中会话
```

### 与现有模块关系

```
                    ┌─────────────────┐
                    │ ProactiveRuntime │
                    │     (新增)       │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌──────────┐
     │PublicEventBus│ │AgentRuntime│  │ Channels │
     │ (事件监听)   │ │ (会话执行)  │  │(结果投递) │
     └────────────┘  └────────────┘  └──────────┘
```

## 核心数据模型

### ProactiveJob

```python
@dataclass
class ProactiveJob:
    id: str                          # UUID
    name: str                        # 人类可读名称，如"每日邮件摘要"
    agent_id: str                    # 执行 agent ID，当前固定 "proactive-agent"
    enabled: bool = True
    trigger: TimeTrigger | EventTrigger | ConditionTrigger
    task: ProactiveTask
    delivery: DeliveryConfig
    safety: SafetyConfig
    state: JobState
    source: str = "config"           # "config" = 配置文件加载, "conversation" = 对话创建
```

### 触发器

```python
@dataclass
class TimeTrigger:
    """时间触发：cron 表达式或固定间隔"""
    kind: Literal["time"] = "time"
    schedule: str                    # cron 表达式 "0 9 * * *" 或间隔 "every 30m"
    condition: str | None = None     # 可选前置条件（自然语言，由 LLM 评估）

@dataclass
class EventTrigger:
    """事件触发：匹配 PublicEventBus 上的特定事件"""
    kind: Literal["event"] = "event"
    event_type: str                  # 如 "email.received", "agent.step_completed"
    filter: dict | None = None       # payload 过滤条件 {"source": "email-agent"}
    debounce_ms: int = 5000          # 防抖：5秒内重复事件只触发一次
    condition: str | None = None     # 可选附加条件

@dataclass
class ConditionTrigger:
    """条件触发：周期性评估条件，满足时执行"""
    kind: Literal["condition"] = "condition"
    check_interval: str = "5m"       # 检查频率
    condition: str                   # 条件描述（自然语言，由 LLM 评估）
```

### 任务、投递、安全、状态

```python
@dataclass
class ProactiveTask:
    prompt: str                      # 任务指令
    use_memory: bool = False         # 是否加载 agent memory
    system_prompt_override: str | None = None

@dataclass
class DeliveryConfig:
    channels: list[str]              # ["web", "feishu"]
    feishu_target: str | None = None # 飞书群/用户 ID
    summary_prompt: str | None = None # 可选：LLM 生成投递摘要

@dataclass
class SafetyConfig:
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    max_tool_calls: int = 20
    max_llm_calls: int = 10
    max_duration_ms: int = 300_000   # 5分钟
    auto_disable_after_errors: int = 3

@dataclass
class JobState:
    last_triggered_at: int | None = None
    last_completed_at: int | None = None
    last_status: str = "idle"        # idle | running | success | failed
    consecutive_errors: int = 0
    total_runs: int = 0
    next_trigger_at: int | None = None
```

## 执行流程

### 时间触发示例：每日邮件摘要

```
1. TimerLoop 检测到 "每日邮件摘要" 的 cron "0 9 * * *" 到期
2. _evaluate_and_execute(job)
   ├── 检查 enabled=true, state.last_status != "running"
   ├── 有 condition? → LLM 轻量评估（本例无 condition，跳过）
3. _spawn_session(job)
   ├── 创建 proactive-agent 隔离会话 session_id=uuid
   ├── 构建上下文: proactive-agent system_prompt + task.prompt + safety 约束
   ├── 发布 USER_INPUT 事件到 PublicEventBus
4. proactive-agent LLM 推理
   ├── 决定调用 send_message(to="email-agent", message="检查今日未读邮件...")
   ├── email-agent 执行邮件检查，返回结果
   ├── proactive-agent 整理格式，输出最终摘要
5. ProactiveRuntime 监听到 AGENT_STEP_COMPLETED
   ├── 提取 agent 输出作为 result
6. _deliver_result(job, result)
   ├── Web: 通过 WebSocketChannel 推送 proactive.result 事件
   ├── 飞书: 通过 FeishuChannel 发送卡片消息
7. 更新 JobState + 写入 proactive_runs 表
```

### 事件触发示例：收到新邮件时分类

```
1. EventListener 订阅 PublicEventBus
2. 收到 event_type="email.received" 事件
   ├── 匹配 EventTrigger，debounce 检查（5秒内不重复）
3. _evaluate_and_execute(job)
   ├── 有 condition "邮件来自重要联系人" → LLM 评估
   ├── 条件满足 → _spawn_session → proactive-agent 推理执行 → 投递
   └── 条件不满足 → 跳过，记录日志
```

### 条件触发示例：根据用户兴趣推送新闻

```
1. TimerLoop 每 5 分钟检查 ConditionTrigger
2. LLM 评估条件 "是否到了用户偏好的推送时间且有新内容"
3. 条件满足 → _spawn_session(job, use_memory=true)
   ├── proactive-agent 加载用户 memory（兴趣偏好）
   ├── 调用 send_message(to="search-agent", ...) 搜索新闻
   ├── 整理汇总，输出推送内容
4. 投递到 Web + 飞书
```

### 结果投递

Web 推送 — 新增事件类型 `proactive.result`：
```python
EventEnvelope(
    type="proactive.result",
    payload={
        "job_id": "...",
        "job_name": "每日邮件摘要",
        "result": "今日共 12 封未读邮件...",
        "session_id": "...",  # 可点击查看完整会话
    }
)
```

飞书推送 — 复用 FeishuChannel 发送能力，格式化为飞书卡片消息。

### 错误处理

- 执行超时 → 强制终止会话，标记 `failed`，`consecutive_errors += 1`
- 工具调用超限 → 中断执行，标记 `failed`
- 连续失败达到 `auto_disable_after_errors` → 自动 `enabled=false`，通知用户

## 任务创建与持久化

### 方式 1：配置文件声明

在 proactive-agent 目录下定义 `PROACTIVE.yaml`：

```yaml
# .agentos/agents/proactive-agent/PROACTIVE.yaml
jobs:
  - name: "每日邮件摘要"
    trigger:
      kind: time
      schedule: "0 9 * * *"
    task:
      prompt: "检查今日未读邮件，按重要程度分类，生成摘要报告"
      use_memory: false
    delivery:
      channels: ["web", "feishu"]
    safety:
      allowed_tools: ["list_emails", "fetch_url", "send_message"]
      max_tool_calls: 30

  - name: "新闻兴趣推送"
    trigger:
      kind: time
      schedule: "0 8 * * 1-5"
    task:
      prompt: "根据用户兴趣偏好，搜索今日热点新闻，整理推送"
      use_memory: true
    delivery:
      channels: ["feishu"]
```

启动时 ProactiveRuntime 从 `.agentos/agents/proactive-agent/PROACTIVE.yaml` 加载 job 定义。

### 方式 2：对话式创建

新增 `create_proactive_job` 工具，用户通过对话创建：

```
用户: "帮我每天早上9点整理邮件摘要，推送到飞书"
Agent: 调用 create_proactive_job 工具 → 写入 DB → 通知 ProactiveRuntime 热加载
```

### 持久化：SQLite

```sql
CREATE TABLE proactive_jobs (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    trigger_config TEXT NOT NULL,    -- JSON
    task_config TEXT NOT NULL,       -- JSON
    delivery_config TEXT NOT NULL,   -- JSON
    safety_config TEXT NOT NULL,     -- JSON
    source TEXT DEFAULT 'config',   -- 'config' | 'conversation'
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE proactive_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    session_id TEXT,                 -- 执行会话 ID
    status TEXT NOT NULL,            -- 'running' | 'success' | 'failed' | 'skipped'
    triggered_by TEXT NOT NULL,      -- 'time' | 'event' | 'condition'
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    result_summary TEXT,
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES proactive_jobs(id)
);
```

配置文件声明的 job 以 `source='config'` 存入 DB，对话创建的以 `source='conversation'`。启动时先加载配置文件，再从 DB 补充 conversation 来源的 job。

## Gateway 集成

### 启动顺序

ProactiveRuntime 加入 Gateway 启动链路，位于 AgentRuntime 之后：

```python
# gateway/main.py
await agent_runtime.start()
await llm_runtime.start()
await tool_runtime.start()
await title_runtime.start()
await proactive_runtime.start()   # 新增
await cron_runtime.start()
await heartbeat_runtime.start()
```

### 新增工具

注册到 ToolRegistry，供 proactive-agent 和其他 agent 使用：

- `create_proactive_job`: 创建 proactive 任务
- `list_proactive_jobs`: 查看所有 proactive 任务
- `manage_proactive_job`: 启用/禁用/删除任务

### REST API

```
GET    /api/proactive/jobs          # 列出所有 job
POST   /api/proactive/jobs          # 创建 job
GET    /api/proactive/jobs/{id}     # 查看 job 详情
PATCH  /api/proactive/jobs/{id}     # 更新 job
DELETE /api/proactive/jobs/{id}     # 删除 job
GET    /api/proactive/runs          # 查看执行历史
GET    /api/proactive/runs/{id}     # 查看单次执行详情
```

### 前端展示

Web dashboard 新增 "Proactive" 页面：
- Job 列表：名称、触发器类型、状态、上次执行、下次触发
- 执行历史：每次 run 的状态、耗时、结果摘要
- 通知面板：proactive 结果以卡片形式展示，可点击查看完整会话

## 文件结构

```
agentos/kernel/proactive/
  ├── __init__.py
  ├── models.py          # ProactiveJob, Trigger, Task, Safety 等数据模型
  ├── runtime.py         # ProactiveRuntime 主逻辑
  ├── triggers.py        # 触发器评估逻辑（时间/事件/条件）
  └── delivery.py        # 结果投递逻辑

agentos/capabilities/tools/
  └── proactive_tools.py # create/list/manage proactive job 工具

agentos/interfaces/http/
  └── proactive_api.py   # REST API 端点

.agentos/agents/proactive-agent/
  ├── AGENTS.md
  ├── SYSTEM_PROMPT.md
  ├── USER.md
  └── PROACTIVE.yaml     # proactive 任务定义
```

## 业界参考

- **Temporal DAPER 模式**: Detect → Analyze → Plan → Execute → Report，proactive agent 的执行流程参考此模式
- **K8s Controller 协调循环**: 周期性检查期望状态 vs 当前状态，差异存在则行动
- **AutoGen v0.4 Actor 模型**: agent 作为 actor 通过异步消息通信，与 PublicEventBus 模式一致
- **LangGraph Schedules**: 将 proactive 执行与 reactive 执行分离，通过 schedule 配置驱动
- **Letta/MemGPT 分层记忆**: agent 通过工具调用管理自己的记忆，支持 memory-driven 决策
