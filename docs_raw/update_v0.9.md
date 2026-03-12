# PRD: AgentOS v0.9 — 飞书 Channel 增强与 Agent 主动通信能力

> 版本: update_v0.9
> 日期: 2026-03-11
> 项目: AgentOS
> 前置: update_v0.7（Plugin + 飞书 Channel）, update_v0.8（Cron + Heartbeat）
> 参考: OpenClaw `extensions/feishu/`, `src/agents/tools/message-tool.ts`, `src/infra/outbound/`
> 方法论: 第一性原理推演 + 苏格拉底追问

---

## 0. 为什么要先追问，再动手

上一轮对话给出了三个方案：MessageTool、流式推送、Markdown Card。看起来合理，但合理不等于正确。以下用苏格拉底追问法逐层质疑，剥去假设，找到真正该做的事。

---

## 1. 苏格拉底追问：十个关键质疑

### Q1: Agent 给飞书发消息的本质需求是什么？

**表面需求**: Agent 需要一个 `message` tool 来主动发消息。

**追问**: 什么叫"主动"？细分场景：

| 场景 | 触发方 | 目标 | 当前能不能做 |
|------|--------|------|-------------|
| 用户发消息 → Agent 回复 | 被动（飞书入站） | 回原会话 | ✅ 已有（`AGENT_STEP_COMPLETED` → `send_event`） |
| Cron 到时间 → Agent 跑任务 → 推送结果 | 主动（系统内部） | 指定用户/群 | ❌ 没有出站通道 |
| 用户在 WebSocket 说"通知飞书群" | 主动（跨 channel） | 飞书群 | ❌ 没有跨 channel 路由 |
| Agent 执行中途 → 给用户发进度 | 半主动（同会话中间状态） | 回原会话 | ❌ 只有 step_completed 有出站 |

**结论**: "主动发消息"其实是三个不同的问题——**跨 channel 路由**、**无 session 的出站投递**、**中间状态推送**。不能用一个 tool 一锅端。

---

### Q2: MessageTool 应该绕过事件总线吗？

**上一轮方案**: `MessageTool.execute()` 直接调用 `channel.send_outbound()`，绕过事件总线。

**追问**: 这样做会丢失什么？

1. **审计性** — 事件总线有 EventPersister，所有事件都入库。绕过后这条消息无迹可查。
2. **一致性** — Gateway 的事件分发逻辑被旁路，两套出站路径增加维护成本。
3. **可测试性** — 直接调 channel 方法需要 mock channel 实例，不如 mock 事件更简单。

**反追问**: 但 Tool 需要同步返回结果（"发送成功/失败"），事件总线是异步的，怎么拿结果？

**解决方案**: **Tool 直接调用，但同时发一个 `message.outbound_sent` 审计事件到 PublicEventBus**。这是 OpenClaw 的实际做法——`runMessageAction` 是同步调用链，但执行完后结果仍然回流到事件系统。

```
MessageTool.execute()
  → Gateway.send_outbound(channel, target, text)
    → channel.send_outbound(target, text)  # 同步等待飞书 API 返回
    → bus.publish(message.outbound_sent)    # 异步审计，不阻塞
  → return {success, message_id}            # 同步给 LLM
```

---

### Q3: Channel 基类该加 `send_outbound` 吗？

**追问**: 所有 Channel 都需要主动发消息能力吗？

- WebSocket Channel：是双向的，但 WebSocket 是连接态——没有"给指定用户发"的概念，只能给已连接的 WebSocket 推送。
- CLI Channel：同理，只能给当前终端回显。
- 飞书 Channel：可以。飞书 API 天然支持按 chat_id / open_id 发消息。
- 未来的 Telegram / Slack：也可以。

**结论**: `send_outbound` 不应该是 Channel 基类的必须方法，而是一个**可选能力**（Optional Capability）。

```python
class OutboundCapable:
    """标记接口：Channel 实现此接口表示支持主动出站"""
    async def send_outbound(self, target: str, text: str, **kwargs) -> dict:
        raise NotImplementedError
```

