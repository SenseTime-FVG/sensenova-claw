# PRD: AgentOS v1.0 — 多 Agent 与 Workflow 编排系统

> 版本: v1.0
> 日期: 2026-03-12
> 项目: AgentOS
> 前置: update_v0.5（双总线架构）, update_v0.8（Cron + Heartbeat）, update_v0.9（飞书 Channel 增强）
> 方法论: 第一性原理推演 + 苏格拉底追问

---

## 0. 先追问，后设计

"多 Agent" 和 "Workflow" 在 AI Agent 领域已经被用滥了——每篇文章的定义都不一样。在写代码之前，必须先剥去概念的外壳，找到真正的需求和约束。

---

## 1. 苏格拉底追问：十个关键质疑

### Q1: 什么是 Agent？什么让多个 Agent 区别于"一个 Agent 的多次调用"？

**表面理解**: 多个 Agent = 多个 LLM 实例并行工作。

**追问**: 当前 AgentOS 的 "default agent" 在一次对话中就可以多次调用 LLM（每次工具调用后都会再次调用）。这和"多 Agent"有什么本质区别？

**分析**:

| 维度 | 同一 Agent 多次调用 | 多 Agent |
|------|---------------------|----------|
| System Prompt | 相同 | **不同**——每个 Agent 有独立的人设和指令 |
| 工具集 | 相同 | **可不同**——代码审查 Agent 不需要搜索工具 |
| Skills 集 | 相同 | **可不同**——数据分析 Agent 不需要前端设计 Skill |
| 模型 | 相同 | **可不同**——简单任务用小模型，复杂推理用大模型 |
| 上下文 | 共享同一条消息链 | **隔离**——各自维护独立的消息历史 |
| 温度等参数 | 相同 | **可不同**——创意 Agent 高温度，审查 Agent 低温度 |

**结论**: Agent 是一个**配置边界**——它定义了一个行为剖面（system prompt + tools + skills + model + temperature）。多 Agent 的本质是**多个独立的配置边界在同一个系统中协作**。

---

### Q2: Agent 之间的协作模式有几种？

**追问**: 从用户视角出发，用户会怎样使用多个 Agent？

| 场景 | 协作模式 | 描述 |
|------|---------|------|
| "帮我调研这个技术方案，然后写一份报告" | **委托** | 主 Agent 把"调研"部分委托给 Research Agent |
| "同时搜索中文和英文资料" | **并行** | 主 Agent 同时委托两个 Agent 分别搜索 |
| "先写代码，再审查，审查不过就重写" | **工作流** | 按预定流程串联 Code Agent → Review Agent → 条件回退 |
| "让 Data Agent 分析数据，让 Chart Agent 画图" | **管道** | 前一个 Agent 的输出是后一个的输入 |

**结论**: 协作模式不是一种，而是一个谱系。最基础的原语是**委托（delegate）**——一个 Agent 请求另一个 Agent 执行一个任务。并行、管道、工作流都可以基于委托组合出来。

---

### Q3: 应该由谁来决定委托？LLM 自己还是预定义的流程？

**追问**: 这是最关键的分叉点，决定了整个系统的复杂度。

**两种极端**:

| 方案 | 优势 | 劣势 |
|------|------|------|
| **LLM 自主决策**: 给主 Agent 一个 `delegate` 工具，让它自己决定何时委托、委托给谁 | 灵活，无需预定义流程 | 不可预测，可能产生无限递归，调试困难 |
| **用户预定义流程**: 用户画一个 DAG（节点 + 边），系统按图执行 | 可控、可预测、可重复 | 不灵活，无法应对动态需求 |

**AgentOS 的选择: 两层都要**。

1. **Layer 1: AgentRegistry + DelegateTool**（动态委托）——Agent 通过工具自主决定委托，适合探索性任务
2. **Layer 2: Workflow Engine**（静态编排）——用户定义 DAG，系统按图执行，适合重复性任务

Layer 1 是 Layer 2 的基础设施。Workflow 的每个节点本质上就是一次委托调用。

---

### Q4: AgentRegistry 和当前的 ToolRegistry / SkillRegistry 有什么关系？

**追问**: 能不能把 Agent 注册为 Tool？

**分析**:

Tool 的接口是 `execute(**kwargs) -> result`——同步调用，返回结果。Agent 的执行流程是异步的、多轮的（可能需要多次 LLM 调用和工具调用）。把 Agent 包装成 Tool 会：

1. 丢失异步事件流——调用方看不到中间过程
2. 超时风险——Agent 执行可能很长
3. 嵌套复杂度——Agent 调 Tool 调 Agent 调 Tool...

**正确的关系**:

```
AgentRegistry —— 管理 Agent 配置（类似 ToolRegistry 管理 Tool 定义）
DelegateTool —— 桥接层，将 Agent 调用包装为 Tool 接口
                 内部通过事件系统异步执行，但对调用方表现为同步结果返回
```

**类比**: SkillRegistry 管理 Skill 的定义和加载，但 Skill 不是 Tool——它通过 system prompt 注入来影响 Agent 行为。AgentRegistry 也类似——它管理 Agent 的定义和生命周期，但 Agent 间的通信通过 DelegateTool 和事件总线实现。

---

### Q5: Agent 之间的通信应该走事件总线还是直接调用？

**追问**: 当前的事件驱动架构天然支持多 Agent 吗？

**分析当前架构**:

```
用户输入 → PublicEventBus → BusRouter → PrivateEventBus(session) → AgentWorker
```

每个 session 有自己的 PrivateEventBus。当前所有 session 都用同一套 Agent 配置（default agent）。多 Agent 需要：

1. 不同的 session 可以绑定到不同的 Agent 配置
2. Agent A 可以创建一个新的"子 session"来委托 Agent B
3. 子 session 完成后，结果需要回传给 Agent A 所在的 session

**最自然的方式**: 委托产生一个**子 session**，子 session 绑定到目标 Agent 的配置，在独立的 PrivateEventBus 中执行，完成后通过事件通知父 session。

```
Session-001 (Agent A)          Session-002 (Agent B，子 session)
    │                              │
    ├── user.input                 │
    ├── agent.step_started         │
    ├── llm.call_requested         │
    ├── llm.call_result            │
    │   └── tool_calls: [delegate] │
    ├── tool.call_requested        │
    │   └── delegate to Agent B    │
    │                              ├── user.input (委托任务描述)
    │                              ├── agent.step_started
    │   (等待...)                  ├── llm.call_requested
    │                              ├── llm.call_result
    │                              ├── agent.step_completed
    │                              │
    ├── tool.call_completed ◄──────┘ (子 session 的最终结果)
    ├── llm.call_requested
    ├── ...
    └── agent.step_completed
```

**结论**: Agent 间通信通过**子 session 机制 + 事件总线**实现，不需要新的通信原语。DelegateTool 负责创建子 session、等待完成、返回结果。

---

### Q6: 子 Agent 能否继续委托？递归深度怎么控制？

**追问**: Agent A 委托 Agent B，Agent B 又委托 Agent C——这合理吗？

**分析**:

合理的场景：研究总监 Agent → 调研 Agent → 搜索 Agent。但无限递归是真实风险。

**控制手段**:

1. **最大委托深度**（`max_delegation_depth`，默认 3）——每次委托时在 payload 中携带当前深度，超过限制拒绝
2. **Agent 白名单**——每个 Agent 配置中声明它可以委托的 Agent 列表
3. **超时**——每次委托有独立的超时限制（默认 5 分钟）

---

### Q7: Workflow 的最小原语是什么？

**追问**: 最简单的 Workflow 长什么样？

**从最简单的用例开始**: "先搜索资料，然后写总结"

```yaml
nodes:
  - id: search
    agent: research-agent
    input: "搜索关于 {topic} 的最新资料"
  - id: summarize
    agent: writer-agent
    input: "根据以下资料写一份总结：\n{search.output}"

edges:
  - from: search
    to: summarize
```

