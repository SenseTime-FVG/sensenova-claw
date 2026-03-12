# 双总线架构 PRD

## 背景

当前系统使用单一 PublicEventBus 广播所有事件，所有 Runtime 模块收到所有 session 的事件，依赖业务逻辑在事件处理函数内部过滤 `session_id` 实现隔离。

```python
# 当前代码（agent_runtime.py）
async for event in self.publisher.bus.subscribe():   # 收到所有 session 的事件
    if event.type == UI_USER_INPUT:
        # 在 state_store.get_turn(session_id, turn_id) 内部靠 key 过滤
        await self._handle_user_input(event)
```

**问题**：

1. **无物理隔离**：所有 session 的事件混在同一条总线上，靠业务逻辑过滤，调试时日志混杂难以追踪单个会话
2. **扩展性差**：未来如果需要跨进程/跨机器分布式部署，单总线无法按 session 拆分到不同节点

## 目标

实现双总线机制：PublicEventBus（全局）+ PrivateEventBus（每会话），通过 BusRouter 路由，Runtime 通过轻量 Worker 订阅私有总线，实现**真正的会话级物理隔离**。

---

## 架构设计

### 整体架构图

```
用户（Web / CLI / TUI）
        ↓
┌─────────────────────────────────────────────────────┐
│                    Gateway                           │
│  接收用户输入，发布到 PublicEventBus                   │
│  订阅 PublicEventBus，下发事件到对应 Channel           │
└──────────────────────┬──────────────────────────────┘
                       ↓ 发布
              ┌────────────────┐
              │ PublicEventBus │ ← 全局总线
              └───────┬────────┘
                      │
          ┌───────────┼─────────── 订阅 ──────────┐
          ↓           ↓                            ↓
     ┌─────────┐  ┌──────────┐              ┌──────────┐
     │BusRouter│  │事件持久化 │              │ 全局监控  │
     └────┬────┘  └──────────┘              └──────────┘
          │ 按 session_id 路由
    ┌─────┼──────┬──────────┐
    ↓     ↓      ↓          ↓
  Priv   Priv   Priv      Priv
  Bus1   Bus2   Bus3      BusN
    ↓     ↓      ↓          ↓
  Wkr1  Wkr2   Wkr3      WkrN    ← 轻量 Worker（每会话一个）
    │     │      │          │
    └─────┴──────┴──────────┘
          │ 回流
          ↓
   PublicEventBus（Gateway / 持久化 / 监控 收到）
```

### 核心概念

| 组件 | 数量 | 职责 |
|------|------|------|
| PublicEventBus | 1 个（全局） | 系统级广播：事件持久化、Gateway 下发、全局监控 |
| PrivateEventBus | N 个（每会话 1 个） | 会话级隔离：只流转该 session 的事件 |
| BusRouter | 1 个（全局） | 路由 + 生命周期管理：Public → Private 分发，GC 回收 |
| Runtime | 每类 1 个（全局单例） | 管理者：持有共享资源（LLM Provider、ToolRegistry），管理 Worker |
| SessionWorker | N 个（每会话 1 个） | 干活的人：订阅 PrivateEventBus，处理该会话的事件 |

**关键设计决策**：Runtime 是"厨师长"（单例，持有共享资源），Worker 是"接单员"（轻量，每会话一个，只负责监听和分派）。不为每个 session 复制一整套 Runtime，但每个 session 确实拥有自己的独立事件通道。

---

## 核心组件

### PublicEventBus（不变）

```python
class PublicEventBus:
    """全局事件总线，用于系统级广播"""
    _subscribers: set[asyncio.Queue[EventEnvelope]]

    async def publish(self, event: EventEnvelope) -> None:
        """广播事件到所有全局订阅者"""
        pass

    async def subscribe(self) -> AsyncIterator[EventEnvelope]:
        """订阅全局事件流"""
        pass
```

### PrivateEventBus（新增）

```python
class PrivateEventBus:
    """会话私有总线，物理隔离单个 session 的事件流"""
    session_id: str
    _subscribers: set[asyncio.Queue[EventEnvelope]]
    _public_bus: PublicEventBus   # 回流目标

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件：先分发给私有订阅者，再回流到公共总线"""
        # 1. 分发给本总线的订阅者（Worker 等）
        for q in list(self._subscribers):
            await q.put(event)
        # 2. 回流到 PublicEventBus（供 Gateway、持久化、监控消费）
        await self._public_bus.publish(event)

    async def subscribe(self) -> AsyncIterator[EventEnvelope]:
        """订阅私有事件流（Worker 调用）"""
        pass
```