Channel 基类不变。FeishuChannel 同时继承 `Channel` 和 `OutboundCapable`。MessageTool 检测 channel 是否 `isinstance(channel, OutboundCapable)`。

---

### Q4: session_key 和 outbound 的关系——Agent 发了消息后对方回复怎么办？

**追问**: 这是上一轮方案完全遗漏的问题。

场景：Cron 任务通过 MessageTool 给用户 A 的飞书发了一条通知。用户 A 看到后回复。这条回复进入 `FeishuChannel._handle_message_event`，构造 `session_key = "dm:<A的open_id>"`。

- 如果 A 之前和 bot 没有对话过，`_chat_sessions` 中没有这个 key，会创建新 session。✅ 合理。
- 如果 A 之前有对话，会复用已有 session。❓ 但那个 session 的上下文是之前的对话，不是 Cron 通知的上下文。

**OpenClaw 的做法**: `ensureOutboundSessionEntry`——outbound 发送时创建或查找目标 session，并将发送记录写入该 session 的 transcript，这样对方回复时能看到完整上下文。

**AgentOS 应该做的最小化方案**: MessageTool 发送成功后，将这条消息作为 assistant message 追加到目标 session 的历史。如果目标 session 不存在，先创建。

```python
# MessageTool.execute() 发送成功后
session_key = f"dm:{target}" if is_user else f"group:{target}"
session_id = feishu_channel.ensure_session(session_key, target)
await repo.save_message(session_id=session_id, role="assistant", content=text)
```

---

### Q5: Markdown Card 真的是 P0 吗？

**追问**: 用户最经常收到的 Agent 回复是什么样的？

- 大部分是纯文本对话（自然语言回复）
- 包含代码块的回复（`bash_command` 工具的结果讨论）
- 包含表格的回复（搜索结果整理）

纯文本在飞书中渲染正常。代码块和表格在纯文本模式下不可读——代码没有高亮、表格没有对齐。

**但——飞书的 `post` 类型消息（富文本）本身支持 Markdown 渲染**。当前 AgentOS 用的是 `msg_type: "text"`。

**更正**: 不一定要上 interactive card。可以先升级到 `msg_type: "post"`（富文本），用飞书原生的 Markdown 支持。只有需要复杂交互（按钮、表单）时才需要 interactive card。

**实际上 OpenClaw 的默认模式就是 `post`**——看 `send.ts` 的 `buildFeishuPostMessagePayload`：

```typescript
// OpenClaw 默认用 post 类型，里面放 md tag
content: JSON.stringify({
  zh_cn: {
    content: [[{ tag: "md", text: messageText }]]
  }
}),
msgType: "post",
```

**修正方案**:

| 阶段 | 渲染方式 | 复杂度 |
|------|---------|--------|
| v0.9a | `msg_type: "post"` + `tag: "md"` | 改一行代码 |
| v0.9b | `msg_type: "interactive"` card（可选配置） | 加 card 构建逻辑 |

P0 应该是 **post 富文本**，不是 interactive card。这是 5 分钟就能改完的事。

---

### Q6: Typing indicator (reaction 模拟) 值不值得做？

**追问**: OpenClaw 为什么用 reaction 模拟 typing？有什么坑？

OpenClaw `reply-dispatcher.ts` 中的注释：

> "Feishu reactions persist until explicitly removed, so skip keepalive re-adds when a reaction already exists. Re-adding the same emoji triggers a new push notification for every call (#28660)."

也就是说，飞书的 reaction 不像 typing indicator 那样自动消失——每次 add reaction 都会触发一次推送通知。如果处理不当，用户会收到大量无意义的通知。

**另一个坑**: reaction 需要 `im:message:reaction` 权限，不是所有企业都开放了这个权限。

**结论**: Typing indicator 是**锦上添花但有坑**的功能。不放入 v0.9，作为 v1.0 的可选配置。当前的优先级应该让给更实际的东西。

---