**原语分解**:

| 概念 | 定义 |
|------|------|
| **WorkflowNode** | 一个执行单元，绑定一个 Agent 配置 + 输入模板 |
| **Edge** | 连接两个 Node，定义数据流和控制流 |
| **Workflow** | Node + Edge 的集合，形成 DAG |
| **WorkflowRun** | 一次 Workflow 的具体执行实例 |

**最小原语就是三个**: Node、Edge、Workflow。不需要更多。

---

### Q8: Workflow 节点的输入输出格式应该是什么？

**追问**: Agent 的输出是自由文本，怎么作为下一个节点的结构化输入？

**方案**:

节点的输入是一个**模板字符串**，支持变量引用：

```
{workflow.input}        → 工作流的初始输入
{node_id.output}        → 某个节点的完整输出文本
{node_id.output.field}  → 从 JSON 输出中提取字段（Agent 返回 JSON 时）
```

节点的输出就是 Agent 的最终响应文本（`agent.step_completed` 的 `final_response`）。

**为什么不用结构化协议**: Agent 的输出天然是自然语言。强制结构化会引入 JSON 解析失败的风险，也限制了 Agent 的灵活性。模板引用 + 自然语言传递是最务实的方案。

---

### Q9: 并行执行和条件分支怎么表达？

**追问**: 用户说"同时搜索中文和英文"——怎么在 DAG 中表达？

**并行（Fan-out）**: 一个节点有多条出边 → 所有目标节点并行执行

```yaml
edges:
  - from: start
    to: search_cn
  - from: start
    to: search_en
  - from: search_cn
    to: merge
  - from: search_en
    to: merge
```

**聚合（Fan-in / Merge）**: 一个节点有多条入边 → 等待所有前置节点完成后执行

`merge` 节点的输入模板可以引用多个前置节点：

```yaml
- id: merge
  agent: writer-agent
  input: |
    中文资料：{search_cn.output}
    英文资料：{search_en.output}
    请合并这两份资料写一份综合报告。
```

**条件分支**: Edge 上添加 `condition` 表达式

```yaml
edges:
  - from: review
    to: publish
    condition: "{review.output} contains '通过'"
  - from: review
    to: rewrite
    condition: "{review.output} contains '不通过'"
```

条件表达式使用简单的字符串匹配（contains / equals / matches regex），不引入复杂的表达式引擎。

---

### Q10: 现有代码需要改多少？

**追问**: 从改动量和风险的角度排序。

| 层级 | 改动 | 风险 |
|------|------|------|
| **事件总线** | 不变。PrivateEventBus + BusRouter 天然支持多 session | 无 |
| **SessionWorker** | 不变。子 session 的 Worker 和普通 session 完全一样 | 无 |
| **AgentRuntime** | 小改。`_create_worker` 时需要查找 Agent 配置 | 低 |
| **ContextBuilder** | 小改。根据 Agent 配置加载不同的 system prompt / tools / skills | 低 |
| **新增: AgentRegistry** | 新模块。管理 Agent 配置的 CRUD | 低 |
| **新增: DelegateTool** | 新 Tool。封装子 session 的创建和等待 | 中 |
| **新增: WorkflowRuntime** | 新模块。DAG 调度引擎 | 中 |
| **新增: WorkflowRegistry** | 新模块。管理 Workflow 定义的 CRUD | 低 |
| **前端** | 新增 Agent 配置页 + Workflow 编辑器 | 独立开发 |

**核心观察**: 双总线架构的先见之明在这里体现——每个 Agent 执行天然隔离在自己的 PrivateEventBus 中，多 Agent 不需要修改事件系统。

---

## 2. 多 Agent 系统设计

### 2.1 Agent 定义

```python
from typing import Any, Literal
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    """一个 Agent 的完整配置。Agent 是行为配置的边界。"""

    id: str                                         # 唯一标识（slug 格式，如 "research-agent"）
    name: str                                       # 人类可读名称
    description: str = ""                           # 描述（用于 LLM 选择委托目标）

    # LLM 配置
    provider: str = "openai"                        # LLM 提供商
    model: str = "gpt-4o-mini"                      # 模型名称
    temperature: float = 0.2                        # 温度参数
    max_tokens: int | None = None                   # 最大 token 数

    # 行为配置
    system_prompt: str = ""                         # 系统提示词
    tools: list[str] = field(default_factory=list)  # 允许使用的工具列表（空 = 全部）
    skills: list[str] = field(default_factory=list) # 允许使用的 Skills 列表（空 = 全部）

    # 委托配置
    can_delegate_to: list[str] = field(default_factory=list)  # 可委托的 Agent ID 列表
    max_delegation_depth: int = 3                              # 最大委托深度

    # 元信息
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0
```

**与当前 "default agent" 的关系**: 现有的 config.yml 中 `agent.*` 配置自动生成一个 `id="default"` 的 AgentConfig，保持向后兼容。

### 2.2 AgentRegistry

```python
class AgentRegistry:
    """Agent 配置的注册表。
    
    职责：
    1. 管理 Agent 配置的 CRUD
    2. 从 config.yml 和持久化文件加载 Agent 配置
    3. 提供 Agent 发现机制（供 DelegateTool 使用）
    
    不做：
    - 不管理 Agent 实例的生命周期（那是 AgentRuntime 的事）
    - 不执行 Agent 逻辑（那是 AgentSessionWorker 的事）
    """

    def __init__(self, config_dir: Path):
        self._agents: dict[str, AgentConfig] = {}
        self._config_dir = config_dir  # 持久化目录

    def register(self, agent: AgentConfig) -> None:
        """注册或更新一个 Agent 配置"""
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> AgentConfig | None:
        """获取 Agent 配置"""
        return self._agents.get(agent_id)

    def list_all(self) -> list[AgentConfig]:
        """列出所有已注册的 Agent"""
        return [a for a in self._agents.values() if a.enabled]

    def get_delegatable(self, from_agent_id: str) -> list[AgentConfig]:
        """获取某个 Agent 可以委托的目标 Agent 列表"""
        source = self._agents.get(from_agent_id)
        if not source:
            return []
        if not source.can_delegate_to:
            # 空列表 = 可以委托给所有其他 Agent
            return [a for a in self._agents.values()
                    if a.id != from_agent_id and a.enabled]
        return [self._agents[aid] for aid in source.can_delegate_to
                if aid in self._agents and self._agents[aid].enabled]

    def load_from_config(self, config: dict[str, Any]) -> None:
        """从 config.yml 加载 Agent 配置"""
        # 1. 始终创建 default agent（从 agent.* 配置映射）
        default = AgentConfig(
            id="default",
            name="Default Agent",
            description="默认 AI Agent",
            provider=config.get("agent", {}).get("provider", "openai"),
            model=config.get("agent", {}).get("default_model", "gpt-4o-mini"),
            temperature=config.get("agent", {}).get("default_temperature", 0.2),
            system_prompt=config.get("agent", {}).get("system_prompt", ""),
        )
        self.register(default)

        # 2. 加载 agents.* 配置中的额外 Agent
        agents_config = config.get("agents", {})
        for agent_id, agent_dict in agents_config.items():
            agent = AgentConfig(id=agent_id, **agent_dict)
            self.register(agent)

    def load_from_dir(self) -> None:
        """从持久化目录加载 Agent 配置（JSON 文件）"""
        if not self._config_dir.exists():
            return
        for f in self._config_dir.glob("*.json"):
            # 从 JSON 反序列化为 AgentConfig
            pass

    def save(self, agent: AgentConfig) -> None:
        """持久化 Agent 配置到磁盘"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        # 序列化为 JSON 并写入文件
        pass
```

### 2.3 config.yml 中的多 Agent 配置

