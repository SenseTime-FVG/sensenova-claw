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
        ├─ 1. 加锁（asyncio.Lock）
        ├─ 2. 持久化到 YAML（含 secret → keyring）
        ├─ 3. 刷新内存 cfg.data
        └─ 4. PublicEventBus.publish(config.updated)
                │
                ├─ BusRouter: 跳过 config.* 前缀（不路由到私有总线）
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
        self._lock = asyncio.Lock()              # 并发写入保护
        self._last_written_hash: str | None = None  # 自写检测（替代布尔标记）

    async def update(self, section: str, data: dict) -> dict:
        """更新指定 section 的配置（唯一写入入口）

        参数:
          section: 配置 section 名称，如 "llm"、"agents"、"tools"
          data: 该 section 下的嵌套字典，如 {"providers": {"openai": {"api_key": "..."}}}
                与现有 section 数据深度合并（非替换）

        流程:
        1. 获取 asyncio.Lock，防止并发写入冲突
        2. 加载当前 YAML 文件（保留未知 section）
        3. 将 data 深度合并到 raw_config[section]
        4. 识别 secret 路径，存入 keyring，YAML 写 ${secret:...} 引用
        5. 非 secret 路径直接写入 YAML
        6. 写回文件，记录写后文件 hash（供文件监听器识别自写）
        7. 刷新内存 cfg.data（调用 cfg._load_config()）
        8. 计算变更内容，构造 payload（secret 脱敏）
        9. 发布 config.updated 事件
        10. 返回更新后的 section 数据（secret 脱敏）
        """

    async def get_section(self, section: str) -> dict:
        """读取指定 section，secret 脱敏"""

    async def get_sections(self, sections: list[str]) -> dict:
        """批量读取多个 section"""

    def start_file_watcher(self):
        """启动 YAML 文件监听"""

    def stop_file_watcher(self):
        """停止文件监听"""

    async def _on_file_changed(self, changed_sections: dict[str, dict]):
        """文件监听回调：刷新内存 + 发布事件（不重复写文件）

        参数:
          changed_sections: {section_name: changes_dict} 变更的 section 及其变更内容
        """

    def _load_raw_yaml(self) -> dict:
        """读取 YAML 文件，保留所有 section（原 config_store.load_raw_config）"""

    def _write_raw_yaml(self, raw_config: dict):
        """写回 YAML 文件（原 config_store.write_raw_config）
        写入后更新 self._last_written_hash"""

    def _reload_memory(self):
        """刷新内存 cfg.data（原 config_store.reload_config）"""
```

**`update()` 接口约定**:

HTTP 层调用示例：
```python
# config_api.py 改造后
@router.put("/api/config/sections")
async def update_sections(body: dict, request: Request):
    config_manager = request.app.state.config_manager
    results = {}
    for section, data in body.items():
        results[section] = await config_manager.update(section, data)
    return results
```

`config_api.py` 不再限制 `EDITABLE_SECTIONS`，任意 section 名称均可接受。原有的 `SectionsUpdateBody` Pydantic 模型替换为通用 `dict`，由 ConfigManager 负责校验。

**合并 config_store.py 的逻辑**:

原 `config_store.py` 中的以下函数合并为 ConfigManager 的内部方法：

| config_store.py 函数 | → ConfigManager 方法 |
|---|---|
| `load_raw_config(cfg)` | `_load_raw_yaml()` |
| `write_raw_config(cfg, raw)` | `_write_raw_yaml(raw)` |
| `persist_path_updates(cfg, updates)` | `update()` 内部逻辑 |
| `reload_config(cfg)` | `_reload_memory()` |

合并后删除 `interfaces/http/config_store.py`。

**并发控制**:

`update()` 内部使用 `asyncio.Lock` 序列化所有写入操作，防止并发 HTTP 请求导致 YAML 文件读写冲突。文件监听回调 `_on_file_changed()` 也需要获取此锁，防止与正在进行的 `update()` 冲突。

**错误处理**:

- YAML 解析失败（文件被外部编辑为无效格式）：记录 warning 日志，不更新内存，不发布事件
- Secret store 写入失败：抛出异常，回滚 YAML 变更
- 文件写入失败：抛出异常，不刷新内存，不发布事件

### 2. 事件定义

**新增事件类型** (`agentos/kernel/events/types.py`):

```python
# 配置变更事件
CONFIG_UPDATED = "config.updated"

