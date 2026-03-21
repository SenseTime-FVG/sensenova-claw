# ConfigManager 设计文档

## 概述

设计一个 `ConfigManager` 模块，统一管理 `config.yml` 的读写，并通过 EventBus 事件驱动机制与下游模块联动，实现配置变更的自动传播。

## 需求

1. **全 section 可编辑** — 所有配置 section（`llm`、`agent`、`agents`、`tools`、`memory`、`cron`、`plugins`、`system`、`skills` 等）均可通过 API 更新
2. **模块自治** — ConfigManager 只负责持久化和发事件，各模块自己决定是否刷新、如何刷新
3. **前端 WebSocket 通知** — 配置变更通过 EventBus → Gateway 广播给所有已连接的 WebSocket 客户端
4. **合并 config_store** — 将 `interfaces/http/config_store.py` 的持久化逻辑合并进 ConfigManager，删除原文件
5. **统一入口 + 文件监听** — 所有写入都通过 `ConfigManager.update()`；额外监听 YAML 文件变化，手动编辑也触发联动

## 架构

```
HTTP API / 内部模块 / 文件监听
        │
        ▼
  ConfigManager.update(section, data)
        │
        ├─ 1. 持久化到 YAML（含 secret → keyring）
        ├─ 2. 刷新内存 cfg.data
        └─ 3. PublicEventBus.publish(config.updated)
                │
                ├─ LLMFactory 订阅 → 重建 provider 表
                ├─ AgentRegistry 订阅 → 重载 agent 定义
                ├─ MemoryManager 订阅 → 重建 MemoryConfig
                └─ Gateway 订阅 → 广播给所有 WebSocket Channel
```

## 详细设计

### 1. ConfigManager 核心

**位置**: `agentos/platform/config/config_manager.py`

```python
class ConfigManager:
    """配置管理器：统一入口，负责持久化、内存同步、事件通知"""

    def __init__(self, config: Config, event_bus: PublicEventBus, secret_store: SecretStore):
        self._config = config
        self._event_bus = event_bus
        self._secret_store = secret_store
        self._watcher: ConfigFileWatcher | None = None
        self._self_writing = False  # 自写标记，防止文件监听循环触发

    async def update(self, section: str, data: dict) -> dict:
        """更新指定 section 的配置（唯一写入入口）

        流程:
        1. 加载当前 YAML 文件（保留未知 section）
        2. 识别 secret 路径，存入 keyring，YAML 写 ${secret:...} 引用
        3. 非 secret 路径直接写入 YAML
        4. 写回文件（设 self._self_writing 标记）
        5. 刷新内存 cfg.data（调用 cfg._load_config()）
        6. 计算变更内容，构造 payload
        7. 发布 config.updated 事件
        8. 返回更新后的 section 数据（secret 脱敏）
        """

    async def get_section(self, section: str) -> dict:
        """读取指定 section，secret 脱敏"""

    async def get_sections(self, sections: list[str]) -> dict:
        """批量读取多个 section"""

    def start_file_watcher(self):
        """启动 YAML 文件监听"""

    def stop_file_watcher(self):
        """停止文件监听"""

    async def _on_file_changed(self, section: str, changes: dict):
        """文件监听回调：刷新内存 + 发布事件（不重复写文件）"""
```

**合并 config_store.py 的逻辑**:

原 `config_store.py` 中的以下函数合并为 ConfigManager 的内部方法：

| config_store.py 函数 | → ConfigManager 方法 |
|---|---|
| `load_raw_config(cfg)` | `_load_raw_yaml()` |
| `write_raw_config(cfg, raw)` | `_write_raw_yaml(raw)` |
| `persist_path_updates(cfg, updates)` | `update()` 内部逻辑 |
| `reload_config(cfg)` | `_reload_memory()` |

合并后删除 `interfaces/http/config_store.py`。

### 2. 事件定义

**新增事件类型** (`agentos/kernel/events/types.py`):

```python
CONFIG_UPDATED = "config.updated"
```

**Envelope 结构**:

```python
EventEnvelope(
    type="config.updated",
    session_id="__system__",
    source="system",
    payload={
        "section": "llm",
        "changes": {
            "llm.providers.openai.api_key": {"new": "sk-***"},       # secret 脱敏
            "llm.providers.openai.base_url": {"new": "https://..."},  # 非 secret 明文
            "llm.default_model": {"new": "gpt_4o"}
        }
    }
)
```

**Payload 规则**:

- `section`: 变更的配置 section 名称
- `changes`: 变更的具体路径及新值
- secret 字段在 payload 中一律脱敏（如 `sk-***`），消费者需要真实值时通过 `config.get()` 读取

### 3. 事件传播路径

```
ConfigManager.update()
  → PublicEventBus.publish(config.updated)
      ├─ BusRouter: session_id="__system__" 找不到私有总线 → 跳过（不影响会话路由）
      ├─ Gateway._dispatch_loop: 识别 config.* 前缀 → 广播给所有 Channel
      └─ 各模块订阅者: 订阅 PublicEventBus，过滤 type=="config.updated"
```

**Gateway 广播改造** (`interfaces/ws/gateway.py`):

在 `_dispatch_loop` 中新增分支，对 `config.*` 事件广播给所有已连接的 Channel：

```python
async for event in self._public_bus.subscribe():
    if event.type.startswith("config."):
        for channel in self._channels.values():
            await channel.send_event(event)
    else:
        await self._dispatch_event(event)
```

