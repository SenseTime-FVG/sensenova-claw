# Multi-Agent 通信架构设计

## 概述

为 AgentOS 新增 Multi-Agent 协作能力，支持任意 Agent 之间的消息通信。

核心设计：**将现有 DelegateTool 重构为 SendMessageTool + 新增 MessageRuntime**。任何 Agent 都可以通过 `send_message` tool 向其他 Agent 发送消息。MessageRuntime 作为全局单例订阅 PublicEventBus，负责 spawn 子 session、session 复用和生命周期管理。

**关键设计**：
- 统一的消息通信模型 —— `send_message` 既能新建 session 发起任务，也能向已有 session 发送后续消息（ping-pong 多轮对话）
- 不区分 Agent 和 Team —— "Team" 只是概念上的名词，物理上只有 Agent↔Agent 消息通信
- 可选 `can_send_message_to` 白名单 —— 配置了则限定范围，不配则全开放
- 安全约束：`max_send_depth`（新建 session 深度限制）+ `max_pingpong_turns`（单 session 多轮限制）+ 循环检测
- 异步消息基于 PrivateEventBus 轮间触发 —— 子 Agent 完成后结果通过 BusRouter 路由到父 session 的 PrivateEventBus 排队，AgentSessionWorker 完成当前 turn 后自动取出处理
- **统一路径**：sync 和 async 都经由 MessageRuntime 处理，SendMessageTool 不直接 spawn session 或订阅 bus

## 与现有代码的关系

当前代码库已有的基础设施：

| 组件 | 文件 | 状态 |
|------|------|------|
| `DelegateTool`（name="delegate"） | `agentos/capabilities/tools/delegate_tool.py` | 已实现，本次重构为 `SendMessageTool` |
| `AgentConfig.can_delegate_to` | `agentos/capabilities/agents/config.py` | 已实现（本次重命名为 `can_send_message_to`） |
| `AgentRegistry.get_delegatable()` | `agentos/capabilities/agents/registry.py` | 已实现（本次重命名为 `get_sendable()`） |
| `agent_worker.py` always_keep `{"delegate"}` | `agentos/kernel/runtime/workers/agent_worker.py:77` | 已实现（改为 `{"send_message"}`） |
| Agent-to-Agent 事件类型 | `agentos/kernel/events/types.py` | 已定义 4 个 |

本设计**重构 DelegateTool 为 SendMessageTool**，增加 session 复用和异步模式（基于 PrivateEventBus 轮间触发）。

## 设计决策

| 维度 | 决策 | 理由 |
|------|------|------|
| 权限模型 | 默认全开放 + 可选 `can_send_message_to` 白名单 | 不配则全开放；配了则精确控制 |
| 通信模型 | 消息发送（send_message），支持新建 session 和复用已有 session | 统一入口，支持一次性任务和 ping-pong 多轮对话 |
| Session 关系 | 独立 session | 隔离上下文，父子通过 tool 结果通信 |
| 深度控制 | `max_send_depth` 限制新建 session 层数 | 防止无限嵌套 |
| Ping-pong 控制 | `max_pingpong_turns` 限制单 session 复用轮数 | 独立于深度，防止同一 session 无限对话 |
| Tool 名称 | `send_message`（替换 `delegate`） | 语义更准确：向 Agent 发消息，而非"委派" |
| 异步消息 | PrivateEventBus 轮间触发：子 Agent 结果经 BusRouter 路由排队，父 Agent 完成当前 turn 后自动处理 | 复用现有基础设施，无需额外 tool 和 inbox 组件 |
| MessageRuntime | 全局单例，订阅 PublicEventBus | 跨 session 协调，只做 spawn + 生命周期管理 |
| 统一路径 | sync/async 均经由 MessageRuntime | SendMessageTool 不直接 spawn session，避免 ToolWorker 阻塞和 per-call bus 订阅泄漏 |
| 编排方式 | 由 Agent 自行决定 | Agent 通过 system_prompt 了解可通信目标，自行决定并行/串行/混合编排 |

## 核心概念

### Agent
一个独立的 AI 执行单元，有自己的 config（model、tools、system_prompt）。已有实现。每个 Agent 都可以通过 `send_message` tool 向任意其他 Agent 发送消息。

### Session 复用（Ping-Pong 模式）
Agent1 向 Agent2 发消息后，Agent2 在独立 session 中执行并返回结果。之后 Agent1 可以选择：
- **继续对话**：再次调用 `send_message` 并传入上一次返回的 `session_id`，在同一 session 中继续交互（多轮 ping-pong），受 `max_pingpong_turns` 限制
- **新建任务**：调用 `send_message` 不传 `session_id`，创建新 session 发起独立任务，受 `max_send_depth` 限制

### "Team" 的含义
Team 不是物理概念。当用户说"一个 research team"时，实际上只是"一个 coordinator Agent（system_prompt 里写了它负责协调研究任务）+ 它会向 writer-agent 和 reviewer-agent 发消息"。不需要 TeamConfig、TeamRegistry 等专门数据结构。

## 数据模型

### MessageRecord（新增）

```python
@dataclass
class MessageRecord:
    id: str                          # message_record_id (UUID)
    parent_session_id: str
    parent_turn_id: str
    parent_tool_call_id: str         # 关联父 Agent 的 tool_call
    child_session_id: str
    target_id: str                   # 目标 agent_id
    status: str                      # "pending" | "running" | "completed" | "failed"
    mode: str                        # "sync" | "async"
    message: str                     # 发送的消息内容
    result: str | None               # 最终结果
    error: str | None                # 失败时的错误信息
    depth: int                       # 新建 session 深度
    pingpong_count: int              # 当前 session 已进行的 ping-pong 轮数
    send_chain: list[str]            # 发送链，如 ["agent1", "agent2"]，用于循环检测
    created_at: float
    completed_at: float | None = None
```

