# Gateway/Channel 架构重构实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 main.py 中 ~250 行 WebSocket 消息处理逻辑移入 Gateway（业务 API）和 WebSocketChannel（协议适配+认证），实现 Client → Channel → Gateway → EventBus 分层。

**Architecture:** Gateway 新增统一业务方法（create_session/send_user_input 等），依赖 repo 和 agent_registry。WebSocketChannel 新增 handle_connection() 处理完整 WS 生命周期，内含认证和消息循环。main.py 的 WS 端点简化为一行委托，HTTP 端点改为调 Gateway 方法。

**Tech Stack:** Python 3.12, FastAPI, asyncio, websockets

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `sensenova_claw/interfaces/ws/gateway.py` | 大改 | 新增统一业务 API，接管会话管理，依赖 repo/agent_registry |
| `sensenova_claw/adapters/channels/base.py` | 小改 | Channel 基类增加 gateway 属性 |
| `sensenova_claw/adapters/channels/websocket_channel.py` | 大改 | 新增 handle_connection()，内含认证+消息循环 |
| `sensenova_claw/app/gateway/main.py` | 大改 | 删除 WS 消息处理，简化 HTTP 端点 |
| `sensenova_claw/adapters/plugins/feishu/channel.py` | 小改 | 适配 Gateway 新 API |
| `tests/unit/test_gateway_refactor.py` | 新建 | Gateway 统一 API 测试 |

---

### Task 1: 扩展 Gateway 统一业务 API

**Files:**
- Modify: `sensenova_claw/interfaces/ws/gateway.py`

- [ ] **Step 1: 给 Gateway 增加 repo 和 agent_registry 依赖**

Gateway.__init__ 新增参数，保留已有的 publisher/channels/session_bindings：

```python
class Gateway:
    def __init__(
        self,
        publisher: EventPublisher,
        repo=None,               # Repository（可选，向后兼容）
        agent_registry=None,     # AgentRegistry（可选）
    ):
        self.publisher = publisher
        self.repo = repo
        self.agent_registry = agent_registry
        self._channels: dict[str, Channel] = {}
        self._session_bindings: dict[str, str] = {}
        self._task: asyncio.Task | None = None
```

- [ ] **Step 2: 新增会话管理方法**

在 Gateway 类中添加（publish_from_channel 和事件路由保持不变）：

```python
async def create_session(self, agent_id: str = "default", meta: dict | None = None, channel_id: str = "") -> dict:
    """创建会话，返回 {session_id, created_at}"""
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session_meta = dict(meta or {})
    session_meta["agent_id"] = agent_id
    await self.repo.create_session(session_id=session_id, meta=session_meta)
    if channel_id:
        self.bind_session(session_id, channel_id)
    logger.info("Session created: %s (agent=%s, channel=%s)", session_id, agent_id, channel_id)
    return {"session_id": session_id, "created_at": time.time()}

async def load_session(self, session_id: str, channel_id: str = "") -> dict:
    """加载会话历史事件"""
    if channel_id:
        self.bind_session(session_id, channel_id)
    events = await self.repo.get_session_events(session_id)
    return {"session_id": session_id, "events": events}

async def delete_session(self, session_id: str) -> None:
    """删除会话及相关数据"""
    await self.repo.delete_session_cascade(session_id)
    self.unbind_session(session_id)
    logger.info("Session deleted: %s", session_id)

async def rename_session(self, session_id: str, title: str) -> None:
    """重命名会话"""
    await self.repo.update_session_title(session_id, title)
    logger.info("Session renamed: %s -> %s", session_id, title)

async def list_sessions(self, limit: int = 50) -> list[dict]:
    """列出会话"""
    return await self.repo.list_sessions(limit=limit)
```

- [ ] **Step 3: 新增消息和查询方法**

```python
async def send_user_input(
    self, session_id: str, content: str,
    attachments: list | None = None, context_files: list | None = None,
    source: str = "websocket",
) -> str:
    """发送用户输入，返回 turn_id"""
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    await self.publish_from_channel(
        EventEnvelope(
            type=USER_INPUT,
            session_id=session_id,
            turn_id=turn_id,
            source=source,
            payload={
                "content": content,
                "attachments": attachments or [],
                "context_files": context_files or [],
            },
        )
    )
    return turn_id

async def cancel_turn(self, session_id: str, reason: str = "user_cancel", source: str = "websocket") -> None:
    """取消当前轮次"""
    await self.publish_from_channel(
        EventEnvelope(
            type=USER_TURN_CANCEL_REQUESTED,
            session_id=session_id,
            source=source,
            payload={"reason": reason},
        )
    )

async def confirm_tool(self, session_id: str, tool_call_id: str, approved: bool, source: str = "websocket") -> None:
    """工具确认响应"""
    await self.publish_from_channel(
        EventEnvelope(
            type=TOOL_CONFIRMATION_RESPONSE,
            session_id=session_id,
            source=source,
            payload={"tool_call_id": tool_call_id, "approved": approved},
        )
    )

async def list_agents(self) -> list[dict]:
    """列出可用 Agent"""
    if not self.agent_registry:
        return []
    return [
        {"id": a.id, "name": a.name, "description": a.description, "model": a.model}
        for a in self.agent_registry.list_all()
    ]

async def get_messages(self, session_id: str) -> list[dict]:
    """获取会话消息历史"""
    return await self.repo.get_session_messages(session_id)

async def get_session_events(self, session_id: str) -> list[dict]:
    """获取会话事件"""
    return await self.repo.get_session_events(session_id)

async def get_session_turns(self, session_id: str) -> list[dict]:
    """获取会话轮次"""
    return await self.repo.get_session_turns(session_id)
```