**回流机制**：Worker 在 PrivateEventBus 上发布的事件（如 `llm.call_requested`）自动回流到 PublicEventBus，确保 Gateway（需要下发给用户）、事件持久化（写数据库）、全局监控等全局订阅者能收到所有事件。

### BusRouter（新增）

```python
class BusRouter:
    """事件路由器 + 私有总线生命周期管理"""
    _public_bus: PublicEventBus
    _private_buses: dict[str, PrivateEventBus]
    _last_active: dict[str, float]
    _ttl_seconds: int   # 从配置读取，默认 3600

    def get_or_create(self, session_id: str) -> PrivateEventBus:
        """惰性创建：首次访问时创建，已存在则复用并刷新活跃时间"""
        if session_id not in self._private_buses:
            self._private_buses[session_id] = PrivateEventBus(
                session_id=session_id,
                _public_bus=self._public_bus,
            )
        self._last_active[session_id] = time.time()
        return self._private_buses[session_id]

    def destroy(self, session_id: str) -> None:
        """销毁私有总线，释放资源"""
        # 关闭该总线的所有订阅者队列
        # 从字典中移除
        pass

    async def route_from_public(self, event: EventEnvelope) -> None:
        """从公共总线路由到对应的私有总线（下行方向）"""
        if event.session_id and event.session_id in self._private_buses:
            bus = self._private_buses[event.session_id]
            # 直接分发给私有订阅者，不回流（事件已在公共总线上了）
            for q in list(bus._subscribers):
                await q.put(event)

    async def _gc_loop(self) -> None:
        """GC 协程：定期清理超时未活跃的私有总线"""
        while True:
            await asyncio.sleep(60)
            now = time.time()
            expired = [
                sid for sid, last in self._last_active.items()
                if now - last > self._ttl_seconds
            ]
            for sid in expired:
                self.destroy(sid)
```

### Runtime + SessionWorker

```python
class AgentRuntime:
    """全局单例（管理者），持有共享资源，管理 Worker 生命周期"""

    def __init__(self, bus_router: BusRouter, repo: Repository,
                 context_builder: ContextBuilder, tool_registry: ToolRegistry,
                 state_store: SessionStateStore):
        self.bus_router = bus_router
        self.repo = repo
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.state_store = state_store
        self._workers: dict[str, AgentSessionWorker] = {}

    async def ensure_worker(self, session_id: str) -> AgentSessionWorker:
        """确保 session 有对应的 Worker，没有则创建"""
        if session_id not in self._workers:
            private_bus = self.bus_router.get_or_create(session_id)
            worker = AgentSessionWorker(
                session_id=session_id,
                private_bus=private_bus,
                runtime=self,         # Worker 引用管理者的共享资源
            )
            self._workers[session_id] = worker
            await worker.start()
        return self._workers[session_id]

    async def start(self) -> None:
        """启动：订阅公共总线，收到 user.input 时为对应 session 创建 Worker"""
        self._task = asyncio.create_task(self._bootstrap_loop())

    async def _bootstrap_loop(self) -> None:
        """只负责"接活"：收到新 session 的事件时创建 Worker"""
        async for event in self.bus_router._public_bus.subscribe():
            if event.type == USER_INPUT:
                await self.ensure_worker(event.session_id)
                # Worker 创建后会自行从 PrivateEventBus 收到事件


class AgentSessionWorker:
    """轻量级会话处理器，订阅 PrivateEventBus，处理单个 session 的事件"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: AgentRuntime):
        self.session_id = session_id
        self.bus = private_bus
        self.rt = runtime         # 引用管理者获取共享资源
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        async for event in self.bus.subscribe():
            # 无需过滤 session_id —— PrivateEventBus 保证只有本 session 的事件
            if event.type == USER_INPUT:
                await self._handle_user_input(event)
            elif event.type == LLM_CALL_RESULT:
                await self._handle_llm_result(event)
            elif event.type == LLM_CALL_COMPLETED:
                await self._handle_llm_completed(event)
            elif event.type == TOOL_CALL_RESULT:
                await self._handle_tool_result(event)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        content = event.payload.get("content", "")
        turn_id = event.turn_id or f"turn_{uuid.uuid4().hex[:12]}"

        await self.rt.repo.create_session(self.session_id, meta={"title": content[:20]})
        history = self.rt.state_store.get_session_history(self.session_id)
        messages = self.rt.context_builder.build_messages(content, history)
        # ...构建 state，发布 llm.call_requested 到 PrivateEventBus...
        await self.bus.publish(EventEnvelope(type=LLM_CALL_REQUESTED, ...))
```