### config.yml 扩展

```yaml
agents:
  default:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    max_tokens: null                # null 表示使用模型默认值
    system_prompt: "你是一个有用的AI助手"
    max_send_depth: 3           # 新建 session 的最大嵌套深度
    max_pingpong_turns: 10      # 单个 session 最大 ping-pong 轮数
    # can_send_message_to 不填 → default Agent 可向所有 Agent 发消息

  research-agent:
    name: "Research Agent"
    description: "擅长搜索和信息整理，可协调 writer 和 reviewer 完成研究任务"
    model: gpt-4o-mini
    tools: [serper_search, fetch_url]
    can_send_message_to: [writer-agent, reviewer-agent]  # 可选白名单，不填则可向所有 Agent 发消息
    system_prompt: |
      你是一个研究协调者。当收到复杂研究任务时，你可以：
      - 自己执行搜索
      - 使用 send_message 工具将写作任务发送给 writer-agent
      - 使用 send_message 工具将审核任务发送给 reviewer-agent
      你可以并行发送(mode="async")或串行发送(mode="sync")。
      如果需要对已有结果进行追问或修改，可以传入之前返回的 session_id 继续对话。
      异步任务完成后，结果会自动送达并触发新一轮对话。

  writer-agent:
    name: "Writer Agent"
    description: "擅长内容创作和文档撰写"
    model: gpt-4o
    tools: [read_file, write_file]
    # can_send_message_to 不填 → 可向所有 Agent 发消息

  reviewer-agent:
    name: "Reviewer Agent"
    description: "擅长代码和文档审核"
    model: gpt-4o-mini
    tools: [read_file]
```

**配置加载规则**：
- `agents.default` 段创建 `id="default"` 的 AgentConfig，作为全局默认值
- 其他 Agent 未指定的 `provider`/`model`/`temperature`/`max_send_depth`/`max_pingpong_turns` 继承 default 的配置
- `can_send_message_to`: 空列表或不配 = 可向所有 Agent 发消息；填了 = 只能向列表中的 Agent 发消息

## 架构组件

### 1. SendMessageTool（入口层）

**重构现有 `DelegateTool`**（`agentos/capabilities/tools/delegate_tool.py`），tool name 改为 `"send_message"`，更新 agent_worker.py 中的 `always_keep`。

```python
class SendMessageTool(Tool):
    name = "send_message"
    description = "向指定 Agent 发送消息。可以新建会话发起任务，也可以向已有会话发送后续消息。"
    parameters = {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "目标 Agent Name"
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容"
            },
            "session_id": {
                "type": "string",
                "description": "可选。已有会话的 session_id，用于在同一会话中继续对话，适用于轻量级信息交换。不传则新建会话，适用于分配完整任务。"
            },
            "mode": {
                "type": "string",
                "enum": ["sync", "async"],
                "default": "sync",
                "description": "sync=等待对方回复; async=发送后继续执行，对方回复后会通知你"
            }
        },
        "required": ["target_id", "message"]
    }
```

#### 执行逻辑

所有 send_message 调用（sync/async、新建/复用）**统一经由 MessageRuntime 处理**。SendMessageTool 不直接 spawn session 或订阅 PublicEventBus，而是：
1. 做前置校验（target 存在、权限、深度/轮数/循环检测）
2. 发布 `AGENT_MESSAGE_REQUESTED` 事件
3. sync 模式：通过 MessageRuntime 维护的 `record_id → Future` 映射 await 结果（不阻塞 ToolWorker 事件循环）
4. async 模式：立即返回

```python
async def execute(self, target_id, message, session_id=None, mode="sync"):
    # 1. 验证目标 Agent 存在
    target = self.agent_registry.get(target_id)
    if not target:
        return f"发送失败：未找到名为 {target_id} 的 Agent。"

    # 2. 权限检查（can_send_message_to 白名单）
    sendable = self.agent_registry.get_sendable(current_agent_id)
    if target_id not in {a.id for a in sendable}:
        return f"发送失败：当前 Agent 未被授权向 {target_id} 发送消息。"

    # 3. 判断是新建 session 还是复用
    if session_id:
        # 复用已有 session（ping-pong）
        # 3a. 验证 session_id 对应的 target 与传入 target_id 一致
        record = self.message_runtime.get_record_by_session(session_id)
        if record and record.target_id != target_id:
            return (
                f"发送失败：session {session_id} 属于 {record.target_id}，"
                f"与目标 {target_id} 不匹配。"
            )
        # 3b. 检查 ping-pong 轮数限制
        pingpong_count = self.message_runtime.get_pingpong_count(session_id)
        if pingpong_count >= max_pingpong_turns:
            return (
                f"发送失败：与 {target_id} 的会话（{session_id}）已达到最大对话轮数 "
                f"{max_pingpong_turns}。如需继续，请新建会话。"
            )
    else:
        # 新建 session
        # 3c. 深度检查
        if current_depth >= max_send_depth:
            return (
                f"发送失败：当前已达到最大消息传递深度 {max_send_depth}，"
                f"无法继续向其他 Agent 发送新任务。"
            )
        # 3d. 循环检测
        if target_id in current_send_chain:
            chain_str = " → ".join(current_send_chain)
            return f"发送失败：检测到循环（{chain_str} → {target_id}），请避免形成环路。"

    # 4. 统一发布 AGENT_MESSAGE_REQUESTED → MessageRuntime 处理
    record_id = str(uuid4())
    await self.bus.publish(EventEnvelope(
        type=EventTypes.AGENT_MESSAGE_REQUESTED,
        session_id=self.session_id,
        trace_id=record_id,
        payload={
            "record_id": record_id,
            "target_id": target_id,
            "message": message,
            "mode": mode,
            "session_id": session_id,   # None = 新建, 有值 = 复用
            "depth": current_depth + (0 if session_id else 1),
            "send_chain": current_send_chain + ([current_agent_id] if not session_id else []),
            "parent_session_id": self.session_id,
            "parent_turn_id": self.turn_id,
            "parent_tool_call_id": self.tool_call_id,
        }
    ))

    # 5. 同步模式：通过 MessageRuntime 的 Future 映射等待结果
    if mode == "sync":
        future = self.message_runtime.register_sync_waiter(record_id)
        try:
            result_payload = await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            self.message_runtime.cancel_sync_waiter(record_id)
            return "处理超时，目标 Agent 未在规定时间内完成。"

        if result_payload["status"] == "completed":
            child_session_id = result_payload["child_session_id"]
            return (
                f"{target_id} {'回复' if session_id else '已完成任务，回复'}如下：\n\n"
                f"{result_payload['result']}\n\n"
                f"如需继续与 {target_id} 对话，请使用 session_id=\"{child_session_id}\"。"
            )
        else:
            return f"{target_id} 处理失败：{result_payload.get('error', '未知错误')}"

    # 6. 异步模式：立即返回
    else:
        if session_id:
            return (
                f"后续消息已发送给 {target_id}（会话: {session_id}）。"
                f"{target_id} 正在处理中，完成后结果会自动送达。"
            )
        else:
            return (
                f"消息已发送给 {target_id}（任务 ID: {record_id}）。"
                f"{target_id} 正在处理中，完成后结果会自动送达。你可以继续处理其他事务。"
            )
```

