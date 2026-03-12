# PRD: AgentOS Plugin 系统与飞书 Channel

> 版本: update_v0.7
> 日期: 2026-03-10
> 项目: AgentOS
> 参考: OpenClaw channel plugin 架构, lark-oapi Python SDK

---

## 1. 概述

为 AgentOS 引入 **Plugin 系统** 和 **飞书（Feishu/Lark）Channel**：

1. **Plugin 系统** — 标准化的第三方扩展机制，支持注册 Channel、Tool、Hook
2. **飞书 Channel** — 基于 `lark-oapi` SDK，通过 WebSocket 长连接接收飞书消息，将 Agent 回复推送回飞书对话

### 1.1 解决的问题

- 当前 AgentOS 仅支持 WebSocket（Web 前端）和 CLI 两种接入方式
- 新增 Channel 需要修改 `main.py`、`gateway.py` 等核心文件，耦合度高
- 缺少标准化的第三方扩展入口，无法让社区贡献 Channel/Tool

### 1.2 核心取舍

| 做 | 不做 |
|---|---|
| 轻量 Plugin 注册协议（Python 类/函数） | 不做独立进程/微服务式插件隔离 |
| 飞书 WebSocket 长连接模式（零公网端口） | 不做 Webhook 回调模式（需要公网域名） |
| 单 bot 账号接入 | 不做多账号管理（v0.7 不需要） |
| 文本消息收发 | 不做富卡片消息、交互式卡片回调 |
| 群聊 @bot 触发 + 私聊直接触发 | 不做群内无 @ 的自动回复 |
| 图片/文件接收（转为文本描述传给 Agent） | 不做图片/文件发送（后续扩展） |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **最小侵入** | Plugin 系统不修改现有 Channel/Tool 代码，仅在 `main.py` 增加加载入口 |
| **约定优于配置** | Plugin 暴露标准 `register(api)` 函数，框架自动发现和加载 |
| **Gateway 复用** | 飞书 Channel 复用现有 `Channel` ABC + `Gateway` 路由，不引入新的消息总线 |
| **渐进增强** | 先文本消息，后续按需增加富卡片/媒体/多账号等能力 |

---

## 2. Plugin 系统设计

### 2.1 Plugin 清单文件

每个 Plugin 是一个 Python 包，放在 `backend/app/plugins/<name>/` 或 `~/.agentos/plugins/<name>/` 下。

目录结构:

```
backend/app/plugins/
├── __init__.py              # PluginRegistry
├── base.py                  # PluginApi / PluginDefinition 类型
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
from dataclasses import dataclass, field
from typing import Callable, Any

from app.gateway.base import Channel
from app.tools.base import Tool


@dataclass
class PluginDefinition:
    """插件元数据"""
    id: str                         # 唯一标识，如 "feishu"
    name: str                       # 显示名称，如 "飞书"
    version: str = "0.1.0"
    description: str = ""


class PluginApi:
    """
    框架传给 Plugin 的注册接口。
    Plugin 通过此对象注册自己提供的 Channel、Tool、Hook。
    """

    def __init__(self, plugin_id: str, registry: "PluginRegistry"):
        self.plugin_id = plugin_id
        self._registry = registry

    def register_channel(self, channel: Channel) -> None:
        """注册一个 Channel（框架自动注册到 Gateway）"""
        self._registry._pending_channels.append(channel)

    def register_tool(self, tool: Tool) -> None:
        """注册一个 Tool（框架自动注册到 ToolRegistry）"""
        self._registry._pending_tools.append(tool)

    def register_hook(
        self,
        event_type: str,
        handler: Callable,
    ) -> None:
        """注册事件钩子（框架在对应事件触发时调用）"""
        self._registry._pending_hooks.append((event_type, handler))

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取 config.yaml 中 plugins.<plugin_id>.<key>"""
        from app.core.config import config
        return config.get(f"plugins.{self.plugin_id}.{key}", default)
```

### 2.3 Plugin 注册协议

每个 Plugin 包必须暴露一个 `register` 函数:

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
    """插件注册入口，框架启动时调用"""
    from .channel import FeishuChannel
    from .config import FeishuConfig

    feishu_config = FeishuConfig.from_plugin_api(api)
    if not feishu_config.enabled:
        return

    channel = FeishuChannel(config=feishu_config)
    api.register_channel(channel)
