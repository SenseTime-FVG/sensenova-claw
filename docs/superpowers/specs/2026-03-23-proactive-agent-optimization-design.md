# Proactive Agent 优化设计：偏好发现与架构改进

日期: 2026-03-23

## 概述

对现有 ProactiveRuntime 进行两方面改进：
1. **新能力**：偏好发现 Job——从 memory 中自动提取用户行为偏好，创建信息聚合推送任务
2. **架构优化**：简化模型（删除 ConditionTrigger）、拆分 runtime、修复并发安全和可靠性问题

## 一、偏好发现 Job

### 1.1 设计思路

偏好发现本质上是一个"定期执行的主动任务"，作为普通 proactive job 配置在 `config.yml` 的 `proactive.jobs` 中，复用现有 ProactiveRuntime 基础设施，不引入新模块。

### 1.2 配置

在 `config.yml` 的 `proactive.jobs` 中添加：

```yaml
proactive:
  enabled: true
  jobs:
    - name: "偏好发现与推送管理"
      agent_id: "proactive-agent"
      trigger:
        kind: time
        cron: "0 2 * * *"
      task:
        prompt: |
          你是偏好发现助手。请执行以下步骤：

          ## 偏好提取
          1. 使用 memory_search 搜索用户的行为偏好信息
          2. 只提取明确的、可操作的偏好信号，忽略模糊或一次性需求
             - 例："用户多次询问 AI 新闻" → 偏好
             - 例："用户某次问了天气" → 不是偏好
          3. 保守策略：宁可漏创建，不要误创建

          ## Job 管理
          4. 调用 list_proactive_jobs 查看当前已有的推送任务
          5. 对比偏好和现有任务：
             - 发现新偏好 → 创建对应的信息聚合推送 job
             - 偏好已变化 → 禁用旧 job，创建新 job
             - 偏好已消失 → 禁用对应 job
          6. 创建的推送 job 模板：
             - 触发：每日定时（根据偏好性质选择合适时间）
             - 工具：只开放搜索和 fetch 类工具
             - 安全：max_llm_calls=3, max_duration_ms=300000
             - 投递：web channel

          ## 兜底策略
          7. 如果没有发现任何明确的用户偏好：
             - 检查是否已存在默认新闻推送 job
             - 如果不存在，创建"每日新闻简报"job
               （推送当日新华社/主流媒体重要新闻）
          8. 天气提醒：
             - 从 memory 中查找用户所在城市信息
             - 能获取到城市 → 创建天气变化提醒 job
             - 无法获取城市 → 不创建天气 job

          ## 输出
          9. 输出变更摘要
        use_memory: true
      safety:
        max_llm_calls: 5
        max_duration_ms: 600000  # 10 分钟
      delivery:
        channels: ["web"]
```

### 1.3 执行流程

```
每日 02:00 触发
  ↓
ProactiveRuntime 创建隔离 session，注入 prompt + memory 上下文
  ↓
LLM 执行：
  ├─ memory_search 搜索偏好信号
  ├─ list_proactive_jobs 获取现有 job
  ├─ 对比分析，决定创建/更新/禁用
  ├─ 无偏好时走兜底策略
  └─ 输出变更摘要
  ↓
结果通过 web channel 投递给用户
```

## 二、模型简化：删除 ConditionTrigger

### 2.1 背景

当前 ConditionTrigger 通过裸 LLM 调用评估自然语言条件，存在根本缺陷：
- LLM 没有实时信息获取能力，无法准确判断需要实时数据的条件
- 每次 check_interval 都要调 LLM，浪费 token
- 失败时 fallback 为 True（直接执行），有安全隐患

### 2.2 改动

1. **删除 `ConditionTrigger` 类**（`models.py`）
2. **删除 `TimeTrigger.condition` 和 `EventTrigger.condition` 字段**
3. **删除条件评估相关代码**：
   - `runtime.py`: `_evaluate_condition()`, `_get_condition()`
   - `triggers.py`: `build_condition_prompt()`, `parse_condition_response()`
