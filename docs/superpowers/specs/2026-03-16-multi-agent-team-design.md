# Multi-Agent Team 架构设计

## 概述

为 AgentOS 新增 Multi-Agent Team 能力，支持 Agent 之间的层级化任务委派和 Team 协作编排。

核心设计：**扩展现有 DelegateTool + 新增 DelegateRuntime**。在现有 `delegate` tool 基础上增加 Team 路由能力，新增 DelegateRuntime 作为全局单例订阅 PublicEventBus，负责 spawn coordinator session 和委派生命周期管理。

**关键简化**：Team 只有一种模式 —— coordinator 模式。Team 委派 = spawn coordinator session + 注入成员信息。coordinator（LLM）自行决定并行/串行/混合编排。DelegateRuntime 不做编排逻辑。

## 与现有代码的关系

当前代码库已有的委派基础设施：

| 组件 | 文件 | 状态 |
|------|------|------|
| `DelegateTool`（name="delegate"） | `agentos/capabilities/tools/delegate_tool.py` | 已实现，支持 Agent→Agent 同步委派 |
| `AgentConfig.can_delegate_to` | `agentos/capabilities/agents/config.py` | 已实现 |
| `AgentRegistry.get_delegatable()` | `agentos/capabilities/agents/registry.py` | 已实现 |
| `agent_worker.py` always_keep `{"delegate"}` | `agentos/kernel/runtime/workers/agent_worker.py:77` | 已实现 |
| 委派事件类型 | `agentos/kernel/events/types.py` | 已定义 4 个 |

本设计**扩展而非替换**现有 DelegateTool，增加 Team 路由和异步模式。

## 设计决策

| 维度 | 决策 | 理由 |
|------|------|------|
| Team 创建 | 静态配置 + 动态组建 | 兼顾预定义模板和运行时灵活性 |
| 通信模式 | 默认同步 + 可选异步 | 同步简单可靠，异步满足并行需求 |
| Session 关系 | 独立 session | 隔离上下文，父子通过 tool 结果通信 |
| 任务分配 | 层级委派（深度限制） | 灵活递归，max_delegation_depth 防止无限嵌套 |
| Team 调度 | 统一 coordinator 模式 | coordinator LLM 自行决定编排方式（并行/串行/混合），DelegateRuntime 不做编排 |
| Tool 设计 | 扩展现有 delegate tool | 复用已有代码，保持 agent_worker 中的 always_keep 兼容 |
| DelegateRuntime | 全局单例，订阅 PublicEventBus | 跨 session 协调，只做 spawn + 生命周期管理，不做编排 |

## 核心概念

### Agent
一个独立的 AI 执行单元，有自己的 config（model、tools、system_prompt）。已有实现。

### Team
一组 Agent 的编排配置，定义 coordinator 和成员列表。coordinator 接收任务后，自行决定如何编排成员（并行、串行、混合均可）。

**命名空间**: Team ID 和 Agent ID 共享同一命名空间，通过 config 加载时的交叉验证确保唯一性。

### Delegation
一次 Agent→Agent 或 Agent→Team 的任务委派，产生独立子 session。跟踪委派状态、深度、结果、委派链。

## 数据模型

### TeamConfig（新增）

```python
@dataclass
class TeamConfig:
    id: str                          # 唯一标识，如 "research-team"
    name: str                        # 显示名
    description: str                 # LLM 可见描述，用于委派决策
    coordinator: str                 # coordinator agent_id，负责接收任务并编排成员
    members: list[str]               # 可编排的 agent_id 列表
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
```

### TeamRegistry（新增）

```python
class TeamRegistry:
    _teams: dict[str, TeamConfig]

    def register(team: TeamConfig) -> None
    def get(team_id: str) -> TeamConfig | None
    def list_all() -> list[TeamConfig]
    def delete(team_id: str) -> bool
    def load_from_config(config_data: dict) -> None  # 从 config.yml teams.* 加载
    def load_from_dir() -> None                       # 从 workspace/teams/*.json 加载

    def validate_no_conflict(self, agent_registry: AgentRegistry) -> list[str]:
        """检查 Team ID 是否与 Agent ID 冲突，返回冲突列表"""
        conflicts = []
        for team_id in self._teams:
            if agent_registry.get(team_id):
                conflicts.append(team_id)
        return conflicts
```