### 2. MessageRuntime（生命周期管理层）

**全局单例**，直接订阅 PublicEventBus（不是 per-session worker）。职责：
- spawn 新 session / 向已有 session 发送消息
- 维护 `record_id → Future` 映射，供 sync 模式使用
- 监听子 session 完成/失败，通知父 Agent
- 管理 `_child_session_index` 生命周期（ping-pong 场景下不清理索引）

```python
class MessageRuntime:
    """全局单例。订阅 PublicEventBus，统一处理所有 agent-to-agent 通信。"""

    def __init__(self, bus: PublicEventBus, bus_router: BusRouter, repo, agent_registry):
        self._bus = bus
        self._bus_router = bus_router
        self._repo = repo
        self._agent_registry = agent_registry

        # record_id → MessageRecord（内存索引）
        self._records: dict[str, MessageRecord] = {}
        # child_session_id → record_id（反向索引，用于匹配子 session 事件）
        # 注意：ping-pong 场景下不清理此索引，因为同一 session 可能收到多次 STEP_COMPLETED
        self._child_session_index: dict[str, str] = {}
        # record_id → Future（sync 模式等待映射）
        self._sync_waiters: dict[str, asyncio.Future] = {}

    async def start(self):
        """启动事件循环，订阅 PublicEventBus"""
        self._task = asyncio.create_task(self._event_loop())

    async def stop(self):
        """停止事件循环，取消所有 pending Future"""
        self._task.cancel()
        for future in self._sync_waiters.values():
            if not future.done():
                future.cancel()
        self._sync_waiters.clear()

    async def _event_loop(self):
        async for event in self._bus.subscribe():
            try:
                if event.type == EventTypes.AGENT_MESSAGE_REQUESTED:
                    await self._handle_message_requested(event)
                elif event.type == EventTypes.AGENT_STEP_COMPLETED:
                    if event.session_id in self._child_session_index:
                        await self._handle_child_completed(event)
                elif event.type == EventTypes.ERROR_RAISED:
                    if event.session_id in self._child_session_index:
                        await self._handle_child_failed(event)
            except Exception as e:
                logger.error(f"MessageRuntime 处理事件出错: {e}")

    # ---------- 供 SendMessageTool 调用的公开方法 ----------

    def register_sync_waiter(self, record_id: str) -> asyncio.Future:
        """注册 sync 等待。SendMessageTool 通过 await 此 Future 获取结果。"""
        future = asyncio.get_event_loop().create_future()
        self._sync_waiters[record_id] = future
        return future

    def cancel_sync_waiter(self, record_id: str):
        """超时时取消等待"""
        future = self._sync_waiters.pop(record_id, None)
        if future and not future.done():
            future.cancel()

    def get_record_by_session(self, session_id: str) -> MessageRecord | None:
        """根据 child_session_id 查找 MessageRecord（用于 ping-pong 验证）"""
        record_id = self._child_session_index.get(session_id)
        if record_id:
            return self._records.get(record_id)
        return None

    def get_pingpong_count(self, session_id: str) -> int:
        """获取指定 session 的当前 ping-pong 轮数"""
        record = self.get_record_by_session(session_id)
        return record.pingpong_count if record else 0
```

#### 处理 AGENT_MESSAGE_REQUESTED（统一入口）

```python
async def _handle_message_requested(self, event):
    payload = event.payload
    session_id = payload.get("session_id")  # None = 新建, 有值 = 复用

    if session_id:
        await self._handle_pingpong(payload)
    else:
        await self._handle_new_session(payload)
```

#### 新建 Session