### Q7: 飞书 Skill (feishu-doc / feishu-wiki / feishu-drive / feishu-perm) 能直接用吗？

**追问**: Skill 的本质是什么？是 system prompt 注入，指导 Agent 用工具完成任务。那 Agent 有没有对应的工具？

分析 `feishu-doc` SKILL.md 的核心内容——它教 Agent 调用飞书文档 API。但在 AgentOS 中：

- Agent 有 `bash_command` 工具 → 可以 `curl` 飞书 API？❌ 需要自己拼 access_token，太脆弱。
- Agent 没有 `feishu_api` 工具 → Skill 内容变成空话——知道怎么做但没手。

**现实**: Skills 依赖 Tools。如果没有 `feishu_api_call` 这样的 Tool，把 feishu-doc SKILL.md 放进去只是浪费 system prompt tokens。

**正确的依赖链**:

```
FeishuApiTool (能调飞书 API)
  → feishu-doc Skill (教 Agent 怎么用这个 tool 操作文档)
    → 用户说"帮我在飞书上建个文档" → Agent 知道怎么做，也能做
```

**v0.9 方案**: 先做 `FeishuApiTool`（通用飞书 API 调用工具），再启用 Skills。

---

### Q8: Gateway._dispatch_event 的事件过滤太粗——FeishuChannel 收不到有用的中间事件

**追问**: 当前 Gateway 订阅 PublicEventBus 后，将所有事件都 dispatch 给 Channel。但 FeishuChannel.send_event 只处理 `AGENT_STEP_COMPLETED` 和 `ERROR_RAISED`。

实际上 PublicEventBus 上流淌着大量事件：`agent.step_started`、`llm.call_requested`、`llm.call_result`、`tool.call_started`、`tool.call_result` 等。这些事件全部被 FeishuChannel 忽略了。

**问题**: 这不是 FeishuChannel 的问题——是 Gateway 的分发设计没有考虑"Channel 只关心哪些事件"。WebSocket Channel 可能想转发所有事件（前端要渲染 tool call 过程），飞书 Channel 只想要最终结果。

**方案**: 给 Channel 增加事件过滤声明。

```python
class Channel(ABC):
    def event_filter(self) -> set[str] | None:
        """返回此 Channel 关心的事件类型集合。None 表示接收所有事件。"""
        return None  # 默认全部接收（向后兼容）
```

FeishuChannel override:

```python
def event_filter(self) -> set[str]:
    return {
        AGENT_STEP_STARTED,    # 可选：显示"思考中"
        AGENT_STEP_COMPLETED,  # 核心：发送回复
        TOOL_CALL_STARTED,     # 可选：显示"正在执行 xxx"
        ERROR_RAISED,          # 核心：发送错误
    }
```

Gateway._dispatch_event 判断：

```python
async def _dispatch_event(self, event: EventEnvelope) -> None:
    # ...
    channel_filter = channel.event_filter()
    if channel_filter is not None and event.type not in channel_filter:
        return
    await channel.send_event(event)
```

---

### Q9: 消息长度和分片——Agent 可能输出很长的内容

**追问**: 飞书消息有长度限制吗？

- text 类型：无官方文档限制，但实测超长文本会被截断或发送失败
- post 类型：单个 `content` element 有限制
- interactive card：body.elements 中的 markdown content 限制约 10000 字符

当前 FeishuChannel 做了 20000 字符硬截断。但更好的做法是**分片发送**——OpenClaw 的 `chunkTextWithMode` 将长文本按 4000 字符分片，逐条发送。

**v0.9 方案**: 实现 `chunk_text(text, limit=4000)` 工具函数，FeishuChannel 出站时自动分片。

---

### Q10: 这些东西的真正依赖关系是什么？

经过上面 9 个追问，重新画依赖关系：

