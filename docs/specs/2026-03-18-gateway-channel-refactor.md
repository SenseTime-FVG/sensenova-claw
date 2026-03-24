# Gateway/Channel 架构重构设计

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Gateway/Channel 架构从"Gateway 空壳 + main.py 巨型端点"重构为"Channel 协议适配+认证 → Gateway 统一业务 API → EventBus"的清晰分层。

**Architecture:** Channel 负责协议转换和各自的认证，Gateway 提供统一业务接口（会话 CRUD、消息收发、事件查询），main.py 只做启动和组装。Client 多连接由 Channel 内部管理，Gateway 只认 Channel 不认具体 client。

---

## 分层职责

```
Client (Web/飞书/CLI)
  ↕
Channel (协议适配 + 各自认证)
  ↕
Gateway (统一业务 API：会话管理、消息收发、事件路由)
  ↕
EventBus → Runtime
```

### Channel 层

- 协议适配：将外部协议（WebSocket/HTTP/飞书回调/CLI stdin）转为统一的方法调用
- 各自认证：WebSocketChannel 验 token，FeishuChannel 验飞书签名，CLIChannel 无需认证
- 多 client 管理：Channel 内部维护连接集合，Gateway 不感知
- 不做业务逻辑，只翻译协议并调用 Gateway 方法

### Gateway 层

- 统一业务接口：所有 Channel 通过相同的方法与 Gateway 交互
- 会话管理：创建/加载/删除/重命名
- 事件路由：订阅 PublicEventBus，分发到绑定的 Channel
- Channel 注册管理
- 不做认证，不关心请求来自哪种 Channel

## Gateway 统一接口

```python
class Gateway:
    # Channel 管理
    def register_channel(channel: Channel) -> None
    def bind_session(session_id: str, channel_id: str) -> None
    def unbind_session(session_id: str) -> None

    # 会话管理
    async def create_session(agent_id: str, meta: dict, channel_id: str) -> dict
    async def load_session(session_id: str, channel_id: str) -> dict
    async def delete_session(session_id: str) -> None
    async def rename_session(session_id: str, title: str) -> None
    async def list_sessions(limit: int = 50) -> list[dict]

    # 消息收发
    async def send_user_input(session_id: str, content: str, attachments: list, context_files: list) -> str
    async def cancel_turn(session_id: str, reason: str) -> None
    async def confirm_tool(session_id: str, tool_call_id: str, approved: bool) -> None

    # 查询
    async def list_agents() -> list[dict]
    async def get_messages(session_id: str) -> list[dict]
    async def get_session_events(session_id: str) -> list[dict]
    async def get_session_turns(session_id: str) -> list[dict]

    # 事件路由（内部）
    async def _loop() -> None  # 订阅 bus，分发到 channel
    async def _dispatch_event(event: EventEnvelope) -> None

    # 主动消息（OutboundCapable channel）
    async def send_outbound(channel_id: str, target: str, text: str, **kwargs) -> dict
```

## Channel 认证

| Channel | 认证方式 | 说明 |
|---------|----------|------|
| WebSocketChannel | Token（cookie/query param） | 连接时验证，复用现有 `verify_websocket()` |
| FeishuChannel | 飞书签名（app_id/app_secret） | 现有逻辑不变 |
| CLI（通过 WebSocket） | 自动读取 `~/.sensenova-claw/token` | 已实现，Channel 层验证 |

## Channel 多 client 管理

Channel 内部维护连接集合，Gateway 只认 Channel 不认具体 client。

```python
# WebSocketChannel 内部
_connections: set[WebSocket]
_session_bindings: dict[str, set[WebSocket]]  # session_id → 多个连接

# FeishuChannel 内部
_chat_sessions: dict[str, str]  # session_key → session_id
```

Gateway 调用 `channel.send_event(event)` 时，Channel 自行决定发给哪些 client。

## WebSocketChannel 重构

新增 `handle_connection(websocket)` 方法，接管整个 WS 连接生命周期：

```python
class WebSocketChannel(Channel):
    async def handle_connection(self, websocket: WebSocket) -> None:
        """处理单个 WebSocket 连接的完整生命周期"""
        # 1. 认证
        if auth_enabled and not verify_websocket(websocket, auth_service):
            await websocket.close(code=1008)
            return
        # 2. 接受连接
        await self.connect(websocket)
        # 3. 消息循环
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(websocket, message)
        except WebSocketDisconnect:
            self.disconnect(websocket)

    async def _handle_message(self, websocket, message) -> None:
        """将 WS 消息翻译为 Gateway 方法调用"""
        msg_type = message.get("type")
        if msg_type == "create_session":
            result = await self.gateway.create_session(...)
            await self.send_json(websocket, {"type": "session_created", ...})
        elif msg_type == "user_input":
            await self.gateway.send_user_input(...)
        # ... 其他消息类型
```

## main.py 简化

重构后 WebSocket 端点变为一行：

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await app.state.services.ws_channel.handle_connection(websocket)
```

HTTP API 端点调用 Gateway 方法：

```python
@app.get("/api/sessions")
async def list_sessions():
    sessions = await app.state.services.gateway.list_sessions()
    return JSONResponse(content={"sessions": sessions})
```

HTTP 认证中间件保留在 main.py（保护 REST API）。

## 文件变动

| 文件 | 变化 | 说明 |
|------|------|------|
| `interfaces/ws/gateway.py` | 大改 | 新增统一 API 方法，接管会话管理逻辑，依赖 repo |
| `adapters/channels/websocket_channel.py` | 大改 | 新增 `handle_connection()`、`_handle_message()`、认证 |
| `adapters/channels/base.py` | 小改 | Channel 基类增加 `gateway` 属性 |
| `app/gateway/main.py` | 大改 | 删除 WS 消息处理和认证，HTTP 端点改为调 Gateway |
| `adapters/plugins/feishu/channel.py` | 小改 | 适配新 Gateway API 签名 |
| `platform/security/middleware.py` | 不变 | WebSocketChannel 内部复用 |

## 不变的部分

- EventBus 事件流转机制不变
- Runtime 层不变
- 前端不变（WS 消息格式不变）
- CLI 不变
- 飞书 Channel 的认证和消息处理逻辑不变，只适配 Gateway API