### DelegationRecord（新增）

```python
@dataclass
class DelegationRecord:
    id: str                          # delegation_id (UUID)
    parent_session_id: str
    parent_turn_id: str
    parent_tool_call_id: str         # 关联父 Agent 的 tool_call
    child_session_id: str
    target_type: str                 # "agent" | "team"
    target_id: str                   # agent_id 或 team_id
    status: str                      # "pending" | "running" | "completed" | "failed"
    task: str                        # 委派的任务描述
    result: str | None               # 最终结果
    depth: int                       # 委派深度
    delegation_chain: list[str]      # 委派链，如 ["agent1", "agent2"]，用于循环检测
    created_at: float
    completed_at: float | None = None
```

### config.yml 扩展

```yaml
agent:
  provider: openai
  default_model: gpt-4o-mini
  max_delegation_depth: 3

agents:
  research-agent:
    name: "Research Agent"
    description: "擅长搜索和信息整理"
    model: gpt-4o-mini
    tools: [serper_search, fetch_url]
    can_delegate_to: [writer-agent]

  writer-agent:
    name: "Writer Agent"
    description: "擅长内容创作和文档撰写"
    model: gpt-4o
    tools: [read_file, write_file]

teams:
  research-team:
    name: "Research Team"
    description: "联合搜索和撰写的研究团队"
    coordinator: research-agent
    members: [research-agent, writer-agent]
```

## 架构组件

### 1. DelegateTool 扩展（入口层）

**扩展现有 `DelegateTool`**（`agentos/capabilities/tools/delegate_tool.py`），保持 tool name 为 `"delegate"`，兼容 agent_worker.py 中的 `always_keep = {"delegate"}`。

新增参数：

```python
class DelegateTool(Tool):
    name = "delegate"  # 保持不变
    description = "将任务委派给指定 Agent 或 Team 执行"
    parameters = {
        "type": "object",
        "properties": {
            "target_id": {
                "type": "string",
                "description": "目标 Agent ID 或 Team ID"
            },
            "task": {
                "type": "string",
                "description": "需要执行的任务描述"
            },
            "mode": {
                "type": "string",
                "enum": ["sync", "async"],
                "default": "sync",
                "description": "sync=等待结果返回; async=发送后继续执行"
            },
            "context": {
                "type": "string",
                "description": "可选的上下文信息传递给目标"
            }
        },
        "required": ["target_id", "task"]
    }
```

#### 执行逻辑