```
[改一行代码] post 富文本渲染
     ↓ (无依赖)
[0.5天] 消息分片 chunk_text
     ↓ (无依赖)
[0.5天] Channel.event_filter + 中间状态推送
     ↓ (无依赖)
[1天] OutboundCapable + FeishuChannel.send_outbound
     ↓
[1天] MessageTool + 出站 session 管理
     ↓
[0.5天] FeishuApiTool (通用飞书 API 调用)
     ↓
[启用] feishu-doc / feishu-wiki / feishu-drive Skills
     ↓
[2天] CronRuntime (v0.8 PRD，依赖 MessageTool 投递结果)
```

---

## 2. 修正后的方案设计

### 2.1 改动一：飞书 post 富文本渲染（5min，P0）

**问题**: 当前 `msg_type: "text"` 不渲染 Markdown。

**方案**: 改 `FeishuChannel._send_reply`，将 `msg_type` 从 `"text"` 改为 `"post"`，用飞书富文本的 `md` tag。

```python
# 变更前
content = json.dumps({"text": text})
msg_type = "text"

# 变更后
content = json.dumps({
    "zh_cn": {
        "content": [[{"tag": "md", "text": text}]]
    }
})
msg_type = "post"
```

单次改动，零风险，立即可用。代码块、表格、链接全部自动渲染。

如果需要更强的渲染（按钮、分栏），可通过配置 `render_mode: auto | raw | card` 切换到 interactive card 模式。这是后续可选增强，不阻塞。

---

### 2.2 改动二：消息分片（0.5天，P0）

**问题**: Agent 输出可能很长，飞书截断或发送失败。

**方案**: 工具函数 + 出站调用时自动分片。

```python
# backend/app/plugins/feishu/text.py

def chunk_text(text: str, limit: int = 4000) -> list[str]:
    """按换行符边界分片，单片不超过 limit 字符。

    优先在空行处切分（段落边界），其次在换行处切分，
    最后在 limit 处硬切。
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # 在 limit 范围内找最后一个空行
        cut = remaining.rfind("\n\n", 0, limit)
        if cut <= 0:
            # 找最后一个换行
            cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            # 硬切
            cut = limit

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")

    return chunks
```

`_send_reply` 中调用：

```python
async def _send_reply(self, session_id: str, text: str) -> None:
    # ... meta 查找 ...
    from app.plugins.feishu.text import chunk_text
    for chunk in chunk_text(text, limit=4000):
        await self._send_single_message(meta.chat_id, chunk)
```

---

### 2.3 改动三：Channel 事件过滤 + 中间状态推送（0.5天，P1）

**问题**: FeishuChannel 只在最终结果时回复，用户等待时间长没有反馈。

**方案**:

**a) Channel 基类增加 `event_filter`**（可选方法，向后兼容）：

```python
# backend/app/gateway/base.py
class Channel(ABC):
    # ... 已有 ...
    def event_filter(self) -> set[str] | None:
        """此 Channel 关心的事件类型。None = 全部。"""
        return None
```

**b) Gateway._dispatch_event 加过滤判断**：

```python
async def _dispatch_event(self, event: EventEnvelope) -> None:
    # ... 已有逻辑 ...
    event_types = channel.event_filter()
    if event_types is not None and event.type not in event_types:
        return
    await channel.send_event(event)
```

**c) FeishuChannel.send_event 处理更多事件**：

```python
def event_filter(self) -> set[str]:
    return {AGENT_STEP_COMPLETED, TOOL_CALL_STARTED, ERROR_RAISED}

async def send_event(self, event: EventEnvelope) -> None:
    if event.type == TOOL_CALL_STARTED:
        tool_name = event.payload.get("tool_name", "")
        if tool_name:
            await self._send_reply(event.session_id, f"⏳ 正在执行 {tool_name}...")
    elif event.type == AGENT_STEP_COMPLETED:
        text = (event.payload.get("result", {}).get("content", "")
                or event.payload.get("final_response", ""))
        if text:
            await self._send_reply(event.session_id, text)
    elif event.type == ERROR_RAISED:
        msg = event.payload.get("error_message", "处理失败")
        await self._send_reply(event.session_id, f"⚠️ {msg}")
```

