# 多 Agent 协作

Sensenova-Claw 当前的多 Agent 协作入口已经统一为 `send_message`，不再使用旧的 `delegate` / `DelegateTool` 路径。

## 核心概念

- **AgentConfig**：定义单个 Agent 的模型、工具、系统提示词和可通信范围
- **AgentRegistry**：管理 Agent 配置的加载、查询、持久化
- **SendMessageTool**：LLM 可直接调用的 Agent-to-Agent 通信工具
- **AgentMessageCoordinator**：跨 session 关联、超时、重试、取消传播的薄协调器

## AgentConfig

位于 `sensenova_claw/capabilities/agents/config.py`。

```python
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    id: str
    name: str
    description: str = ""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int | None = None

    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    can_send_message_to: list[str] = field(default_factory=list)
    max_send_depth: int = 3
    max_pingpong_turns: int = 10
```

兼容性说明：
- 代码里仍兼容读取 `can_delegate_to` / `max_delegation_depth`
- 新文档和新实现都应优先使用 `can_send_message_to` / `max_send_depth`

## AgentRegistry

位于 `sensenova_claw/capabilities/agents/registry.py`。

```python
class AgentRegistry:
    def register(self, agent: AgentConfig) -> None:
        # 注册或更新 Agent 配置
        pass

    def get(self, agent_id: str) -> AgentConfig | None:
        # 按 ID 获取 Agent
        pass

    def list_all(self) -> list[AgentConfig]:
        # 返回所有已启用 Agent
        pass

    def get_sendable(self, from_agent_id: str) -> list[AgentConfig]:
        # 返回当前 Agent 可发送消息的目标 Agent 列表
        pass
```

`get_sendable()` 的规则：
- 若 `can_send_message_to` 为空，则允许向所有其他已启用 Agent 发送消息
- 若配置了白名单，则只允许向白名单中的 Agent 发送消息

## send_message 工具

位于 `sensenova_claw/capabilities/tools/send_message_tool.py`。

```python
class SendMessageTool(Tool):
    name = "send_message"

    async def execute(
        self,
        target_agent: str,
        message: str,
        session_id: str | None = None,
        mode: str = "sync",
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        # 1. 校验目标 Agent 是否存在
        # 2. 校验 can_send_message_to / max_send_depth
        # 3. 若复用 session，校验 session_id 与 target_agent 是否匹配
        # 4. 发布 agent.message_requested
        # 5. sync 模式等待结果，async 模式立即返回
        pass
```

支持的能力：
- 新建子 session 执行任务
- 复用已有子 session 继续追问
- `sync` 同步等待
- `async` 异步回传
- 总超时控制
- 失败自动重试
- 取消传播

## 运行时组件

### AgentRuntime

负责启动目标 Agent session，并向指定 session 注入新的 `user.input`。

```python
class AgentRuntime:
    async def spawn_agent_session(
        self,
        agent_id: str,
        session_id: str,
        user_input: str,
        parent_session_id: str | None = None,
        meta: dict | None = None,
        trace_id: str | None = None,
    ) -> str:
        # 创建 session 并注入首条输入，返回 turn_id
        pass

    async def send_user_input(
        self,
        session_id: str,
        user_input: str,
        extra_payload: dict | None = None,
        trace_id: str | None = None,
    ) -> str:
        # 向已有 session 注入一条新的 user.input，返回 turn_id
        pass
```

### AgentMessageCoordinator

负责跨 session 的最小协调能力。

```python
class AgentMessageCoordinator:
    async def start(self) -> None:
        # 订阅 PublicEventBus
        pass

    async def cancel_message(self, record_id: str, reason: str) -> bool:
        # 取消 send_message 链路，并向子 session 传播取消事件
        pass

    async def _handle_message_requested(self, event: EventEnvelope) -> None:
        # 创建 MessageRecord
        # 启动或复用子 session
        # 注册超时 watch
        pass

    async def _handle_child_failed(self, event: EventEnvelope) -> None:
        # 根据 max_retries 决定重试或失败
        pass
```

它负责：
- `record_id -> waiter` 映射
- `child_session_id -> record_id` 映射
- `agent_messages` 持久化
- 总超时 watchdog
- 自动重试调度
- 父子 session 取消传播

它不负责：
- LLM 编排
- 工具执行
- Bus 路由
- session Worker 生命周期

### AgentSessionWorker

父 session 会消费：
- `agent.message_completed`
- `agent.message_failed`

它会把异步结果转成新的 `user.input`，继续当前任务。

子 session 会消费：
- `user.turn_cancel_requested`

当父链路取消时，子 session 当前 turn 会被标记为 `cancelled`，后续晚到的 `llm/tool` 结果会被忽略。

## 典型流程

### 同步模式

```text
Agent A
  -> send_message(target_agent="helper", message="请分析这段日志")
  -> 发布 agent.message_requested

AgentMessageCoordinator
  -> 保存 agent_messages 记录
  -> AgentRuntime.spawn_agent_session(...)

子 session
  -> user.input
  -> llm / tool / agent 正常执行
  -> agent.step_completed

AgentMessageCoordinator
  -> 更新记录为 completed
  -> 唤醒 sync waiter

SendMessageTool
  -> 返回目标 Agent 的最终结果
```

### 异步模式

```text
Agent A
  -> send_message(..., mode="async")
  -> 立即返回“结果会自动回传”

子 session 完成
  -> agent.step_completed

AgentMessageCoordinator
  -> 发布 agent.message_completed 到父 session

父 AgentSessionWorker
  -> 将结果整理成新的 user.input
  -> 进入下一轮处理
```

### 取消与重试

```text
父 session 收到 user.turn_cancel_requested
  -> AgentMessageCoordinator 查找该父 session 下所有活动中的 agent_messages
  -> 向子 session 发布 user.turn_cancel_requested
  -> 子 AgentSessionWorker 标记 turn cancelled

子 session 执行失败
  -> 若 attempt_count < max_attempts，则按 backoff 重试
  -> 否则发布 agent.message_failed
```

## 配置示例

```yaml
agents:
  orchestrator:
    name: Orchestrator
    can_send_message_to: [researcher, writer]
    max_send_depth: 3

  researcher:
    name: Researcher
    tools: [serper_search, fetch_url, read_file]

delegation:
  enabled: true
  default_timeout: 300
  retry:
    max_retries: 0
    backoff_seconds: [0, 1, 3]
```

说明：
- `delegation.*` 这组配置名目前仍保留，是运行时兼容字段
- 工具和文档语义已经统一到 `send_message`
