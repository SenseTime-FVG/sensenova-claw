# WebSocket 通信协议

## 概述

前后端通过 WebSocket 进行实时双向通信，所有消息使用 JSON 格式。

## 连接建立

### 客户端连接

```typescript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
    console.log('Connected to AgentOS');
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    handleMessage(message);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected from AgentOS');
};
```

### 服务端处理

```python
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await handle_client_message(websocket, data)
    except WebSocketDisconnect:
        await handle_disconnect(websocket)
```

## 消息格式

### 基础消息结构

```typescript
interface WebSocketMessage {
    type: string;           // 消息类型
    session_id?: string;    // 会话ID
    payload: any;           // 消息负载
    timestamp: number;      // 时间戳
}
```

## 客户端发送的消息类型

### 1. user_input
用户发送消息。

```json
{
    "type": "user_input",
    "session_id": "sess_123",
    "payload": {
        "content": "帮我写一个Python函数",
        "attachments": [],
        "context_files": ["/path/to/file.py"]
    },
    "timestamp": 1709640513.123
}
```

### 2. create_session
创建新会话。

```json
{
    "type": "create_session",
    "payload": {
        "meta": {
            "title": "新对话",
            "model": "gpt-4"
        }
    },
    "timestamp": 1709640513.123
}
```

### 3. cancel_turn
取消当前轮次。

```json
{
    "type": "cancel_turn",
    "session_id": "sess_123",
    "payload": {
        "turn_id": "turn_456"
    },
    "timestamp": 1709640513.123
}
```

### 4. list_sessions
获取会话列表。

```json
{
    "type": "list_sessions",
    "payload": {
        "limit": 50
    },
    "timestamp": 1709640513.123
}
```

### 5. load_session
加载历史会话。

```json
{
    "type": "load_session",
    "payload": {
        "session_id": "sess_123"
    },
    "timestamp": 1709640513.123
}
```

## 服务端发送的消息类型

### 1. session_created
会话创建成功。

```json
{
    "type": "session_created",
    "session_id": "sess_123",
    "payload": {
        "created_at": 1709640513.123
    },
    "timestamp": 1709640513.123
}
```

### 2. agent_thinking
Agent 正在思考。

```json
{
    "type": "agent_thinking",
    "session_id": "sess_123",
    "payload": {
        "step_type": "llm_call",
        "description": "正在调用 GPT-4..."
    },
    "timestamp": 1709640513.123
}
```

### 3. agent_response
Agent 响应内容（可能分块发送）。

```json
{
    "type": "agent_response",
    "session_id": "sess_123",
    "payload": {
        "content": "这是响应内容",
        "is_final": false
    },
    "timestamp": 1709640513.123
}
```

### 4. tool_execution
工具执行状态。

```json
{
    "type": "tool_execution",
    "session_id": "sess_123",
    "payload": {
        "tool_name": "bash_command",
        "status": "running",
        "arguments": {"command": "ls -la"}
    },
    "timestamp": 1709640513.123
}
```

### 5. tool_result
工具执行结果。

```json
{
    "type": "tool_result",
    "session_id": "sess_123",
    "payload": {
        "tool_call_id": "tool_call_789",
        "tool_name": "bash_command",
        "result": "file1.txt\nfile2.py",
        "success": true,
        "error": ""
    },
    "timestamp": 1709640513.123
}
```

### 6. llm_result
LLM 返回结果（支持流式）。

```json
{
    "type": "llm_result",
    "session_id": "sess_123",
    "payload": {
        "llm_call_id": "llm_abc123",
        "content": "这是LLM的响应内容",
        "tool_calls": [],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        },
        "finish_reason": "stop"
    },
    "timestamp": 1709640513.123
}
```

**说明**:
- `content`: LLM 生成的文本内容
- `tool_calls`: 如果 LLM 决定调用工具，此字段包含工具调用信息
- `finish_reason`: 结束原因，可能的值：
  - `stop`: 正常结束
  - `tool_calls`: 需要调用工具
  - `length`: 达到最大长度限制
  - `error`: 发生错误