**注意**: `TOOL_CALL_STARTED` 的中间推送应该是可配置的（有些用户觉得烦）。通过 `plugins.feishu.show_tool_progress: true/false` 控制。

---

### 2.4 改动四：OutboundCapable + FeishuChannel.send_outbound（1天，P1）

**问题**: Agent 无法主动给指定目标发消息。

**方案**:

**a) 定义 OutboundCapable 协议**：

```python
# backend/app/gateway/base.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class OutboundCapable(Protocol):
    """Channel 实现此协议表示支持主动出站消息"""
    async def send_outbound(
        self,
        target: str,
        text: str,
        msg_type: str = "post",
    ) -> dict:
        """向指定目标发送消息。返回 {success, message_id, ...}"""
        ...
```

不改 Channel ABC，零侵入。

**b) FeishuChannel 实现 OutboundCapable**：

```python
class FeishuChannel(Channel):  # 同时满足 OutboundCapable 协议

    async def send_outbound(self, target: str, text: str, msg_type: str = "post") -> dict:
        """主动出站：target 格式 chat_id | user:<open_id>"""
        if not self._client:
            return {"success": False, "error": "Client not initialized"}

        if target.startswith("user:"):
            receive_id, receive_id_type = target[5:], "open_id"
        else:
            receive_id, receive_id_type = target, "chat_id"

        from app.plugins.feishu.text import chunk_text
        last_result = {}
        for chunk in chunk_text(text, limit=4000):
            content = json.dumps({"zh_cn": {"content": [[{"tag": "md", "text": chunk}]]}})
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("post")
                    .content(content)
                    .build()
                ).build()
            )
            response = await asyncio.to_thread(self._client.im.v1.message.create, request)
            if not response.success():
                return {"success": False, "code": response.code, "msg": response.msg}
            last_result = {
                "success": True,
                "message_id": response.data.message_id,
            }
        return last_result
```

**c) Gateway 增加 outbound 路由**：

```python
# backend/app/gateway/gateway.py
class Gateway:
    # ... 已有 ...

    async def send_outbound(
        self, channel_id: str, target: str, text: str, **kwargs
    ) -> dict:
        """通过指定 Channel 发送主动出站消息"""
        channel = self._channels.get(channel_id)
        if not channel:
            return {"success": False, "error": f"Channel '{channel_id}' not found"}
        if not isinstance(channel, OutboundCapable):
            return {"success": False, "error": f"Channel '{channel_id}' does not support outbound"}
        return await channel.send_outbound(target=target, text=text, **kwargs)
```

---

### 2.5 改动五：MessageTool + 出站 session 管理（1天，P1）

**问题**: Agent 需要一个 tool 来主动发消息，且发送后对方回复能衔接上下文。

**方案**:

```python
# backend/app/tools/message_tool.py

from typing import Any
from app.tools.base import Tool

class MessageTool(Tool):
    name = "message"
    description = (
        "主动发送消息到指定渠道和目标。"
        "channel: 渠道名 (feishu/websocket)。"
        "target: 目标 ID (chat_id / user:<open_id>)。"
        "省略 channel 和 target 则回复当前会话。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send"],
                "description": "消息动作",
            },
            "channel": {
                "type": "string",
                "description": "目标渠道 (feishu)。省略则用当前会话的渠道。",
            },
            "target": {
                "type": "string",
                "description": "目标 ID。飞书: chat_id 或 user:<open_id>。",
            },
            "message": {
                "type": "string",
                "description": "消息内容 (支持 Markdown)",
            },
        },
        "required": ["action", "message"],
    }

    def __init__(self, gateway: "Gateway", publisher: "EventPublisher"):
        self._gateway = gateway
        self._publisher = publisher

    async def execute(self, **kwargs: Any) -> Any:
        channel = kwargs.get("channel", "feishu")
        target = kwargs.get("target")
        message = kwargs.get("message", "")

        if not target:
            return {"success": False, "error": "target is required for outbound send"}

        result = await self._gateway.send_outbound(
            channel_id=channel, target=target, text=message,
        )

        # 审计事件（异步，不阻塞）
        if result.get("success"):
            from app.events.envelope import EventEnvelope
            await self._publisher.publish(EventEnvelope(
                type="message.outbound_sent",
                session_id="",
                source="message_tool",
                payload={
                    "channel": channel,
                    "target": target,
                    "message_preview": message[:200],
                    "message_id": result.get("message_id"),
                },
            ))

        return result
```

