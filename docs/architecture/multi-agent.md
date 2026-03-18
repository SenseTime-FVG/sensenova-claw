# Multi-Agent 通信架构设计

## 概述

为 AgentOS 增加 Multi-Agent 协作能力，支持一个 Agent 通过 `send_message` 向另一个 Agent 发送任务或追问，并同时支持：

- 新建子 session 执行独立任务
- 复用既有子 session 继续对话
- `sync` 同步等待结果
- `async` 异步回传结果并触发父 session 后续处理

本文档采用**收敛后的最小方案**：

- 使用 `SendMessageTool` 作为统一 Agent-to-Agent 通信入口
- 不再引入一个“大而全”的 `MessageRuntime`
- 保留一个很薄的 `AgentMessageCoordinator`
- 尽量复用现有 `AgentRuntime / BusRouter / AgentSessionWorker / Repository`

核心判断：跨 session 关联和 sync 等待映射确实需要一个全局协调点，但 `spawn session`、持久化、异步结果消费不应该继续堆在同一个新模块里。

## 设计目标

- 让 LLM 只感知一个统一工具：`send_message`
- 复用现有事件驱动链路，不引入 inbox 拉取模型
- 保持 `BusRouter` 只做路由和 session 生命周期管理
- 保持 `AgentRuntime` 负责 worker 生命周期和 session 启动
- 保持 `Repository` 只负责持久化
- 仅将“跨 session 关联状态”放进一个薄协调器中

## 与现有代码的映射

当前多 Agent 方案收敛后的基础设施命名如下：

| 组件 | 文件 | 当前职责 | 在本设计中的角色 |
|------|------|------|------|
| `SendMessageTool` | `agentos/capabilities/tools/send_message_tool.py` | Agent-to-Agent 消息发送入口 | 负责参数校验 + 发布请求事件 |
| `AgentConfig.can_send_message_to` | `agentos/capabilities/agents/config.py` | 可发送目标白名单 | 用于限制 send_message 目标范围 |
| `AgentConfig.max_send_depth` | `agentos/capabilities/agents/config.py` | 最大消息传递深度 | 用于限制新建子 session 深度 |
| `AgentRegistry.get_sendable()` | `agentos/capabilities/agents/registry.py` | 获取可发送目标 | 供 prompt 注入和工具校验使用 |
| `BusRouter` | `agentos/kernel/events/router.py` | Public/Private Bus 路由 + GC | 保持不变，不承载消息业务状态 |
| `AgentRuntime` | `agentos/kernel/runtime/agent_runtime.py` | 创建/销毁 `AgentSessionWorker` | 增加轻量 helper，统一启动目标 Agent session |
| `AgentSessionWorker` | `agentos/kernel/runtime/workers/agent_worker.py` | 处理 session 内事件链 | 增加异步回传事件消费分支 |
| `Repository` | `agentos/adapters/storage/repository.py` | session/turn/message/event 持久化 | 新增 `agent_messages` 记录 |

## 为什么不保留重型 MessageRuntime

旧提案中的 `MessageRuntime` 同时承担了：

- 订阅 `PublicEventBus`
- 新建/复用 session
- 维护 `record_id -> Future`
- 维护 `child_session_id -> record_id`
- 持久化 `MessageRecord`
- 处理完成/失败事件
- 清理索引和超时

这会把“业务编排、状态管理、持久化协调、session 启动”绑成一个重模块，后续一旦加上取消传播、重试、超时策略、回放，复杂度会继续膨胀。

因此本设计改为：

- `SendMessageTool` 负责入口校验
- `AgentMessageCoordinator` 负责跨 session 关联和 sync waiter
- `AgentRuntime` 负责启动目标 Agent session
- `Repository` 负责持久化消息记录
- `AgentSessionWorker` 负责消费异步回传

## 总体架构

```text
Agent A
  -> SendMessageTool.execute()
  -> 发布 AGENT_MESSAGE_REQUESTED

AgentMessageCoordinator
  -> 创建/更新 MessageRecord
  -> 若为 sync: 注册 waiter
  -> 调用 AgentRuntime.spawn_agent_session(...)
  -> 监听子 session 的 AGENT_STEP_COMPLETED / ERROR_RAISED
  -> sync: resolve waiter
  -> async: 发布 AGENT_MESSAGE_COMPLETED / AGENT_MESSAGE_FAILED 到父 session

BusRouter
  -> 按 session_id 路由到父 session 的 PrivateEventBus

AgentSessionWorker(父 session)
  -> 消费 AGENT_MESSAGE_COMPLETED / FAILED
  -> 合成新的 USER_INPUT 或内部 follow-up 事件
  -> 进入下一轮 LLM 编排
```