```python
async def _handle_new_session(self, payload):
    record_id = payload["record_id"]
    target_id = payload["target_id"]

    child_session_id = f"agent2agent_{uuid.uuid4().hex[:12]}"

    # 持久化 MessageRecord
    record = MessageRecord(
        id=record_id,
        parent_session_id=payload["parent_session_id"],
        parent_turn_id=payload.get("parent_turn_id"),
        parent_tool_call_id=payload.get("parent_tool_call_id"),
        child_session_id=child_session_id,
        target_id=target_id,
        mode=payload.get("mode", "sync"),
        message=payload["message"],
        depth=payload["depth"],
        pingpong_count=0,
        send_chain=payload.get("send_chain", []),
        status="running",
        created_at=time.time(),
    )
    self._records[record_id] = record
    self._child_session_index[child_session_id] = record_id
    await self._repo.save_message_record(record)

    # 创建 session 记录
    await self._repo.create_session(child_session_id, {
        "agent_id": target_id,
        "parent_session_id": payload["parent_session_id"],
        "record_id": record_id,
        "send_depth": payload["depth"],
        "send_chain": payload.get("send_chain", []) + [target_id],
    })

    # 发布 AGENT_MESSAGE_STARTED
    await self._bus.publish(EventEnvelope(
        type=EventTypes.AGENT_MESSAGE_STARTED,
        session_id=payload["parent_session_id"],
        trace_id=record_id,
        payload={"record_id": record_id, "target_id": target_id, "message": payload["message"]},
    ))

    # 向子 session 注入 USER_INPUT（触发 BusRouter 创建 workers）
    await self._bus.publish(EventEnvelope(
        type=EventTypes.USER_INPUT,
        session_id=child_session_id,
        payload={
            "text": payload["message"],
            "send_depth": payload["depth"],
            "send_chain": payload.get("send_chain", []) + [target_id],
        },
        source="agent_to_agent",
    ))
```

#### 复用 Session（Ping-Pong）

```python
async def _handle_pingpong(self, payload):
    """向已有 session 发送后续消息"""
    record_id = payload["record_id"]
    session_id = payload["session_id"]
    target_id = payload["target_id"]

    # 更新 ping-pong 计数
    existing_record = self.get_record_by_session(session_id)
    if existing_record:
        existing_record.pingpong_count += 1
        await self._repo.update_message_record(existing_record)

    # 为本次 ping-pong 创建新的 record（便于追踪）
    # 注意：child_session_id 复用已有 session
    record = MessageRecord(
        id=record_id,
        parent_session_id=payload["parent_session_id"],
        parent_turn_id=payload.get("parent_turn_id"),
        parent_tool_call_id=payload.get("parent_tool_call_id"),
        child_session_id=session_id,
        target_id=target_id,
        mode=payload.get("mode", "sync"),
        message=payload["message"],
        depth=payload["depth"],
        pingpong_count=existing_record.pingpong_count if existing_record else 0,
        send_chain=payload.get("send_chain", []),
        status="running",
        created_at=time.time(),
    )
    self._records[record_id] = record
    # 更新反向索引指向最新 record_id（同一 session 的最新一次调用）
    self._child_session_index[session_id] = record_id
    await self._repo.save_message_record(record)

    # 向已有 session 发送 USER_INPUT
    await self._bus.publish(EventEnvelope(
        type=EventTypes.USER_INPUT,
        session_id=session_id,
        payload={"text": payload["message"]},
        source="agent_to_agent",
    ))
```

#### 子 Session 完成处理

```python
async def _handle_child_completed(self, event):
    child_session_id = event.session_id
    record_id = self._child_session_index.get(child_session_id)
    if not record_id:
        return

    record = self._records.get(record_id)
    if not record:
        return

    # 更新状态
    record.status = "completed"
    record.result = event.payload.get("content", "")
    record.completed_at = time.time()
    await self._repo.update_message_record(record)

    # 注意：不从 _child_session_index 删除 —— ping-pong 场景下同一 session
    # 可能收到多次 STEP_COMPLETED，需要保留索引。
    # GC 策略：session 过期或显式关闭时清理（见下方"索引生命周期管理"）。

    result_payload = {
        "record_id": record.id,
        "agent_id": record.target_id,
        "result": record.result,
        "child_session_id": child_session_id,
        "status": "completed",
    }

    # sync 模式：resolve Future
    if record_id in self._sync_waiters:
        future = self._sync_waiters.pop(record_id)
        if not future.done():
            future.set_result(result_payload)
    else:
        # async 模式：发布 AGENT_MESSAGE_COMPLETED 到 PublicEventBus
        # BusRouter 根据 session_id 路由到父 session 的 PrivateEventBus
        # AgentSessionWorker 完成当前 turn 后从 queue 取出并处理
        await self._bus.publish(EventEnvelope(
            type=EventTypes.AGENT_MESSAGE_COMPLETED,
            session_id=record.parent_session_id,
            trace_id=record.id,
            payload=result_payload,
        ))
```

#### 子 Session 失败处理

```python
async def _handle_child_failed(self, event):
    """处理子 session 的 ERROR_RAISED 事件"""
    child_session_id = event.session_id
    record_id = self._child_session_index.get(child_session_id)
    if not record_id:
        return

    record = self._records.get(record_id)
    if not record:
        return

    record.status = "failed"
    record.error = event.payload.get("error", "未知错误")
    record.completed_at = time.time()
    await self._repo.update_message_record(record)

    error_payload = {
        "record_id": record.id,
        "agent_id": record.target_id,
        "error": record.error,
        "child_session_id": child_session_id,
        "status": "failed",
    }

    # sync 模式：resolve Future（带 error）
    if record_id in self._sync_waiters:
        future = self._sync_waiters.pop(record_id)
        if not future.done():
            future.set_result(error_payload)
    else:
        # async 模式：发布 AGENT_MESSAGE_FAILED
        await self._bus.publish(EventEnvelope(
            type=EventTypes.AGENT_MESSAGE_FAILED,
            session_id=record.parent_session_id,
            trace_id=record.id,
            payload=error_payload,
        ))
```

#### 索引生命周期管理

