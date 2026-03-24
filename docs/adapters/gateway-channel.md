# Gateway 与 Channel

> 路径：`sensenova_claw/interfaces/ws/`、`sensenova_claw/adapters/channels/`

Gateway 是用户接入的核心路由层，负责在各种 Channel（接入渠道）和 PublicEventBus 之间双向转发事件。

---

## Gateway

```python
class Gateway:
    _channels: dict[str, Channel]             # channel_id -> Channel
    _session_bindings: dict[str, str]         # session_id -> channel_id

    register_channel(channel)                  # 注册 Channel
    bind_session(session_id, channel_id)       # 绑定会话到 Channel
    publish_from_channel(event)                # Channel -> PublicEventBus

    _loop():                                   # 订阅 PublicEventBus
        for event in bus.subscribe():
            _dispatch_event(event)             # 路由到对应 Channel

    _dispatch_event(event):
        channel = _session_bindings[event.session_id]
        channel.send_event(event)              # 推送给用户
```

**核心职责**：

1. **Channel 管理**：注册和管理多个 Channel 实例
2. **会话绑定**：维护 `session_id` 到 `channel_id` 的映射关系
3. **上行路由**：将 Channel 收到的用户消息发布到 PublicEventBus
4. **下行路由**：订阅 PublicEventBus，将事件路由到对应 Channel 推送给用户

---

## Channel 抽象

```python
class Channel(ABC):
    get_channel_id() -> str
    start() / stop()
    send_event(event: EventEnvelope)           # 推送事件给用户
    event_filter() -> set[str] | None          # 事件类型过滤
```

| 方法 | 说明 |
|------|------|
| `get_channel_id()` | 返回 Channel 唯一标识 |
| `start()` / `stop()` | 生命周期管理 |
| `send_event(event)` | 将内部事件推送给用户端 |
| `event_filter()` | 返回该 Channel 关心的事件类型集合，`None` 表示接收所有事件 |

---

## WebSocketChannel

> 路径：`sensenova_claw/adapters/channels/websocket/`

WebSocketChannel 是 Web 前端的主要接入方式：

- 管理 FastAPI WebSocket 连接集合
- 绑定 `session_id -> set[WebSocket]`，支持同一会话多个连接
- 将内部 `EventEnvelope` 转换为前端消息格式（JSON）
- 处理 `cron.delivery_requested` 事件，广播给所有已连接的客户端

**连接生命周期**：

```
客户端连接 WebSocket
  → WebSocketChannel 记录连接
  → 绑定 session_id
  → 开始双向通信
  → 断开时清理连接
```

---

## FeishuChannel

> 路径：`sensenova_claw/adapters/plugins/feishu/`

FeishuChannel 支持飞书/钉钉机器人集成：

- 接收飞书 Webhook 回调消息
- 卡片渲染：将 Agent 响应转换为飞书卡片格式
- 支持 `OutboundCapable` 协议，实现主动推送消息能力
- 通过飞书 API 发送富文本消息和交互卡片

---

## 事件流向

完整的事件流向如下：

```
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌────────────────┐
│  用户端   │ ──>│  Channel   │ ──>│ Gateway  │ ──>│ PublicEventBus │
│(浏览器等) │    │(WebSocket) │    │          │    │                │
└──────────┘    └───────────┘    └──────────┘    └────────────────┘
                                                         │
                                                         ▼
                                                  Runtime 处理
                                                  (Agent/LLM/Tool)
                                                         │
                                                         ▼
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌────────────────┐
│  用户端   │ <──│  Channel   │ <──│ Gateway  │ <──│ PublicEventBus │
│(浏览器等) │    │(WebSocket) │    │          │    │                │
└──────────┘    └───────────┘    └──────────┘    └────────────────┘
```

**上行（用户 -> 系统）**：

```
用户消息 → WebSocket → Channel → Gateway → PublicEventBus
```

**下行（系统 -> 用户）**：

```
PublicEventBus → Gateway → Channel → WebSocket → 前端
```

Gateway 通过 `session_id` 确定事件应该路由到哪个 Channel，Channel 再根据自身维护的连接映射将事件推送到具体的用户连接。
