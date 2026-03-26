# Turn-End 会话推荐设计

## 概述

每次对话轮次（turn）结束后，proactive-agent 异步生成 3-5 条推荐，展示在前端 Dashboard 看板上。用户点击推荐可跳转到对应会话并将推荐内容填入输入框。

## 需求

- 每次 `agent.step_completed` 后异步触发推荐生成，不阻塞主对话流
- 推荐基于当前完整对话上下文 + agent 自主查询的 memory
- 推荐展示在 ProactiveAgentPanel 看板中，不内联在对话流里
- 智能合并：同 session 新推荐替换旧推荐，不同 session 共存
- 只展示最新批次：最多 3 个 session 的推荐，每个 session 最多 5 条
- 点击推荐跳转到对应 session，将 prompt 填入输入框，用户手动发送

## 架构

### 触发与执行链路

```
agent.step_completed
  → ProactiveScheduler (EventTrigger, debounce 5s per session, 排除 recommendation turn)
    → ProactiveExecutor
      → 在原始会话中插入 user 消息（复用 KV cache）
        → AgentWorker 正常处理，LLM 生成推荐 JSON
      → Executor 解析 JSON
      → ProactiveDelivery
        → proactive_result 事件 (type=turn_end, 携带 source_session_id + items)
          → WebSocket → 前端看板
```

### 方案选择

采用方案 A：基于现有 ProactiveJob EventTrigger 机制。

理由：改动最小，完全复用现有 proactive 基础设施（调度、执行、投递、安全限制、前端展示）。

## 详细设计

### 1. 内置 ProactiveJob

系统启动时自动注册，无需用户手动配置：

```yaml
id: "builtin-turn-end-recommendation"
name: "会话推荐"
agent_id: "proactive-agent"
enabled: true
trigger:
  kind: event                              # 注意：代码中使用 kind 而非 type
  event_type: "agent.step_completed"
  debounce_ms: 5000                        # 与 EventTrigger 模型一致
  exclude_payload:                         # 新增字段，见 Section 2
    source: "recommendation"
task:
  prompt: "根据以上完整对话上下文，生成3-5条用户接下来可能想做的事。每条包含title和prompt字段，输出JSON。"
  use_memory: false
delivery:
  channels: ["web"]
  recommendation_type: "turn_end"
safety:
  max_tool_calls: 5
  max_llm_calls: 3
  max_duration_ms: 30000
```

用户可在 `config.yml` 中覆盖默认配置：

```yaml
proactive:
  turn_end_recommendation:
    enabled: true
    max_items: 5
    debounce_ms: 5000
```

### 2. 防止自触发

推荐 turn 本身也会产生 `agent.step_completed` 事件，必须过滤以避免无限循环。

**实现方式**：

1. 推荐 turn 插入的 user 消息携带元数据 `meta: {"source": "recommendation"}`
2. AgentWorker 在发布 `agent.step_completed` 时，将 turn 的 `meta.source` 透传到 payload 中
3. `EventTrigger` 模型新增 `exclude_payload: dict | None` 字段
4. `is_event_match()` 方法增加排除逻辑：如果事件 payload 中包含 `exclude_payload` 指定的 key-value，则不匹配

**代码改动**：
- `EventTrigger` dataclass 新增 `exclude_payload: dict | None = None`
- `is_event_match()` 增加排除判断
- `_parse_job_config()` 解析 `exclude_payload` 配置

### 3. 上下文传递与执行方式

**不启动独立会话**。直接在原始会话中追加一条 user 消息触发推荐生成，复用已有的 KV cache。

**执行流程**：
1. EventTrigger 触发时，透传 `EventEnvelope`（需扩展调用链）
2. Executor 从 `trigger_event.session_id` 获取源会话 ID
3. 在源会话中插入一条 user 消息（携带 `meta: {"source": "recommendation"}`）
4. 该 turn 由 AgentWorker 正常处理，复用原始会话的 KV cache
5. Executor 通过 `turn_id`（而非 `session_id`）监听对应的 `agent.step_completed` 事件，区分推荐 turn 和普通用户 turn
6. turn 完成后，从 agent 回复中解析推荐 JSON，通过 ProactiveDelivery 投递

