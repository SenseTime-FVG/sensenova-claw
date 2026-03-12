# 飞书 Channel 增强与 Agent 主动通信能力

> 版本: v0.9 | 日期: 2026-03-11
> 前置: [19_plugin_feishu_channel.md](./19_plugin_feishu_channel.md) (v0.7), [20_cron_heartbeat_system.md](./20_cron_heartbeat_system.md) (v0.8)
> 原始需求: [docs_raw/update_v0.9.md](../docs_raw/update_v0.9.md)

---

## 1. 对原始 PRD 的关键修正

### 1.1 飞书 post 消息不支持 md tag

原始 PRD 声称 `msg_type: "post"` 配合 `tag: "md"` 可渲染 Markdown，**这是事实错误**。飞书 post 消息仅支持 `text`/`a`/`at`/`img`/`media`/`emotion` 等结构化 tag。**Markdown 渲染（`lark_md`）只在 `msg_type: "interactive"` 的消息卡片中可用。**

### 1.2 其他修正

| 原始 PRD | 修正 |
|---|---|
| `post` + `tag: "md"` 能渲染 Markdown | 需用 `msg_type: "interactive"` + `lark_md` 卡片 |
| MessageTool 审计事件 `session_id=""` | 应透传当前 Agent session_id |
| FeishuChannel "继承" OutboundCapable | Protocol 是结构化类型检查，不需显式继承，实现方法即可 |
| MessageTool 有冗余 `action: ["send"]` 参数 | 移除，避免浪费 LLM tokens |
| FeishuApiTool 无安全限制 | 增加 `risk_level=HIGH` + 路径白名单 + 方法白名单 |
| FeishuApiTool 串行依赖 MessageTool | 并行独立，可同时开发 |
| 消息分片不感知代码块边界 | 增加 ``` 闭合/重开逻辑 |

### 1.3 出站路径设计决策

AgentOS 存在三条出站路径，各有不同职责：

| 路径 | 语义 | 调用方 |
|------|------|--------|
| `Gateway._dispatch_event` | 事件驱动回复（session 绑定查找） | 自动 |
| `Gateway.deliver_to_channel` | 事件转发到指定 Channel | CronRuntime |
| `Gateway.send_outbound` (新增) | 主动投递消息到指定目标 | MessageTool |

`send_outbound` 与 `deliver_to_channel` 职责不同：前者是"给某人发消息"（需要 target），后者是"把事件送到某 Channel"（需要 EventEnvelope）。两者共存，`_send_reply` 和 `send_outbound` 共享消息构建逻辑（card 构建 + 分片）。

---

## 2. 方案设计

### 2.1 飞书 Markdown 卡片渲染（P0，0.5天）

新增 `card.py`：

```python
# backend/app/plugins/feishu/card.py

import json


def build_markdown_card(text: str, title: str | None = None) -> str:
    """构建包含 Markdown 内容的最简飞书消息卡片"""
    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": text},
        }
    ]
    card: dict = {
        "config": {"wide_screen_mode": True},
        "elements": elements,
    }
    if title:
        card["header"] = {
            "title": {"tag": "plain_text", "content": title},
        }
    return json.dumps(card)
```

FeishuChannel 新增 `_build_content` 供 `_send_reply` 和 `send_outbound` 共用：

```python
def _build_content(self, text: str) -> tuple[str, str]:
    """根据 render_mode 构建消息内容，返回 (content_json, msg_type)"""
    if self._config.render_mode == "card":
        from app.plugins.feishu.card import build_markdown_card
        return build_markdown_card(text), "interactive"
    return json.dumps({"text": text}), "text"
```

### 2.2 消息分片（P0，与 2.1 一起交付）

```python
# backend/app/plugins/feishu/text.py