4. **删除 `_parse_job_config()` 中 `kind: "condition"` 的解析分支**
5. **更新序列化代码**（`models.py`）：
   - `trigger_to_json()`: 移除 `ConditionTrigger` 分支，移除 `TimeTrigger`/`EventTrigger` 的 `condition` 字段写入
   - `trigger_from_json()`: 移除 `kind == "condition"` 分支，移除 `condition` 字段读取
6. **更新 `CreateProactiveJobTool`**（`proactive_tools.py`）：
   - `_parse_trigger()`: 移除 `condition` 分支
   - 工具参数定义中移除 condition 相关字段
   - 新增 `safety` 参数，允许调用方自定义 `max_llm_calls` 和 `max_duration_ms`（当前工具始终使用 `SafetyConfig()` 默认值）
7. **修复已知 bug**：`ListProactiveJobsTool.execute()` 中 `self._runtime.list_jobs()` 缺少 `await`

### 2.3 迁移

需要条件判断的场景，改为在 job 的 task prompt 中描述条件，让 agent 执行时自己判断（agent 有完整工具能力）。

## 三、ProactiveRuntime 拆分

### 3.1 当前问题

`runtime.py` 618 行，混合了调度、执行、投递三个职责。

### 3.2 拆分方案

```
agentos/kernel/proactive/
  ├─ runtime.py      # 入口，组合 scheduler + executor + delivery
  ├─ scheduler.py    # 触发调度（timer loop + event loop）
  ├─ executor.py     # session 创建、prompt 构建、等待完成
  ├─ delivery.py     # 结果投递（已存在，保持）
  ├─ models.py       # 数据模型（已存在，保持）
  └─ triggers.py     # 触发器计算（已存在，简化后保持）
```

**scheduler.py** 职责：
- `_on_timer()`: 扫描 time-triggered job，计算下次触发时间
- `_event_loop()`: 订阅 PublicEventBus，匹配 event-triggered job
- `_arm_timer()`: 管理定时器

**executor.py** 职责：
- `_execute_job()`: 创建隔离 session，注入 prompt 和 safety 约束
- `_build_prompt()`: 构建执行 prompt（含 memory 注入）
- `_wait_for_completion()`: 等待 agent 完成

**runtime.py** 瘦身为：
- `start()` / `stop()`: 生命周期管理
- `add_job()` / `remove_job()` / `set_job_enabled()`: job CRUD（沿用现有 API 命名）
- 组合 scheduler 和 executor

## 四、并发安全修复

### 4.1 Job 状态锁

为每个 job 添加 `asyncio.Lock`，保护以下操作的原子性：
- `_running_jobs.add()` / `.discard()`
- `job.state` 字段更新
- DB 持久化

```python
class ProactiveRuntime:
    def __init__(self):
        self._job_locks: dict[str, asyncio.Lock] = {}

    async def _execute_job(self, job):
        lock = self._job_locks.setdefault(job.id, asyncio.Lock())
        async with lock:
            if job.id in self._running_jobs:
                return  # 已在执行，跳过
            self._running_jobs.add(job.id)
            try:
                # ... 执行逻辑
            finally:
                self._running_jobs.discard(job.id)
```

注意：lock 需要包裹整个 try/finally，确保即使 `_build_prompt` 等前置步骤抛异常，job ID 也能从 `_running_jobs` 中正确移除。

当 job 被 `remove_job()` 删除时，同步清理 `_job_locks` 中对应的条目。

## 五、可靠性改进

### 5.1 事件订阅队列清理

`_wait_for_completion()` 订阅 bus 等待 `AGENT_STEP_COMPLETED` 事件。当前如果 session 异常退出未发事件，队列对象会泄漏。

改进：在 `finally` 中确保从 `_bus._subscribers` 移除 queue，并增加超时保护。当前实现已有 `finally: self._bus._subscribers.discard(queue)` 但缺少对 `asyncio.TimeoutError` 的优雅处理（当前直接抛出异常）。

改进后：捕获 `TimeoutError`，记录警告日志，返回 `None` 表示超时，由调用方处理：