```python
def cleanup_session(self, session_id: str):
    """session 过期或显式关闭时，清理相关索引。由 BusRouter GC 调用。"""
    if session_id in self._child_session_index:
        record_id = self._child_session_index.pop(session_id)
        # 清理 sync waiter（如果还有的话）
        future = self._sync_waiters.pop(record_id, None)
        if future and not future.done():
            future.cancel()
```

### 3. 异步回传处理

#### 基于 PrivateEventBus 的队列缓冲 + 轮间触发

异步模式不使用 inbox 拉取机制。子 Agent 完成后，MessageRuntime 发布 `AGENT_MESSAGE_COMPLETED` 到 PublicEventBus（session_id = 父 session），BusRouter 路由到父 session 的 PrivateEventBus，事件在 asyncio.Queue 中排队。AgentSessionWorker 完成当前 turn 后从 queue 取出，构造合成 USER_INPUT 触发新一轮 LLM 对话。

**核心机制**：PrivateEventBus 内部就是 `asyncio.Queue`（FIFO），AgentSessionWorker 的 `_loop` 串行消费。当 Worker 在处理当前 turn 的事件链（LLM 调用 → tool 处理 → ...）时，新到达的 `AGENT_MESSAGE_COMPLETED` 自然在 queue 中等待，直到当前 turn 结束后才被取出。

#### AgentSessionWorker 变更

仅在 `_handle` 方法中新增事件分支：

```python
async def _handle(self, event: EventEnvelope) -> None:
    try:
        if event.type == USER_INPUT:
            await self._handle_user_input(event)
        elif event.type == LLM_CALL_RESULT:
            await self._handle_llm_result(event)
        elif event.type == LLM_CALL_COMPLETED:
            await self._handle_llm_completed(event)
        elif event.type == TOOL_CALL_RESULT:
            await self._handle_tool_result(event)
        # 新增：异步子 Agent 完成/失败回传
        elif event.type == AGENT_MESSAGE_COMPLETED:
            await self._handle_async_message_completed(event)
        elif event.type == AGENT_MESSAGE_FAILED:
            await self._handle_async_message_failed(event)
        self._consecutive_errors = 0
    except Exception as exc:
        ...

async def _handle_async_message_completed(self, event: EventEnvelope) -> None:
    """异步子 Agent 完成，构造合成 USER_INPUT 触发新一轮对话"""
    agent_id = event.payload.get("agent_id", "unknown")
    result = event.payload.get("result", "")
    child_session_id = event.payload.get("child_session_id", "")

    content = (
        f"[来自 {agent_id} 的异步任务结果]\n\n"
        f"{result}\n\n"
        f"如需继续与 {agent_id} 对话，请使用 "
        f"send_message(target_agent=\"{agent_id}\", session_id=\"{child_session_id}\")。"
    )

    # 复用 _handle_user_input 的完整流程
    synthetic_event = EventEnvelope(
        type=USER_INPUT,
        session_id=self.session_id,
        source="agent_to_agent",
        payload={"content": content},
    )
    await self._handle_user_input(synthetic_event)

async def _handle_async_message_failed(self, event: EventEnvelope) -> None:
    """异步子 Agent 失败，构造合成 USER_INPUT 通知父 Agent"""
    agent_id = event.payload.get("agent_id", "unknown")
    error = event.payload.get("error", "未知错误")

    content = f"[来自 {agent_id} 的异步任务失败]\n\n错误：{error}"

    synthetic_event = EventEnvelope(
        type=USER_INPUT,
        session_id=self.session_id,
        source="agent_to_agent",
        payload={"content": content},
    )
    await self._handle_user_input(synthetic_event)
```

#### 处理场景

| 父 Agent 状态 | 子 Agent 消息到达时 | 处理方式 |
|---|---|---|
| LLM 调用中 / 处理 tool 中 | completed / failed | 事件在 PrivateEventBus 的 asyncio.Queue 中排队，当前 turn 结束后自动取出处理 |
| Idle（已完成 turn） | completed / failed | Worker 的 `_loop` 立即取出事件，触发新一轮 LLM 对话 |
| 多个子 Agent 同时完成 | 多个 completed | FIFO 逐个取出，每个触发独立的一轮 LLM 对话 |

#### 时序保证

1. **FIFO 排队**：PrivateEventBus 使用 `asyncio.Queue`，先到先处理
2. **串行消费**：AgentSessionWorker 的 `_loop` 是 `async for event in bus.subscribe()` → `await _handle(event)`，一次只处理一个事件
3. **无需状态守卫**：当前 turn 的 `_handle_llm_completed` / `_handle_tool_result` 返回后，下一次 `async for` 自然取出队列中等待的异步回传事件
4. **无需 idle 检测**：不论父 Agent 当前是否空闲，事件都经由 BusRouter → PrivateEventBus 排队，Worker 按序处理

#### Announce 机制

子 Agent 通过 `report_progress` tool 发布进度（可选，v1 暂不实现，预留事件类型）。

### 4. ContextBuilder 扩展

#### 可通信目标注入

```python
def _build_agent_to_agent_context(self, agent_config: AgentConfig) -> str:
    # 使用 get_sendable() 获取当前 Agent 可通信的目标（遵循 can_send_message_to 白名单）
    sendable_agents = self.agent_registry.get_sendable(agent_config.id)
    targets = []
    for agent in sendable_agents:
        targets.append(f"- {agent.id}: {agent.description}")

    if not targets:
        return ""

    return f"""
## 可通信的 Agent

你可以使用 send_message 工具向以下 Agent 发送消息：

{chr(10).join(targets)}

- sync 模式：等待对方回复后继续
- async 模式：发送后立即继续，对方完成后结果自动送达并触发新一轮对话
- 传入 session_id：在已有会话中继续对话（多轮交互）
"""
```

#### 子 Session 上下文

被发送消息的 Agent 在 system_prompt 中注入信息：