# 系统级事件的 session_id 常量
SYSTEM_SESSION_ID = "__system__"
```

`SYSTEM_SESSION_ID` 是广播哨兵值，表示此事件不属于任何用户会话，用于系统级事件（如配置变更）。

**Envelope 结构**:

```python
EventEnvelope(
    type="config.updated",
    session_id=SYSTEM_SESSION_ID,  # "__system__"，广播哨兵
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
- `changes`: 变更的具体路径及新值（`{"path": {"new": value}}`）
- secret 字段在 payload 中一律脱敏（如 `sk-***`），消费者需要真实值时通过 `config.get()` 读取
- 不携带 `old` 值：这是刻意选择。消费者收到事件后应直接读取最新配置，而非基于 diff 做决策。如果需要知道"是否真的变了"，比对 `changes[path]["new"]` 与自身缓存的旧值即可

### 3. 事件传播路径

```
ConfigManager.update()
  → PublicEventBus.publish(config.updated)
      ├─ BusRouter._route_loop: 跳过 config.* 前缀（与 system.* 同等处理）
      ├─ Gateway._event_loop: 识别 config.* 前缀 → 广播给所有 Channel
      └─ 各模块订阅者: 订阅 PublicEventBus，过滤 type=="config.updated"
```

**BusRouter 改造** (`kernel/events/router.py`):

在 `_route_loop` 中将 `config.*` 加入跳过列表，避免无意义的私有总线查找：

```python
async def _route_loop(self) -> None:
    async for event in self._public_bus.subscribe():
        if not event.session_id:
            continue
        # system.* 和 config.* 事件不路由到私有总线
        if event.type.startswith("system.") or event.type.startswith("config."):
            continue
        # ... 原有路由逻辑
```

**Gateway 广播改造** (`interfaces/ws/gateway.py`):

在 Gateway 的事件循环中（`_event_loop` 方法），新增 `config.*` 前缀的广播分支。完整改造如下：

```python
async def _event_loop(self) -> None:
    """订阅 PublicEventBus，分发事件到对应 Channel"""
    async for event in self._public_bus.subscribe():
        if event.type.startswith("config."):
            # 配置变更：广播给所有已连接的 Channel
            for channel in self._channels.values():
                try:
                    await channel.send_event(event)
                except Exception as exc:
                    logger.error(f"Failed to broadcast config event to channel: {exc}")
        else:
            # 其他事件：按 session_id 路由到绑定的 Channel
            await self._dispatch_event(event)
```

### 4. 文件监听

**位置**: `agentos/platform/config/config_file_watcher.py`

```python
class ConfigFileWatcher:
    """监听 config.yml 文件变化，外部编辑也触发联动"""

    def __init__(self, config_path: Path, on_change: Callable, event_loop: asyncio.AbstractEventLoop):
        self._config_path = config_path
        self._on_change = on_change           # async 回调: ConfigManager._on_file_changed
        self._event_loop = event_loop         # 用于线程→asyncio 桥接
        self._observer: Observer | None = None
        self._debounce_seconds = 1.0
        self._last_known_hash: str | None = None  # 内容 hash，用于自写检测 + 无实质变更跳过

    def start(self): ...
    def stop(self): ...

    def _on_modified(self, event):
        """watchdog 回调（在 OS 线程中执行）
        通过 loop.call_soon_threadsafe + run_coroutine_threadsafe 桥接到 asyncio"""
```

**防误触发机制**（两层，不使用布尔标记）:

1. **防抖** — 1 秒内多次文件事件只处理最后一次（通过 `threading.Timer` 实现）
2. **内容 hash 比对**（主要机制） — 计算文件内容 hash，与 `_last_known_hash` 比较：
   - 相同 → 跳过（无实质变更，或是 ConfigManager 自写）
   - 不同 → 视为外部变更，触发回调，更新 hash

   ConfigManager 写文件后也更新 `_last_written_hash`，watcher 的 `_last_known_hash` 与之同步。这样 ConfigManager 自写的文件，hash 一致，自然跳过。

**线程→asyncio 桥接**:

`watchdog` 回调在 OS 线程中执行，需要通过 `asyncio.run_coroutine_threadsafe(callback, loop)` 调度到事件循环：

```python
def _on_debounced(self):
    """防抖后的实际处理（仍在 OS 线程中）"""
    new_hash = self._compute_file_hash()
    if new_hash == self._last_known_hash:
        return  # 无实质变更或自写，跳过
    self._last_known_hash = new_hash

    # 加载新 YAML，diff 出变更 sections
    try:
        new_config = yaml.safe_load(self._config_path.read_text())
    except yaml.YAMLError:
        logger.warning("config.yml YAML 解析失败，跳过本次变更")
        return

    changed_sections = self._diff_sections(new_config)
    if changed_sections:
        asyncio.run_coroutine_threadsafe(
            self._on_change(changed_sections), self._event_loop
        )
```

**变更检测流程**:

```
文件变化 → 防抖(1s) → hash 比对 → 相同? → 跳过（自写或无实质变更）
                                  → 不同? → 解析 YAML → 解析失败? → 记录 warning，跳过
                                                       → 成功? → diff sections
                                                                → 桥接到 asyncio
                                                                → _on_file_changed()
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

**Config 单例一致性**:

当前 `LLMFactory` 通过模块级 `from agentos.platform.config.config import config` 导入全局单例。Gateway lifespan 中也使用此单例初始化 ConfigManager。两者引用的是同一个 `Config` 实例，因此 `ConfigManager._reload_memory()` 刷新 `cfg.data` 后，`LLMFactory` 中的 `_has_api_key()` 自然能读到最新值。

**实现时须确保**: Gateway lifespan 使用 `from agentos.platform.config.config import config` 获取的同一单例传给 ConfigManager，不要另建新实例。

### 6. 生命周期集成

**Gateway lifespan** (`gateway/main.py`):

```python
from agentos.platform.config.config import config  # 全局单例

# 初始化
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
async def update_sections(body: dict, request: Request):
    config_manager = request.app.state.config_manager
    results = {}
    for section, data in body.items():
        results[section] = await config_manager.update(section, data)
    return results
```

## 文件变更清单

| 操作 | 文件 |
|---|---|
| **新建** | `agentos/platform/config/config_manager.py` |
| **新建** | `agentos/platform/config/config_file_watcher.py` |
| **修改** | `agentos/kernel/events/types.py` — 新增 `CONFIG_UPDATED`、`SYSTEM_SESSION_ID` |
| **修改** | `agentos/kernel/events/router.py` — `_route_loop` 跳过 `config.*` 前缀 |
| **修改** | `agentos/interfaces/ws/gateway.py` — 广播 `config.*` 事件给所有 Channel |
| **修改** | `agentos/interfaces/http/config_api.py` — 改用 ConfigManager，移除 `EDITABLE_SECTIONS` 限制 |
| **修改** | `agentos/adapters/llm/factory.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/capabilities/agents/registry.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/capabilities/memory/manager.py` — 新增 `start_config_listener()` |
| **修改** | `agentos/app/gateway/main.py` — 初始化 ConfigManager + 启动订阅任务 |
| **删除** | `agentos/interfaces/http/config_store.py` |
| **修改** | `pyproject.toml` — 添加 `watchdog` 依赖 |

## 测试策略

### 单元测试

- **ConfigManager.update()** — mock 文件 I/O + EventBus，验证：事件发布、payload 结构正确、secret 脱敏、深度合并行为
- **并发写入** — 两个并发 `update()` 调用不会导致 YAML 文件损坏（Lock 生效）
- **YAML 解析失败** — 文件监听检测到无效 YAML 时，不更新内存、不发布事件、记录 warning
- **自写检测** — ConfigManager 写入文件后，文件监听器不会重复触发

### 集成测试

- **端到端事件流** — `update()` → EventBus 发布 → 订阅者收到事件 → 模块刷新生效（使用进程内 PublicEventBus）
- **LLMFactory 刷新** — 更新 `llm.providers.openai.api_key` 后，`get_provider("openai")` 返回新的 provider 实例
- **AgentRegistry 刷新** — 更新 `agents` section 后，`get_agent()` 返回新的 agent 定义

### 边界情况

- 空 section 更新（`data={}`）— 不发布事件
- 更新不存在的 section — 创建新 section
- 文件监听期间文件被删除 — 记录 warning，不崩溃

## 设计要点

- **唯一写入入口** — 所有配置变更都通过 `ConfigManager.update()`，保证一致性
- **事件驱动** — 复用现有 `PublicEventBus`，不引入新的通知机制
- **模块自治** — 各模块自己订阅、自己决定刷新策略
- **并发安全** — `asyncio.Lock` 序列化写入，防止竞态
- **幂等刷新** — 模块刷新逻辑为 clear → rebuild，多次触发无副作用
- **正在执行的会话不受影响** — Worker 持有的引用在当前调用中仍有效，下次调用才拿新的
- **Secret 安全** — 事件 payload 中 secret 一律脱敏，真实值只在内存中通过 `config.get()` 访问
- **Config 单例一致性** — Gateway 和所有模块使用同一个 Config 实例，ConfigManager 刷新后全局可见