```yaml
# 默认 Agent（向后兼容）
agent:
  provider: openai
  default_model: gpt-4o-mini
  system_prompt: "你是一个通用 AI 助手"

# 额外 Agent 定义
agents:
  research-agent:
    name: "Research Agent"
    description: "专注于信息调研和资料搜集"
    model: gpt-4o
    temperature: 0.3
    system_prompt: |
      你是一个专业的调研助手。你的职责是：
      1. 使用搜索工具广泛搜集信息
      2. 使用 fetch_url 获取详细内容
      3. 整理和总结发现的信息
      请以结构化的方式呈现调研结果。
    tools: [serper_search, fetch_url, read_file, write_file]
    skills: []

  code-review-agent:
    name: "Code Review Agent"
    description: "专注于代码审查和质量把控"
    model: gpt-4o
    temperature: 0.1
    system_prompt: |
      你是一个严格的代码审查专家。你的职责是：
      1. 审查代码的正确性、性能和安全性
      2. 指出潜在问题并提供修改建议
      3. 评估代码是否符合最佳实践
      回复格式：PASS（通过）或 FAIL（不通过）+ 详细说明。
    tools: [read_file, bash_command]
    skills: []

  writer-agent:
    name: "Writer Agent"
    description: "专注于文档写作和内容整理"
    model: gpt-4o-mini
    temperature: 0.7
    system_prompt: |
      你是一个优秀的文档写作助手。你的职责是将信息整理成
      结构清晰、文笔流畅的文档。善于使用 Markdown 格式。
    tools: [write_file, read_file]
    skills: [doc-coauthoring]
```

### 2.4 DelegateTool：Agent 间委托的桥梁

```python
class DelegateTool(Tool):
    """委托工具：允许一个 Agent 将子任务委托给另一个 Agent。

    内部机制：
    1. 创建一个子 session（绑定到目标 Agent 的配置）
    2. 向子 session 注入委托任务作为 user.input
    3. 等待子 session 的 agent.step_completed 事件
    4. 将子 Agent 的最终响应作为工具结果返回

    这个 Tool 对调用方（LLM）表现为同步调用，
    但内部通过事件系统异步执行。
    """

    name = "delegate"
    description = (
        "将子任务委托给另一个专门的 Agent 处理。"
        "target_agent: 目标 Agent 的 ID。"
        "task: 要委托的任务描述。"
        "context: 需要传递给目标 Agent 的上下文信息（可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "目标 Agent 的 ID",
            },
            "task": {
                "type": "string",
                "description": "要委托的任务描述",
            },
            "context": {
                "type": "string",
                "description": "传递给目标 Agent 的上下文信息",
            },
        },
        "required": ["target_agent", "task"],
    }

    def __init__(
        self,
        agent_registry: AgentRegistry,
        bus_router: BusRouter,
        repo: Repository,
        timeout: float = 300,  # 默认 5 分钟超时
    ):
        self._registry = agent_registry
        self._bus_router = bus_router
        self._repo = repo
        self._timeout = timeout

    async def execute(self, **kwargs) -> Any:
        target_id = kwargs.get("target_agent", "")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")

        # 1. 验证目标 Agent 存在
        target_config = self._registry.get(target_id)
        if not target_config:
            return {"success": False, "error": f"Agent '{target_id}' not found"}

        # 2. 检查委托深度（从当前 session 的 metadata 中读取）
        current_depth = kwargs.get("_delegation_depth", 0)
        if current_depth >= target_config.max_delegation_depth:
            return {"success": False, "error": "Maximum delegation depth exceeded"}

        # 3. 创建子 session
        sub_session_id = f"delegate_{uuid.uuid4().hex[:12]}"
        await self._repo.create_session(
            session_id=sub_session_id,
            meta={
                "title": f"[delegate] {task[:30]}",
                "agent_id": target_id,
                "parent_session_id": kwargs.get("_session_id"),
                "delegation_depth": current_depth + 1,
            },
        )

        # 4. 构造用户输入
        user_input = task
        if context:
            user_input = f"上下文信息：\n{context}\n\n任务：\n{task}"

        # 5. 发布 user.input 到公共总线（BusRouter 会自动创建 Worker）
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        event = EventEnvelope(
            type=USER_INPUT,
            session_id=sub_session_id,
            turn_id=turn_id,
            source="delegate_tool",
            payload={"content": user_input},
        )
        await self._bus_router.public_bus.publish(event)

        # 6. 等待子 session 完成（订阅 PublicEventBus 监听 step_completed）
        result = await self._wait_for_completion(sub_session_id, turn_id)
        return result

    async def _wait_for_completion(
        self, session_id: str, turn_id: str,
    ) -> dict:
        """等待子 session 的 agent.step_completed 事件"""
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _listener():
            async for event in self._bus_router.public_bus.subscribe():
                if (event.session_id == session_id
                    and event.type == AGENT_STEP_COMPLETED):
                    if not result_future.done():
                        result_future.set_result(event.payload)
                    return
                if (event.session_id == session_id
                    and event.type == ERROR_RAISED):
                    if not result_future.done():
                        result_future.set_result({
                            "success": False,
                            "error": event.payload.get("error_message", "Unknown error"),
                        })
                    return

        listener_task = asyncio.create_task(_listener())
        try:
            payload = await asyncio.wait_for(result_future, timeout=self._timeout)
            content = payload.get("result", {}).get("content", "")
            return {"success": True, "result": content}
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Delegation timed out after {self._timeout}s"}
        finally:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task
```

### 2.5 AgentRuntime 改造：感知 Agent 配置

当前 `AgentRuntime._create_worker` 创建 Worker 时，所有 Worker 使用相同的配置。需要改造为根据 session 绑定的 agent_id 查找对应配置。

```python
class AgentRuntime:
    def __init__(
        self,
        bus_router: BusRouter,
        repo: Repository,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        state_store: SessionStateStore,
        agent_registry: AgentRegistry,   # 新增
        memory_manager: Any = None,
    ):
        # ...
        self.agent_registry = agent_registry

    async def _create_worker(self, session_id: str, private_bus: PrivateEventBus) -> None:
        """Worker 工厂：根据 session 绑定的 agent_id 选择配置"""
        # 查找 session 的 agent_id
        session_meta = await self.repo.get_session_meta(session_id)
        agent_id = session_meta.get("agent_id", "default") if session_meta else "default"
        agent_config = self.agent_registry.get(agent_id)

        worker = AgentSessionWorker(
            session_id=session_id,
            private_bus=private_bus,
            runtime=self,
            agent_config=agent_config,    # 传递 Agent 配置
        )
        self._workers[session_id] = worker
        await worker.start()
```

### 2.6 AgentSessionWorker 改造：使用 Agent 配置

```python
class AgentSessionWorker(SessionWorker):
    def __init__(
        self,
        session_id: str,
        private_bus: PrivateEventBus,
        runtime: AgentRuntime,
        agent_config: AgentConfig | None = None,
    ):
        super().__init__(session_id, private_bus)
        self.rt = runtime
        self.agent_config = agent_config

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        # ...（前半部分不变）

        # 使用 Agent 配置构建上下文
        messages = self.rt.context_builder.build_messages(
            content, history,
            memory_context=memory_context,
            context_files=context_files,
            agent_config=self.agent_config,  # 传递 Agent 配置
        )

        # 使用 Agent 配置的 provider/model/temperature
        cfg = self.agent_config or AgentConfig(id="default")
        tools = self._get_filtered_tools()

        await self.bus.publish(EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id=self.session_id,
            turn_id=turn_id,
            trace_id=llm_call_id,
            source="agent",
            payload={
                "llm_call_id": llm_call_id,
                "provider": cfg.provider,
                "model": cfg.model,
                "messages": messages,
                "tools": tools,
                "temperature": cfg.temperature,
            },
        ))

    def _get_filtered_tools(self) -> list[dict]:
        """根据 Agent 配置过滤可用工具"""
        all_tools = self.rt.tool_registry.as_llm_tools()
        if not self.agent_config or not self.agent_config.tools:
            return all_tools  # 空列表 = 全部工具
        allowed = set(self.agent_config.tools)
        return [t for t in all_tools if t["name"] in allowed]
```