```python
async def execute(self, target_id, task, mode="sync", context=None):
    # 1. 路由：查 AgentRegistry → TeamRegistry
    target = self.agent_registry.get(target_id)
    target_type = "agent" if target else None
    if not target:
        target = self.team_registry.get(target_id)
        target_type = "team" if target else None
    if not target:
        return {"error": f"未找到 Agent 或 Team: {target_id}"}

    # 2. 权限检查：复用现有 AgentRegistry.get_delegatable()
    delegatable = self.agent_registry.get_delegatable(current_agent_id)
    delegatable_ids = {a.id for a in delegatable}
    # Team 的权限：检查 team_id 是否在 can_delegate_to 中，或 can_delegate_to 为空
    if target_type == "agent" and target_id not in delegatable_ids:
        return {"error": f"当前 Agent 无权委派给 {target_id}"}

    # 3. 深度检查
    if current_depth >= max_delegation_depth:
        return {"error": f"已达到最大委派深度 {max_delegation_depth}"}

    # 4. 循环检测
    if target_id in current_delegation_chain:
        return {"error": f"检测到循环委派: {' -> '.join(current_delegation_chain)} -> {target_id}"}

    # 5. 对于 Agent 直接委派（sync 模式）：复用现有 DelegateTool 的逻辑
    if target_type == "agent" and mode == "sync":
        return await self._delegate_to_agent_sync(target_id, task, context)

    # 6. 对于 Team 委派或 async 模式：通过 DelegateRuntime 处理
    delegation_id = str(uuid4())
    await self.bus.publish(EventEnvelope(
        type=EventTypes.AGENT_DELEGATE_REQUESTED,
        session_id=self.session_id,
        trace_id=delegation_id,
        payload={
            "delegation_id": delegation_id,
            "target_type": target_type,
            "target_id": target_id,
            "task": task,
            "context": context,
            "mode": mode,
            "depth": current_depth + 1,
            "delegation_chain": current_delegation_chain + [current_agent_id],
            "parent_session_id": self.session_id,
            "parent_turn_id": self.turn_id,
            "parent_tool_call_id": self.tool_call_id,
        }
    ))

    if mode == "sync":
        # 等待 DelegateRuntime 发布 AGENT_DELEGATE_COMPLETED
        # 通过订阅 PublicEventBus 并过滤 delegation_id（同现有 DelegateTool 的监听模式）
        result = await self._wait_for_delegate_completed(delegation_id, timeout=300)
        return {"result": result}
    else:
        return {"delegation_id": delegation_id, "status": "dispatched"}

async def _wait_for_delegate_completed(self, delegation_id, timeout):
    """订阅 PublicEventBus，等待 AGENT_DELEGATE_COMPLETED 事件。
    复用现有 DelegateTool 的监听模式（subscribe + filter by trace_id）。"""
    future = asyncio.get_event_loop().create_future()

    async def listener():
        async for event in self.bus.subscribe():
            if (event.type == EventTypes.AGENT_DELEGATE_COMPLETED
                    and event.trace_id == delegation_id):
                future.set_result(event.payload.get("result", ""))
                return
            elif (event.type == EventTypes.AGENT_DELEGATE_FAILED
                    and event.trace_id == delegation_id):
                future.set_result(f"[委派失败] {event.payload.get('error', '')}")
                return

    task = asyncio.create_task(listener())
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        return "[委派超时]"
```

### 2. DelegateRuntime（编排层）

**全局单例**，直接订阅 PublicEventBus（不是 per-session worker）。职责收窄为：spawn session + 生命周期管理。不做编排逻辑。

```python
class DelegateRuntime:
    """全局单例。订阅 PublicEventBus，处理 Team 委派的 session 创建和生命周期管理。"""

    def __init__(self, bus: PublicEventBus, bus_router: BusRouter, repo, agent_registry, team_registry):
        self._bus = bus
        self._bus_router = bus_router
        self._repo = repo
        self._agent_registry = agent_registry
        self._team_registry = team_registry

        # delegation_id → record（内存索引）
        self._delegations: dict[str, DelegationRecord] = {}
        # child_session_id → delegation_id（反向索引，O(1) 查找）
        self._child_session_index: dict[str, str] = {}

    async def start(self):
        """启动事件循环，订阅 PublicEventBus"""
        self._task = asyncio.create_task(self._event_loop())

    async def stop(self):
        """停止事件循环"""
        self._task.cancel()

    async def _event_loop(self):
        async for event in self._bus.subscribe():
            try:
                if event.type == EventTypes.AGENT_DELEGATE_REQUESTED:
                    await self._handle_delegate_requested(event)
                elif event.type == EventTypes.AGENT_STEP_COMPLETED:
                    # 用 child_session_index 做 O(1) 查找
                    if event.session_id in self._child_session_index:
                        await self._handle_child_completed(event)
            except Exception as e:
                logger.error(f"DelegateRuntime 处理事件出错: {e}")
```

#### Agent 委派流程