**Executor 双模式**：ProactiveExecutor 需要支持两种执行模式：
- **独立会话模式**（现有逻辑）：TimeTrigger 等场景，创建 `proactive_` 前缀的新会话
- **注入模式**（新增）：EventTrigger 携带 `trigger_event` 时，在源会话中插入消息

通过 `trigger_event` 是否为 `None` 区分：有 trigger_event 且 job 配置了 `inject_into_source: true` → 注入模式，否则 → 独立会话模式。

**调用链扩展**：
- `ProactiveScheduler._on_trigger(job, trigger_event: EventEnvelope | None)`
- `ProactiveRuntime._evaluate_and_execute(job, trigger_event: EventEnvelope | None)`
- `ProactiveRuntime._run_and_deliver(job, trigger_event: EventEnvelope | None)`
- `ProactiveExecutor.execute_job(job, trigger_event: EventEnvelope | None)`

TimeTrigger 调用时传 `trigger_event=None`，保持向后兼容。

**上下文压缩**：不需要额外截断逻辑。AgentRuntime 已有 turn 级上下文压缩机制，推荐 turn 天然受益于此。

Memory 不主动注入。proactive-agent 已配置 `memory_search` 工具，由 agent 自主决定是否查询历史记忆。

### 4. Debounce 作用域

当前 debounce 实现按 `job_id` 全局去重。需要改为按 `(job_id, session_id)` 去重，确保不同 session 的推荐不会互相吞掉。

**代码改动**：`EventTrigger.should_debounce()` 的 key 从 `job_id` 改为 `f"{job_id}:{event.session_id}"`。

### 5. LLM 输出格式

proactive-agent 生成结构化 JSON：

```json
{
  "recommendations": [
    {
      "id": "uuid",
      "title": "深入研究量子计算应用",
      "prompt": "帮我详细调研量子计算在金融领域的最新应用案例",
      "category": "research"
    },
    {
      "id": "uuid",
      "title": "生成调研报告",
      "prompt": "根据刚才的搜索结果，生成一份结构化的调研报告",
      "category": "action"
    }
  ]
}
```

字段说明：
- `id`：UUID，前端去重用
- `title`：卡片展示标题
- `prompt`：点击后填入输入框的完整文本
- `category`：可选，用于卡片图标/颜色区分。枚举值：`research`（调研）、`action`（执行）、`follow-up`（跟进）。前端对未知 category 使用 neutral 样式兜底。

### 6. JSON 解析与容错

推荐 turn 完成后，由 ProactiveExecutor 负责从 agent 回复中解析 JSON：

1. 尝试从回复文本中提取 JSON（支持 markdown code block 包裹）
2. 从 JSON 中读取 `recommendations` 字段作为推荐列表
3. 解析成功 → 将 `recommendations` 列表作为 `items` 传给 ProactiveDelivery
4. 解析失败（LLM 返回非法 JSON 或缺少 `recommendations` 字段）→ 记录 warning 日志，本次推荐静默跳过，不投递到前端

### 7. DeliveryConfig 模型扩展

`DeliveryConfig` dataclass 新增字段：

```python
@dataclass
class DeliveryConfig:
    channels: list[str]
    feishu_target: str | None = None
    summary_prompt: str | None = None
    recommendation_type: str | None = None  # 新增：区分推荐类型
```

同步更新 `_delivery_to_dict` / `_delivery_from_dict` 序列化方法。

### 8. ProactiveDelivery 扩展

`deliver()` 方法签名扩展，增加可选参数：

```python
async def deliver(
    self, job: ProactiveJob, session_id: str, result: str,
    *,
    source_session_id: str | None = None,  # 新增：原始会话 ID
    items: list[dict] | None = None,       # 新增：结构化推荐列表
) -> None:
```

`proactive_result` 事件 payload 增加字段：

```python
{
    "job_id": "builtin-turn-end-recommendation",
    "job_name": "会话推荐",
    "result": "...",
    "source_session_id": "xxx",           # 原始会话 ID，推荐跳转目标
    "recommendation_type": "turn_end",    # 区分普通 proactive 推送
    "items": [                            # 结构化推荐列表
        {"id": "uuid", "title": "...", "prompt": "...", "category": "..."},
    ]
}
```

### 9. 前端 ProactiveAgentPanel 改造

#### 推荐卡片渲染

- 通过 `recommendation_type === "turn_end"` 识别推荐卡片，与普通 proactive 推送区分渲染
- 每条推荐显示 title + category 图标，可点击