- [ ] **Step 4: 添加必要的 import**

文件顶部添加：
```python
import time
import uuid
from sensenova_claw.kernel.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED, TOOL_CONFIRMATION_RESPONSE
```

- [ ] **Step 5: 验证 import**

Run: `python3 -c "from sensenova_claw.interfaces.ws.gateway import Gateway; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/interfaces/ws/gateway.py
git commit -m "refactor: Gateway 新增统一业务 API（会话管理、消息收发、查询）"
```

---

### Task 2: Channel 基类增加 gateway 引用

**Files:**
- Modify: `sensenova_claw/adapters/channels/base.py`

- [ ] **Step 1: 给 Channel 基类添加 gateway 属性**

```python
class Channel(ABC):
    """Channel 抽象基类"""

    gateway: "Gateway | None"  # 由 Gateway.register_channel() 注入

    def __init__(self):
        self.gateway = None

    # ... 其他方法不变
```

注意：现有子类（WebSocketChannel、FeishuChannel）的 `__init__` 需要调用 `super().__init__()`。

- [ ] **Step 2: Gateway.register_channel() 注入 gateway 引用**

在 `gateway.py` 的 `register_channel` 中添加：

```python
def register_channel(self, channel: Channel) -> None:
    channel_id = channel.get_channel_id()
    self._channels[channel_id] = channel
    channel.gateway = self  # 注入引用
    logger.info(f"Registered channel: {channel_id}")
```

- [ ] **Step 3: Commit**

```bash
git add sensenova_claw/adapters/channels/base.py sensenova_claw/interfaces/ws/gateway.py
git commit -m "refactor: Channel 基类增加 gateway 引用，由注册时注入"
```

---

### Task 3: WebSocketChannel 接管连接生命周期和认证

**Files:**
- Modify: `sensenova_claw/adapters/channels/websocket_channel.py`

- [ ] **Step 1: 新增 handle_connection() 方法**

在 WebSocketChannel 中添加，把 main.py 的 WS 消息循环和认证移入：

```python
async def handle_connection(self, websocket: WebSocket) -> None:
    """处理单个 WebSocket 连接的完整生命周期（认证+消息循环）"""
    from sensenova_claw.platform.config.config import config
    from sensenova_claw.platform.security.middleware import verify_websocket

    # 认证
    auth_enabled = config.get("security.auth_enabled", False)
    if auth_enabled:
        # auth_service 从 gateway 获取（gateway 持有 Services 引用不合适，通过属性注入）
        auth_service = getattr(self, '_auth_service', None)
        if auth_service and not verify_websocket(websocket, auth_service):
            logger.warning("WebSocket connection rejected: invalid or missing token")
            await websocket.close(code=1008, reason="Invalid or missing token")
            return

    await self.connect(websocket)
    logger.info("WebSocket client connected")

    try:
        while True:
            message = await websocket.receive_json()
            await self._handle_message(websocket, message)
    except WebSocketDisconnect:
        self.disconnect(websocket)
    except Exception as exc:
        logger.exception("WebSocket connection error")
        self.disconnect(websocket)
        try:
            await self.send_json(websocket, {
                "type": "error",
                "payload": {"error_type": type(exc).__name__, "message": str(exc), "details": {}},
                "timestamp": time.time(),
            })
        except Exception:
            pass
```

- [ ] **Step 2: 新增 _handle_message() 方法**

将每种消息类型翻译为 Gateway 方法调用：

