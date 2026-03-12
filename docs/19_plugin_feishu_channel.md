# Plugin 系统与飞书 Channel 设计

> 版本: v0.7 | 日期: 2026-03-10

---

## 1. 概述

为 AgentOS 引入 **Plugin 系统** 和 **飞书（Feishu/Lark）Channel**：

1. **Plugin 系统** — 标准化的第三方扩展机制，支持注册 Channel、Tool、Hook
2. **飞书 Channel** — 基于 `lark-oapi` SDK，通过 WebSocket 长连接接收飞书消息，将 Agent 回复推送回飞书对话

### 1.1 核心取舍

| 做 | 不做 |
|---|---|
| 轻量 Plugin 注册协议（Python 类/函数） | 不做独立进程/微服务式插件隔离 |
| 飞书 WebSocket 长连接模式（零公网端口） | 不做 Webhook 回调模式（需要公网域名） |
| 单 bot 账号接入 | 不做多账号管理 |
| 文本消息收发 | 不做富卡片消息、交互式卡片回调 |
| 群聊 @bot 触发 + 私聊直接触发 | 不做群内无 @ 的自动回复 |

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **最小侵入** | 仅在 `main.py` 增加加载入口，不修改现有 Channel/Tool/Gateway 代码 |
| **约定优于配置** | Plugin 暴露标准 `register(api)` 函数，框架自动发现和加载 |
| **Gateway 复用** | 飞书 Channel 通过 `gateway.bind_session()` 复用现有 `_session_bindings`，不修改 `_dispatch_event` |
| **双总线兼容** | 入站事件通过 `gateway.publish_from_channel()` 进入 PublicEventBus，由 BusRouter 路由到 PrivateBus |

---

## 2. Plugin 系统设计

### 2.1 目录结构

```
backend/app/plugins/
├── __init__.py              # PluginRegistry
├── base.py                  # PluginApi / PluginDefinition
├── loader.py                # 插件发现和加载
└── feishu/                  # 飞书插件（内置）
    ├── __init__.py
    ├── plugin.py            # register(api) 入口
    ├── channel.py           # FeishuChannel(Channel)
    ├── client.py            # 飞书 API client 封装
    ├── config.py            # FeishuConfig
    └── events.py            # 飞书事件解析
```

### 2.2 核心类型

```python
from dataclasses import dataclass
from typing import Callable, Any

from app.gateway.base import Channel
from app.tools.base import Tool


@dataclass
class PluginDefinition:
    id: str                         # 唯一标识，如 "feishu"
    name: str                       # 显示名称
    version: str = "0.1.0"
    description: str = ""


class PluginApi:
    """
    框架传给 Plugin 的注册接口（门面模式）。
    Plugin 通过此对象注册 Channel/Tool/Hook，并访问受限的框架服务。
    """

    def __init__(self, plugin_id: str, registry: "PluginRegistry"):
        self.plugin_id = plugin_id
        self._registry = registry

    def register_channel(self, channel: Channel) -> None:
        self._registry._pending_channels.append(channel)

    def register_tool(self, tool: Tool) -> None:
        self._registry._pending_tools.append(tool)

    def register_hook(self, event_type: str, handler: Callable) -> None:
        """v0.7 预留接口，不实现 hook 分发"""
        self._registry._pending_hooks.append((event_type, handler))

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取 config.yaml 中 plugins.<plugin_id>.<key>"""
        from app.core.config import config
        return config.get(f"plugins.{self.plugin_id}.{key}", default)

    def get_gateway(self) -> "Gateway":
        """获取 Gateway 引用（apply() 后可用）"""
        return self._registry._gateway

    def get_publisher(self) -> "EventPublisher":
        """获取 EventPublisher 引用"""
        return self._registry._publisher
```

### 2.3 Plugin 注册协议

每个 Plugin 包暴露 `definition` 对象和 `register` 函数:

```python
# backend/app/plugins/feishu/plugin.py

from app.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="feishu",
    name="飞书",
    version="0.1.0",
    description="飞书/Lark 消息 Channel 插件",
)

async def register(api: PluginApi) -> None:
    from .channel import FeishuChannel
    from .config import FeishuConfig

    feishu_config = FeishuConfig.from_plugin_api(api)
    if not feishu_config.enabled:
        return

    channel = FeishuChannel(config=feishu_config, plugin_api=api)
    api.register_channel(channel)
```