## 核心组件

### 1. SendMessageTool

`SendMessageTool` 是唯一暴露给 LLM 的 Agent-to-Agent 工具。

职责：

- 验证目标 Agent 是否存在
- 验证 `can_send_message_to` 白名单
- 验证深度限制
- 验证 session 复用是否合法
- 检查简单循环
- 发布 `AGENT_MESSAGE_REQUESTED`
- sync 模式下等待协调器返回结果

不做：

- 不直接创建子 session
- 不直接订阅 `PublicEventBus`
- 不直接持有跨 session 完成监听逻辑

```python
class SendMessageTool(Tool):
    name = "send_message"
    description = "向指定 Agent 发送消息，可新建子会话，也可继续已有子会话。"
    parameters = {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "目标 Agent 的 ID"
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容"
            },
            "session_id": {
                "type": "string",
                "description": "可选。已有子会话 ID，用于继续对话"
            },
            "mode": {
                "type": "string",
                "enum": ["sync", "async"],
                "default": "sync",
                "description": "sync 表示等待结果，async 表示稍后回传"
            }
        },
        "required": ["target_agent", "message"]
    }

    async def execute(
        self,
        target_agent: str,
        message: str,
        session_id: str | None = None,
        mode: str = "sync",
    ) -> str:
        # 1. 校验 target 是否存在
        # 2. 校验 can_send_message_to / max_send_depth
        # 3. 若复用 session，校验该 session 是否属于目标 Agent
        # 4. 发布 AGENT_MESSAGE_REQUESTED
        # 5. sync 模式下向协调器注册 waiter 并等待结果
        pass
```

### 2. AgentMessageCoordinator

这是对旧 `MessageRuntime` 的收敛替代。

它是一个**很薄的全局协调器**，直接订阅 `PublicEventBus`，但只负责跨 session 无法自然落在现有模块里的那部分能力。

职责：

- 接收 `AGENT_MESSAGE_REQUESTED`
- 建立 `record_id -> waiter`
- 建立 `child_session_id -> record_id`
- 关联子 session 完成/失败事件
- 将 sync 结果回填给 `SendMessageTool`
- 将 async 结果转发回父 session

不做：

- 不自己写 `create_session` 细节
- 不负责 per-session worker 生命周期
- 不负责消息内容组装
- 不承载路由逻辑

```python
class AgentMessageCoordinator:
    def __init__(
        self,
        bus: PublicEventBus,
        repo: Repository,
        agent_runtime: AgentRuntime,
    ):
        self._bus = bus
        self._repo = repo
        self._agent_runtime = agent_runtime
        self._sync_waiters: dict[str, Future] = {}
        self._child_session_index: dict[str, str] = {}

    async def start(self):
        # 订阅 PublicEventBus
        pass

    async def stop(self):
        # 取消所有 waiter
        pass

    def register_sync_waiter(self, record_id: str) -> Future:
        # SendMessageTool 调用
        pass

    def get_record_by_session(self, session_id: str) -> MessageRecord | None:
        # 供 SendMessageTool 做 ping-pong 校验
        pass

    async def _handle_message_requested(self, event: EventEnvelope):
        # 1. 构造 MessageRecord
        # 2. 持久化到 Repository
        # 3. 调用 AgentRuntime.spawn_agent_session(...) 或向已有 session 注入 USER_INPUT
        pass

    async def _handle_child_completed(self, event: EventEnvelope):
        # 1. 更新 MessageRecord
        # 2. sync: resolve waiter
        # 3. async: 发布 AGENT_MESSAGE_COMPLETED 到父 session
        pass

    async def _handle_child_failed(self, event: EventEnvelope):
        # 与 completed 类似，只是状态改为 failed
        pass

    def cleanup_session(self, session_id: str):
        # 由 BusRouter.on_destroy 回调触发
        pass
```

### 3. AgentRuntime

`AgentRuntime` 已经负责 worker 生命周期，因此新建子 session 的逻辑更适合通过它暴露一个轻量 helper，而不是再放进新的 runtime。

建议新增的方法：