```python
async def _handle_message(self, websocket: WebSocket, message: dict) -> None:
    """将 WS 消息翻译为 Gateway 方法调用"""
    msg_type = message.get("type")
    payload = message.get("payload", {})
    session_id = message.get("session_id")
    gw = self.gateway

    logger.info("Received WS message: %s", msg_type)

    if msg_type == "create_session":
        agent_id = payload.get("agent_id", "default")
        meta = payload.get("meta", {})
        result = await gw.create_session(agent_id=agent_id, meta=meta, channel_id=self._channel_id)
        sid = result["session_id"]
        self.bind_session(sid, websocket)
        await self.send_json(websocket, {
            "type": "session_created", "session_id": sid,
            "payload": {"created_at": result["created_at"]}, "timestamp": time.time(),
        })
        return

    if msg_type == "list_sessions":
        sessions = await gw.list_sessions(limit=int(payload.get("limit", 50)))
        await self.send_json(websocket, {
            "type": "sessions_list", "payload": {"sessions": sessions}, "timestamp": time.time(),
        })
        return

    if msg_type == "load_session":
        sid = payload.get("session_id")
        if sid:
            result = await gw.load_session(sid, channel_id=self._channel_id)
            self.bind_session(sid, websocket)
            await self.send_json(websocket, {
                "type": "session_loaded", "session_id": sid,
                "payload": {"events": result["events"]}, "timestamp": time.time(),
            })
        return

    if msg_type == "user_input":
        if not session_id:
            result = await gw.create_session(channel_id=self._channel_id)
            session_id = result["session_id"]
            self.bind_session(session_id, websocket)
            await self.send_json(websocket, {
                "type": "session_created", "session_id": session_id,
                "payload": {"created_at": result["created_at"]}, "timestamp": time.time(),
            })
        await gw.send_user_input(
            session_id=session_id,
            content=payload.get("content", ""),
            attachments=payload.get("attachments", []),
            context_files=payload.get("context_files", []),
            source="websocket",
        )
        return

    if msg_type == "cancel_turn":
        if session_id:
            await gw.cancel_turn(session_id, source="websocket")
        return

    if msg_type == "delete_session":
        sid = payload.get("session_id")
        if sid:
            try:
                await gw.delete_session(sid)
                self._session_bindings.pop(sid, None)
                await self.send_json(websocket, {
                    "type": "session_deleted", "payload": {"session_id": sid}, "timestamp": time.time(),
                })
            except Exception as e:
                await self.send_json(websocket, {
                    "type": "error", "payload": {"message": f"删除会话失败: {e}"}, "timestamp": time.time(),
                })
        return

    if msg_type == "rename_session":
        sid = payload.get("session_id") or session_id
        title = payload.get("title", "")
        if sid and title:
            try:
                await gw.rename_session(sid, title)
                await self.send_json(websocket, {
                    "type": "session_renamed", "payload": {"session_id": sid, "title": title}, "timestamp": time.time(),
                })
            except Exception as e:
                await self.send_json(websocket, {
                    "type": "error", "payload": {"message": f"重命名会话失败: {e}"}, "timestamp": time.time(),
                })
        else:
            await self.send_json(websocket, {
                "type": "error", "payload": {"message": "需要 session_id 和 title"}, "timestamp": time.time(),
            })
        return

    if msg_type == "list_agents":
        agents = await gw.list_agents()
        await self.send_json(websocket, {
            "type": "agents_list", "payload": {"agents": agents}, "timestamp": time.time(),
        })
        return

    if msg_type == "tool_confirmation_response":
        if session_id:
            await gw.confirm_tool(
                session_id=session_id,
                tool_call_id=payload.get("tool_call_id"),
                approved=payload.get("approved", False),
                source="websocket",
            )
        return

    if msg_type == "get_messages":
        sid = payload.get("session_id") or session_id
        messages = await gw.get_messages(sid) if sid else []
        await self.send_json(websocket, {
            "type": "messages_list", "payload": {"messages": messages}, "timestamp": time.time(),
        })
        return

    # 未知消息类型
    await self.send_json(websocket, {
        "type": "error",
        "payload": {"error_type": "InvalidMessage", "message": f"unsupported message type: {msg_type}"},
        "timestamp": time.time(),
    })
```

- [ ] **Step 3: 添加必要的 import**

文件顶部添加：
```python
import time
from fastapi import WebSocketDisconnect
```

- [ ] **Step 4: WebSocketChannel.__init__ 调用 super().__init__() 并接受 auth_service**

```python
def __init__(self, channel_id: str = "websocket", auth_service=None):
    super().__init__()
    self._channel_id = channel_id
    self._connections: set[WebSocket] = set()
    self._session_bindings: dict[str, set[WebSocket]] = {}
    self._auth_service = auth_service
```

- [ ] **Step 5: 验证 import**

Run: `python3 -c "from sensenova_claw.adapters.channels.websocket_channel import WebSocketChannel; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/adapters/channels/websocket_channel.py sensenova_claw/adapters/channels/base.py
git commit -m "refactor: WebSocketChannel 接管连接生命周期（认证+消息循环+Gateway 调用）"
```