```python
async def _handle_delegate_requested(self, event):
    payload = event.payload
    target_type = payload["target_type"]

    if target_type == "agent":
        # 直接 spawn agent session
        await self._spawn_agent_session(payload)
    elif target_type == "team":
        # Team 委派 = spawn coordinator session + 注入成员信息
        team_config = self._team_registry.get(payload["target_id"])
        await self._spawn_coordinator_session(payload, team_config)

async def _spawn_coordinator_session(self, payload, team_config):
    """Team 委派的唯一处理方式：spawn coordinator，注入成员信息，由 coordinator LLM 自行编排"""
    coordinator_id = team_config.coordinator
    enhanced_task = f"""你是 Team "{team_config.name}" 的 Coordinator。

你可以委派的团队成员：
{self._format_team_members(team_config)}

任务：{payload['task']}

请分析任务，使用 delegate 工具将子任务分配给合适的成员。
你可以：
- 并行委派多个成员（使用 mode="async"），然后等待结果
- 串行委派（使用 mode="sync"），将上一步结果传给下一步
- 混合使用以上方式
完成后汇总所有结果回复。"""

    await self._spawn_agent_session({
        **payload,
        "target_id": coordinator_id,
        "task": enhanced_task,
    })
    # coordinator session 完成后，_handle_child_completed 自动处理

async def _spawn_agent_session(self, payload):
    delegation_id = payload["delegation_id"]
    target_id = payload["target_id"]

    # 使用下划线分隔（与现有 DelegateTool 保持一致）
    child_session_id = f"delegate_{uuid.uuid4().hex[:12]}"

    # 持久化
    record = DelegationRecord(
        id=delegation_id,
        parent_session_id=payload["parent_session_id"],
        parent_turn_id=payload.get("parent_turn_id"),
        parent_tool_call_id=payload.get("parent_tool_call_id"),
        child_session_id=child_session_id,
        target_type=payload["target_type"],
        target_id=target_id,
        task=payload["task"],
        depth=payload["depth"],
        delegation_chain=payload.get("delegation_chain", []),
        status="running",
        created_at=time.time(),
    )
    self._delegations[delegation_id] = record
    self._child_session_index[child_session_id] = delegation_id
    await self._repo.save_delegation(record)

    # 创建 session 记录
    await self._repo.create_session(child_session_id, {
        "agent_id": target_id,
        "parent_session_id": payload["parent_session_id"],
        "delegation_id": delegation_id,
        "delegation_depth": payload["depth"],
        "delegation_chain": payload.get("delegation_chain", []) + [target_id],
    })

    # 发布 AGENT_DELEGATE_STARTED
    await self._bus.publish(EventEnvelope(
        type=EventTypes.AGENT_DELEGATE_STARTED,
        session_id=payload["parent_session_id"],
        trace_id=delegation_id,
        payload={"delegation_id": delegation_id, "target_id": target_id, "task": payload["task"]},
    ))

    # 向子 session 注入 USER_INPUT（触发 BusRouter 创建 workers）
    await self._bus.publish(EventEnvelope(
        type=EventTypes.USER_INPUT,
        session_id=child_session_id,
        payload={
            "text": payload["task"],
            "context": payload.get("context"),
            "delegation_depth": payload["depth"],
            "delegation_chain": payload.get("delegation_chain", []) + [target_id],
        },
        source="delegate",
    ))
```

#### 子 Session 完成处理

```python
async def _handle_child_completed(self, event):
    child_session_id = event.session_id
    delegation_id = self._child_session_index.get(child_session_id)
    if not delegation_id:
        return

    record = self._delegations.get(delegation_id)
    if not record:
        return

    # 更新状态
    record.status = "completed"
    record.result = event.payload.get("content", "")
    record.completed_at = time.time()
    await self._repo.update_delegation(record)

    # 清理索引
    del self._child_session_index[child_session_id]

    # 发布 AGENT_DELEGATE_COMPLETED 到父 session
    await self._bus.publish(EventEnvelope(
        type=EventTypes.AGENT_DELEGATE_COMPLETED,
        session_id=record.parent_session_id,
        trace_id=record.id,
        payload={
            "delegation_id": record.id,
            "agent_id": record.target_id,
            "result": record.result,
            "child_session_id": child_session_id,
        },
    ))
```

### 3. 异步回传处理

#### 消息 Inbox 机制

AgentSessionWorker 新增 delegation inbox 用于缓存异步回传消息：

```python
class AgentSessionWorker(SessionWorker):
    _delegation_inbox: list[dict] = []
    _active_async_delegations: set[str] = set()

    async def _handle(self, event):
        # ... 现有逻辑 ...

        if event.type == EventTypes.AGENT_DELEGATE_ANNOUNCE:
            self._delegation_inbox.append({
                "type": "announce",
                "delegation_id": event.trace_id,
                "from_agent": event.payload["agent_id"],
                "content": event.payload["content"],
            })

        elif event.type == EventTypes.AGENT_DELEGATE_COMPLETED:
            if event.trace_id in self._active_async_delegations:
                self._delegation_inbox.append({
                    "type": "completed",
                    "delegation_id": event.trace_id,
                    "from_agent": event.payload["agent_id"],
                    "result": event.payload["result"],
                })
                self._active_async_delegations.discard(event.trace_id)
```