### 2.7 ContextBuilder 改造：根据 Agent 配置注入 prompt

```python
class ContextBuilder:
    def build_messages(
        self,
        user_input: str,
        history: list[dict],
        *,
        memory_context: str | None = None,
        context_files: list[dict] | None = None,
        agent_config: AgentConfig | None = None,
    ) -> list[dict]:
        # 根据 agent_config 选择 system prompt
        if agent_config and agent_config.system_prompt:
            system_prompt = agent_config.system_prompt
        else:
            system_prompt = config.get("agent.system_prompt", "")

        # 根据 agent_config 过滤 skills 注入
        skills = self._get_filtered_skills(agent_config)

        # 构建完整的 system prompt（现有逻辑 + 可委托 Agent 列表）
        # ...

    def _get_filtered_skills(self, agent_config: AgentConfig | None) -> list[Skill]:
        """根据 Agent 配置过滤 Skills"""
        all_skills = self._skill_registry.get_all()
        if not agent_config or not agent_config.skills:
            return all_skills
        allowed = set(agent_config.skills)
        return [s for s in all_skills if s.name in allowed]

    def _build_delegation_prompt(self, agent_config: AgentConfig) -> str:
        """构建可委托 Agent 的信息（注入到 system prompt）"""
        delegatable = self._agent_registry.get_delegatable(agent_config.id)
        if not delegatable:
            return ""
        lines = ["<available_agents>"]
        for agent in delegatable:
            lines.append(f"- {agent.id}: {agent.description}")
        lines.append("</available_agents>")
        lines.append("")
        lines.append("你可以使用 delegate 工具将子任务委托给以上 Agent。")
        return "\n".join(lines)
```

### 2.8 事件类型扩展

```python
# backend/app/events/types.py 新增

# Agent 委托事件
AGENT_DELEGATE_REQUESTED = "agent.delegate_requested"
AGENT_DELEGATE_STARTED = "agent.delegate_started"
AGENT_DELEGATE_COMPLETED = "agent.delegate_completed"
AGENT_DELEGATE_FAILED = "agent.delegate_failed"
```

### 2.9 Agent 崩溃自动恢复

子 Agent 可能因为 LLM 调用超时、工具执行异常等原因崩溃。DelegateTool 已经通过 `asyncio.wait_for` 实现了超时保护。除此之外，需要在 Worker 层面增加异常恢复：

```python
class AgentSessionWorker(SessionWorker):
    MAX_CONSECUTIVE_ERRORS = 3

    async def _handle(self, event: EventEnvelope) -> None:
        try:
            # ... 正常的事件处理 ...
            self._consecutive_errors = 0
        except Exception as exc:
            self._consecutive_errors += 1
            logger.exception("Worker error in session %s", self.session_id)

            if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                # 连续错误过多，发布失败事件并停止
                await self.bus.publish(EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=self.session_id,
                    source="agent",
                    payload={
                        "error_type": "WorkerCrash",
                        "error_message": f"Worker crashed after {self.MAX_CONSECUTIVE_ERRORS} consecutive errors: {exc}",
                    },
                ))
```

---

## 3. Workflow 编排系统设计

### 3.1 设计原则

| 原则 | 说明 |
|------|------|
| **DAG 优先** | Workflow 是有向无环图，不支持回路（循环通过"条件回退到前置节点"实现，有最大迭代限制） |
| **Agent 即节点** | 每个节点本质上是一次 Agent 委托调用 |
| **声明式定义** | Workflow 通过 YAML 或 JSON 定义，而非代码 |
| **内置模板** | 提供常用模式的模板（plan-execute-review、fan-out-merge）|
| **事件可观测** | 每个节点的执行状态都通过事件总线广播 |

### 3.2 数据模型

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class WorkflowNode:
    """工作流节点：一个执行单元"""

    id: str                             # 节点唯一 ID（如 "search", "review"）
    agent_id: str = "default"           # 绑定的 Agent ID
    input_template: str = ""            # 输入模板，支持 {var} 变量引用
    description: str = ""               # 节点描述（用于日志和 UI）

    # 执行配置
    timeout: float = 300                # 单节点超时（秒）
    retry: int = 0                      # 失败重试次数
    allow_tools: bool = True            # 是否允许使用工具

    # 特殊节点类型
    node_type: Literal["agent", "condition", "merge"] = "agent"

    # condition 节点专用
    condition_expr: str = ""            # 条件表达式

    # merge 节点专用（输入来自多个前置节点）
    merge_strategy: Literal["concat", "template"] = "template"


@dataclass
class WorkflowEdge:
    """工作流边：连接两个节点"""

    from_node: str                      # 源节点 ID
    to_node: str                        # 目标节点 ID
    condition: str | None = None        # 条件表达式（None = 无条件）
    label: str = ""                     # 边的标签（用于 UI 显示）


@dataclass
class Workflow:
    """工作流定义"""

    id: str                             # 唯一标识
    name: str                           # 人类可读名称
    description: str = ""               # 描述
    version: str = "1.0"                # 版本号

    # 图结构
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)

    # 入口和出口
    entry_node: str = ""                # 入口节点 ID
    exit_nodes: list[str] = field(default_factory=list)  # 出口节点 ID 列表

    # 全局配置
    max_iterations: int = 10            # 最大迭代次数（防止条件回退导致的无限循环）
    timeout: float = 1800               # 全局超时（秒）

    # 元信息
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class WorkflowNodeResult:
    """节点执行结果"""

    node_id: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    output: str = ""                    # Agent 输出
    error: str = ""                     # 错误信息
    started_at: float = 0.0
    completed_at: float = 0.0
    agent_id: str = ""


@dataclass
class WorkflowRun:
    """一次工作流执行实例"""

    run_id: str                         # 执行实例 ID
    workflow_id: str                    # 工作流定义 ID
    status: Literal["running", "completed", "failed", "cancelled"]
    input: str = ""                     # 工作流输入
    output: str = ""                    # 工作流最终输出
    node_results: dict[str, WorkflowNodeResult] = field(default_factory=dict)
    iteration_count: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    session_id: str = ""                # 关联的主 session