### 4. 文件监听

**位置**: `agentos/platform/config/config_file_watcher.py`

```python
class ConfigFileWatcher:
    """监听 config.yml 文件变化，外部编辑也触发联动"""

    def __init__(self, config_path: Path, on_change: Callable):
        self._config_path = config_path
        self._on_change = on_change
        self._observer: Observer | None = None
        self._debounce_seconds = 1.0
        self._last_hash: str | None = None

    def start(self): ...
    def stop(self): ...
```

**防误触发机制**:

1. **防抖** — 1 秒内多次文件事件只处理最后一次
2. **内容 hash 比对** — 计算文件 md5，与上次相同则跳过
3. **自写过滤** — ConfigManager 写文件时设置 `_self_writing` 标记，监听器检查标记后跳过

**变更检测流程**:

```
文件变化 → 防抖(1s) → hash 比对 → 是自写? → 跳过
                                  → 非自写? → 加载新 YAML
                                             → diff 出变更的 sections
                                             → 对每个变更 section 调 _on_file_changed()
                                             → 刷新内存 + 发布事件
```

**依赖**: `watchdog`（纯 Python，跨平台），添加到 `pyproject.toml`。

### 5. 模块订阅

各模块的配置敏感度分析：

| 模块 | 监听 section | 刷新动作 | 必要性 |
|---|---|---|---|
| **LLMFactory** | `llm` | 重建 `_lazy` 表 + 清除已实例化 provider | 必须 |
| **AgentRegistry** | `agents` | 清除 `_agents` + 重新 `load_from_config()` | 必须 |
| **MemoryManager** | `memory` | 重建 `MemoryConfig` 替换 `self.config` | 必须 |
| ToolRegistry | — | 不需要订阅（动态读取 api_key） | — |
| NotificationService | — | 不需要订阅（动态读取） | — |
| 各 Worker | — | 不需要订阅（每次执行动态读 config） | — |

**订阅实现**:

每个需要刷新的模块新增 `start_config_listener(bus)` 方法：

```python
# LLMFactory
class LLMFactory:
    async def start_config_listener(self, bus: PublicEventBus):
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload["section"] == "llm":
                self._providers.clear()
                self._lazy.clear()
                self._register_providers()
                logger.info("LLMFactory: providers reloaded due to config change")

# AgentRegistry
class AgentRegistry:
    async def start_config_listener(self, bus: PublicEventBus, config: Config):
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload["section"] == "agents":
                self._agents.clear()
                self.load_from_config(config.data)
                logger.info("AgentRegistry: agents reloaded due to config change")

# MemoryManager
class MemoryManager:
    async def start_config_listener(self, bus: PublicEventBus, config: Config):
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload["section"] == "memory":
                new_mem_config = MemoryConfig.from_dict(config.data.get("memory", {}))
                self.config = new_mem_config
                logger.info("MemoryManager: config reloaded due to config change")
```

### 6. 生命周期集成

**Gateway lifespan** (`gateway/main.py`):

```python
# 初始化
config = Config()
secret_store = KeyringSecretStore()
config_manager = ConfigManager(config, public_event_bus, secret_store)
config_manager.start_file_watcher()
app.state.config_manager = config_manager

# 启动模块订阅
asyncio.create_task(llm_factory.start_config_listener(public_bus))
asyncio.create_task(agent_registry.start_config_listener(public_bus, config))
asyncio.create_task(memory_manager.start_config_listener(public_bus, config))

# shutdown
config_manager.stop_file_watcher()
```

**HTTP 层瘦化** (`config_api.py`):

```python
# 改造前
@router.put("/api/config/sections")
async def update_sections(body, request):
    cfg = request.app.state.config
    persist_path_updates(cfg, updates)
    return sanitized_response

# 改造后
@router.put("/api/config/sections")
async def update_sections(body, request):
    config_manager = request.app.state.config_manager
    result = await config_manager.update(section, data)
    return result
```

## 文件变更清单

| 操作 | 文件 |
|---|---|
| **新建** | `agentos/platform/config/config_manager.py` |
| **新建** | `agentos/platform/config/config_file_watcher.py` |
| **修改** | `agentos/kernel/events/types.py` — 新增 `CONFIG_UPDATED` |
| **修改** | `agentos/interfaces/ws/gateway.py` — 广播 `config.*` 事件 |
| **修改** | `agentos/interfaces/http/config_api.py` — 改用 ConfigManager |
| **修改** | `agentos/adapters/llm/factory.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/capabilities/agents/registry.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/capabilities/memory/manager.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/app/gateway/main.py` — 初始化 ConfigManager + 启动订阅任务 |
| **删除** | `agentos/interfaces/http/config_store.py` |
| **修改** | `pyproject.toml` — 添加 `watchdog` 依赖 |

## 设计要点

- **唯一写入入口** — 所有配置变更都通过 `ConfigManager.update()`，保证一致性
- **事件驱动** — 复用现有 `PublicEventBus`，不引入新的通知机制
- **模块自治** — 各模块自己订阅、自己决定刷新策略
- **幂等刷新** — 模块刷新逻辑为 clear → rebuild，多次触发无副作用
- **正在执行的会话不受影响** — Worker 持有的引用在当前调用中仍有效，下次调用才拿新的
- **Secret 安全** — 事件 payload 中 secret 一律脱敏，真实值只在内存中通过 `config.get()` 访问