#### 处理场景

| 父 Agent 状态 | 子 Agent 消息到达时 | 处理方式 |
|---|---|---|
| LLM 调用中 / 处理 tool 中 | announce / completed | 存入 inbox，下轮 LLM 调用前注入 |
| Idle（已完成 turn） | completed | 作为新 USER_INPUT 触发新 turn |

#### Inbox 注入

每轮 LLM 调用之前，如果 inbox 非空，将内容注入到 LLM 消息中。使用 `role: "system"` 避免污染对话历史：

```python
async def _prepare_next_llm_call(self, turn_state):
    if self._delegation_inbox:
        inbox_text = self._format_inbox()
        self._delegation_inbox.clear()
        # 使用 system role，不会被持久化为用户消息
        turn_state.messages.append({
            "role": "system",
            "content": f"[Delegation Updates]\n{inbox_text}"
        })
```

#### Announce 机制

子 Agent 通过 `report_progress` tool 发布进度（可选，v1 暂不实现，预留事件类型）。

### 4. ContextBuilder 扩展

#### 委派目标注入

```python
def _build_delegation_context(self, agent_config: AgentConfig) -> str:
    targets = []

    # 可委派的 Agent（复用 AgentRegistry.get_delegatable）
    delegatable_agents = self.agent_registry.get_delegatable(agent_config.id)
    for agent in delegatable_agents:
        targets.append(f"- Agent: {agent.id} — {agent.description}")

    # 可委派的 Team
    if self.team_registry:
        for team in self.team_registry.list_all():
            if team.enabled:
                members = ", ".join(team.members)
                targets.append(
                    f"- Team: {team.id} — {team.description} "
                    f"(coordinator: {team.coordinator}, 成员: {members})"
                )

    if not targets:
        return ""

    return f"""
## 可委派目标

你可以使用 delegate 工具将子任务委派给以下 Agent 或 Team：

{chr(10).join(targets)}

sync 模式等待结果返回，async 模式可并行发起多个委派。
"""
```

#### 子 Session 上下文

被委派的 Agent 在 system_prompt 中注入委派信息：

```python
delegation_note = f"""
你正在作为被委派的 Agent 执行任务。
- 委派深度: {depth}/{max_depth}
- 请专注完成指定任务，完成后直接回复最终结果。
"""
```

### 5. 前端事件映射

WebSocketChannel 新增委派事件到前端消息的映射：

```python
AGENT_DELEGATE_STARTED → {"type": "delegation_started", "delegation_id": ..., "target_id": ..., "task": ...}
AGENT_DELEGATE_ANNOUNCE → {"type": "delegation_progress", "delegation_id": ..., "content": ...}
AGENT_DELEGATE_COMPLETED → {"type": "delegation_completed", "delegation_id": ..., "result": ...}
AGENT_DELEGATE_FAILED → {"type": "delegation_failed", "delegation_id": ..., "error": ...}
```

### 6. DB 持久化

Repository 新增 `delegations` 表：

```sql
CREATE TABLE IF NOT EXISTS delegations (
    id TEXT PRIMARY KEY,
    parent_session_id TEXT NOT NULL,
    parent_turn_id TEXT,
    parent_tool_call_id TEXT,
    child_session_id TEXT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    task TEXT,
    result TEXT,
    depth INTEGER DEFAULT 0,
    delegation_chain TEXT,          -- JSON 数组，如 '["agent1", "agent2"]'
    created_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (child_session_id) REFERENCES sessions(session_id)
);
```

## 事件类型

复用现有 + 新增。遵循现有命名约定（`agent.delegate_xxx`，用下划线分隔单词）：

