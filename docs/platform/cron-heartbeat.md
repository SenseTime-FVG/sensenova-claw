# 定时任务与心跳

> 路径：`sensenova_claw/kernel/scheduler/`、`sensenova_claw/kernel/heartbeat/`

CronRuntime 和 HeartbeatRuntime 共同提供定时任务调度和周期性健康检查能力。

---

## CronRuntime（定时任务调度器）

CronRuntime 负责管理和执行定时任务：

- 基于计时器驱动，周期性检查是否有任务到期
- 任务定义持久化在 SQLite `cron_jobs` 表
- 到期时计算 `next_run_at_ms`，触发 `cron.system_event` 事件
- 将事件推送给 HeartbeatRuntime 或其他订阅者

**调度流程**：

```
定时检查循环
  → 查询 cron_jobs 表，找到 next_run_at_ms <= now 的任务
  → 创建 cron_runs 记录（status = running）
  → 发布 cron.system_event 事件
  → 更新 next_run_at_ms 为下一次触发时间
  → 任务完成后更新 cron_runs（status = success/failed）
```

---

## HeartbeatRuntime（心跳检查）

HeartbeatRuntime 提供周期性的 Agent 健康检查：

- 按配置的时间间隔（如 30 分钟）唤醒
- 将待处理的 `system_event` 注入到 prompt 中
- 创建临时 session 进行检查
- 等待 `AGENT_STEP_COMPLETED` 响应（带超时机制）
- 完成后清理临时 session 和相关资源

**检查流程**：

```
心跳触发
  → 创建临时 session
  → 构建 prompt（包含 HEARTBEAT.md 内容和待处理事件）
  → 发布 user.input 事件
  → 等待 agent.step_completed 事件（超时保护）
  → 处理 Agent 响应（如发送通知）
  → 清理临时 session
```

---

## 事件类型

### Cron 相关事件

| 事件类型 | 说明 |
|----------|------|
| `cron.job_added` | 新增定时任务 |
| `cron.job_updated` | 更新定时任务 |
| `cron.job_removed` | 删除定时任务 |
| `cron.job_started` | 任务开始执行 |
| `cron.job_finished` | 任务执行完成 |
| `cron.system_event` | 触发文本事件（传递给 Agent 处理） |
| `cron.delivery_requested` | 广播给所有已连接的客户端 |

### Heartbeat 相关事件

| 事件类型 | 说明 |
|----------|------|
| `heartbeat.wake_requested` | 请求唤醒心跳检查 |
| `heartbeat.check_started` | 心跳检查开始 |
| `heartbeat.completed` | 心跳检查完成 |

---

## CronRuntime 与 HeartbeatRuntime 的协作

```
CronRuntime                          HeartbeatRuntime
    │                                       │
    │  cron.system_event                    │
    │ ────────────────────────────────────> │
    │                                       │
    │                               创建临时 session
    │                               注入 prompt
    │                               发布 user.input
    │                                       │
    │                               等待 agent.step_completed
    │                                       │
    │                               处理响应
    │  cron.delivery_requested              │
    │ <──────────────────────────────────── │
    │                                       │
    ▼  广播给所有客户端                      │
```

---

## 配置

在 `config.yml` 中配置定时任务和心跳：

```yaml
cron:
  enabled: true                    # 启用定时任务调度器

heartbeat:
  enabled: false                   # 心跳默认关闭
  every: 30m                       # 检查间隔
  prompt: "Read HEARTBEAT.md and check pending tasks"  # 心跳 prompt
```

**注意事项**：

- `cron.enabled` 控制是否启动 CronRuntime
- `heartbeat.enabled` 控制是否启动 HeartbeatRuntime
- 心跳检查会消耗 LLM 调用额度，建议根据实际需求调整间隔时间
- 定时任务通过 API 或 Agent 工具进行增删改查管理