```python
agent_to_agent_note = f"""
你正在接受来自其他 Agent 的任务请求。
- 当前消息传递深度: {depth}/{max_depth}
- 请专注完成指定任务，完成后直接回复最终结果。
"""
```

### 5. 前端事件映射

WebSocketChannel 新增 agent-to-agent 事件到前端消息的映射：

```python
AGENT_MESSAGE_STARTED → {"type": "agent_message_started", "record_id": ..., "target_id": ..., "message": ...}
AGENT_MESSAGE_ANNOUNCE → {"type": "agent_message_progress", "record_id": ..., "content": ...}
AGENT_MESSAGE_COMPLETED → {"type": "agent_message_completed", "record_id": ..., "result": ...}
AGENT_MESSAGE_FAILED → {"type": "agent_message_failed", "record_id": ..., "error": ...}
```

### 6. DB 持久化

Repository 新增 `agent_messages` 表：

```sql
CREATE TABLE IF NOT EXISTS agent_messages (
    id TEXT PRIMARY KEY,
    parent_session_id TEXT NOT NULL,
    parent_turn_id TEXT,
    parent_tool_call_id TEXT,
    child_session_id TEXT,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    mode TEXT NOT NULL DEFAULT 'sync',
    message TEXT,
    result TEXT,
    error TEXT,
    depth INTEGER DEFAULT 0,
    pingpong_count INTEGER DEFAULT 0,
    send_chain TEXT,              -- JSON 数组，如 '["agent1", "agent2"]'
    created_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (child_session_id) REFERENCES sessions(session_id)
);
```

## 事件类型

重命名现有事件 + 新增。遵循现有命名约定（用下划线分隔单词）：

```python
# 重命名（原 agent.delegate_xxx → agent.message_xxx）
AGENT_MESSAGE_REQUESTED = "agent.message_requested"
AGENT_MESSAGE_STARTED = "agent.message_started"
AGENT_MESSAGE_COMPLETED = "agent.message_completed"
AGENT_MESSAGE_FAILED = "agent.message_failed"

# 新增
AGENT_MESSAGE_ANNOUNCE = "agent.message_announce"      # 异步中间状态（v2 实现）

# 已有（MessageRuntime 需要监听）
ERROR_RAISED = "error.raised"                          # 子 session 异常时映射为 AGENT_MESSAGE_FAILED
```

## 完整事件流

### 同步发送（新建 Session）

```
Agent1 LLM → tool_call: send_message(target_id="agent2", message="搜索 AI 最新论文")
  → ToolWorker: TOOL_CALL_REQUESTED
  → SendMessageTool.execute()
    → AgentRegistry.get("agent2") → 找到
    → 无 session_id → 新建 session
    → 深度检查通过，循环检测通过
    → 发布 AGENT_MESSAGE_REQUESTED（统一经由 MessageRuntime）
    → MessageRuntime._handle_new_session():
      → 创建 MessageRecord + 持久化
      → 创建子 session "agent2agent_xxxx"
      → 发布 USER_INPUT → BusRouter 创建 workers
    → SendMessageTool await MessageRuntime.register_sync_waiter() 返回的 Future
    → Agent2 执行: USER_INPUT → LLM → (tools) → AGENT_STEP_COMPLETED
    → MessageRuntime._handle_child_completed():
      → 有 sync_waiter → resolve Future
    → Future 被 resolve，SendMessageTool 拿到结果
    → 返回 tool_result:
      "agent2 已完成任务，回复如下：
       [Agent2 的结果内容]
       如需继续与 agent2 对话，请使用 session_id="agent2agent_xxxx"。"
  → ToolWorker: TOOL_CALL_RESULT
→ Agent1 继续 LLM 对话
```

### 继续对话（复用 Session，Ping-Pong）

```
Agent1 LLM → tool_call: send_message(
    target_id="agent2",
    message="请补充关于 Transformer 的部分",
    session_id="agent2agent_xxxx"
  )
  → SendMessageTool.execute()
    → 有 session_id → 复用已有 session
    → 验证 session_id 对应的 target_id 与传入 target_id 一致 ✓
    → ping-pong 轮数检查（当前 3 < max 10 ✓）
    → 发布 AGENT_MESSAGE_REQUESTED（session_id 字段非空 → MessageRuntime 走 pingpong 路径）
    → MessageRuntime._handle_pingpong():
      → 更新 ping-pong 计数
      → 向 "agent2agent_xxxx" 发布 USER_INPUT
    → sync 模式: await Future
    → Agent2 收到后续消息，执行新一轮 LLM（保有完整对话历史）
    → AGENT_STEP_COMPLETED
    → MessageRuntime resolve Future
    → 返回 tool_result:
      "agent2 回复如下：
       [Agent2 的新结果]
       如需继续与 agent2 对话，请使用 session_id="agent2agent_xxxx"。"
→ Agent1 可以继续 ping-pong 或转向其他任务
```

### 异步发送 + PrivateEventBus 轮间触发

```
Agent1 LLM → tool_call: send_message(target_id="agent2", message="...", mode="async")
  → SendMessageTool.execute()
    → 发布 AGENT_MESSAGE_REQUESTED
    → 立即返回 tool_result:
      "消息已发送给 agent2（任务 ID: abc123）。agent2 正在处理中，完成后结果会自动送达。你可以继续处理其他事务。"
  → Agent1 继续执行其他操作...

  (并行) MessageRuntime._handle_new_session() + Agent2 执行...
    → Agent2 完成: AGENT_STEP_COMPLETED
    → MessageRuntime._handle_child_completed():
      → 无 sync_waiter → 发布 AGENT_MESSAGE_COMPLETED 到 PublicEventBus（session_id = 父 session）
    → BusRouter 路由到父 session 的 PrivateEventBus
    → 事件进入 PrivateEventBus 的 asyncio.Queue 排队

  Agent1 当前 turn 完成（AGENT_STEP_COMPLETED）后:
    → AgentSessionWorker._loop() 从 queue 取出 AGENT_MESSAGE_COMPLETED
    → _handle_async_message_completed():
      → 构造合成 USER_INPUT:
        "[来自 agent2 的异步任务结果]
         [结果内容]
         如需继续对话，请使用 send_message(target_agent="agent2", session_id="agent2agent_xxxx")。"
      → 复用 _handle_user_input 流程开启新一轮 LLM 对话
    → Agent1 LLM 处理结果
```