### 2.4 PluginRegistry

```python
class PluginRegistry:
    """插件注册表：发现、加载、管理所有 Plugin"""

    def __init__(self):
        self._plugins: dict[str, PluginDefinition] = {}
        self._pending_channels: list[Channel] = []
        self._pending_tools: list[Tool] = []
        self._pending_hooks: list[tuple[str, Callable]] = []
        self._gateway: Gateway | None = None
        self._publisher: EventPublisher | None = None

    async def load_plugins(self, config: dict) -> None:
        """
        扫描并加载所有启用的 Plugin。
        加载顺序: 内置插件(app/plugins/*/) → 用户插件(~/.agentos/plugins/*/)
        错误处理: 缺少 definition/register 跳过+警告；register() 异常跳过+错误日志；id 冲突后者覆盖
        """
        pass

    async def apply(
        self,
        gateway: "Gateway",
        tool_registry: "ToolRegistry",
        publisher: "EventPublisher",
    ) -> None:
        """将收集到的 Channel/Tool/Hook 注入到框架中"""
        self._gateway = gateway
        self._publisher = publisher
        for channel in self._pending_channels:
            gateway.register_channel(channel)
        for tool in self._pending_tools:
            tool_registry.register(tool)
```

### 2.5 main.py 集成

```python
# main.py lifespan 中，Gateway 创建之后、start 之前:
plugin_registry = PluginRegistry()
await plugin_registry.load_plugins(config.data)
await plugin_registry.apply(gateway=gateway, tool_registry=tool_registry, publisher=publisher)
await gateway.start()
```

### 2.6 配置

```yaml
plugins:
  feishu:
    enabled: true
    app_id: "cli_xxx"
    app_secret: "xxx"
    dm_policy: "open"           # open | allowlist
    group_policy: "mention"     # mention | open | disabled
    log_level: "INFO"
```

---

## 3. 飞书 Channel 实现

### 3.1 架构总览

```
飞书服务器
    │ WebSocket 长连接
    ▼
┌──────────────────────────────────────────────┐
│               FeishuChannel                   │
│                                               │
│  lark-oapi WSClient (SDK线程)                 │
│       │ _handle_message_event                 │
│       │ run_coroutine_threadsafe              │
│       ▼                                       │
│  _on_message_async (asyncio线程)              │
│    1. 构造 EventEnvelope                      │
│    2. gateway.bind_session(sid, "feishu")     │
│    3. gateway.publish_from_channel(envelope)  │
│                                               │
│  send_event (asyncio线程)                     │
│    1. _session_meta[sid] → chat_id            │
│    2. 飞书消息 API 发送回复                     │
└──────────────────────────────────────────────┘
         │                    ▲
         ▼                    │
    PublicEventBus ←→ Gateway._dispatch_event()
         │             （复用 _session_bindings，零修改）
    BusRouter → PrivateEventBus → Workers
```

**关键设计**:
- FeishuChannel 通过 `gateway.bind_session()` 注册 session 绑定，Gateway `_dispatch_event` 零修改
- 入站事件 → PublicEventBus → BusRouter → PrivateEventBus → Worker，与 WebSocket Channel 路径一致
- SDK 回调在后台线程，通过 `run_coroutine_threadsafe` 跨线程调度到 asyncio

### 3.2 FeishuConfig

```python
from dataclasses import dataclass, field

@dataclass
class FeishuConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    dm_policy: str = "open"         # open | allowlist
    group_policy: str = "mention"   # mention | open | disabled
    allowlist: list[str] = field(default_factory=list)
    log_level: str = "INFO"

    @classmethod
    def from_plugin_api(cls, api) -> "FeishuConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            app_id=api.get_config("app_id", ""),
            app_secret=api.get_config("app_secret", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "mention"),
            allowlist=api.get_config("allowlist", []),
            log_level=api.get_config("log_level", "INFO"),
        )
```

### 3.3 FeishuChannel