**注册时机**（在 `main.py` 中 gateway 创建后、start 前）：

```python
from app.tools.message_tool import MessageTool
tool_registry.register(MessageTool(gateway=gateway, publisher=publisher))
```

**出站 session 管理**（确保对方回复时有上下文）：

在 FeishuChannel.send_outbound 成功后，需要做两件事：

1. 确保目标有对应的 session（如果没有就创建）
2. 将 assistant 消息追加到该 session 的历史

这需要 FeishuChannel 能访问 Repository。通过 PluginApi 传入：

```python
# FeishuChannel.send_outbound 成功后
session_key = f"dm:{receive_id}" if receive_id_type == "open_id" else f"group:{receive_id}"
with self._lock:
    session_id = self._chat_sessions.get(session_key)
    if not session_id:
        session_id = f"feishu_{uuid.uuid4().hex[:12]}"
        self._chat_sessions[session_key] = session_id
        self._session_meta[session_id] = FeishuSessionMeta(
            chat_id=receive_id if receive_id_type == "chat_id" else "",
            chat_type="p2p" if receive_id_type == "open_id" else "group",
            last_message_id="", sender_id="",
        )
```

---

### 2.6 改动六：FeishuApiTool（0.5天，P2）

**问题**: 飞书 Skills 需要一个能调飞书 API 的 Tool。

**方案**: 通用飞书 API 调用工具，复用 FeishuChannel 的 `lark.Client`。

```python
# backend/app/tools/feishu_api_tool.py

from typing import Any
from app.tools.base import Tool

class FeishuApiTool(Tool):
    name = "feishu_api"
    description = (
        "调用飞书开放平台 API。支持文档、知识库、云空间、权限等操作。"
        "method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)。"
        "path: API 路径 (如 /open-apis/docx/v1/documents)。"
        "body: 请求体 (JSON 对象)。"
        "params: URL 查询参数 (JSON 对象)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "description": "HTTP 方法",
            },
            "path": {
                "type": "string",
                "description": "飞书 API 路径 (如 /open-apis/docx/v1/documents)",
            },
            "body": {
                "type": "object",
                "description": "请求体",
            },
            "params": {
                "type": "object",
                "description": "URL 查询参数",
            },
        },
        "required": ["method", "path"],
    }

    def __init__(self, feishu_client):
        self._client = feishu_client

    async def execute(self, **kwargs: Any) -> Any:
        import asyncio
        import httpx

        method = kwargs.get("method", "GET")
        path = kwargs.get("path", "")
        body = kwargs.get("body")
        params = kwargs.get("params")

        # 获取 tenant_access_token
        token = await asyncio.to_thread(
            lambda: self._client._token_manager.get_tenant_access_token()
        )

        url = f"https://open.feishu.cn{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers,
                json=body, params=params,
            )
        return {
            "status_code": resp.status_code,
            "data": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:5000],
        }
```

有了这个 Tool，feishu-doc / feishu-wiki / feishu-drive / feishu-perm Skills 就能真正工作了。

---

## 3. 实施计划

### 3.1 分阶段交付

| 阶段 | 内容 | 工期 | 改动文件 |
|------|------|------|----------|
| **v0.9a** | post 富文本 + 消息分片 | **2小时** | `channel.py`(飞书), 新增 `text.py` |
| **v0.9b** | Channel 事件过滤 + 中间状态推送 | **0.5天** | `base.py`, `gateway.py`, `channel.py`(飞书) |
| **v0.9c** | OutboundCapable + send_outbound | **1天** | `base.py`, `gateway.py`, `channel.py`(飞书) |
| **v0.9d** | MessageTool + 出站 session | **1天** | 新增 `message_tool.py`, `main.py`, `channel.py`(飞书) |
| **v0.9e** | FeishuApiTool + 启用 Skills | **0.5天** | 新增 `feishu_api_tool.py`, `main.py` |