**开销对比**：

| | 原 PRD（per-session Runtime） | 改进（Runtime + Worker） |
|--|--|--|
| AgentRuntime | N 个实例 | 1 个单例 + N 个 Worker |
| LLMRuntime | N 个实例 | 1 个单例 + N 个 Worker |
| ToolRuntime | N 个实例 | 1 个单例 + N 个 Worker |
| 共享资源 | 每个实例各持一份 | 单例持有，Worker 引用 |
| 每 session 开销 | 3 个完整 Runtime + 3 个 Task | 3 个轻量 Worker + 3 个 Task |
| 物理隔离 | 有 | 有（Worker 订阅 PrivateEventBus） |

Worker 本质上只是一个 `asyncio.Task` + 几个事件处理方法的引用，不持有独立资源，开销远小于完整 Runtime。

---

## 事件流转详解

以用户在 Web 输入 "搜索最新新闻"（session 301）为例，完整数据流如下：

```
┌──────┐    ┌─────────┐    ┌────────────────┐    ┌───────────┐
│ 用户  │───→│ Gateway  │───→│ PublicEventBus │───→│ BusRouter │
│(Web) │    │          │    │                │    │           │
└──────┘    └─────────┘    └───────┬────────┘    └─────┬─────┘
                    ▲              │                    │
                    │              │ 订阅               │ 路由
                    │              ↓                    ↓
                    │       ┌────────────┐    ┌──────────────────┐
                    │       │ 事件持久化  │    │ PrivateEventBus  │
                    │       │ (写入 DB)  │    │    session-301    │
                    │       └────────────┘    └────────┬─────────┘
                    │              ▲                    │
                    │              │ 回流               │ 订阅
                    │              │                    ↓
                    │       ┌──────┴───┐    ┌──────────────────────────────┐
                    │       │ Public   │    │     SessionWorkers-301       │
                    │       │ EventBus │    │                              │
                    │       └──────────┘    │  AgentWorker ←→ LLMWorker   │
                    │              ▲        │       ↕                      │
                    │              │ 回流    │  ToolWorker                  │
                    │              │        └──────────────────────────────┘
                    │              │                    │
                    │              └────────────────────┘
                    │                    所有 Worker 发布的事件
                    │                    通过 PrivateEventBus 回流
                    │                         │
                    │                         ↓
                    │                  PublicEventBus
                    │                         │
                    └─────────────────────────┘
                      Gateway 订阅 PublicEventBus
                      找到 session-301 的 Channel 下发
```

**逐步数据流**：

```
步骤  事件                   位置                     方向
───────────────────────────────────────────────────────────────
 ①   user.input             Gateway → PublicEventBus   用户输入进入系统
 ②   user.input             BusRouter → PrivBus-301    路由到私有总线（不回流）
 ③   agent.step_started     PrivBus-301 → PublicBus    AgentWorker 发布，回流
 ④   llm.call_requested     PrivBus-301 → PublicBus    AgentWorker 发布，回流
 ⑤   llm.call_started       PrivBus-301 → PublicBus    LLMWorker 发布，回流
 ⑥   llm.call_result        PrivBus-301 → PublicBus    LLMWorker 发布（含 tool_calls）
 ⑦   llm.call_completed     PrivBus-301 → PublicBus    LLMWorker 发布
 ⑧   tool.call_requested    PrivBus-301 → PublicBus    AgentWorker 发布
 ⑨   tool.call_started      PrivBus-301 → PublicBus    ToolWorker 发布
 ⑩   tool.call_result       PrivBus-301 → PublicBus    ToolWorker 发布（含搜索结果）
 ⑪   tool.call_completed    PrivBus-301 → PublicBus    ToolWorker 发布
 ⑫   llm.call_requested     PrivBus-301 → PublicBus    AgentWorker 带工具结果再次请求 LLM
 ⑬   llm.call_result        PrivBus-301 → PublicBus    LLMWorker 发布（最终响应）
 ⑭   llm.call_completed     PrivBus-301 → PublicBus    LLMWorker 发布
 ⑮   agent.step_completed   PrivBus-301 → PublicBus    AgentWorker 发布
 ⑯   (WebSocket 下发)        PublicBus → Gateway → 用户  Gateway 匹配 session-301
```