```python
import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from app.events.envelope import EventEnvelope
from app.events.types import AGENT_STEP_COMPLETED, ERROR_RAISED
from app.gateway.base import Channel

logger = logging.getLogger(__name__)


@dataclass
class FeishuSessionMeta:
    """飞书会话元数据，用于出站回复时查找 chat_id"""
    chat_id: str
    chat_type: str          # "p2p" | "group"
    last_message_id: str
    sender_id: str


class FeishuChannel(Channel):
    """
    线程模型:
    - _handle_message_event: SDK 后台线程
    - _on_message_async / send_event: asyncio 线程
    - _chat_sessions / _session_meta: threading.Lock 保护
    """

    def __init__(self, config: "FeishuConfig", plugin_api: "PluginApi"):
        self._config = config
        self._plugin_api = plugin_api
        self._client: lark.Client | None = None
        self._ws_client: lark.ws.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # 正向: session_key("dm:<id>" / "group:<id>") → session_id
        self._chat_sessions: dict[str, str] = {}
        # 反向: session_id → FeishuSessionMeta（O(1) 查找 chat_id）
        self._session_meta: dict[str, FeishuSessionMeta] = {}
        self._lock = threading.Lock()

    def get_channel_id(self) -> str:
        return "feishu"

    async def start(self) -> None:
        self._loop = asyncio.get_event_loop()

        self._client = (
            lark.Client.builder()
            .app_id(self._config.app_id)
            .app_secret(self._config.app_secret)
            .log_level(lark.LogLevel.DEBUG if self._config.log_level == "DEBUG" else lark.LogLevel.INFO)
            .build()
        )

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self._config.app_id,
            self._config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.DEBUG if self._config.log_level == "DEBUG" else lark.LogLevel.INFO,
        )

        # SDK 的 start() 是阻塞的，放到后台线程
        asyncio.get_event_loop().run_in_executor(None, self._ws_client.start)
        logger.info("FeishuChannel started (WebSocket mode)")

    async def stop(self) -> None:
        logger.info("FeishuChannel stopped")

    # ---- 入站: 飞书 → AgentOS ----

    def _handle_message_event(self, ctx, conf, event) -> None:
        """SDK 线程回调，跨线程调度到 asyncio"""
        try:
            msg = event.event.message
            sender = event.event.sender
            chat_id = msg.chat_id
            chat_type = msg.chat_type
            message_id = msg.message_id
            sender_id = sender.sender_id.open_id

            text = self._extract_text(msg.message_type, msg.content, chat_type, msg)
            if text is None:
                return
            if not self._should_respond(chat_type, sender_id, msg):
                return

            logger.info("Feishu message: chat=%s sender=%s text=%s", chat_id, sender_id, text[:100])

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._on_message_async(text, chat_id, chat_type, message_id, sender_id),
                    self._loop,
                )
                future.result(timeout=15)
        except Exception:
            logger.exception("Failed to handle Feishu message event")

    async def _on_message_async(self, text, chat_id, chat_type, message_id, sender_id) -> None:
        """asyncio 线程：session 管理 → bind → 发布事件"""
        session_key = f"dm:{sender_id}" if chat_type == "p2p" else f"group:{chat_id}"

        with self._lock:
            session_id = self._chat_sessions.get(session_key)
            if not session_id:
                session_id = f"feishu_{uuid.uuid4().hex[:12]}"
                self._chat_sessions[session_key] = session_id
            self._session_meta[session_id] = FeishuSessionMeta(
                chat_id=chat_id, chat_type=chat_type,
                last_message_id=message_id, sender_id=sender_id,
            )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "feishu")

        await gateway.publish_from_channel(EventEnvelope(
            type="ui.user_input",
            session_id=session_id,
            turn_id=f"turn_{uuid.uuid4().hex[:12]}",
            source="feishu",
            payload={"content": text, "attachments": [], "context_files": []},
        ))

    def _extract_text(self, msg_type, content_str, chat_type, msg) -> str | None:
        if msg_type == "text":
            content = json.loads(content_str)
            text = content.get("text", "").strip()
            if chat_type == "group" and msg.mentions:
                for mention in msg.mentions:
                    text = text.replace(mention.key, "").strip()
            return text if text else None
        if msg_type == "image":
            return "[用户发送了一张图片]"
        if msg_type == "file":
            content = json.loads(content_str)
            return f"[用户发送了文件: {content.get('file_name', 'unknown')}]"
        logger.debug("Unsupported Feishu message type: %s", msg_type)
        return None

    def _should_respond(self, chat_type, sender_id, msg) -> bool:
        if chat_type == "p2p":
            if self._config.dm_policy == "allowlist":
                return sender_id in self._config.allowlist
            return True
        if chat_type == "group":
            if self._config.group_policy == "disabled":
                return False
            if self._config.group_policy == "mention":
                return bool(msg.mentions)
            return True
        return False

    # ---- 出站: AgentOS → 飞书 ----

    async def send_event(self, event: EventEnvelope) -> None:
        if event.type == AGENT_STEP_COMPLETED:
            text = event.payload.get("result", {}).get("content", "") or event.payload.get("final_response", "")
            if text:
                await self._send_reply(event.session_id, text)
        elif event.type == ERROR_RAISED:
            await self._send_reply(event.session_id, f"⚠️ 错误: {event.payload.get('error_message', '处理失败')}")

    async def _send_reply(self, session_id: str, text: str) -> None:
        if not self._client:
            return
        with self._lock:
            meta = self._session_meta.get(session_id)
        if not meta:
            logger.warning("No feishu meta for session %s", session_id)
            return

        if len(text) > 20000:
            text = text[:20000] + "\n\n... (内容过长，已截断)"

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(meta.chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                ).build()
            )
            response = await asyncio.to_thread(self._client.im.v1.message.create, request)
            if not response.success():
                logger.error("Feishu send failed: code=%s msg=%s", response.code, response.msg)
        except Exception:
            logger.exception("Failed to send Feishu message")
```