```python
class AgentRuntime:
    async def spawn_agent_session(
        self,
        agent_id: str,
        session_id: str,
        user_input: str,
        parent_session_id: str | None = None,
        meta: dict | None = None,
    ) -> None:
        # 1. 写入 repo.create_session(...)
        # 2. 补充 agent_id / parent_session_id / record_id 等 meta
        # 3. 发布 USER_INPUT
        # 4. 其余仍交给 BusRouter + AgentSessionWorker
        pass

    async def send_user_input(
        self,
        session_id: str,
        user_input: str,
        extra_payload: dict | None = None,
    ) -> None:
        # 向已有 session 注入新的 USER_INPUT
        pass
```

这样做的好处：

- 启动 session 的入口统一
- 旧工具中的重复逻辑可以自然下沉
- 未来不论是 `send_message`、cron、外部 webhook 还是系统任务，都可以复用同一入口

### 4. AgentSessionWorker

异步回传不需要 inbox 拉取模型，继续复用 `PrivateEventBus` 的 FIFO 队列能力。

只需要在 `AgentSessionWorker` 中新增两个事件分支：

- `AGENT_MESSAGE_COMPLETED`
- `AGENT_MESSAGE_FAILED`

处理方式：

- 将子 Agent 返回结果整理成一段 follow-up 输入
- 触发父 session 的新一轮对话
- 或者在失败时生成错误提示，交给当前 Agent 决定后续动作

```python
class AgentSessionWorker(SessionWorker):
    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == USER_INPUT:
            await self._handle_user_input(event)
        elif event.type == AGENT_MESSAGE_COMPLETED:
            await self._handle_agent_message_completed(event)
        elif event.type == AGENT_MESSAGE_FAILED:
            await self._handle_agent_message_failed(event)
        elif event.type == LLM_CALL_RESULT:
            await self._handle_llm_result(event)
        elif event.type == LLM_CALL_COMPLETED:
            await self._handle_llm_completed(event)
        elif event.type == TOOL_CALL_RESULT:
            await self._handle_tool_result(event)

    async def _handle_agent_message_completed(self, event: EventEnvelope) -> None:
        # 将异步结果合成为 follow-up 输入，例如：
        # 「来自 writer-agent 的异步结果：...」
        # 然后复用现有 _handle_user_input 流程
        pass

    async def _handle_agent_message_failed(self, event: EventEnvelope) -> None:
        # 将失败信息注入后续上下文，由父 Agent 决定重试或改道
        pass
```

### 5. Repository

跨 session 关联需要持久化，避免服务重启后无法恢复最基本的追踪信息。

建议新增 `agent_messages` 表，并保持 Repository 职责纯粹：

```python
class MessageRecord:
    id: str
    parent_session_id: str
    parent_turn_id: str | None
    parent_tool_call_id: str | None
    child_session_id: str
    target_id: str
    status: str                  # "pending" | "running" | "completed" | "failed"
    mode: str                    # "sync" | "async"
    message: str
    result: str | None
    error: str | None
    depth: int
    pingpong_count: int
    created_at: float
    completed_at: float | None


class Repository:
    async def save_message_record(self, record: MessageRecord):
        pass

    async def update_message_record(self, record: MessageRecord):
        pass

    async def get_message_record(self, record_id: str) -> MessageRecord | None:
        pass

    async def get_message_record_by_child_session(
        self,
        child_session_id: str,
    ) -> MessageRecord | None:
        pass
```

## 配置策略

文档中统一使用 `send_message` 命名的配置字段：

```yaml
agents:
  research-agent:
    can_send_message_to: [writer-agent, reviewer-agent]
    max_send_depth: 3
```

解释方式：

- `can_send_message_to` 表示“允许 send_message 的目标范围”
- `max_send_depth` 表示“允许新建子 session 的最大深度”

这样做可以减少以下改动：

- 配置加载器
- Agent CRUD API
- 前端 Agent 配置页面
- 现有测试夹具

## 事件流

### 同步模式

```text
Agent A
  -> SendMessageTool.execute()
  -> 发布 AGENT_MESSAGE_REQUESTED(record_id)

AgentMessageCoordinator
  -> 保存 MessageRecord
  -> register waiter(record_id)
  -> AgentRuntime.spawn_agent_session(...)

子 session
  -> USER_INPUT
  -> ... 正常 agent/llm/tool 流程 ...
  -> AGENT_STEP_COMPLETED

AgentMessageCoordinator
  -> 根据 child_session_id 找到 record_id
  -> 更新 MessageRecord = completed
  -> resolve waiter

SendMessageTool
  -> 返回子 Agent 结果
```