#### 智能合并策略

- 同一 `source_session_id` 的新推荐直接替换旧推荐
- 不同 session 的推荐共存，按时间倒序排列
- 看板总数上限：最多展示 3 个 session 的推荐，超出的最旧批次淘汰
- 单个 session 最多 5 条推荐

#### 点击跳转与填入

- 点击推荐卡片 → 调用 `loadSession(source_session_id)` 切换到目标会话
- 切换完成后 → 调用新增的 `prefillInput(text)` 方法将 prompt 填入输入框
- 用户可编辑后手动发送

**`prefillInput` 实现**：在 ChatSessionContext 中新增 `pendingInput` state。`prefillInput(text)` 设置该 state，输入框组件通过 `useEffect` 监听 `pendingInput` 变化，非空时写入输入框并清除 `pendingInput`。这样即使 `loadSession` 是异步的，输入框 mount 后也能正确读取待填入内容。

#### 边界情况

- **源会话已删除**：点击推荐时，`loadSession` 失败 → 显示 toast "会话已删除"，自动移除该推荐卡片
- **推荐 turn 对用户不可见**：推荐 turn 在原始会话中产生的消息，后端在存储时标记 `hidden: true`（通过 turn 的 `meta.source === "recommendation"` 判断）。前端加载会话消息时过滤 `hidden: true` 的消息不展示。
- **推荐 turn 不影响会话列表**：推荐 turn 不触发 `session_list_changed` 事件，不影响会话列表排序和更新

#### 24 小时过期

前端在渲染推荐列表时，检查每条推荐的 `receivedAt` 时间戳，超过 24 小时的自动过滤掉。无需定时器，每次渲染时惰性清理。

#### 数据流

```
proactive_result (type=turn_end)
  → ChatSessionContext.handleWsMessage()
    → setRecommendations() [按 source_session_id 分组，合并去重，保留最新批次]
  → ProactiveAgentPanel 渲染推荐卡片
  → 用户点击
    → loadSession(source_session_id)
    → prefillInput(prompt)
```

### 10. 安全约束

| 约束项 | 值 | 说明 |
|--------|-----|------|
| max_duration_ms | 30000 | 单次推荐最多 30 秒 |
| max_llm_calls | 3 | 生成推荐 + 可能的 memory 查询 |
| max_tool_calls | 5 | memory_search 等工具调用上限 |
| debounce_ms | 5000 | 同 session 短时间内多次 step_completed 只触发一次 |

## 改动范围

### 后端

1. **EventTrigger 模型**：新增 `exclude_payload` 字段，`is_event_match()` 增加排除逻辑，`_parse_job_config()` 解析新字段
2. **ProactiveScheduler**：扩展 `_on_trigger` 调用链透传 `EventEnvelope | None`；debounce 改为按 `(job_id, session_id)` 去重
3. **ProactiveExecutor**：新增注入模式（在源会话中插入 user 消息），通过 `turn_id` 监听完成事件；从 agent 回复中解析 `recommendations` JSON
4. **ProactiveDelivery**：`deliver()` 签名增加 `source_session_id` 和 `items` 可选参数；payload 增加对应字段
4. **DeliveryConfig**：新增 `recommendation_type` 字段及序列化支持
5. **内置 Job 注册**：ProactiveRuntime 启动时自动注册 `builtin-turn-end-recommendation` job
6. **配置**：`proactive.turn_end_recommendation` 配置项
7. **消息标记**：推荐 turn 的消息标记 `source: "recommendation"`，前端可据此隐藏

### 前端

1. **ChatSessionContext**：新增 `recommendations` state、`setRecommendations` 处理逻辑、`pendingInput` state 和 `prefillInput(text)` 方法
2. **ProactiveAgentPanel**：区分 `turn_end` 类型推荐卡片，实现合并/替换/过期逻辑，点击跳转 + 填入输入框
3. **输入框组件**：监听 `pendingInput` 变化，自动填入
4. **对话流**：过滤 `source: "recommendation"` 的消息不展示

## 不做的事

- 不在对话流中内联展示推荐
- 不自动发送推荐内容
- 不主动注入 memory，由 agent 自主决定
- 不启动独立会话，直接在原始会话中执行以复用 KV cache
- 不手动截断上下文，依赖 AgentRuntime 已有的上下文压缩机制