**关键观察**：
- ①→② 是唯一的**下行路由**（Public → Private），由 BusRouter 执行，不触发回流
- ③~⑮ 全部在 PrivateEventBus-301 上产生，**自动回流**到 PublicEventBus
- 回流保证了事件持久化和 Gateway 下发不受影响
- 整个过程中 session 302、303 等其他会话的 Worker **完全看不到**这些事件

---

## 生命周期管理

### 创建策略：惰性创建

```
用户首次发消息 → BusRouter.get_or_create(session_id)
                 → 创建 PrivateEventBus
                 → Runtime.ensure_worker(session_id)
                 → 创建 SessionWorker 并 start
```

不是连接建立时创建，而是**首次有事件时**才创建。这样：
- 建立 WebSocket 连接但不发消息 → 不消耗资源
- 从历史会话列表点进去但不说话 → 不消耗资源

### 断连策略：保留 + 超时回收

```
WebSocket 断开
  ↓
Gateway 通知 BusRouter.mark_inactive(session_id)
  ↓
PrivateEventBus 和 Worker 保留（不销毁）
  ↓
用户 30 秒后重连同一 session
  ↓
BusRouter.get_or_create(session_id) → 命中已有总线，直接复用
  ↓
Worker 仍在运行，无感知
```

```
WebSocket 断开
  ↓
BusRouter.mark_inactive(session_id)
  ↓
超过 TTL（默认 1 小时）无活动
  ↓
GC 协程执行 destroy：
  1. 停止该 session 的所有 Worker（cancel Task）
  2. 关闭 PrivateEventBus 的所有订阅者队列
  3. 从 _private_buses 字典中移除
  4. 从 Runtime._workers 字典中移除
```

### 配置项

```yaml
bus:
  private_bus_ttl: 3600          # 私有总线存活时间（秒），超时未活跃则回收
  gc_interval: 60                # GC 扫描间隔（秒）
```

---

## 路由规则

| 事件类型 | 方向 | 说明 |
|----------|------|------|
| `system.*` | 仅 PublicEventBus | 系统级事件，不路由到私有总线 |
| `user.*`, `agent.*`, `llm.*`, `tool.*` | Public → BusRouter → Private | 下行：Gateway 发到公共总线后路由到对应私有总线 |
| Worker 发布的所有事件 | Private → Public（回流） | 上行：Worker 的输出回流到公共总线，供 Gateway/持久化/监控消费 |

**防重复**：`route_from_public` 分发到私有总线时不经过 `PrivateEventBus.publish`（不触发回流），直接往私有订阅者队列放，避免事件在公共→私有→公共之间无限循环。

---

## 优势

1. **物理隔离**：每个会话的事件在独立 PrivateEventBus 中流转，Worker 无需过滤 `session_id`
2. **资源高效**：Runtime 单例持有共享资源（LLM Provider、ToolRegistry），Worker 只是轻量引用
3. **调试友好**：可单独订阅某个 PrivateEventBus 追踪完整会话事件流
4. **断连恢复**：PrivateEventBus 和 Worker 保留，重连后无缝恢复
5. **内存可控**：GC 协程自动回收不活跃的总线和 Worker，防止泄漏
6. **可扩展**：未来分布式部署时，BusRouter 可替换为跨进程路由（如 Redis Pub/Sub）

## 兼容性

- Gateway、事件持久化、全局监控订阅 PublicEventBus 不变（通过回流机制保证能收到所有事件）
- 数据库存储逻辑不变
- 前端 WebSocket 协议不变

## 实施步骤

1. 实现 `PrivateEventBus`（含回流 + 防重复）和 `BusRouter`（含惰性创建 + GC）
2. 实现 `SessionWorker` 基类，将 AgentRuntime/LLMRuntime/ToolRuntime 的事件处理逻辑拆分为 Worker
3. 改造 Runtime 为管理者模式：`_bootstrap_loop` 监听新 session，`ensure_worker` 创建 Worker
4. 修改 Gateway 在 Channel 连接/断开时通知 BusRouter
5. 编写集成测试：验证会话隔离（两个 session 并发不串扰）
6. 编写集成测试：验证断连恢复（断开 → 重连 → Worker 仍在）
7. 压力测试：100 并发 session 的内存占用和 GC 回收效果