```

### 2.4 PluginRegistry

```python
class PluginRegistry:
    """
    插件注册表：发现、加载、管理所有 Plugin。
    生命周期由 main.py lifespan 管理。
    """

    def __init__(self):
        self._plugins: dict[str, PluginDefinition] = {}
        self._pending_channels: list[Channel] = []
        self._pending_tools: list[Tool] = []
        self._pending_hooks: list[tuple[str, Callable]] = []

    async def load_plugins(self, config: dict) -> None:
        """
        扫描并加载所有启用的 Plugin。
        加载顺序:
          1. 内置插件: backend/app/plugins/*/
          2. 用户插件: ~/.agentos/plugins/*/
        """
        pass

    async def apply(
        self,
        gateway: "Gateway",
        tool_registry: "ToolRegistry",
    ) -> None:
        """
        将收集到的 Channel/Tool/Hook 注入到框架中。
        在所有 Plugin register() 执行完毕后调用。
        """
        for channel in self._pending_channels:
            gateway.register_channel(channel)
        for tool in self._pending_tools:
            tool_registry.register(tool)
        # hook 注册暂预留，v0.7 不实现
```

### 2.5 加载流程（main.py 集成）

```python
# main.py lifespan 中新增:

# --- 在 Gateway 创建之后、start 之前 ---
plugin_registry = PluginRegistry()
await plugin_registry.load_plugins(config.data)
await plugin_registry.apply(gateway=gateway, tool_registry=tool_registry)

# --- 然后正常 start ---
await gateway.start()
```

### 2.6 配置约定

Plugin 的配置统一放在 `config.yaml` 的 `plugins` 段下:

```yaml
plugins:
  feishu:
    enabled: true
    app_id: "cli_xxx"
    app_secret: "xxx"
    # 消息触发策略
    dm_policy: "open"           # open | allowlist
    group_policy: "mention"     # mention | open | disabled
    # 可选
    log_level: "INFO"