### 3.4 Session 管理

| 飞书场景 | session_key | 说明 |
|----------|------------|------|
| 私聊 | `dm:<sender_open_id>` | 每个用户一个 session |
| 群聊 | `group:<chat_id>` | 每个群一个 session，群成员共享上下文 |

- `_chat_sessions`: session_key → session_id（正向）
- `_session_meta`: session_id → FeishuSessionMeta（反向，含 chat_id）
- `threading.Lock` 保护并发访问
- 内存存储，重启后映射丢失

---

## 4. 飞书 Bot 创建指南

1. [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 获取 `App ID` 和 `App Secret`
3. 添加「机器人」能力
4. 事件配置选择 **使用长连接接收事件**
5. 事件订阅添加 `im.message.receive_v1`
6. 权限开通 `im:message` + `im:message:send_as_bot`
7. 发布应用版本

---

## 5. 变更影响

### 新增文件

```
backend/app/plugins/
├── __init__.py, base.py, loader.py
└── feishu/
    ├── __init__.py, plugin.py, channel.py
    ├── client.py, config.py, events.py
```

### 修改文件

| 文件 | 修改 |
|------|------|
| `app/main.py` | lifespan 添加 PluginRegistry 加载 + apply（~5 行） |
| `app/core/config.py` | DEFAULT_CONFIG 添加 `plugins` 段 |
| `pyproject.toml` | 添加 `lark-oapi>=1.5.0` |

**不修改**: `gateway/base.py`（Channel ABC 不变）、`gateway/gateway.py`（`_dispatch_event` 不变）

---

## 6. 验收标准

1. `plugins.feishu.enabled: true` 时启动日志显示 "FeishuChannel started"
2. `enabled: false` 时无飞书相关日志
3. 私聊收发正常
4. 群聊 @bot 触发正常，未 @bot 不触发
5. 同一用户多条消息保持同一 session
6. 飞书连接断开不影响 WebSocket Channel
7. Gateway `_dispatch_event` 无代码变更

---

## 7. 交付计划

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | Plugin 系统骨架（base.py + registry + loader） | 0.5 天 |
| 2 | FeishuConfig + 配置集成 | 0.5 天 |
| 3 | FeishuChannel 入站（长连接 + 消息解析 + session 绑定） | 1 天 |
| 4 | FeishuChannel 出站（回复 → 飞书消息 API） | 0.5 天 |
| 5 | main.py 集成 | 0.5 天 |
| 6 | 线程安全 + 集成测试 | 0.5 天 |
| 7 | E2E 测试（真实飞书 bot） | 1 天 |

**总计: 4.5 天**

---

## 8. 后续扩展

| 特性 | 优先级 |
|------|--------|
| 富卡片消息（Markdown → 飞书卡片） | P1 |
| 图片/文件发送 | P1 |
| Session 持久化到 SQLite | P1 |
| `/new` 命令重置 session | P2 |
| 多账号支持 | P2 |
| Webhook 模式 | P3 |
| 消息回复引用 | P3 |
| 更多 Channel Plugin（Slack/Discord/微信） | P3 |