### 多级通信示例（"Team" 行为）

```
用户 → send_message(target_id="research-agent", message="调研 AI Agent 现状")
  → research-agent 接收消息
  → research-agent 的 system_prompt 知道它是协调者
  → research-agent LLM 决定编排:
    → send_message(target="writer-agent", message="写初稿", mode="async")
      → 返回: "消息已发送给 writer-agent...正在处理中..."
    → send_message(target="reviewer-agent", message="准备审核标准", mode="async")
      → 返回: "消息已发送给 reviewer-agent...正在处理中..."
    → research-agent 继续执行其他工作...
    → 当前 turn 完成（AGENT_STEP_COMPLETED）

  → writer-agent 完成 → AGENT_MESSAGE_COMPLETED 进入 research-agent 的 PrivateEventBus
  → research-agent Worker 取出事件，触发新 turn:
    → LLM 收到: "[来自 writer-agent 的异步任务结果] ..."
    → LLM 处理结果，当前 turn 完成

  → reviewer-agent 完成 → AGENT_MESSAGE_COMPLETED 进入 research-agent 的 PrivateEventBus
  → research-agent Worker 取出事件，触发新 turn:
    → LLM 收到: "[来自 reviewer-agent 的异步任务结果] ..."
    → 决定追问: send_message(target="reviewer-agent", message="请审核这份初稿: ...", session_id="agent2agent_yyy")
      → ping-pong: 复用 reviewer 的已有 session
    → 汇总最终结果
  → research-agent AGENT_STEP_COMPLETED
  → 结果返回给用户
```

## 安全约束

1. **深度限制**: `max_send_depth`（默认 3），每次新建 session 时 depth+1，超限拒绝
2. **Ping-pong 限制**: `max_pingpong_turns`（默认 10），单个 session 最大复用轮数，超限提示新建 session。独立于深度限制
3. **超时机制**: 同步等待超时默认 300s，超时后 `cancel_sync_waiter()` 清理 Future
4. **循环检测**: `send_chain` 记录完整发送路径，新建 session 前检查 target_id 是否已在链中。复用 session 不做循环检测（已是同一 Agent）
5. **取消传播**: 父 session 取消（`USER_TURN_CANCEL_REQUESTED`）时，MessageRuntime 向子 session 传播取消事件（v2 实现）
6. **target_id/session_id 一致性**: ping-pong 时验证 session_id 对应的 target 与传入 target_id 匹配，防止误发
7. **ERROR_RAISED 映射**: 子 session 抛出 `ERROR_RAISED` 时，MessageRuntime 将其映射为 `AGENT_MESSAGE_FAILED`，sync 模式通过 Future 返回错误，async 模式经 BusRouter 路由到父 session 的 PrivateEventBus 排队处理
8. **索引 GC**: `_child_session_index` 不在子 session 完成时立即清理（为 ping-pong 保留），由 BusRouter GC 在 session 过期时调用 `MessageRuntime.cleanup_session()` 统一回收
9. **并发安全**: 同一 session 的多个 ping-pong 请求串行处理（通过 `_child_session_index` 指向最新 record_id），避免多个 Future 竞争同一 STEP_COMPLETED

## 实现分期

### v1（MVP）
- SendMessageTool（替换 DelegateTool）+ sync 模式 + 新建 session
- MessageRuntime（全局单例，统一处理 sync/async 路径 + spawn 子 session + Future 映射）
- MessageRecord + DB 持久化（agent_messages 表）
- ContextBuilder 可通信目标注入（列出所有 Agent）
- 循环检测 + 深度检查 + pingpong 轮数限制 + target_id/session_id 一致性校验
- ERROR_RAISED → AGENT_MESSAGE_FAILED 映射
- 自然语言 tool 返回
- 索引 GC（BusRouter 回调 MessageRuntime.cleanup_session）

### v2
- Session 复用（ping-pong 多轮对话）
- Async 模式 + PrivateEventBus 轮间触发（AgentSessionWorker 新增 AGENT_MESSAGE_COMPLETED/FAILED 处理）
- 前端事件映射
- 取消传播（父 session cancel → 子 session cancel）
- report_progress tool (announce)

### v3
- 子 Agent 监控与干预（kill/steer）
- 前端 agent-to-agent 可视化（树形执行视图）
- Token 预算管理

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `agentos/kernel/runtime/message_runtime.py` | MessageRuntime（全局单例） |
| `agentos/capabilities/tools/send_message_tool.py` | SendMessageTool（替换 DelegateTool） |

### 修改文件