**总计: 3.5天**

### 3.2 v0.9a 改动极小，建议立即执行

只改 `FeishuChannel._send_reply` 的消息格式（text → post/md），加一个 `chunk_text` 函数。影响面极小，收益极大——Agent 所有回复立即支持 Markdown 渲染。

### 3.3 验收标准

| 阶段 | 验收 |
|------|------|
| v0.9a | 飞书收到的回复正确渲染代码块、表格、链接 |
| v0.9a | 超长回复自动分片发送，无截断 |
| v0.9b | Agent 执行工具时飞书显示"⏳ 正在执行 xxx..." |
| v0.9c | `channel.send_outbound("chat_xxx", "hello")` 飞书群收到消息 |
| v0.9d | Agent 调用 `message` tool 成功发送飞书消息；对方回复后上下文连续 |
| v0.9e | Agent 能根据 feishu-doc Skill 的指引，通过 feishu_api tool 创建飞书文档 |

---

## 4. 被否决的方案及理由

| 方案 | 否决理由 |
|------|---------|
| Typing indicator (reaction 模拟) | 飞书 reaction 每次添加都触发推送通知，实现复杂且干扰用户。推迟到 v1.0 作为可选配置。 |
| Streaming Card（实时更新卡片内容） | AgentOS 当前 LLM 调用是非流式的（参见 v0.2 架构）。没有流式输出，streaming card 无意义。前置依赖：LLM 流式响应。 |
| 直接把 OpenClaw 的 interactive card 移植过来 | 过度设计。飞书 post 类型的 md tag 已经覆盖 90% 的渲染需求。interactive card 只在需要按钮/表单时才必要。 |
| MessageTool 绕过事件总线且不做审计 | 丢失审计性。修正为：同步调用 + 异步审计事件。 |
| Channel 基类强制要求 send_outbound | 不是所有 Channel 都支持主动出站（WebSocket、CLI 都不支持）。改为 Protocol 类型检查。 |

---

## 5. 对 v0.8 (Cron/Heartbeat) 的影响

v0.8 PRD 中设计了 Cron 的结果投递：

> "投递方式: Gateway.deliver_to_channel()"

有了 v0.9 的 `Gateway.send_outbound()` + `MessageTool`，Cron 的结果投递可以：

1. **内部路径**: CronRuntime 直接调用 `gateway.send_outbound("feishu", target, text)` — 用于系统级定时投递
2. **Agent 路径**: Cron 触发的 Agent Turn 中，Agent 自己决定调用 `message` tool 来投递 — 用于 Agent 自主决策

两条路径共享同一套 outbound 基础设施。v0.9 是 v0.8 的前置依赖。

---

## 附录 A: 从 OpenClaw 学到的，没有照搬的

| OpenClaw 特性 | AgentOS 的适配决策 |
|---|---|
| `replyDispatcher` + streaming card | 不搬。Python asyncio 单线程 + 非流式 LLM，没有 streaming 的前提条件 |
| 多账号 (accounts) | 不搬。v0.7 明确取舍了单账号。多账号等有真实需求再加 |
| 消息编辑 (`editMessageFeishu`) | 不搬。需要 message_id 追踪，当前场景不需要 |
| `sendWithEffect` | 飞书不支持消息效果，这是 iMessage 的功能 |
| `normalizeFeishuTarget` 的复杂 target 解析 | 简化。只支持 `chat_id` 和 `user:<open_id>` 两种格式 |
| 飞书 `renderMode: auto/raw/card` 三模式 | 采纳理念，简化实现。默认 post/md，可选 card 模式 |
| `chunk_text` 的多种 chunk mode | 简化。只实现 newline-aware 分片，不做按 token 分片 |
