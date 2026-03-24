# 事件总线与路由

## 概述

Sensenova-Claw 的事件总线由三个核心组件构成：**PublicEventBus**（全局广播）、**PrivateEventBus**（会话隔离）、**BusRouter**（路由桥梁）。它们共同实现了事件的广播、路由和会话隔离。

---

## PublicEventBus

### 职责

全局事件广播系统，是所有事件的入口和出口。

### 实现原理

- 基于 `asyncio.Queue` 实现
- 支持多个订阅者，每个订阅者获得独立的事件流
- `subscribe()` 返回异步迭代器，订阅者通过 `async for` 消费事件

### 核心接口

```python
class PublicEventBus:
    async def publish(self, event: EventEnvelope) -> None:
        """发布事件，广播给所有订阅者"""

    def subscribe(self) -> AsyncIterator[EventEnvelope]:
        """订阅事件流，返回异步迭代器"""
```

### 订阅者

PublicEventBus 有以下主要订阅者：

| 订阅者 | 用途 |
|--------|------|
| **BusRouter** | 按 session_id 路由事件到 PrivateEventBus |
| **EventPersister** | 将所有事件持久化到 SQLite |
| **Gateway** | 将事件推送给对应的 Channel（前端/CLI/飞书） |
| **TitleRuntime** | 监听 `agent.step_completed` 生成会话标题 |

---

## PrivateEventBus

### 职责

每个 session 独占一个 PrivateEventBus 实例，实现会话间的**物理隔离**。

### 实现原理

- 同样基于 `asyncio.Queue`
- 由 BusRouter 按需创建（懒加载）
- 该 session 的所有 Worker 订阅同一个 PrivateEventBus
- Worker 产生的新事件回流到 PublicEventBus（而非直接发布到 PrivateEventBus）

### 核心接口

```python
class PrivateEventBus:
    async def publish(self, event: EventEnvelope) -> None:
        """发布事件到此会话的总线"""

    def subscribe(self) -> AsyncIterator[EventEnvelope]:
        """订阅此会话的事件流"""

    async def close(self) -> None:
        """关闭总线，释放资源"""
```

### 为什么需要 PrivateEventBus

- **性能**：Worker 只收到自己 session 的事件，无需过滤全局事件流
- **隔离**：一个 session 的异常不会影响其他 session
- **生命周期**：session 结束后，对应的 PrivateEventBus 和 Worker 可以被回收

---

## BusRouter

### 职责

连接 PublicEventBus 和 PrivateEventBus 的桥梁，是事件路由的核心组件。

### 核心功能

1. **事件路由**：根据 `event.session_id` 将事件从 PublicEventBus 转发到对应的 PrivateEventBus
2. **懒加载创建**：首次收到某 session 的 `user.input` 时，创建该 session 的 PrivateEventBus 和 Worker
3. **Worker 创建**：通过 factory pattern，使用各 Runtime 注册的 factory 创建 Worker
4. **生命周期管理**：基于超时机制回收不活跃的 PrivateEventBus（默认 TTL 3600 秒）

### 核心接口

```python
class BusRouter:
    def register_worker_factory(self, name: str, factory: Callable) -> None:
        """注册 Worker 工厂函数（由 Runtime 调用）"""

    async def start(self) -> None:
        """开始监听 PublicEventBus 并路由事件"""

    async def stop(self) -> None:
        """停止路由，关闭所有 PrivateEventBus"""
```

### 路由逻辑

```
PublicEventBus 事件到达
      │
      ▼
读取 event.session_id
      │
      ├── 已存在对应 PrivateEventBus？
      │     │
      │     ├── 是 → 直接转发到该 PrivateEventBus
      │     │
      │     └── 否 → 且事件类型为 user.input？
      │             │
      │             ├── 是 → 创建 PrivateEventBus + Worker → 转发
      │             │
      │             └── 否 → 丢弃（orphan 事件）
      │
      ▼
更新 TTL 计时器
```

### Worker 创建过程

当 BusRouter 为新 session 创建 PrivateEventBus 时，会同时通过已注册的 factory 创建所有 Worker：

```
BusRouter 检测到新 session
      │
      ▼
创建 PrivateEventBus(session_id)
      │
      ▼
遍历已注册的 worker factory
      │
      ├── AgentRuntime.factory → AgentSessionWorker(session_id)
      ├── LLMRuntime.factory   → LLMSessionWorker(session_id)
      └── ToolRuntime.factory  → ToolSessionWorker(session_id)
      │
      ▼
所有 Worker 订阅 PrivateEventBus
      │
      ▼
转发 user.input 事件到 PrivateEventBus
```

### TTL 回收机制

- 每个 PrivateEventBus 有一个最后活跃时间
- 每次收到该 session 的事件时更新活跃时间
- BusRouter 定期检查，超过 TTL（默认 3600 秒）未活跃的 session 会被回收
- 回收时关闭 PrivateEventBus 并销毁所有 Worker

---

## 数据流关系图

```
                         ┌──────────────────┐
                         │  EventPersister   │
                         │  (持久化到 SQLite)  │
                         └────────▲─────────┘
                                  │ subscribe
                                  │
  ┌─────────┐  publish   ┌───────┴──────────┐  subscribe   ┌──────────┐
  │ Channel  │──────────►│  PublicEventBus   │◄────────────│ Gateway   │
  │(前端/CLI) │           │  (全局广播)        │             │(推送响应)  │
  └─────────┘           └───────┬──────────┘             └──────────┘
                                │ subscribe
                                │
                         ┌──────▼──────────┐
                         │   BusRouter      │
                         │ (按 session 路由)  │
                         └──────┬──────────┘
                    ┌───────────┼───────────┐
                    │           │           │
             ┌──────▼──┐ ┌─────▼───┐ ┌─────▼───┐
             │Private   │ │Private   │ │Private   │
             │EventBus  │ │EventBus  │ │EventBus  │
             │(session1)│ │(session2)│ │(session3)│
             └──────┬──┘ └─────┬───┘ └─────┬───┘
                    │          │           │
              ┌─────▼────┐    ...         ...
              │ Workers   │
              │ ┌────────┐│
              │ │Agent   ││──┐
              │ │Worker  ││  │ 新事件回流
              │ ├────────┤│  │
              │ │LLM     ││  ├──► PublicEventBus
              │ │Worker  ││  │
              │ ├────────┤│  │
              │ │Tool    ││──┘
              │ │Worker  ││
              │ └────────┘│
              └───────────┘
```

### 事件流转总结

1. **入口**：Channel 或 Worker 将事件发布到 PublicEventBus
2. **广播**：PublicEventBus 将事件广播给所有订阅者（BusRouter、EventPersister、Gateway、TitleRuntime）
3. **路由**：BusRouter 根据 session_id 将事件转发到对应的 PrivateEventBus
4. **消费**：Worker 从 PrivateEventBus 消费事件并处理
5. **回流**：Worker 产生的新事件发布回 PublicEventBus，重新开始流转