### 异步模式

```text
Agent A
  -> SendMessageTool.execute()
  -> 发布 AGENT_MESSAGE_REQUESTED
  -> 立即返回“任务已发送”

AgentMessageCoordinator
  -> 保存 MessageRecord
  -> AgentRuntime.spawn_agent_session(...)

子 session 完成
  -> AGENT_STEP_COMPLETED

AgentMessageCoordinator
  -> 更新 MessageRecord
  -> 发布 AGENT_MESSAGE_COMPLETED(session_id = 父 session)

BusRouter
  -> 路由到父 session 的 PrivateEventBus

AgentSessionWorker(父)
  -> 消费 AGENT_MESSAGE_COMPLETED
  -> 触发新一轮 follow-up
```

### Ping-Pong 复用

当调用方传入 `session_id` 时：

- `SendMessageTool` 校验该 session 是否属于目标 Agent
- `AgentMessageCoordinator` 新建一条新的 `MessageRecord`
- `child_session_id` 复用原 session
- `AgentRuntime.send_user_input(...)` 向既有 session 注入消息

注意：

- 复用 session 不增加 send depth
- 但会增加 `pingpong_count`
- 若未来需要更严格控制，可在 `MessageRecord` 或 session meta 中追加计数

## 为什么不把这些逻辑拆进 BusRouter

不合适，原因很直接：

- `BusRouter` 是基础设施层，当前职责非常清晰
- 若把 `record_id -> waiter`、消息完成映射、失败重写放进去，会把业务状态带入路由层
- 一旦进入 `BusRouter`，后续所有 Agent-to-Agent 特化逻辑都会自然向它堆积

因此 `BusRouter` 只保留：

- `register_worker_factory`
- `on_destroy`
- `touch`
- Public/Private Bus 路由
- GC 清理

## 为什么也不建议全部塞进 AgentRuntime

`AgentRuntime` 适合拥有“如何启动一个 session”的能力，但不适合承接全部跨 session 状态。

因为它的核心边界仍然是：

- 持有共享资源
- 管理 `AgentSessionWorker`
- 响应 `BusRouter` 的 worker 生命周期回调

若再塞入 waiter 映射、消息结果关联、父子 session 状态机，它也会逐步变成新的重模块。

最稳妥的边界是：

- `AgentRuntime` 管 session 启动
- `AgentMessageCoordinator` 管跨 session 关联

## 实施顺序

### Phase 1

- 使用 `SendMessageTool` 作为统一入口
- 统一配置字段命名为 `can_send_message_to` / `max_send_depth`
- 新增 `AGENT_MESSAGE_REQUESTED / COMPLETED / FAILED`
- 引入薄 `AgentMessageCoordinator`
- 为 `AgentRuntime` 增加 `spawn_agent_session(...)`
- 打通 sync 模式

### Phase 2

- 增加 async 模式
- 在 `AgentSessionWorker` 中处理异步回传事件
- 增加 `agent_messages` 持久化
- 处理 session 复用和 `pingpong_count`

### Phase 3

- 增加取消传播
- 增加超时和重试策略
- 增加更完整的可观测性和链路追踪

## 测试建议

- `SendMessageTool` 单测
  - target 不存在
  - 白名单拒绝
  - 深度超限
  - 复用 session 与 target 不匹配

- `AgentMessageCoordinator` 单测
  - requested -> spawn
  - child completed -> resolve waiter
  - child failed -> 发布失败事件
  - cleanup_session 清理索引

- 进程内集成测试
  - sync 全链路
  - async 全链路
  - ping-pong 复用
  - BusRouter GC 后协调器索引清理

## 最终结论

Multi-Agent 这里仍然需要一个全局对象，但它不应该是重型 `MessageRuntime`。

更合适的落点是：

- 用 `SendMessageTool` 作为唯一入口
- 用 `AgentMessageCoordinator` 承担最少量的跨 session 关联职责
- 把 session 启动放回 `AgentRuntime`
- 把持久化放回 `Repository`
- 把异步结果消费放回 `AgentSessionWorker`

这样既能支持 Multi-Agent 的核心能力，也不会破坏当前代码库已经比较清晰的模块边界。