```python
# 已存在于 types.py
AGENT_DELEGATE_REQUESTED = "agent.delegate_requested"
AGENT_DELEGATE_STARTED = "agent.delegate_started"
AGENT_DELEGATE_COMPLETED = "agent.delegate_completed"
AGENT_DELEGATE_FAILED = "agent.delegate_failed"

# 新增
AGENT_DELEGATE_ANNOUNCE = "agent.delegate_announce"      # 异步中间状态（v2 实现）
```

## 完整事件流

### 同步委派（Agent → Agent）

```
Agent1 LLM → tool_call: delegate(target_id="agent2", task="...", mode="sync")
  → ToolWorker: TOOL_CALL_REQUESTED
  → DelegateTool.execute()
    → 路由: AgentRegistry.get("agent2") → 找到 → target_type="agent"
    → mode="sync" + target_type="agent" → 走现有 DelegateTool 同步路径
    → 创建子 session "delegate_xxxx"
    → 发布 USER_INPUT 到子 session
    → BusRouter 创建 PrivateEventBus + Workers
    → Agent2 执行: USER_INPUT → LLM → (tools) → AGENT_STEP_COMPLETED
    → DelegateTool 监听到 AGENT_STEP_COMPLETED
    → 返回 tool_result
  → ToolWorker: TOOL_CALL_RESULT
→ Agent1 继续 LLM 对话
```

### 同步委派（Agent → Team）

```
Agent1 LLM → tool_call: delegate(target_id="research-team", task="...", mode="sync")
  → DelegateTool.execute()
    → 路由: AgentRegistry.get → 未找到 → TeamRegistry.get → 找到 → target_type="team"
    → 发布 AGENT_DELEGATE_REQUESTED
    → DelegateRuntime 接收
      → 识别为 Team → spawn coordinator session
      → 注入增强任务（含团队成员信息）
      → Coordinator LLM 分析任务，自行决定编排方式:
        → delegate(target="member1", task="...", mode="async")  // 并行
        → delegate(target="member2", task="...", mode="async")  // 并行
        → 等待结果，汇总
        → AGENT_STEP_COMPLETED
      → DelegateRuntime → AGENT_DELEGATE_COMPLETED
    → DelegateTool._wait_for_delegate_completed() 收到结果
    → 返回 tool_result
```

### 异步委派

```
Agent1 LLM → tool_call: delegate(target_id="agent2", task="...", mode="async")
  → DelegateTool.execute()
    → 发布 AGENT_DELEGATE_REQUESTED
    → 立即返回 {"delegation_id": "xxx", "status": "dispatched"}
  → Agent1 继续执行其他操作...

  (并行) DelegateRuntime 处理 + Agent2 执行...
    → Agent2 完成: AGENT_STEP_COMPLETED
    → DelegateRuntime → AGENT_DELEGATE_COMPLETED

  Agent1 下一轮 LLM 调用前:
    → 检查 delegation_inbox
    → 注入 [Delegation Updates] (role: system)
    → Agent1 LLM 自主决定处理方式
```

### Team 委派（Coordinator 模式）

```
Agent1 → delegate(target_id="research-team") → DelegateRuntime
  → spawn Coordinator Agent session
  → Coordinator 接收增强任务（含团队成员信息）
  → Coordinator LLM 自行决定编排方式:
    → 并行: delegate(target="member1", mode="async") + delegate(target="member2", mode="async")
    → 串行: delegate(target="member1", mode="sync") → 拿结果 → delegate(target="member2", mode="sync")
    → 混合: 先并行搜索，再串行分析
  → Coordinator 汇总结果
  → Coordinator AGENT_STEP_COMPLETED
  → DelegateRuntime → AGENT_DELEGATE_COMPLETED → Agent1
```

## 安全约束

1. **深度限制**: `max_delegation_depth`（默认 3），每次委派 depth+1，超限拒绝
2. **权限控制**: 复用 `AgentRegistry.get_delegatable()`，`can_delegate_to` 空列表 = 可委派所有
3. **超时机制**: 同步委派超时默认 300s
4. **循环检测**: `delegation_chain` 记录完整委派路径，spawn 前检查 target_id 是否已在链中
5. **取消传播**: 父 session 取消（`USER_TURN_CANCEL_REQUESTED`）时，DelegateRuntime 向子 session 传播取消事件（v2 实现）
6. **namespace 唯一性**: config 加载时 TeamRegistry.validate_no_conflict() 检查 Team ID 与 Agent ID 不冲突