```

---

## 3. 飞书 Channel 实现

### 3.1 lark-oapi SDK 能力

飞书官方 Python SDK `lark-oapi`（v1.5.3）支持:

- **WebSocket 长连接**: 无需公网 IP/域名，SDK 自动维护连接和重连
- **事件订阅**: 接收 `im.message.receive_v1`（新消息）等事件
- **消息 API**: 发送文本/富文本/卡片/图片/文件消息
- **身份验证**: app_id + app_secret，SDK 自动管理 tenant_access_token

WebSocket 模式优势:
- 零运维成本（不需要配置域名、SSL、反代）
- 适合本地开发和内网部署
- 自动重连、心跳保活

### 3.2 架构总览

```
飞书服务器
    │
    │ WebSocket 长连接 (wss://open.feishu.cn/...)
    │
    ▼
┌─────────────────────────────────────────────┐
│              FeishuChannel                   │
│                                              │
│  ┌──────────┐    ┌──────────┐               │
│  │ lark-oapi│    │ EventMap │               │
│  │ WSClient │───▶│ (解析飞书 │               │
│  │          │    │  事件)    │               │
│  └──────────┘    └────┬─────┘               │
│                       │                      │
│              ┌────────▼──────────┐           │
│              │ _on_message()     │           │
│              │ 构造 EventEnvelope │           │
│              │ (ui.user_input)   │           │
│              └────────┬──────────┘           │
│                       │                      │
│              Gateway.publish_from_channel()   │
│                       │                      │
│              ┌────────▼──────────┐           │
│              │ send_event()      │           │
│              │ 接收 Agent 回复    │           │
│              │ → 调飞书发消息 API  │           │
│              └───────────────────┘           │
└─────────────────────────────────────────────┘
         │                    ▲
         ▼                    │
    PublicEventBus ──────── Gateway
         │
    ┌────┴────┐
    │ Agent   │  LLM  │  Tool
    │ Runtime │Runtime │Runtime
    └─────────┘
```

### 3.3 FeishuConfig

```python
from dataclasses import dataclass


@dataclass
class FeishuConfig:
    """飞书插件配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""

    # 消息策略
    dm_policy: str = "open"         # open: 所有私聊 | allowlist: 仅白名单
    group_policy: str = "mention"   # mention: 需@bot | open: 所有消息 | disabled: 不响应群聊
    allowlist: list[str] | None = None  # dm_policy=allowlist 时生效

    # 运行参数
    log_level: str = "INFO"

    @classmethod
    def from_plugin_api(cls, api) -> "FeishuConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            app_id=api.get_config("app_id", ""),
            app_secret=api.get_config("app_secret", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "mention"),
            allowlist=api.get_config("allowlist"),
            log_level=api.get_config("log_level", "INFO"),
        )
```

### 3.4 FeishuChannel 核心实现

```python
import asyncio
import json
import logging
import uuid
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from app.events.envelope import EventEnvelope
from app.events.types import AGENT_STEP_COMPLETED, ERROR_RAISED
from app.gateway.base import Channel

logger = logging.getLogger(__name__)


class FeishuChannel(Channel):
    """
    飞书 Channel：通过 lark-oapi WebSocket 长连接接收消息，
    通过飞书消息 API 发送 Agent 回复。
    """

    def __init__(self, config: "FeishuConfig"):
        self._config = config
        self._client: lark.Client | None = None
        self._ws_client: lark.ws.Client | None = None
        self._gateway = None  # 由 Gateway 注入
        self._loop: asyncio.AbstractEventLoop | None = None

        # chat_id → session_id 映射
        # 飞书的一个对话（私聊或群聊）对应一个 AgentOS session
        self._chat_sessions: dict[str, str] = {}

    def get_channel_id(self) -> str:
        return "feishu"

    def set_gateway(self, gateway) -> None:
        """Gateway 注册 Channel 时调用，注入 Gateway 引用"""
        self._gateway = gateway

    async def start(self) -> None:
        """启动飞书 WebSocket 长连接"""
        self._loop = asyncio.get_event_loop()

        # 创建飞书 API Client（用于发消息）
        self._client = (
            lark.Client.builder()
            .app_id(self._config.app_id)
            .app_secret(self._config.app_secret)
            .log_level(lark.LogLevel.DEBUG if self._config.log_level == "DEBUG" else lark.LogLevel.INFO)
            .build()
        )

        # 创建事件处理器
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

        # 创建 WebSocket Client（长连接，自动重连）
        self._ws_client = (
            lark.ws.Client(
                self._config.app_id,
                self._config.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.DEBUG if self._config.log_level == "DEBUG" else lark.LogLevel.INFO,
            )
        )

        # 在后台线程启动 WebSocket（lark-oapi 的 ws.Client.start() 是阻塞的）
        asyncio.get_event_loop().run_in_executor(None, self._ws_client.start)
        logger.info("FeishuChannel started (WebSocket mode)")

    async def stop(self) -> None:
        """停止飞书连接"""
        # lark-oapi ws.Client 暂无显式 stop 方法，靠进程退出清理
        logger.info("FeishuChannel stopped")

    # ================================================================
    # 入站: 飞书 → AgentOS
    # ================================================================

    def _handle_message_event(self, ctx, conf, event) -> None:
        """
        lark-oapi 事件回调（在 SDK 线程中执行，非 asyncio）。
        解析飞书消息，构造 EventEnvelope 发布到 Gateway。
        """
        try:
            msg = event.event.message
            sender = event.event.sender

            chat_id = msg.chat_id
            chat_type = msg.chat_type        # "p2p" 或 "group"
            message_id = msg.message_id
            msg_type = msg.message_type      # "text", "image", "file", ...
            content_str = msg.content        # JSON 字符串
            sender_id = sender.sender_id.open_id

            # 解析消息内容
            text = self._extract_text(msg_type, content_str, chat_type, msg)
            if text is None:
                return

            # 策略过滤
            if not self._should_respond(chat_type, sender_id, msg):
                return

            logger.info(
                "Feishu message: chat=%s sender=%s type=%s text=%s",
                chat_id, sender_id, chat_type, text[:100],
            )

            # 解析/创建 session
            session_key = self._resolve_session_key(chat_id, chat_type, sender_id)
            session_id = self._chat_sessions.get(session_key)
            if not session_id:
                session_id = f"feishu_{uuid.uuid4().hex[:12]}"
                self._chat_sessions[session_key] = session_id

            # 构造事件并发布（从 SDK 线程调度到 asyncio 事件循环）
            envelope = EventEnvelope(
                type="ui.user_input",
                session_id=session_id,
                turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                source="feishu",
                payload={
                    "content": text,
                    "attachments": [],
                    "context_files": [],
                    # 飞书特有元数据，供 send_event 回复时使用
                    "_feishu_meta": {
                        "chat_id": chat_id,
                        "chat_type": chat_type,
                        "message_id": message_id,
                        "sender_id": sender_id,
                    },
                },
            )

            if self._gateway and self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._gateway.publish_from_channel(envelope),
                    self._loop,
                )
                future.result(timeout=10)

        except Exception:
            logger.exception("Failed to handle Feishu message event")

    def _extract_text(
        self,
        msg_type: str,
        content_str: str,
        chat_type: str,
        msg: Any,
    ) -> str | None:
        """从飞书消息中提取纯文本"""
        if msg_type == "text":
            content = json.loads(content_str)
            text = content.get("text", "").strip()
            # 群聊中去掉 @bot 前缀
            if chat_type == "group" and msg.mentions:
                for mention in msg.mentions:
                    text = text.replace(mention.key, "").strip()
            return text if text else None

        if msg_type == "image":
            return "[用户发送了一张图片]"

        if msg_type == "file":
            content = json.loads(content_str)
            file_name = content.get("file_name", "unknown")
            return f"[用户发送了文件: {file_name}]"

        # 不支持的消息类型
        logger.debug("Unsupported Feishu message type: %s", msg_type)
        return None

    def _should_respond(
        self,
        chat_type: str,
        sender_id: str,
        msg: Any,
    ) -> bool:
        """根据配置策略决定是否响应"""
        if chat_type == "p2p":
            if self._config.dm_policy == "allowlist":
                return (
                    self._config.allowlist is not None
                    and sender_id in self._config.allowlist
                )
            return True  # dm_policy == "open"

        if chat_type == "group":
            if self._config.group_policy == "disabled":
                return False
            if self._config.group_policy == "mention":
                # 仅当 @bot 时响应
                return bool(msg.mentions)
            return True  # group_policy == "open"

        return False

    def _resolve_session_key(
        self,
        chat_id: str,
        chat_type: str,
        sender_id: str,
    ) -> str:
        """
        构造 session 映射 key。
        - 私聊: 每个用户一个 session
        - 群聊: 每个群一个 session（群内所有人共享上下文）
        """
        if chat_type == "p2p":
            return f"dm:{sender_id}"
        return f"group:{chat_id}"

    # ================================================================
    # 出站: AgentOS → 飞书
    # ================================================================

    async def send_event(self, event: EventEnvelope) -> None:
        """
        接收 Gateway 分发的事件，将 Agent 回复发送到飞书。
        仅处理 agent.step_completed 和 error.raised 两类事件。
        """
        if event.type == AGENT_STEP_COMPLETED:
            text = event.payload.get("result", {}).get("content", "")
            if not text:
                text = event.payload.get("final_response", "")
            if text:
                await self._send_reply(event.session_id, text)

        elif event.type == ERROR_RAISED:
            error_msg = event.payload.get("error_message", "处理失败")
            await self._send_reply(
                event.session_id,
                f"⚠️ 错误: {error_msg}",
            )

    async def _send_reply(self, session_id: str, text: str) -> None:
        """通过飞书 API 发送文本消息"""
        if not self._client:
            logger.warning("Feishu client not initialized, skipping reply")
            return

        # 查找 session 对应的 chat_id
        chat_id = self._find_chat_id(session_id)
        if not chat_id:
            logger.warning("No chat_id found for session %s", session_id)
            return

        # 文本截断（飞书单条消息限制约 30000 字符）
        max_len = 20000
        if len(text) > max_len:
            text = text[:max_len] + "\n\n... (内容过长，已截断)"

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )

            response = await asyncio.to_thread(
                self._client.im.v1.message.create, request
            )

            if not response.success():
                logger.error(
                    "Feishu send failed: code=%s msg=%s",
                    response.code,
                    response.msg,
                )

        except Exception:
            logger.exception("Failed to send Feishu message")

    def _find_chat_id(self, session_id: str) -> str | None:
        """根据 session_id 反查 chat_id"""
        for key, sid in self._chat_sessions.items():
            if sid == session_id:
                # key 格式: "dm:<sender_id>" 或 "group:<chat_id>"
                parts = key.split(":", 1)
                if parts[0] == "group":
                    return parts[1]
                # 私聊需要 chat_id，但我们存的是 sender_id
                # 实际需要通过飞书 API 或缓存的 chat_id 获取
                # 这里使用 _chat_id_cache 辅助
                return self._dm_chat_id_cache.get(parts[1])
        return None
```

> **注意**: 上面的伪代码展示核心逻辑。实际实现中需要补充:
> - 私聊场景下 `sender_id → chat_id` 的缓存（在 `_handle_message_event` 中缓存 `chat_id`）
> - 长消息分片发送
> - 更完善的错误重试

### 3.5 Session 管理策略

飞书消息不像 WebSocket 有持久连接，需要将飞书会话映射为 AgentOS session:

| 飞书场景 | session_key | 说明 |
|----------|------------|------|
| 私聊 | `dm:<sender_open_id>` | 每个用户一个独立 session，跨消息保持上下文 |
| 群聊 | `group:<chat_id>` | 每个群一个 session，群成员共享上下文 |

映射存储在内存 `dict` 中。Gateway 重启后映射丢失，新消息会创建新 session（对话上下文重置）。

后续可增强为:
- 持久化到 SQLite（重启不丢失）
- Session 超时自动清理（如 24h 无消息则关闭 session）
- 支持 `/new` 命令手动重置

### 3.6 Gateway 集成改造

当前 `Gateway` 需要小幅增强，支持 Channel 反向引用 Gateway:

```python
# app/gateway/gateway.py 修改

class Gateway:
    def register_channel(self, channel: Channel) -> None:
        channel_id = channel.get_channel_id()
        self._channels[channel_id] = channel
        # 新增: 注入 Gateway 引用，供 Channel 主动发布事件
        if hasattr(channel, "set_gateway"):
            channel.set_gateway(self)
        # 新增: 自动绑定 session
        self._session_bindings[channel_id] = channel_id
        logger.info(f"Registered channel: {channel_id}")
```

飞书 Channel 与 WebSocket Channel 的关键区别:

| 维度 | WebSocket Channel | Feishu Channel |
|------|-------------------|----------------|
| 连接发起方 | 前端主动连接后端 | 后端主动连接飞书服务器 |
| 入站消息 | `main.py` 的 WS endpoint 调用 `gateway.publish_from_channel()` | Channel 内部回调调用 `gateway.publish_from_channel()` |
| session 绑定 | `main.py` 里手动 `gateway.bind_session()` | Channel 内部自管理 `_chat_sessions` 映射 |
| 出站分发 | Gateway `_dispatch_event()` 按 session_id 查 channel_id | 同左，但需要增加动态绑定逻辑 |

为支持飞书 Channel 的动态 session 绑定，`Gateway._dispatch_event` 需要增强:

```python
async def _dispatch_event(self, event: EventEnvelope) -> None:
    if not event.session_id:
        return

    channel_id = self._session_bindings.get(event.session_id)
    if not channel_id:
        # 新增: 按 session_id 前缀匹配 Channel
        # feishu session 以 "feishu_" 开头
        if event.session_id.startswith("feishu_"):
            channel_id = "feishu"
        else:
            return

    channel = self._channels.get(channel_id)
    if not channel:
        return

    try:
        await channel.send_event(event)
    except Exception as exc:
        logger.error(f"Failed to send event to channel {channel_id}: {exc}")
```

### 3.7 Channel 基类增强

为支持 "Channel 主动推送入站消息" 的模式（飞书、Slack、Telegram 等都是这种模式），为 `Channel` ABC 增加可选方法:

```python
# app/gateway/base.py

class Channel(ABC):
    @abstractmethod
    def get_channel_id(self) -> str:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def send_event(self, event: EventEnvelope) -> None:
        pass

    # 新增: 可选方法，Gateway 注册时注入引用
    def set_gateway(self, gateway: "Gateway") -> None:
        """Gateway 注入，供 Channel 主动发布入站事件。默认空实现。"""
        pass
```

---

## 4. 飞书 Bot 创建指南（用户侧）

用户需要在飞书开放平台创建一个企业自建应用:

### 4.1 步骤

1. 访问 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 在「凭证与基础信息」页获取 `App ID` 和 `App Secret`
3. 在「添加应用能力」中添加「机器人」
4. 在「事件与回调」→「事件配置方式」中选择 **使用长连接接收事件**
5. 在「事件订阅」中添加事件:
   - `im.message.receive_v1`（接收消息）
6. 在「权限管理」中开通:
   - `im:message`（获取与发送单聊、群组消息）
   - `im:message:send_as_bot`（以应用的身份发消息）
7. 发布应用版本

### 4.2 配置写入 config.yaml

```yaml
plugins:
  feishu:
    enabled: true
    app_id: "cli_xxxxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxxxxxxxxxx"
    dm_policy: "open"
    group_policy: "mention"
```

---

## 5. 新增文件

```
backend/app/plugins/
├── __init__.py              # PluginRegistry 类
├── base.py                  # PluginApi, PluginDefinition
├── loader.py                # 插件发现和加载逻辑
└── feishu/
    ├── __init__.py
    ├── plugin.py            # register(api) 入口
    ├── channel.py           # FeishuChannel(Channel) 实现
    ├── client.py            # 飞书 API client 封装
    ├── config.py            # FeishuConfig
    └── events.py            # 飞书事件类型解析
```

## 6. 修改文件

| 文件 | 修改 |
|------|------|
| `main.py` | lifespan 中添加 PluginRegistry 加载和 apply |
| `gateway/base.py` | Channel 增加 `set_gateway()` 默认实现 |
| `gateway/gateway.py` | `register_channel` 注入 gateway；`_dispatch_event` 增加前缀匹配 |
| `config.py` | DEFAULT_CONFIG 添加 `plugins` 段 |
| `pyproject.toml` | dependencies 添加 `lark-oapi` |

---

## 7. 新增依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| `lark-oapi` | `>=1.5.0` | 飞书 OpenAPI SDK（WebSocket 长连接 + 消息 API） |

---

## 8. 验收标准

1. **Plugin 加载**: `config.yaml` 中 `plugins.feishu.enabled: true` 时，启动日志显示 "FeishuChannel started"
2. **Plugin 禁用**: `enabled: false` 时，无飞书相关日志，不影响 WebSocket Channel
3. **私聊收发**: 在飞书中给 bot 发消息 → Agent 处理 → 回复出现在飞书对话中
4. **群聊 @bot**: 在群中 @bot + 消息 → Agent 处理 → 回复出现在群中
5. **群聊过滤**: 群中未 @bot 的消息不触发 Agent
6. **多轮对话**: 同一飞书用户的多条消息保持在同一 session 中（上下文连贯）
7. **错误容错**: 飞书连接断开后 WebSocket Channel 不受影响
8. **WebSocket 不受影响**: 新增飞书 Channel 后，原有 Web 前端功能完全正常

---

## 9. 交付计划

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | Plugin 系统骨架（base.py + registry + loader） | 0.5 天 |
| 2 | FeishuConfig + 配置集成 | 0.5 天 |
| 3 | FeishuChannel 入站（WebSocket 长连接 + 消息解析） | 1 天 |
| 4 | FeishuChannel 出站（Agent 回复 → 飞书消息 API） | 0.5 天 |
| 5 | Gateway 改造（set_gateway + 动态 session 绑定） | 0.5 天 |
| 6 | main.py 集成 + 配置 | 0.5 天 |
| 7 | E2E 测试（真实飞书 bot） | 1 天 |

**总计: 4.5 天**

---

## 10. 后续扩展

| 特性 | 优先级 | 说明 |
|------|--------|------|
| 富卡片消息 | P1 | Markdown → 飞书卡片消息（代码块、表格等） |
| 图片/文件发送 | P1 | Agent 生成的文件通过飞书文件 API 发送 |
| Session 持久化 | P1 | chat_id → session_id 映射持久化到 SQLite |
| `/new` 命令 | P2 | 飞书内发送 `/new` 重置 session |
| 多账号 | P2 | 一个 AgentOS 实例连接多个飞书 bot |
| Webhook 模式 | P3 | 适配有公网域名的部署场景 |
| 消息回复引用 | P3 | 使用飞书的 reply 消息接口保持对话线程 |
| 更多 Channel | P3 | 使用 Plugin 系统接入 Slack、Discord、微信等 |