def chunk_text(text: str, limit: int = 4000) -> list[str]:
    """按换行符边界分片，感知 Markdown 代码块状态。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit

        chunk = remaining[:cut].rstrip()
        rest = remaining[cut:].lstrip("\n")

        fence_count = chunk.count("```")
        if fence_count % 2 == 1:
            chunk += "\n```"
            rest = "```\n" + rest

        chunks.append(chunk)
        remaining = rest

    return chunks
```

### 2.3 Channel 事件过滤 + 中间状态推送（P1，0.5天）

`event_filter` 仅影响 `Gateway._dispatch_event` 路径；`Gateway.deliver_to_channel` 不受过滤影响。

```python
# backend/app/gateway/base.py — Channel 基类新增
class Channel(ABC):
    # ... 已有方法 ...
    def event_filter(self) -> set[str] | None:
        """此 Channel 关心的事件类型集合。None = 全部（默认，向后兼容）。"""
        return None
```

```python
# backend/app/gateway/gateway.py — _dispatch_event 增加过滤
async def _dispatch_event(self, event: EventEnvelope) -> None:
    # ... 已有 session_id / channel_id 查找 ...
    event_types = channel.event_filter()
    if event_types is not None and event.type not in event_types:
        return
    await channel.send_event(event)
```

```python
# FeishuChannel
def event_filter(self) -> set[str]:
    types = {AGENT_STEP_COMPLETED, ERROR_RAISED}
    if self._config.show_tool_progress:
        types.add(TOOL_CALL_STARTED)
    return types
```

### 2.4 OutboundCapable + send_outbound（P1，1天）

```python
# backend/app/gateway/base.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class OutboundCapable(Protocol):
    async def send_outbound(
        self, target: str, text: str, msg_type: str = "card",
    ) -> dict:
        """向指定目标发送消息。返回 {success, message_id, ...}"""
        ...
```

```python
# FeishuChannel — 实现 send_outbound（满足 OutboundCapable 结构化类型）
async def send_outbound(self, target: str, text: str, msg_type: str = "card") -> dict:
    if not self._client:
        return {"success": False, "error": "Client not initialized"}

    if target.startswith("user:"):
        receive_id, receive_id_type = target[5:], "open_id"
    else:
        receive_id, receive_id_type = target, "chat_id"

    last_result = {}
    for chunk in chunk_text(text, limit=4000):
        content, actual_msg_type = self._build_content(chunk)
        request = self._build_message_request(
            receive_id, receive_id_type, content, actual_msg_type,
        )
        response = await asyncio.to_thread(
            self._client.im.v1.message.create, request,
        )
        if not response.success():
            return {"success": False, "code": response.code, "msg": response.msg}
        last_result = {"success": True, "message_id": response.data.message_id}

    return last_result
```

```python
# Gateway 新增
async def send_outbound(
    self, channel_id: str, target: str, text: str, **kwargs,
) -> dict:
    channel = self._channels.get(channel_id)
    if not channel:
        return {"success": False, "error": f"Channel '{channel_id}' not found"}
    if not isinstance(channel, OutboundCapable):
        return {"success": False, "error": f"Channel '{channel_id}' does not support outbound"}
    return await channel.send_outbound(target=target, text=text, **kwargs)
```

### 2.5 MessageTool + 审计事件（P1，1天）

```python
# backend/app/tools/message_tool.py

from typing import Any
from app.tools.base import Tool, ToolRiskLevel


class MessageTool(Tool):
    name = "message"
    description = (
        "主动发送消息到指定渠道和目标。"
        "channel: 渠道名 (feishu)。"
        "target: 目标 ID (chat_id 或 user:<open_id>)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "目标渠道 (feishu)",
                "default": "feishu",
            },
            "target": {
                "type": "string",
                "description": "目标 ID。飞书: chat_id 或 user:<open_id>",
            },
            "message": {
                "type": "string",
                "description": "消息内容 (支持 Markdown)",
            },
        },
        "required": ["target", "message"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, gateway, publisher):
        self._gateway = gateway
        self._publisher = publisher

    async def execute(self, **kwargs: Any) -> Any:
        channel = kwargs.get("channel", "feishu")
        target = kwargs.get("target")
        message = kwargs.get("message", "")

        if not target:
            return {"success": False, "error": "target is required"}

        result = await self._gateway.send_outbound(
            channel_id=channel, target=target, text=message,
        )

        if result.get("success"):
            from app.events.envelope import EventEnvelope
            from app.events.types import MESSAGE_OUTBOUND_SENT
            await self._publisher.publish(EventEnvelope(
                type=MESSAGE_OUTBOUND_SENT,
                session_id=kwargs.get("_session_id", ""),
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

ToolRuntime 需透传 `session_id` 到 `kwargs["_session_id"]`，以便审计事件关联会话。

注册时机（`main.py` 中 gateway 创建后、start 前）：

```python
from app.tools.message_tool import MessageTool
tool_registry.register(MessageTool(gateway=gateway, publisher=publisher))
```

### 2.6 FeishuApiTool（P2，0.5天）

```python
# backend/app/tools/feishu_api_tool.py

class FeishuApiTool(Tool):
    name = "feishu_api"
    description = (
        "调用飞书开放平台 API。"
        "method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)。"
        "path: API 路径 (如 /open-apis/docx/v1/documents)。"
        "body: 请求体 (JSON 对象)。params: URL 查询参数。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
            "path": {"type": "string", "description": "飞书 API 路径"},
            "body": {"type": "object", "description": "请求体"},
            "params": {"type": "object", "description": "URL 查询参数"},
        },
        "required": ["method", "path"],
    }
    risk_level = ToolRiskLevel.HIGH

    def __init__(self, feishu_client, allowed_methods=None, allowed_path_prefixes=None):
        self._client = feishu_client
        self._allowed_methods = set(allowed_methods or ["GET"])
        self._allowed_prefixes = allowed_path_prefixes or []

    async def execute(self, **kwargs: Any) -> Any:
        import asyncio, httpx

        method = kwargs.get("method", "GET")
        path = kwargs.get("path", "")

        if method not in self._allowed_methods:
            return {"error": f"Method {method} not allowed"}
        if self._allowed_prefixes and not any(path.startswith(p) for p in self._allowed_prefixes):
            return {"error": f"Path {path} not in allowed prefixes"}

        token = await asyncio.to_thread(
            lambda: self._client._token_manager.get_tenant_access_token()
        )
        url = f"https://open.feishu.cn{path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers,
                json=kwargs.get("body"), params=kwargs.get("params"),
            )
        return {
            "status_code": resp.status_code,
            "data": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text[:5000],
        }
```

---

## 3. 新增事件类型

```python
# events/types.py
MESSAGE_OUTBOUND_SENT = "message.outbound_sent"
```

---

## 4. 新增配置

```yaml
plugins:
  feishu:
    # ... 已有配置 ...
    render_mode: "card"              # text | card
    show_tool_progress: false        # 是否推送工具执行中间状态
    api_tool:
      enabled: false
      allowed_methods: ["GET"]
      allowed_path_prefixes:
        - /open-apis/docx/v1/documents
        - /open-apis/wiki/v2/spaces
        - /open-apis/drive/v1/files
```

FeishuConfig 新增字段：

```python
@dataclass
class FeishuConfig:
    # ... 已有 ...
    render_mode: str = "card"
    show_tool_progress: bool = False
```

---

## 5. 实施计划

### 5.1 依赖图

```
[0.5天] card 构建 + 消息分片 (v0.9a)
    ↓
[0.5天] Channel.event_filter + 中间状态推送 (v0.9b)  ← 可与 v0.9a 并行
    ↓
[1天] OutboundCapable + send_outbound (v0.9c)
    ↓
[1天] MessageTool + 审计事件 (v0.9d)

[0.5天] FeishuApiTool (v0.9e)  ← 与 v0.9c/d 并行
```

### 5.2 分阶段交付

| 阶段 | 内容 | 工期 | 改动文件 |
|------|------|------|----------|
| **v0.9a** | interactive card 渲染 + 消息分片 | **0.5天** | 新增 `card.py` `text.py`；修改 `channel.py` `config.py` |
| **v0.9b** | Channel 事件过滤 + 中间状态推送 | **0.5天** | `base.py`, `gateway.py`, `channel.py` |
| **v0.9c** | OutboundCapable + send_outbound | **1天** | `base.py`, `gateway.py`, `channel.py` |
| **v0.9d** | MessageTool + 审计事件 | **1天** | 新增 `message_tool.py`；修改 `types.py`, `main.py`, `tool_runtime.py` |
| **v0.9e** | FeishuApiTool + 启用 Skills | **0.5天** | 新增 `feishu_api_tool.py`；修改 `config.py`, `main.py` |

**总计: 3.5天**

### 5.3 验收标准

| 阶段 | 验收 |
|------|------|
| v0.9a | 飞书收到卡片形式回复，正确渲染代码块、表格、链接；`render_mode: text` 降级为纯文本；超 4000 字符自动分片；代码块跨片正确闭合 |
| v0.9b | 开启配置后飞书显示"⏳ 正在执行 xxx..." |
| v0.9c | `channel.send_outbound("chat_xxx", "hello")` 飞书群收到卡片消息 |
| v0.9d | Agent 调用 message tool 成功发送；`message.outbound_sent` 事件入库 |
| v0.9e | Agent 通过 feishu_api tool 调用飞书 API；白名单外路径被拒绝 |

---

## 6. 对 v0.8 (Cron/Heartbeat) 的影响

v0.9 引入 card 渲染后，FeishuChannel._send_reply 自动升级为 card 格式，Cron 投递结果也受益于 Markdown 渲染，无需额外修改。两条投递路径共享 `_build_content` 和 `chunk_text`。

---

## 7. 被否决的方案

| 方案 | 否决理由 |
|------|---------|
| `msg_type: "post"` + `tag: "md"` | 飞书 post 不支持 md tag，Markdown 仅在 interactive card 可用 |
| Typing indicator (reaction) | 每次添加触发推送通知，推迟到 v1.0 |
| Streaming Card | 当前 LLM 非流式，前置依赖未满足 |
| 纯事件驱动出站 | MessageTool 需同步返回结果，纯异步过于复杂 |
| Channel 基类强制 send_outbound | 并非所有 Channel 都支持，改为 Protocol 检查 |