## 实现分期

### v1（MVP）
- TeamConfig / TeamRegistry（coordinator + members）
- DelegateTool 扩展（Team 路由 + sync 模式）
- DelegateRuntime（全局单例，spawn coordinator session）
- DelegationRecord + DB 持久化
- ContextBuilder 委派目标注入
- 循环检测 + namespace 验证

### v2
- Async 模式 + delegation_inbox
- 前端事件映射
- 取消传播
- report_progress tool (announce)

### v3
- 动态 Team 组建（Agent 运行时创建 Team）
- 子 Agent 监控与干预（kill/steer）
- 前端委派可视化（树形执行视图）
- Token 预算管理

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `agentos/capabilities/teams/__init__.py` | 模块初始化 |
| `agentos/capabilities/teams/config.py` | TeamConfig 数据类 |
| `agentos/capabilities/teams/registry.py` | TeamRegistry |
| `agentos/kernel/runtime/delegate_runtime.py` | DelegateRuntime（全局单例） |

### 修改文件

| 文件 | 变更 |
|------|------|
| `agentos/kernel/events/types.py` | 新增 AGENT_DELEGATE_ANNOUNCE（其余已存在） |
| `agentos/capabilities/tools/delegate_tool.py` | 扩展：Team 路由 + mode 参数 + 循环检测 |
| `agentos/kernel/runtime/workers/agent_worker.py` | v2: 新增 delegation_inbox |
| `agentos/kernel/runtime/context_builder.py` | 注入 Team 委派目标 + 子 session 委派信息 |
| `agentos/adapters/storage/repository.py` | 新增 delegations 表 + CRUD |
| `agentos/adapters/channels/websocket_channel.py` | v2: 映射委派事件 |
| `agentos/app/gateway/main.py` | 初始化 TeamRegistry + DelegateRuntime |

## 测试策略

1. **单元测试**: TeamRegistry CRUD、namespace 冲突检测、循环检测、深度检查
2. **集成测试**: Agent→Agent 同步委派事件链、Agent→Team coordinator 委派事件链
3. **E2E 测试**: 配置多 Agent + Team，用户输入触发委派，验证最终响应

## 设计考量

### 为什么统一为 Coordinator 模式

原设计有三种策略（leader/parallel/pipeline）。分析后发现：
- Parallel = coordinator 使用 `delegate(mode="async")` 并行委派所有成员
- Pipeline = coordinator 使用 `delegate(mode="sync")` 串行委派
- 混合 = coordinator 自由组合 sync/async

**LLM 编排能做的事代码编排全都能做，而且更灵活。** 代码编排唯一的"优势"是确定性，但这可以通过 coordinator 的 system_prompt 约束（"你必须将任务并行分发给所有成员"）。

统一后的好处：
1. DelegateRuntime 大幅简化 —— 去掉 `_strategy_parallel`、`_strategy_pipeline`、`_pending_sub_completions`、策略 Task 管理
2. TeamConfig 简化 —— 去掉 `strategy` 字段
3. 灵活性更高 —— coordinator 可根据任务动态选择编排方式
4. 无死锁风险 —— 不再有策略方法阻塞事件循环的问题

### Coordinator 的深度预算

当使用 Team 委派时，coordinator 本身消耗 1 层深度。如果原始委派已在 depth=2 且 max_depth=3，coordinator 只能再委派 1 层给成员。用户配置 Team 时需考虑深度预算。

### DelegateRuntime 与 BusRouter 的关系

DelegateRuntime 是 PublicEventBus 的直接订阅者（类似 TitleRuntime），而非通过 BusRouter 管理的 per-session worker。这是因为 DelegateRuntime 需要跨 session 协调（监听子 session 的完成事件，发布到父 session），per-session 模式无法满足此需求。

### DB 写入性能

Repository 使用同步 sqlite3。委派操作的 DB 写入频率较低（每次委派创建/完成各一次），不会成为瓶颈。
