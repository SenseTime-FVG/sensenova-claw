# 插件系统

> 路径：`agentos/adapters/plugins/`

插件系统允许在不修改核心代码的情况下扩展 AgentOS 的功能。

---

## PluginRegistry

`PluginRegistry` 在系统启动时加载和管理所有插件：

```python
class PluginRegistry:
    _plugins: dict[str, Plugin]

    load_plugins()                 # 启动时扫描并加载插件
    get_plugin(name) -> Plugin     # 获取已注册的插件
    list_plugins() -> list[str]    # 列出所有插件名称
```

---

## 插件能力

插件可以通过以下方式扩展系统功能：

| 扩展点 | 方法 | 说明 |
|--------|------|------|
| 注册新的 Channel | `Gateway.register_channel()` | 添加新的用户接入渠道 |
| 注册新的工具 | `ToolRegistry.register()` | 添加自定义工具供 Agent 使用 |
| 订阅事件 | `PublicEventBus.subscribe()` | 监听和响应系统事件 |
| 扩展 Gateway | Gateway API | 扩展 Gateway 的路由和处理逻辑 |

---

## 当前内置插件

### FeishuChannel 插件

飞书机器人接入插件，提供以下功能：

- 接收飞书 Webhook 回调，将用户消息转发到 Agent
- 将 Agent 响应渲染为飞书卡片格式
- 支持 `OutboundCapable` 协议，实现主动推送消息
- 处理 `cron.delivery_requested` 事件，向飞书用户/群组广播通知

---

## 开发自定义插件

### 1. 实现 Plugin 接口

```python
from agentos.adapters.plugins import Plugin

class MyPlugin(Plugin):
    name = "my_plugin"

    async def on_load(self, context):
        """插件加载时调用"""
        # 注册新的 Channel
        channel = MyCustomChannel()
        context.gateway.register_channel(channel)

        # 注册新的工具
        @context.tool_registry.register()
        def my_custom_tool(param: str) -> str:
            """自定义工具描述"""
            return f"处理结果: {param}"

        # 订阅事件
        context.event_bus.subscribe(
            "agent.step_completed",
            self.on_step_completed
        )

    async def on_unload(self):
        """插件卸载时调用"""
        # 清理资源
        pass

    async def on_step_completed(self, event):
        """自定义事件处理"""
        # 处理逻辑
        pass
```

### 2. 放置插件文件

将插件代码放置在 `agentos/adapters/plugins/` 目录下：

```
agentos/adapters/plugins/
  __init__.py
  feishu/              # 飞书插件
    __init__.py
    channel.py
    ...
  my_plugin/           # 自定义插件
    __init__.py
    plugin.py
```

### 3. 在配置中启用

在 `config.yml` 中启用插件：

```yaml
plugins:
  feishu:
    enabled: true
    app_id: cli_xxx
    app_secret: xxx
  my_plugin:
    enabled: true
    # 插件自定义配置...
```

---

## 插件生命周期

```
系统启动
  → PluginRegistry.load_plugins()
  → 扫描 plugins 目录
  → 逐个调用 plugin.on_load(context)
  → 插件注册 Channel / 工具 / 事件监听
  → 系统正常运行

系统关闭
  → 逐个调用 plugin.on_unload()
  → 清理插件注册的资源
```

**注意事项**：

- 插件加载顺序可能影响依赖关系，需要注意插件间的依赖
- 插件注册的工具会出现在 LLM 的工具列表中，需确保工具描述清晰准确
- 插件订阅的事件处理应避免阻塞，推荐使用异步处理