---

### Task 4: 简化 main.py

**Files:**
- Modify: `sensenova_claw/app/gateway/main.py`

- [ ] **Step 1: 更新 Gateway 初始化，传入 repo 和 agent_registry**

将 `lifespan` 中的：
```python
gateway = Gateway(publisher=publisher)
```
改为：
```python
gateway = Gateway(publisher=publisher, repo=repo, agent_registry=agent_registry)
```

- [ ] **Step 2: 更新 WebSocketChannel 初始化，传入 auth_service**

在 `lifespan` 中，将 ws_channel 的创建移到 auth_service 之后：
```python
auth_service = TokenAuthService(sensenova_claw_home=sensenova_claw_home)
ws_channel = WebSocketChannel("websocket", auth_service=auth_service)
```

- [ ] **Step 3: 替换 WebSocket 端点为一行委托**

将 `@app.websocket("/ws")` 下的 ~250 行替换为：

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await app.state.services.ws_channel.handle_connection(websocket)
```

- [ ] **Step 4: HTTP 端点改为调 Gateway 方法**

```python
@app.get("/api/sessions")
async def list_sessions():
    sessions = await app.state.services.gateway.list_sessions()
    return JSONResponse(content={"sessions": sessions})

@app.get("/api/sessions/{session_id}/turns")
async def get_session_turns(session_id: str):
    turns = await app.state.services.gateway.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})

@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str):
    events = await app.state.services.gateway.get_session_events(session_id)
    return JSONResponse(content={"events": events})

@app.get("/api/sessions/{session_id}/messages")
async def list_session_messages(session_id: str):
    messages = await app.state.services.gateway.get_messages(session_id)
    return JSONResponse(content={"messages": messages})
```

- [ ] **Step 5: 清理不再需要的 import**

从 main.py 移除：
- `from sensenova_claw.kernel.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED, TOOL_CONFIRMATION_RESPONSE`
- `from sensenova_claw.kernel.events.envelope import EventEnvelope`（如果其他地方不用）
- `from sensenova_claw.platform.security.middleware import verify_websocket`（已移入 Channel）

保留：
- `verify_request`（HTTP 中间件仍需要）
- `WebSocket`, `WebSocketDisconnect`（端点签名需要 WebSocket 类型）

- [ ] **Step 6: 验证启动**

Run: `python3 -c "from sensenova_claw.app.gateway.main import app; print('OK')"`

- [ ] **Step 7: Commit**

```bash
git add sensenova_claw/app/gateway/main.py
git commit -m "refactor: main.py 简化，WS 端点委托给 Channel，HTTP 端点调 Gateway"
```

---

### Task 5: 适配 FeishuChannel

**Files:**
- Modify: `sensenova_claw/adapters/plugins/feishu/channel.py`

- [ ] **Step 1: FeishuChannel.__init__ 调用 super().__init__()**

在 `__init__` 方法开头添加 `super().__init__()`。

- [ ] **Step 2: 将 gateway.publish_from_channel 调用改为 gateway 业务方法（可选）**

FeishuChannel 当前直接构造 EventEnvelope 并调 `gateway.publish_from_channel()`。
可以保持不变（Gateway 仍暴露 publish_from_channel），或改为调 `gateway.send_user_input()`。

推荐：先保持不变，后续单独优化。只需确保 `super().__init__()` 被调用。

- [ ] **Step 3: Commit**

```bash
git add sensenova_claw/adapters/plugins/feishu/channel.py
git commit -m "refactor: FeishuChannel 调用 super().__init__() 适配新基类"
```

---

### Task 6: 更新测试 fixture

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_cli_client.py`
- Modify: `tests/unit/test_cli_app_unit.py`

- [ ] **Step 1: 更新所有创建 Gateway 的地方，传入 repo**

搜索 `Gateway(publisher=` 出现的位置，改为 `Gateway(publisher=..., repo=repo)`。

- [ ] **Step 2: 更新 WebSocketChannel 创建，传入 auth_service**

搜索 `WebSocketChannel(` 出现的位置，确保与新签名兼容。

- [ ] **Step 3: 运行完整测试**

Run: `python3 -m pytest tests/unit/ -q --tb=short`

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: 更新测试 fixture 适配 Gateway/Channel 新签名"
```

---

### Task 7: 验证和最终提交

- [ ] **Step 1: 完整测试**

Run: `python3 -m pytest tests/unit/ -q --tb=line`

- [ ] **Step 2: 手动验证**

启动后端 → 打开前端 → 新建会话 → 发送消息 → 确认响应正常
启动 CLI → 发送消息 → 确认响应正常

- [ ] **Step 3: Push 并创建 PR**

```bash
git push
```