```

### 3.3 WorkflowRegistry

```python
class WorkflowRegistry:
    """管理 Workflow 定义的注册表。

    职责：
    1. CRUD Workflow 定义
    2. 从 YAML 文件和 config 加载 Workflow
    3. 验证 Workflow 的 DAG 合法性（无环、入口/出口正确、节点 ID 唯一）
    """

    def __init__(self, config_dir: Path):
        self._workflows: dict[str, Workflow] = {}
        self._config_dir = config_dir

    def register(self, workflow: Workflow) -> None:
        """注册工作流（含 DAG 合法性验证）"""
        self._validate(workflow)
        self._workflows[workflow.id] = workflow

    def get(self, workflow_id: str) -> Workflow | None:
        return self._workflows.get(workflow_id)

    def list_all(self) -> list[Workflow]:
        return list(self._workflows.values())

    def _validate(self, workflow: Workflow) -> None:
        """验证 DAG 合法性"""
        node_ids = {n.id for n in workflow.nodes}

        # 1. 节点 ID 唯一
        if len(node_ids) != len(workflow.nodes):
            raise ValueError("Duplicate node IDs detected")

        # 2. 边引用的节点必须存在
        for edge in workflow.edges:
            if edge.from_node not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.from_node}")
            if edge.to_node not in node_ids:
                raise ValueError(f"Edge references unknown node: {edge.to_node}")

        # 3. 入口节点必须存在
        if workflow.entry_node and workflow.entry_node not in node_ids:
            raise ValueError(f"Entry node not found: {workflow.entry_node}")

        # 4. DAG 无环检测（拓扑排序）
        self._check_acyclic(workflow)

    def _check_acyclic(self, workflow: Workflow) -> None:
        """拓扑排序检测环"""
        adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
        in_degree: dict[str, int] = {n.id: 0 for n in workflow.nodes}
        for edge in workflow.edges:
            adj[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            nid = queue.pop(0)
            visited += 1
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(workflow.nodes):
            raise ValueError("Workflow contains a cycle")

    def load_from_dir(self) -> None:
        """从目录加载 YAML 格式的 Workflow 定义"""
        if not self._config_dir.exists():
            return
        for f in self._config_dir.glob("*.yaml"):
            # 解析 YAML，构建 Workflow 对象
            pass
        for f in self._config_dir.glob("*.yml"):
            pass
```

### 3.4 WorkflowRuntime：DAG 调度引擎

```python
class WorkflowRuntime:
    """工作流调度引擎。

    职责：
    1. 接收工作流执行请求
    2. 按 DAG 拓扑顺序调度节点
    3. 管理并行执行和聚合
    4. 处理条件分支
    5. 通过事件总线报告执行状态

    核心算法：
    - 使用就绪队列（ready queue）驱动执行
    - 节点就绪条件：所有入边的源节点都已完成
    - 并行：多个节点同时就绪时并发执行
    - 聚合：等待所有入边完成后执行
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        workflow_registry: WorkflowRegistry,
        bus_router: BusRouter,
        repo: Repository,
        publisher: EventPublisher,
    ):
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry
        self.bus_router = bus_router
        self.repo = repo
        self.publisher = publisher
        self._active_runs: dict[str, WorkflowRun] = {}

    async def execute(
        self,
        workflow_id: str,
        input_text: str,
        session_id: str,
    ) -> WorkflowRun:
        """执行一个工作流"""
        workflow = self.workflow_registry.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        run = WorkflowRun(
            run_id=f"wf_run_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            status="running",
            input=input_text,
            started_at=time.time(),
            session_id=session_id,
        )
        self._active_runs[run.run_id] = run

        # 发布工作流开始事件
        await self._emit(WORKFLOW_RUN_STARTED, session_id, {
            "run_id": run.run_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
        })

        try:
            await self._run_dag(workflow, run)
        except asyncio.TimeoutError:
            run.status = "failed"
            await self._emit(WORKFLOW_RUN_FAILED, session_id, {
                "run_id": run.run_id,
                "error": "Workflow execution timed out",
            })
        except Exception as exc:
            run.status = "failed"
            await self._emit(WORKFLOW_RUN_FAILED, session_id, {
                "run_id": run.run_id,
                "error": str(exc),
            })
        finally:
            run.completed_at = time.time()
            self._active_runs.pop(run.run_id, None)

        return run

    async def _run_dag(self, workflow: Workflow, run: WorkflowRun) -> None:
        """DAG 调度核心算法"""
        # 构建图结构
        adj, in_edges = self._build_graph(workflow)
        remaining_in_degree = {n.id: len(in_edges.get(n.id, [])) for n in workflow.nodes}

        # 初始化所有节点状态
        for node in workflow.nodes:
            run.node_results[node.id] = WorkflowNodeResult(
                node_id=node.id,
                status="pending",
                agent_id=node.agent_id,
            )

        # 找到入口节点（入度为 0）
        ready_queue = [nid for nid, deg in remaining_in_degree.items() if deg == 0]

        while ready_queue and run.iteration_count < workflow.max_iterations:
            run.iteration_count += 1

            # 并行执行所有就绪节点
            tasks = []
            executing = []
            for node_id in ready_queue:
                node = self._find_node(workflow, node_id)
                if not node:
                    continue

                # 检查条件边（如果所有入边都有条件，且没有一个满足，则跳过）
                if self._should_skip_node(node, workflow, run):
                    run.node_results[node_id].status = "skipped"
                    executing.append(node_id)
                    continue

                tasks.append(self._execute_node(node, workflow, run))
                executing.append(node_id)

            ready_queue.clear()

            # 等待所有并行任务完成
            if tasks:
                await asyncio.gather(*tasks)

            # 更新入度，找到新的就绪节点
            for node_id in executing:
                for neighbor_id in adj.get(node_id, []):
                    edge = self._find_edge(workflow, node_id, neighbor_id)
                    if edge and edge.condition:
                        # 条件边：检查条件是否满足
                        if not self._evaluate_condition(edge.condition, run):
                            continue
                    remaining_in_degree[neighbor_id] -= 1
                    if remaining_in_degree[neighbor_id] <= 0:
                        ready_queue.append(neighbor_id)

            # 检查是否有节点失败导致无法继续
            if not ready_queue and not self._all_exit_nodes_done(workflow, run):
                # 检查是否所有剩余节点都是不可达的
                blocked = [nid for nid, deg in remaining_in_degree.items()
                           if deg > 0 and run.node_results[nid].status == "pending"]
                if blocked:
                    logger.warning("Workflow stuck: blocked nodes = %s", blocked)
                    break

        # 收集输出
        run.output = self._collect_output(workflow, run)
        run.status = "completed" if self._all_exit_nodes_done(workflow, run) else "failed"

        await self._emit(WORKFLOW_RUN_COMPLETED, run.session_id, {
            "run_id": run.run_id,
            "status": run.status,
            "output_preview": run.output[:500],
        })

    async def _execute_node(
        self,
        node: WorkflowNode,
        workflow: Workflow,
        run: WorkflowRun,
    ) -> None:
        """执行单个节点"""
        result = run.node_results[node.id]
        result.status = "running"
        result.started_at = time.time()

        await self._emit(WORKFLOW_NODE_STARTED, run.session_id, {
            "run_id": run.run_id,
            "node_id": node.id,
            "agent_id": node.agent_id,
        })

        try:
            # 解析输入模板
            input_text = self._resolve_template(node.input_template, workflow, run)

            # 创建子 session 并执行 Agent
            sub_session_id = f"wf_{run.run_id}_{node.id}"
            await self.repo.create_session(
                session_id=sub_session_id,
                meta={
                    "title": f"[workflow:{workflow.id}] {node.id}",
                    "agent_id": node.agent_id,
                    "workflow_run_id": run.run_id,
                    "workflow_node_id": node.id,
                },
            )

            # 发布 user.input 并等待 agent.step_completed
            turn_id = f"turn_{uuid.uuid4().hex[:12]}"
            await self.bus_router.public_bus.publish(EventEnvelope(
                type=USER_INPUT,
                session_id=sub_session_id,
                turn_id=turn_id,
                source="workflow",
                payload={"content": input_text},
            ))

            # 等待完成
            output = await self._wait_for_node_completion(sub_session_id, node.timeout)
            result.output = output
            result.status = "completed"

        except asyncio.TimeoutError:
            result.status = "failed"
            result.error = f"Node timed out after {node.timeout}s"
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)

        result.completed_at = time.time()

        await self._emit(WORKFLOW_NODE_COMPLETED, run.session_id, {
            "run_id": run.run_id,
            "node_id": node.id,
            "status": result.status,
            "output_preview": result.output[:200] if result.output else "",
            "error": result.error,
        })

    def _resolve_template(
        self, template: str, workflow: Workflow, run: WorkflowRun,
    ) -> str:
        """解析输入模板中的变量引用

        支持的变量：
        - {workflow.input}      → 工作流的初始输入
        - {node_id.output}      → 某个节点的完整输出
        """
        result = template

        # 替换 workflow.input
        result = result.replace("{workflow.input}", run.input)

        # 替换 node_id.output
        for node_id, node_result in run.node_results.items():
            placeholder = f"{{{node_id}.output}}"
            if placeholder in result:
                result = result.replace(placeholder, node_result.output or "(无输出)")

        return result

    def _evaluate_condition(self, condition: str, run: WorkflowRun) -> bool:
        """评估条件表达式

        支持的语法：
        - "{node_id.output} contains '关键词'"
        - "{node_id.status} == 'completed'"
        """
        resolved = condition
        for node_id, node_result in run.node_results.items():
            resolved = resolved.replace(f"{{{node_id}.output}}", node_result.output or "")
            resolved = resolved.replace(f"{{{node_id}.status}}", node_result.status)

        if " contains " in resolved:
            parts = resolved.split(" contains ", 1)
            return parts[1].strip("'\"") in parts[0]
        if " == " in resolved:
            parts = resolved.split(" == ", 1)
            return parts[0].strip() == parts[1].strip("'\"")

        return True  # 无法解析的条件默认为真

    async def _wait_for_node_completion(
        self, session_id: str, timeout: float,
    ) -> str:
        """等待子 session 完成"""
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _listener():
            async for event in self.bus_router.public_bus.subscribe():
                if event.session_id == session_id:
                    if event.type == AGENT_STEP_COMPLETED:
                        content = event.payload.get("result", {}).get("content", "")
                        if not future.done():
                            future.set_result(content)
                        return
                    if event.type == ERROR_RAISED:
                        if not future.done():
                            future.set_exception(
                                RuntimeError(event.payload.get("error_message", ""))
                            )
                        return

        task = asyncio.create_task(_listener())
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _build_graph(self, workflow: Workflow):
        """构建邻接表和入边映射"""
        adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
        in_edges: dict[str, list[WorkflowEdge]] = {n.id: [] for n in workflow.nodes}
        for edge in workflow.edges:
            adj[edge.from_node].append(edge.to_node)
            in_edges[edge.to_node].append(edge)
        return adj, in_edges

    def _find_node(self, workflow: Workflow, node_id: str) -> WorkflowNode | None:
        return next((n for n in workflow.nodes if n.id == node_id), None)

    def _find_edge(self, workflow: Workflow, from_id: str, to_id: str) -> WorkflowEdge | None:
        return next((e for e in workflow.edges
                      if e.from_node == from_id and e.to_node == to_id), None)

    def _should_skip_node(self, node, workflow, run) -> bool:
        """判断节点是否应被跳过（所有入边的条件都不满足）"""
        in_edges = [e for e in workflow.edges if e.to_node == node.id]
        if not in_edges:
            return False
        conditional_edges = [e for e in in_edges if e.condition]
        if not conditional_edges:
            return False
        return not any(self._evaluate_condition(e.condition, run) for e in conditional_edges)

    def _all_exit_nodes_done(self, workflow: Workflow, run: WorkflowRun) -> bool:
        exit_ids = workflow.exit_nodes or [n.id for n in workflow.nodes
                                           if not any(e.from_node == n.id for e in workflow.edges)]
        return all(run.node_results.get(nid, WorkflowNodeResult(node_id=nid, status="pending")).status
                   in ("completed", "skipped")
                   for nid in exit_ids)

    def _collect_output(self, workflow: Workflow, run: WorkflowRun) -> str:
        """收集出口节点的输出作为工作流最终输出"""
        exit_ids = workflow.exit_nodes or [n.id for n in workflow.nodes
                                           if not any(e.from_node == n.id for e in workflow.edges)]
        outputs = []
        for nid in exit_ids:
            result = run.node_results.get(nid)
            if result and result.output:
                outputs.append(result.output)
        return "\n\n".join(outputs)

    async def _emit(self, event_type: str, session_id: str, payload: dict) -> None:
        """发布工作流事件到公共总线"""
        await self.publisher.publish(EventEnvelope(
            type=event_type,
            session_id=session_id,
            source="workflow",
            payload=payload,
        ))
```

### 3.5 事件类型扩展

```python
# backend/app/events/types.py 新增

# Workflow 编排事件
WORKFLOW_RUN_STARTED = "workflow.run_started"
WORKFLOW_RUN_COMPLETED = "workflow.run_completed"
WORKFLOW_RUN_FAILED = "workflow.run_failed"
WORKFLOW_NODE_STARTED = "workflow.node_started"
WORKFLOW_NODE_COMPLETED = "workflow.node_completed"
```

### 3.6 WorkflowTool：让 Agent 能触发工作流

```python
class WorkflowTool(Tool):
    """工作流触发工具：允许 Agent 启动预定义的工作流。"""

    name = "run_workflow"
    description = (
        "启动一个预定义的工作流。"
        "workflow_id: 工作流 ID。"
        "input: 传递给工作流的输入文本。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "工作流 ID",
            },
            "input": {
                "type": "string",
                "description": "传递给工作流的输入",
            },
        },
        "required": ["workflow_id", "input"],
    }

    def __init__(self, workflow_runtime: WorkflowRuntime):
        self._runtime = workflow_runtime

    async def execute(self, **kwargs) -> Any:
        workflow_id = kwargs.get("workflow_id", "")
        input_text = kwargs.get("input", "")
        session_id = kwargs.get("_session_id", "")

        try:
            run = await self._runtime.execute(workflow_id, input_text, session_id)
            return {
                "success": run.status == "completed",
                "run_id": run.run_id,
                "status": run.status,
                "output": run.output,
                "node_count": len(run.node_results),
                "duration": run.completed_at - run.started_at,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
```

### 3.7 内置 Workflow 模板

#### 模板 1: Plan-Execute-Review

```yaml
# workflows/plan-execute-review.yaml
id: plan-execute-review
name: "计划-执行-审查"
description: "先制定计划，然后执行，最后审查结果。审查不通过则重新执行。"
version: "1.0"

nodes:
  - id: plan
    agent_id: default
    description: "分析需求，制定执行计划"
    input_template: |
      请分析以下任务并制定详细的执行计划：

      {workflow.input}

      要求：
      1. 列出具体的步骤
      2. 标注每步需要使用的工具
      3. 估计所需时间

  - id: execute
    agent_id: default
    description: "按照计划执行任务"
    input_template: |
      请按照以下计划执行任务：

      计划：
      {plan.output}

      原始需求：
      {workflow.input}

      请逐步执行计划中的每个步骤。

  - id: review
    agent_id: code-review-agent
    description: "审查执行结果"
    input_template: |
      请审查以下执行结果：

      原始需求：
      {workflow.input}

      执行计划：
      {plan.output}

      执行结果：
      {execute.output}

      请评估：
      1. 是否完成了所有需求
      2. 是否有质量问题
      回复 PASS 或 FAIL + 具体说明。

edges:
  - from: plan
    to: execute
  - from: execute
    to: review

entry_node: plan
exit_nodes: [review]
max_iterations: 10
```

#### 模板 2: Fan-out-Merge

```yaml
# workflows/fan-out-merge.yaml
id: research-and-merge
name: "并行调研-合并报告"
description: "并行搜索多个方向的资料，然后合并成一份综合报告。"
version: "1.0"

nodes:
  - id: analyze
    agent_id: default
    description: "分析调研需求，拆分为子课题"
    input_template: |
      请分析以下调研需求，拆分为 2-3 个独立的子课题：

      {workflow.input}

      请用编号列出每个子课题。

  - id: research_1
    agent_id: research-agent
    description: "调研子课题 1"
    input_template: |
      从以下分析中，请执行第一个子课题的调研：

      {analyze.output}

      使用搜索工具广泛搜集信息，并整理成结构化的调研笔记。

  - id: research_2
    agent_id: research-agent
    description: "调研子课题 2"
    input_template: |
      从以下分析中，请执行第二个子课题的调研：

      {analyze.output}

      使用搜索工具广泛搜集信息，并整理成结构化的调研笔记。

  - id: merge
    agent_id: writer-agent
    description: "合并所有调研结果"
    input_template: |
      请将以下调研结果合并成一份综合报告：

      原始需求：
      {workflow.input}

      子课题分析：
      {analyze.output}

      调研结果 1：
      {research_1.output}

      调研结果 2：
      {research_2.output}

      请写一份结构清晰、信息完整的综合报告。

edges:
  - from: analyze
    to: research_1
  - from: analyze
    to: research_2
  - from: research_1
    to: merge
  - from: research_2
    to: merge

entry_node: analyze
exit_nodes: [merge]
```

---

## 4. API 设计

### 4.1 Agent 管理 API

```
GET    /api/agents                    → 列出所有 Agent
GET    /api/agents/{agent_id}         → 获取 Agent 详情
POST   /api/agents                    → 创建新 Agent
PUT    /api/agents/{agent_id}         → 更新 Agent 配置
DELETE /api/agents/{agent_id}         → 删除 Agent（不能删除 default）
PUT    /api/agents/{agent_id}/preferences → 更新工具/技能偏好（现有 API 保持不变）
```

### 4.2 Workflow 管理 API

```
GET    /api/workflows                 → 列出所有 Workflow
GET    /api/workflows/{workflow_id}   → 获取 Workflow 定义
POST   /api/workflows                 → 创建新 Workflow
PUT    /api/workflows/{workflow_id}   → 更新 Workflow 定义
DELETE /api/workflows/{workflow_id}   → 删除 Workflow
POST   /api/workflows/{workflow_id}/run → 手动触发 Workflow 执行
GET    /api/workflows/runs            → 列出所有执行记录
GET    /api/workflows/runs/{run_id}   → 获取执行详情（含节点结果）
```

### 4.3 WebSocket 协议扩展

```python
# 创建会话时指定 agent_id
{
    "type": "create_session",
    "payload": {
        "agent_id": "research-agent"    # 可选，默认 "default"
    }
}

# 触发工作流
{
    "type": "run_workflow",
    "session_id": "sess_xxx",
    "payload": {
        "workflow_id": "plan-execute-review",
        "input": "帮我调研 RAG 技术方案"
    }
}

# 工作流状态推送（服务端 → 客户端）
{
    "type": "workflow.node_started",
    "session_id": "sess_xxx",
    "payload": {
        "run_id": "wf_run_xxx",
        "node_id": "search",
        "agent_id": "research-agent"
    }
}

{
    "type": "workflow.node_completed",
    "session_id": "sess_xxx",
    "payload": {
        "run_id": "wf_run_xxx",
        "node_id": "search",
        "status": "completed",
        "output_preview": "找到了 15 篇相关文章..."
    }
}
```

---

## 5. 系统集成

### 5.1 main.py 改造

```python
# main.py lifespan 中新增初始化

# 初始化 AgentRegistry
agent_config_dir = Path(config.get("system.workspace_dir", ".")) / "agents"
agent_registry = AgentRegistry(config_dir=agent_config_dir)
agent_registry.load_from_config(config.data)
agent_registry.load_from_dir()

# 初始化 WorkflowRegistry
workflow_config_dir = Path(config.get("system.workspace_dir", ".")) / "workflows"
workflow_registry = WorkflowRegistry(config_dir=workflow_config_dir)
workflow_registry.load_from_dir()

# 改造 AgentRuntime，注入 AgentRegistry
agent_runtime = AgentRuntime(
    bus_router=bus_router,
    repo=repo,
    context_builder=context_builder,
    tool_registry=tool_registry,
    state_store=state_store,
    agent_registry=agent_registry,
    memory_manager=memory_manager,
)

# 初始化 WorkflowRuntime
workflow_runtime = WorkflowRuntime(
    agent_registry=agent_registry,
    workflow_registry=workflow_registry,
    bus_router=bus_router,
    repo=repo,
    publisher=publisher,
)

# 注册多 Agent 相关 Tool
tool_registry.register(DelegateTool(
    agent_registry=agent_registry,
    bus_router=bus_router,
    repo=repo,
))
tool_registry.register(WorkflowTool(workflow_runtime=workflow_runtime))

# 挂载到 app.state
app.state.agent_registry = agent_registry
app.state.workflow_registry = workflow_registry
app.state.workflow_runtime = workflow_runtime
```

### 5.2 配置文件扩展

```yaml
# config.yml

# 多 Agent 配置
agents:
  research-agent:
    name: "Research Agent"
    description: "专注于信息调研"
    model: gpt-4o
    system_prompt: "你是调研专家..."
    tools: [serper_search, fetch_url]
    can_delegate_to: []

  writer-agent:
    name: "Writer Agent"
    description: "专注于文档写作"
    model: gpt-4o-mini
    temperature: 0.7
    system_prompt: "你是写作助手..."
    tools: [write_file, read_file]

# 委托配置
delegation:
  max_depth: 3
  default_timeout: 300
  enabled: true

# 工作流配置
workflow:
  enabled: true
  max_concurrent_runs: 3
  default_timeout: 1800
```

---

## 6. 架构图

### 6.1 多 Agent 架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                      前端 (Next.js)                               │
│  ┌────────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │  对话界面      │  │  Agent 配置  │  │  Workflow 编辑器     │  │
│  │ (选择 Agent)   │  │  管理页面    │  │  (节点+边可视化)     │  │
│  └────────────────┘  └─────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                            │ WebSocket
┌──────────────────────────────────────────────────────────────────┐
│                      后端 (FastAPI)                               │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   AgentRegistry                             │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────┐       │  │
│  │  │ default  │  │research-agent│  │ writer-agent   │  ...  │  │
│  │  └──────────┘  └──────────────┘  └────────────────┘       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 WorkflowRegistry                            │  │
│  │  ┌────────────────────┐  ┌──────────────────────┐         │  │
│  │  │ plan-execute-review│  │ research-and-merge   │  ...    │  │
│  │  └────────────────────┘  └──────────────────────┘         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    PublicEventBus                          │   │
│  └───────────────────────────────────────────────────────────┘   │
│           │                │                │                     │
│  ┌────────┴─────┐  ┌──────┴─────┐  ┌───────┴──────┐             │
│  │  BusRouter   │  │ EventPersist│  │   Gateway    │             │
│  └──────┬───────┘  └────────────┘  └──────────────┘             │
│         │                                                         │
│    ┌────┼────┬─────────┐                                         │
│    ↓    ↓    ↓         ↓                                         │
│  Priv  Priv  Priv    Priv                                        │
│  Bus1  Bus2  Bus3    BusN                                        │
│    ↓    ↓    ↓         ↓                                         │
│  ┌───┐ ┌───┐ ┌───┐  ┌───┐                                      │
│  │W-1│ │W-2│ │W-3│  │W-N│  ← Workers (使用不同 AgentConfig)     │
│  └───┘ └───┘ └───┘  └───┘                                      │
│    │                                                              │
│    └── Agent/LLM/Tool Workers 引用各自 AgentConfig               │
│        的 provider, model, tools, skills                         │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  WorkflowRuntime                            │  │
│  │  - 接收 workflow 执行请求                                    │  │
│  │  - DAG 调度：创建子 session → 注入 user.input → 等待完成     │  │
│  │  - 并行执行 + 聚合 + 条件分支                                │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 委托执行序列图

```
User        Gateway      AgentWorker-A     DelegateTool     BusRouter     AgentWorker-B
  │            │               │                │              │               │
  │──input──→│               │                │              │               │
  │            │──user.input──→│                │              │               │
  │            │               │──llm.call──→  │              │               │
  │            │               │  (决定委托)    │              │               │
  │            │               │──tool.call──→ │              │               │
  │            │               │  (delegate)   │              │               │
  │            │               │               │──create──→  │               │
  │            │               │               │  sub-session │               │
  │            │               │               │──user.input──→──create──→  │
  │            │               │               │              │  Worker-B    │
  │            │               │               │              │               │──llm.call
  │            │               │               │              │               │──tool.call
  │            │               │               │              │               │──...
  │            │               │               │              │               │──step_done
  │            │               │               │◄─result──────│◄──────────── │
  │            │               │◄─tool.result──│              │               │
  │            │               │──llm.call──→  │              │               │
  │            │               │  (总结结果)    │              │               │
  │            │               │──step_done──→ │              │               │
  │            │◄──────────── │               │              │               │
  │◄─response─│               │                │              │               │
```

---

## 7. 实施计划

### Phase 1: 多 Agent 基础设施（3天）

| 任务 | 内容 | 改动文件 |
|------|------|----------|
| AgentRegistry | 数据模型 + CRUD + 从 config 加载 | 新增 `agent_registry.py` |
| AgentRuntime 改造 | 根据 session 绑定的 agent_id 创建 Worker | `agent_runtime.py` |
| AgentSessionWorker 改造 | 使用 AgentConfig 选择 provider/model/tools/skills | `agent_worker.py` |
| ContextBuilder 改造 | 根据 AgentConfig 注入 system prompt 和 skills | `context_builder.py` |
| Agent API | CRUD REST API | 改造 `agents.py` |
| 单元测试 | AgentRegistry + 多 Agent 配置加载 | 新增测试文件 |

### Phase 2: 委托机制（2天）

| 任务 | 内容 | 改动文件 |
|------|------|----------|
| DelegateTool | 创建子 session + 等待完成 + 超时 | 新增 `delegate_tool.py` |
| 事件类型 | delegate 相关事件 | `types.py` |
| main.py 集成 | 注册 DelegateTool | `main.py` |
| E2E 测试 | Agent A 委托 Agent B 执行搜索任务 | 新增测试文件 |

### Phase 3: Workflow 引擎（3天）

| 任务 | 内容 | 改动文件 |
|------|------|----------|
| WorkflowRegistry | 数据模型 + CRUD + YAML 加载 + DAG 验证 | 新增 `workflow_registry.py` |
| WorkflowRuntime | DAG 调度核心 + 并行 + 聚合 + 条件分支 | 新增 `workflow_runtime.py` |
| WorkflowTool | Agent 触发工作流 | 新增 `workflow_tool.py` |
| Workflow API | CRUD + 执行 + 查看结果 | 新增 `workflow_api.py` |
| 内置模板 | plan-execute-review + fan-out-merge | 新增 YAML 文件 |
| E2E 测试 | 两个模板的完整执行 | 新增测试文件 |

### Phase 4: 前端支持（2天）

| 任务 | 内容 |
|------|------|
| Agent 配置页 | 创建/编辑/删除 Agent，配置 tools/skills/prompt |
| Workflow 编辑器 | 节点+边的可视化编辑器，YAML 预览 |
| 对话中的 Agent 选择 | 创建会话时选择 Agent |
| Workflow 执行状态 | 实时显示节点执行进度 |

**总计: 约 10 天**

---

## 8. 验收标准

| 编号 | 验收条件 | 优先级 |
|------|---------|--------|
| A1 | 可通过 config.yml 定义多个 Agent | P0 |
| A2 | 不同 Agent 使用不同的 system prompt / tools / model | P0 |
| A3 | 前端可创建指定 Agent 的会话 | P0 |
| A4 | 主 Agent 能通过 delegate 工具将任务委托给子 Agent | P0 |
| A5 | 委托执行异步完成，事件总线通知 | P0 |
| A6 | 委托深度超过限制时拒绝 | P0 |
| A7 | 子 Agent 崩溃时父 Agent 收到超时错误 | P0 |
| W1 | 可通过 YAML 定义 Workflow | P1 |
| W2 | Workflow 按 DAG 拓扑顺序执行节点 | P1 |
| W3 | 多个无依赖节点并行执行 | P1 |
| W4 | 条件边正确分支 | P1 |
| W5 | plan-execute-review 模板端到端执行 | P1 |
| W6 | fan-out-merge 模板端到端执行 | P1 |
| W7 | 前端实时显示 Workflow 节点执行状态 | P2 |

---

## 9. 被否决的方案及理由

| 方案 | 否决理由 |
|------|---------|
| 为每个 Agent 创建独立的 Runtime 实例 | 资源浪费。Agent 配置不同但执行引擎相同，共享 Runtime 单例 + Worker 引用 AgentConfig 更高效 |
| Agent 间通信用直接方法调用 | 丢失事件可观测性。通过事件总线 + 子 session 可以完整追踪委托链 |
| Workflow 用代码定义（Python DSL） | 声明式 YAML 更易于非技术用户理解和编辑，也便于 UI 可视化 |
| Workflow 支持循环（while 节点） | 增加复杂度。条件回退 + max_iterations 足够覆盖"重试"场景 |
| 用 LangGraph / CrewAI 等框架 | AgentOS 已有完整的事件驱动基础设施，引入外部框架会产生阻抗不匹配。保持自建 |
| Agent 热切换（运行中更换 Agent 配置） | 引发状态一致性问题。session 创建时绑定 Agent 配置，运行中不变 |

---

## 10. 与现有系统的兼容性

| 维度 | 兼容策略 |
|------|---------|
| **默认 Agent** | `id="default"` 始终存在，从 `config.yml` 的 `agent.*` 映射，向后兼容 |
| **单 Agent 使用场景** | 不配置 `agents.*` 时，系统行为与当前完全一致 |
| **事件总线** | PublicEventBus / PrivateEventBus / BusRouter 不变 |
| **数据库** | sessions 表新增 `agent_id` 列（默认 "default"），不影响现有数据 |
| **WebSocket 协议** | 新消息类型是新增的，现有消息类型不变 |
| **前端** | 新页面是新增的，现有页面不变 |
| **Cron / Heartbeat** | CronJob 的 `agent_id` 字段指向 AgentRegistry，自然支持多 Agent |

---

## 11. 未来扩展

本方案为以下能力预留了空间：

1. **Agent 模板市场**: AgentConfig 可以打包为模板分享
2. **Workflow 模板市场**: Workflow YAML 可以打包分享
3. **跨实例委托**: BusRouter 替换为 Redis Pub/Sub 后，Agent 可以跨进程/跨机器委托
4. **Agent 记忆隔离**: 每个 Agent 可以有独立的 MEMORY.md
5. **Workflow 版本管理**: Workflow 定义支持版本历史和回滚
6. **Agent 性能监控**: 基于事件持久化，分析每个 Agent 的调用量、成功率、延迟
7. **动态 Workflow**: Agent 在运行时动态生成 Workflow DAG（结合 LLM 的规划能力）

---

## 12. 术语表

| 术语 | 定义 |
|------|------|
| **AgentConfig** | Agent 的配置描述，定义行为边界（prompt + tools + skills + model） |
| **AgentRegistry** | 管理所有 AgentConfig 的注册表 |
| **DelegateTool** | Agent 间委托的桥接工具，创建子 session 并等待结果 |
| **子 Session** | 委托执行时创建的独立会话，绑定到目标 Agent 的配置 |
| **委托深度** | 嵌套委托的层级数，受 max_delegation_depth 限制 |
| **Workflow** | 预定义的执行流程，由 Node + Edge 组成的 DAG |
| **WorkflowNode** | 工作流中的一个执行单元，绑定一个 AgentConfig |
| **WorkflowEdge** | 连接两个 Node 的有向边，可附带条件表达式 |
| **WorkflowRun** | 一次 Workflow 执行的实例 |
| **Fan-out** | 一个节点向多个节点并行发出任务 |
| **Fan-in / Merge** | 多个节点的结果汇聚到一个节点 |
| **模板变量** | Workflow 输入模板中的变量引用，如 `{node_id.output}` |

---

## 相关文档

- [01_architecture.md](./01_architecture.md) - 系统架构总览
- [02_event_system.md](./02_event_system.md) - 事件系统设计
- [03_core_modules.md](./03_core_modules.md) - 核心模块详解
- [14_dual_bus_architecture.md](./14_dual_bus_architecture.md) - 双总线架构（多 Agent 的基础设施）
- [13_skills_system.md](./13_skills_system.md) - Skills 系统（Agent 配置的一部分）