| 文件 | 变更 |
|------|------|
| `agentos/kernel/events/types.py` | 重命名 AGENT_DELEGATE_* → AGENT_MESSAGE_*；新增 AGENT_MESSAGE_ANNOUNCE |
| `agentos/capabilities/agents/registry.py` | `get_delegatable()` 重命名为 `get_sendable()`，遵循 `can_send_message_to` 白名单 |
| `agentos/kernel/runtime/workers/agent_worker.py` | always_keep 改为 `{"send_message"}`；v2: 新增 AGENT_MESSAGE_COMPLETED/FAILED 事件处理 |
| `agentos/kernel/runtime/context_builder.py` | 注入可通信目标列表 + 子 session 信息 |
| `agentos/adapters/storage/repository.py` | 新增 agent_messages 表 + CRUD |
| `agentos/adapters/channels/websocket_channel.py` | v2: 映射 agent-to-agent 事件 |
| `agentos/app/gateway/main.py` | 初始化 MessageRuntime |
| `agentos/capabilities/agents/config.py` | `can_delegate_to` 重命名为 `can_send_message_to` |

### 删除

| 文件 | 变更 |
|------|------|
| `agentos/capabilities/tools/delegate_tool.py` | 删除，由 send_message_tool.py 替代 |

## 测试策略

1. **单元测试**: 循环检测、深度检查、pingpong 轮数限制、target_id/session_id 一致性校验、MessageRecord CRUD
2. **集成测试**:
   - Agent→Agent 同步发送事件链（统一经由 MessageRuntime）
   - ping-pong 多轮对话事件链（index 不清理 + 多次 STEP_COMPLETED）
   - 异步发送 + PrivateEventBus 轮间触发事件链（AGENT_MESSAGE_COMPLETED → 合成 USER_INPUT → 新 turn）
   - ERROR_RAISED → AGENT_MESSAGE_FAILED 映射 + 合成 USER_INPUT
   - 多个异步子 Agent 同时完成时的 FIFO 逐个触发
   - 超时 → Future cancel 清理
3. **E2E 测试**: 配置多 Agent，用户输入触发 agent-to-agent 通信，验证最终响应

## 设计考量

### 为什么用 send_message 替代 delegate

`delegate` 隐含"单向的任务分配"语义，而 `send_message` 更准确地表达了 Agent 间的通信本质：
- 支持双向多轮对话（ping-pong），而非单次委派→返回
- 语义更自然 —— Agent 之间在"对话"，而非"命令"
- tool 返回的自然语言更容易组织 —— "消息已发送给 xxx" 比 "delegation dispatched" 更直观

### 为什么异步回传用 PrivateEventBus 轮间触发而非 inbox 拉取

早期设计使用 inbox 拉取模式（ReadInboxTool + inbox 缓存 + DB 持久化）。改为 PrivateEventBus 轮间触发的理由：

1. **更简单** —— 不需要 ReadInboxTool、inbox 缓存、agent_inbox 表、_prepare_next_llm_call 注入逻辑等额外组件
2. **复用现有基础设施** —— PrivateEventBus 的 asyncio.Queue 本身就是天然的消息队列，BusRouter 路由机制已被充分验证
3. **确定性时序** —— 当前 turn 处理完毕后自动触发，不依赖 LLM 决定"何时查看 inbox"
4. **零额外 tool** —— 减少 LLM 需要理解和调用的工具数量，降低编排复杂度

权衡：LLM 失去了"选择性查看"的能力（原 inbox 模式下 Agent 可以决定先看谁的消息），但实践中这种选择性的价值有限 —— Agent 通常需要处理所有回传结果，逐个触发更可预测。

### 为什么 ping-pong 和深度分开限制

深度（`max_send_depth`）控制的是新建 session 的嵌套层数，防止 A→B→C→D→... 无限嵌套。

Ping-pong（`max_pingpong_turns`）控制的是同一 session 内的多轮对话次数，防止 A 和 B 在同一 session 里无限来回。

两者是正交维度：
- depth=1, pingpong=10: 只能委派一层，但可以和那个 Agent 聊 10 轮
- depth=3, pingpong=1: 可以嵌套三层，但每层只能单轮

### Session 复用的价值

不复用 session 的问题：如果 Agent1 收到 Agent2 的结果后想追问，只能新建 session。新 session 丢失了之前的对话上下文，Agent2 需要从头理解问题。

复用 session 后，Agent2 保持完整的对话历史，追问、修改、补充都发生在同一上下文中，效率更高。

### 为什么不需要 Team 数据结构

"Team" 的本质是"一个 coordinator Agent 知道它可以向哪些其他 Agent 发消息"。这完全可以通过 Agent 自身的 `system_prompt` + `description` 来表达。

### MessageRuntime 与 BusRouter 的关系

MessageRuntime 是 PublicEventBus 的直接订阅者（类似 TitleRuntime），而非通过 BusRouter 管理的 per-session worker。这是因为 MessageRuntime 需要跨 session 协调（监听子 session 的完成事件，发布到父 session），per-session 模式无法满足此需求。

### DB 写入性能

Repository 使用同步 sqlite3。Agent-to-agent 操作的 DB 写入频率较低（每次通信创建/完成各一次），不会成为瓶颈。

### 为什么 sync/async 统一经由 MessageRuntime

早期设计中 sync 模式由 SendMessageTool 直接 spawn session 并订阅 PublicEventBus 等待结果，async 模式才走 MessageRuntime。这有三个严重问题：

1. **ToolWorker 阻塞**: sync 模式下 `_wait_for_completed()` 阻塞 ToolWorker 事件循环，该 session 的其他事件无法处理
2. **per-call bus 订阅泄漏**: 每次 sync 调用创建一个新的 PublicEventBus 订阅（asyncio.Queue），O(N×M) 内存增长，超时取消后队列残留
3. **双路径不一致**: 新建/复用 session 在 Tool 和 Runtime 各有一套逻辑，边界模糊

统一后：
- SendMessageTool 只做校验 + 发布事件，不 spawn session
- MessageRuntime 通过 `_sync_waiters: dict[str, Future]` 映射，sync 模式 `await future` 不阻塞事件循环
- 所有 session 创建/复用/完成/失败逻辑集中在 MessageRuntime，单一职责