```python
async def _wait_for_completion(self, session_id: str, timeout: float = 300) -> str | None:
    """订阅 PublicEventBus 等待 AGENT_STEP_COMPLETED。"""
    queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
    self._bus._subscribers.add(queue)
    try:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Proactive session 超时: %s", session_id)
                return None
            event = await asyncio.wait_for(queue.get(), timeout=remaining)
            if event.type == AGENT_STEP_COMPLETED and event.session_id == session_id:
                return event.payload.get("result", {}).get("content", "")
    except asyncio.TimeoutError:
        logger.warning("Proactive session 超时: %s", session_id)
        return None
    finally:
        self._bus._subscribers.discard(queue)
```

注意：`_execute_job` 调用方需要检查返回值，`None` 表示超时，应走 `_handle_failure` 路径（标记 `last_status="timeout"`），而非成功路径。

### 5.2 心跳超时检测

在 `_wait_for_completion` 中增加心跳检测：如果 session 超过一定时间（如 `max_duration_ms / 3`）没有产出任何新事件（不限于 COMPLETED），提前判定为异常。

### 5.3 Delivery 失败重试

`delivery.py` 中通知发送失败时，增加简单重试（最多 3 次，间隔 3 秒）：

```python
async def deliver(self, job: ProactiveJob, session_id: str, result: str):
    # ... 发布 PROACTIVE_RESULT 事件（不变）...

    notification = Notification(...)
    for attempt in range(3):
        try:
            await self._notification_service.send(notification, channels=job.delivery.channels)
            return
        except Exception as e:
            if attempt == 2:
                logger.error("投递通知失败，已重试 3 次: %s - %s", job.name, e)
            else:
                logger.warning("投递通知失败，%d 秒后重试: %s", 3, e)
                await asyncio.sleep(3)
```

### 5.4 Debounce 字典清理

`_last_event_fires` 字典只增不减。在 `_on_timer()` 中增加清理逻辑，移除超过 1 小时的过期条目：

```python
def _cleanup_debounce(self):
    now_ms = int(time.time() * 1000)
    expired = [k for k, v in self._last_event_fires.items()
               if now_ms - v > 3_600_000]
    for k in expired:
        del self._last_event_fires[k]
```

## 六、清理项

### 6.1 实现 `summary_prompt` 字段

`DeliveryConfig` 中已定义 `summary_prompt` 字段但从未使用。实现它：

- 如果 `summary_prompt` 非空：用 LLM 对 result 做摘要后再投递
- 如果 `summary_prompt` 为空或未配置：保持原样，直接投递原始结果

实现位置：`ProactiveDelivery.deliver()` 中，在发送通知前检查 `summary_prompt`。

## 七、改动清单总结

| 序号 | 类别 | 改动 | 涉及文件 |
|------|------|------|----------|
| 1 | 新能力 | 偏好发现 Job 配置 | `config.yml` |
| 2 | 模型简化 | 删除 ConditionTrigger 及 condition 字段 | `models.py`, `triggers.py`, `runtime.py`, `proactive_tools.py` |
| 3 | 架构优化 | ProactiveRuntime 拆分为 scheduler + executor | `runtime.py` → `scheduler.py` + `executor.py` + `runtime.py` |
| 4 | 并发安全 | Job 状态变更加 asyncio.Lock | `runtime.py`（或拆分后的 `executor.py`） |
| 5 | 可靠性 | 事件订阅队列超时清理 | `executor.py` |
| 6 | 可靠性 | 心跳超时检测 | `executor.py` |
| 7 | 可靠性 | Delivery 失败重试 | `delivery.py` |
| 8 | 内存泄漏 | Debounce 字典定期清理 | `scheduler.py` |
| 9 | 清理 | 实现 summary_prompt（有则摘要，无则原样） | `delivery.py` |

## 八、不改动的部分

- 事件总线、Gateway、Channel 层
- 现有 job 的 CRUD API
- Memory 系统（不需要结构化存储偏好）
- 现有 TimeTrigger 和 EventTrigger 的核心逻辑
- 前端 UI