### 7. turn_completed
对话轮次完成。

```json
{
    "type": "turn_completed",
    "session_id": "sess_123",
    "payload": {
        "turn_id": "turn_456",
        "final_response": "任务已完成"
    },
    "timestamp": 1709640513.123
}
```

### 8. error
错误消息。

```json
{
    "type": "error",
    "session_id": "sess_123",
    "payload": {
        "error_type": "LLMError",
        "message": "API调用失败",
        "details": {"context": "Rate limit exceeded"}
    },
    "timestamp": 1709640513.123
}
```

### 9. sessions_list
会话列表响应。

```json
{
    "type": "sessions_list",
    "payload": {
        "sessions": [
            {
                "session_id": "sess_123",
                "created_at": 1709640513.123,
                "last_active": 1709640600.456,
                "meta": {"title": "重构代码"}
            }
        ]
    },
    "timestamp": 1709640513.123
}
```

## 事件到 WebSocket 消息的映射

### 后端事件转发规则

并非所有事件都需要发送到前端，只转发用户关心的事件：

| 事件类型 | WebSocket 消息类型 | 是否转发 | 说明 |
|---------|-------------------|---------|------|
| ui.user_input | - | 否 | 客户端已知 |
| agent.step_started | agent_thinking | 是 | Agent 开始思考 |
| agent.step_completed | turn_completed | 是 | 对话轮次完成 |
| llm.call_requested | agent_thinking | 是 | 开始调用 LLM |
| llm.call_result | llm_result | 是 | LLM 返回结果 |
| llm.call_completed | - | 否 | 内部流程控制 |
| tool.call_requested | tool_execution | 是 | 工具开始执行 |
| tool.call_completed | tool_result | 是 | 工具执行完成 |
| error.raised | error | 是 | 错误信息 |

### 转发逻辑

```python
async def forward_event_to_websocket(event: EventEnvelope, websocket: WebSocket):
    """将内部事件转换为 WebSocket 消息"""

    if event.type == "agent.step_started":
        await websocket.send_json({
            "type": "agent_thinking",
            "session_id": event.session_id,
            "payload": event.payload,
            "timestamp": event.ts
        })

    elif event.type == "llm.call_result":
        response = event.payload.get("response", {})
        await websocket.send_json({
            "type": "llm_result",
            "session_id": event.session_id,
            "payload": {
                "llm_call_id": event.payload.get("llm_call_id"),
                "content": response.get("content", ""),
                "tool_calls": response.get("tool_calls", []),
                "usage": event.payload.get("usage", {}),
                "finish_reason": event.payload.get("finish_reason", "stop")
            },
            "timestamp": event.ts
        })

    elif event.type == "tool.call_completed":
        await websocket.send_json({
            "type": "tool_result",
            "session_id": event.session_id,
            "payload": {
                "tool_call_id": event.payload.get("tool_call_id"),
                "tool_name": event.payload.get("tool_name"),
                "result": event.payload.get("result"),
                "success": event.payload.get("success", False),
                "error": event.payload.get("error", "")
            },
            "timestamp": event.ts
        })

    # ... 其他事件类型的转换
```

## 连接管理

### 连接池

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_to_client(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)
```

## 心跳机制

### 客户端心跳

```typescript
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'ping',
            timestamp: Date.now()
        }));
    }
}, 30000); // 每30秒发送一次
```

### 服务端响应

```python
if data["type"] == "ping":
    await websocket.send_json({
        "type": "pong",
        "timestamp": time.time()
    })
```

## 错误处理

### 客户端重连

```typescript
class WebSocketClient {
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onclose = () => {
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                setTimeout(() => {
                    this.reconnectAttempts++;
                    this.connect();
                }, 1000 * Math.pow(2, this.reconnectAttempts));
            }
        };
    }
}
```
