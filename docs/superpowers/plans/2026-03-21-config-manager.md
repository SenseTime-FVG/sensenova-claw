# ConfigManager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a ConfigManager module that unifies config.yml persistence, in-memory refresh, and event-driven downstream module coordination.

**Architecture:** ConfigManager lives in `platform/config/`, merges `config_store.py` logic, publishes `config.updated` events via PublicEventBus. LLMFactory, AgentRegistry, MemoryManager subscribe and self-refresh. Gateway broadcasts config events to all WebSocket clients. A file watcher detects external YAML edits.

**Tech Stack:** Python 3.12, asyncio, watchdog, PyYAML, FastAPI, PublicEventBus

**Spec:** `docs/superpowers/specs/2026-03-21-config-manager-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `agentos/platform/config/config_manager.py` | Unified config write entry: persist YAML, refresh memory, publish events |
| Create | `agentos/platform/config/config_file_watcher.py` | Watch config.yml for external changes, debounce, bridge to asyncio |
| Create | `tests/unit/test_config_manager.py` | Unit tests for ConfigManager |
| Create | `tests/unit/test_config_file_watcher.py` | Unit tests for file watcher |
| Create | `tests/unit/test_config_event_subscribers.py` | Tests for module subscription handlers |
| Modify | `agentos/kernel/events/types.py` | Add CONFIG_UPDATED, SYSTEM_SESSION_ID |
| Modify | `agentos/kernel/events/router.py:122` | Skip `config.*` in route loop |
| Modify | `agentos/interfaces/ws/gateway.py:183-186` | Broadcast `config.*` to all channels |
| Modify | `agentos/adapters/llm/factory.py` | Add `start_config_listener()` |
| Modify | `agentos/capabilities/agents/registry.py` | Add `start_config_listener()` |
| Modify | `agentos/capabilities/memory/manager.py` | Add `start_config_listener()` |
| Modify | `agentos/interfaces/http/config_api.py` | Use ConfigManager instead of config_store |
| Modify | `agentos/interfaces/http/notification_api.py` | Use ConfigManager instead of config_store |
| Modify | `agentos/interfaces/http/tools.py` | Use ConfigManager instead of config_store |
| Modify | `agentos/app/gateway/main.py` | Init ConfigManager, start listeners, shutdown watcher |
| Modify | `tests/unit/test_config_api.py` | Update to use ConfigManager |
| Modify | `tests/unit/test_config_store_secrets.py` | Migrate to test ConfigManager |
| Delete | `agentos/interfaces/http/config_store.py` | Logic merged into ConfigManager |
| Modify | `pyproject.toml` | Add `watchdog>=4.0.0` dependency |

---

## Task 1: Add event type constants

**Files:**
- Modify: `agentos/kernel/events/types.py:59-60`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_config_event_subscribers.py
"""config.updated 事件常量和订阅者测试"""
import pytest
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID


def test_config_updated_constant():
    assert CONFIG_UPDATED == "config.updated"


def test_system_session_id_constant():
    assert SYSTEM_SESSION_ID == "__system__"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py::test_config_updated_constant -v`
Expected: FAIL with `ImportError: cannot import name 'CONFIG_UPDATED'`

- [ ] **Step 3: Add constants to types.py**

Add at the end of `agentos/kernel/events/types.py`:

```python
# 配置变更事件
CONFIG_UPDATED = "config.updated"

# 系统级事件的 session_id（广播哨兵，不属于任何用户会话）
SYSTEM_SESSION_ID = "__system__"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentos/kernel/events/types.py tests/unit/test_config_event_subscribers.py
git commit -m "feat: add CONFIG_UPDATED and SYSTEM_SESSION_ID event constants"
```

---

## Task 2: BusRouter skip config.* events

**Files:**
- Modify: `agentos/kernel/events/router.py:121-123`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_config_event_subscribers.py`:

```python
import asyncio
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.router import BusRouter


@pytest.mark.asyncio
async def test_bus_router_skips_config_events():
    """config.* 事件不应路由到私有总线"""
    bus = PublicEventBus()
    router = BusRouter(public_bus=bus)

    # 创建一个私有总线
    private_bus = router.get_or_create("test-session")
    delivered = []

    async def collect():
        async for event in private_bus.subscribe():
            delivered.append(event)

    task = asyncio.create_task(collect())
    await router.start()

    # 发布 config.updated 事件
    await bus.publish(EventEnvelope(
        type="config.updated",
        session_id="__system__",
        source="system",
        payload={"section": "llm", "changes": {}},
    ))

    # 发布一个普通事件到 test-session
    await bus.publish(EventEnvelope(
        type="user.input",
        session_id="test-session",
        payload={"text": "hello"},
    ))

    await asyncio.sleep(0.1)
    await router.stop()
    task.cancel()

    # 只应收到 user.input，不应收到 config.updated
    types = [e.type for e in delivered]
    assert "user.input" in types
    assert "config.updated" not in types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py::test_bus_router_skips_config_events -v`
Expected: FAIL — `config.updated` 事件会被路由到私有总线（session_id="__system__" 不匹配，实际会被跳过因为没有对应的私有总线，但为了语义明确仍需添加跳过逻辑）

注意：这个测试当前可能意外 PASS（因为 `__system__` 没有对应的私有总线所以不会 deliver），但我们仍需修改代码使语义明确。如果 PASS，先继续实现再验证。

- [ ] **Step 3: Add config.* skip to BusRouter**

In `agentos/kernel/events/router.py`, modify `_route_loop` method. Change line 122 from:

```python
            # system.* 事件不路由到私有总线
            if event.type.startswith("system."):
                continue
```

To:

```python
            # system.* 和 config.* 事件不路由到私有总线
            if event.type.startswith("system.") or event.type.startswith("config."):
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentos/kernel/events/router.py tests/unit/test_config_event_subscribers.py
git commit -m "feat: BusRouter skips config.* events from private bus routing"
```

---

## Task 3: ConfigManager core implementation

**Files:**
- Create: `agentos/platform/config/config_manager.py`
- Create: `tests/unit/test_config_manager.py`

This is the largest task. It merges `config_store.py` logic into ConfigManager and adds event publishing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_config_manager.py
"""ConfigManager 单元测试"""
import asyncio
import pytest
import yaml
from pathlib import Path

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID
from agentos.platform.config.config import Config
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.secrets.store import InMemorySecretStore


@pytest.fixture
def setup(tmp_path):
    """构建测试环境：config 文件 + bus + secret_store + ConfigManager"""
    config_path = tmp_path / "config.yml"
    initial = {
        "llm": {
            "providers": {"openai": {"api_key": "sk-old", "base_url": ""}},
            "default_model": "gpt-4o-mini",
        },
        "agent": {"temperature": 0.2},
        "tools": {},
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)
    return manager, cfg, bus, config_path, secret_store


@pytest.mark.asyncio
async def test_update_persists_to_yaml(setup):
    """update() 应将数据写入 YAML 文件"""
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.8})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["temperature"] == 0.8


@pytest.mark.asyncio
async def test_update_refreshes_memory(setup):
    """update() 应刷新内存中的 cfg.data"""
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.9})
    assert cfg.data["agent"]["temperature"] == 0.9


@pytest.mark.asyncio
async def test_update_publishes_event(setup):
    """update() 应发布 config.updated 事件"""
    manager, cfg, bus, config_path, _ = setup
    events = []

    async def collect():
        async for event in bus.subscribe():
            events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await manager.update("agent", {"temperature": 0.7})
    await asyncio.sleep(0.05)

    task.cancel()

    assert len(events) == 1
    assert events[0].type == CONFIG_UPDATED
    assert events[0].session_id == SYSTEM_SESSION_ID
    assert events[0].payload["section"] == "agent"
    assert "agent.temperature" in events[0].payload["changes"]
    assert events[0].payload["changes"]["agent.temperature"]["new"] == 0.7


@pytest.mark.asyncio
async def test_update_deep_merges(setup):
    """update() 应深度合并而非覆盖"""
    manager, cfg, bus, config_path, _ = setup
    await manager.update("llm", {"providers": {"anthropic": {"api_key": "sk-ant"}}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # openai 应仍存在
    assert "openai" in written["llm"]["providers"]
    # anthropic 应被新增
    assert "anthropic" in written["llm"]["providers"]


@pytest.mark.asyncio
async def test_update_handles_secrets(setup):
    """update() 应将 secret 路径存入 keyring"""
    manager, cfg, bus, config_path, secret_store = setup
    await manager.update("llm", {"providers": {"openai": {"api_key": "sk-new"}}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # YAML 中应为 secret ref
    assert written["llm"]["providers"]["openai"]["api_key"].startswith("${secret:")
    # secret store 中应有真实值
    assert secret_store.get("agentos/llm.providers.openai.api_key") == "sk-new"


@pytest.mark.asyncio
async def test_update_event_masks_secrets(setup):
    """事件 payload 中 secret 应脱敏"""
    manager, cfg, bus, config_path, _ = setup
    events = []

    async def collect():
        async for event in bus.subscribe():
            events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await manager.update("llm", {"providers": {"openai": {"api_key": "sk-newsecretkey"}}})
    await asyncio.sleep(0.05)
    task.cancel()

    changes = events[0].payload["changes"]
    api_key_change = changes.get("llm.providers.openai.api_key", {})
    # 不应包含完整 key
    assert "sk-newsecretkey" not in str(api_key_change)


@pytest.mark.asyncio
async def test_update_preserves_other_sections(setup):
    """update() 不应丢失其他 section"""
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.5})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "llm" in written
    assert "tools" in written


@pytest.mark.asyncio
async def test_update_concurrent_lock(setup):
    """并发 update() 不应导致数据损坏"""
    manager, cfg, bus, config_path, _ = setup

    async def update_agent(temp):
        await manager.update("agent", {"temperature": temp})

    await asyncio.gather(
        update_agent(0.1),
        update_agent(0.2),
        update_agent(0.3),
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # 温度值应是三者之一（最后一个获得锁的）
    assert written["agent"]["temperature"] in (0.1, 0.2, 0.3)
    # 不应损坏
    assert "llm" in written


@pytest.mark.asyncio
async def test_get_section(setup):
    """get_section() 应返回脱敏的 section 数据"""
    manager, cfg, bus, config_path, _ = setup
    result = manager.get_section("llm")
    assert "providers" in result


@pytest.mark.asyncio
async def test_update_new_section(setup):
    """update() 应能创建新的 section"""
    manager, cfg, bus, config_path, _ = setup
    await manager.update("memory", {"enabled": True})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["memory"]["enabled"] is True


@pytest.mark.asyncio
async def test_update_empty_data_no_event(setup):
    """空 data 更新不应发布事件"""
    manager, cfg, bus, config_path, _ = setup
    events = []

    async def collect():
        async for event in bus.subscribe():
            events.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await manager.update("agent", {})
    await asyncio.sleep(0.05)
    task.cancel()

    assert len(events) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_config_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agentos.platform.config.config_manager'`

- [ ] **Step 3: Implement ConfigManager**

Create `agentos/platform/config/config_manager.py`:

```python
"""ConfigManager — 配置管理器：统一入口，负责持久化、内存同步、事件通知。

合并了原 interfaces/http/config_store.py 的逻辑。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID
from agentos.platform.config.config import Config
from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref
from agentos.platform.secrets.registry import is_secret_path

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器：统一入口，负责持久化、内存同步、事件通知"""

    def __init__(
        self,
        config: Config,
        event_bus: PublicEventBus,
        secret_store: Any | None = None,
    ):
        self._config = config
        self._event_bus = event_bus
        self._secret_store = secret_store
        self._lock = asyncio.Lock()
        self._last_written_hash: str | None = None
        self._watcher: Any | None = None  # ConfigFileWatcher，延迟导入

    # ── 公共接口 ──────────────────────────────────

    async def update(self, section: str, data: dict) -> dict:
        """更新指定 section 的配置（唯一写入入口）

        参数:
          section: 配置 section 名称，如 "llm"、"agents"、"tools"
          data: 该 section 下的嵌套字典，与现有数据深度合并
        返回:
          更新后的 section 数据（secret 脱敏）
        """
        async with self._lock:
            raw_config = self._load_raw_yaml()
            old_section = deepcopy(raw_config.get(section, {}))

            # 深度合并
            if section not in raw_config or not isinstance(raw_config[section], dict):
                raw_config[section] = {}
            _deep_merge(raw_config[section], data)

            # 展平为 dotted path 用于 secret 处理
            flat_updates = _flatten(data, prefix=section)

            # 处理 secret 路径
            for path, value in flat_updates.items():
                if is_secret_path(path) and self._secret_store is not None:
                    if value:
                        ref = f"agentos/{path}"
                        try:
                            self._secret_store.set(ref, value)
                            _set_nested(raw_config, path, build_secret_ref(ref))
                        except Exception:
                            logger.warning("secret store 不可用，%s 将明文写入 config.yml", path)
                            _set_nested(raw_config, path, value)
                    else:
                        ref = f"agentos/{path}"
                        existing_raw = _get_nested(raw_config, path)
                        if isinstance(existing_raw, str) and is_secret_ref(existing_raw):
                            try:
                                self._secret_store.delete(ref)
                            except Exception:
                                logger.warning("secret store 不可用，跳过删除 %s", path)
                        _set_nested(raw_config, path, "")

            # 写回文件
            self._write_raw_yaml(raw_config)

            # 刷新内存
            self._reload_memory()

            # 构造变更 payload
            changes = {}
            for path, value in flat_updates.items():
                if is_secret_path(path):
                    changes[path] = {"new": _mask_secret(value)}
                else:
                    changes[path] = {"new": value}

            # 发布事件
            if changes:
                event = EventEnvelope(
                    type=CONFIG_UPDATED,
                    session_id=SYSTEM_SESSION_ID,
                    source="system",
                    payload={"section": section, "changes": changes},
                )
                await self._event_bus.publish(event)

            return self.get_section(section)

    def get_section(self, section: str) -> dict:
        """读取指定 section（从内存），secret 脱敏"""
        resolved = deepcopy(self._config.data.get(section, {}))
        raw_config = self._load_raw_yaml()
        raw = deepcopy(raw_config.get(section, {}))
        return _sanitize_section(section, resolved, raw)

    def get_sections(self, sections: list[str]) -> dict:
        """批量读取多个 section"""
        return {s: self.get_section(s) for s in sections}

    # ── 文件监听 ──────────────────────────────────

    def start_file_watcher(self) -> None:
        """启动 config.yml 文件监听"""
        config_path = self._get_config_path()
        if not config_path:
            logger.warning("无法获取配置文件路径，跳过文件监听")
            return
        try:
            from agentos.platform.config.config_file_watcher import ConfigFileWatcher
            loop = asyncio.get_event_loop()
            self._watcher = ConfigFileWatcher(
                config_path=config_path,
                on_change=self._on_file_changed,
                event_loop=loop,
                get_last_written_hash=lambda: self._last_written_hash,
            )
            self._watcher.start()
            logger.info("ConfigFileWatcher started for %s", config_path)
        except ImportError:
            logger.warning("watchdog 未安装，跳过文件监听")
        except Exception:
            logger.warning("启动文件监听失败", exc_info=True)

    def stop_file_watcher(self) -> None:
        """停止文件监听"""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    async def _on_file_changed(self, changed_sections: dict[str, dict]) -> None:
        """文件监听回调：刷新内存 + 发布事件（不重复写文件）"""
        async with self._lock:
            self._reload_memory()
            for section, changes in changed_sections.items():
                if changes:
                    event = EventEnvelope(
                        type=CONFIG_UPDATED,
                        session_id=SYSTEM_SESSION_ID,
                        source="system",
                        payload={"section": section, "changes": changes},
                    )
                    await self._event_bus.publish(event)
                    logger.info("Config file changed externally: section=%s", section)

    # ── 内部方法（合并自 config_store.py）────────

    def _get_config_path(self) -> Path | None:
        """返回可写配置文件路径"""
        path = getattr(self._config, "_config_path", None)
        return path if isinstance(path, Path) else None

    def _load_raw_yaml(self) -> dict[str, Any]:
        """读取原始 config.yml，保持未知 section 不丢失"""
        config_path = self._get_config_path()
        if not config_path or not config_path.exists():
            return {}
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return data if isinstance(data, dict) else {}

    def _write_raw_yaml(self, raw_config: dict[str, Any]) -> None:
        """写回 config.yml，并更新文件 hash"""
        config_path = self._get_config_path()
        if not config_path:
            raise RuntimeError("当前配置实例不支持直接写回 config.yml")
        yaml_text = yaml.dump(
            raw_config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        config_path.write_text(yaml_text, encoding="utf-8")
        self._last_written_hash = hashlib.md5(yaml_text.encode()).hexdigest()

    def _reload_memory(self) -> None:
        """刷新内存 cfg.data"""
        if getattr(self._config, "_config_path", None) is not None:
            self._config.data = self._config._load_config()
        else:
            self._config.data = self._config._load_config_from_project_root()


# ── 工具函数 ──────────────────────────────────


def _deep_merge(base: dict, override: dict) -> None:
    """深度合并 override 到 base（原地修改 base）"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _flatten(data: dict, prefix: str = "") -> dict[str, Any]:
    """展平嵌套 dict 为 dotted path"""
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _set_nested(target: dict, dotted_path: str, value: Any) -> None:
    """按 a.b.c 写入嵌套字段"""
    keys = dotted_path.split(".")
    current = target
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def _get_nested(target: dict, dotted_path: str, default: Any = None) -> Any:
    """按 a.b.c 读取嵌套字段"""
    current: Any = target
    for key in dotted_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _mask_secret(secret: Any) -> str | None:
    """脱敏 secret 值"""
    if not isinstance(secret, str) or not secret:
        return None
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def _sanitize_section(path: str, resolved: Any, raw: Any) -> Any:
    """递归脱敏 section 数据"""
    if is_secret_path(path):
        return {
            "configured": bool(resolved),
            "masked_value": _mask_secret(resolved),
            "source": _detect_secret_source(raw),
        }
    if isinstance(resolved, dict):
        raw_dict = raw if isinstance(raw, dict) else {}
        return {
            key: _sanitize_section(
                path=f"{path}.{key}",
                resolved=value,
                raw=raw_dict.get(key),
            )
            for key, value in resolved.items()
        }
    if isinstance(resolved, list):
        return resolved
    return resolved


def _detect_secret_source(raw_value: Any) -> str:
    """检测 secret 来源"""
    if not raw_value:
        return "empty"
    if isinstance(raw_value, str) and is_secret_ref(raw_value):
        return "secret"
    if isinstance(raw_value, str) and raw_value.startswith("${") and raw_value.endswith("}"):
        return "env"
    return "plain"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_config_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentos/platform/config/config_manager.py tests/unit/test_config_manager.py
git commit -m "feat: implement ConfigManager with persist, refresh, and event publishing"
```

---

## Task 4: ConfigFileWatcher implementation

**Files:**
- Create: `agentos/platform/config/config_file_watcher.py`
- Create: `tests/unit/test_config_file_watcher.py`
- Modify: `pyproject.toml` — add `watchdog>=4.0.0`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_config_file_watcher.py
"""ConfigFileWatcher 单元测试"""
import asyncio
import hashlib
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.yml"
    p.write_text(yaml.dump({"llm": {"default_model": "gpt-4o"}}), encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_watcher_detects_external_change(config_file):
    """外部修改应触发回调"""
    from agentos.platform.config.config_file_watcher import ConfigFileWatcher

    callback = AsyncMock()
    loop = asyncio.get_event_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: None,
    )
    watcher.start()

    await asyncio.sleep(0.5)

    # 外部修改
    new_content = yaml.dump({"llm": {"default_model": "gpt-5"}})
    config_file.write_text(new_content, encoding="utf-8")

    # 等待防抖 + 处理
    await asyncio.sleep(2.0)
    watcher.stop()

    assert callback.call_count >= 1


@pytest.mark.asyncio
async def test_watcher_skips_self_write(config_file):
    """ConfigManager 自写应被跳过（hash 一致）"""
    from agentos.platform.config.config_file_watcher import ConfigFileWatcher

    content = yaml.dump({"llm": {"default_model": "gpt-4o"}})
    content_hash = hashlib.md5(content.encode()).hexdigest()

    callback = AsyncMock()
    loop = asyncio.get_event_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: content_hash,
    )
    watcher.start()

    await asyncio.sleep(0.5)

    # 写入相同内容（模拟 ConfigManager 自写）
    config_file.write_text(content, encoding="utf-8")

    await asyncio.sleep(2.0)
    watcher.stop()

    # 不应触发回调
    assert callback.call_count == 0


@pytest.mark.asyncio
async def test_watcher_handles_invalid_yaml(config_file):
    """无效 YAML 不应触发回调或崩溃"""
    from agentos.platform.config.config_file_watcher import ConfigFileWatcher

    callback = AsyncMock()
    loop = asyncio.get_event_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: None,
    )
    watcher.start()

    await asyncio.sleep(0.5)

    config_file.write_text("invalid: yaml: [unterminated", encoding="utf-8")

    await asyncio.sleep(2.0)
    watcher.stop()

    assert callback.call_count == 0
```

- [ ] **Step 2: Add watchdog dependency**

In `pyproject.toml`, add `"watchdog>=4.0.0",` to the `dependencies` list.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_config_file_watcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement ConfigFileWatcher**

Create `agentos/platform/config/config_file_watcher.py`:

```python
"""ConfigFileWatcher — 监听 config.yml 文件变化，外部编辑也触发联动。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigFileWatcher:
    """监听 config.yml 文件变化

    防误触发:
    1. 防抖（1秒）— 多次文件事件只处理最后一次
    2. 内容 hash 比对 — 无实质变更或自写时跳过
    """

    def __init__(
        self,
        config_path: Path,
        on_change: Callable[[dict[str, dict]], Awaitable[None]],
        event_loop: asyncio.AbstractEventLoop,
        get_last_written_hash: Callable[[], str | None],
        debounce_seconds: float = 1.0,
    ):
        self._config_path = config_path
        self._on_change = on_change
        self._event_loop = event_loop
        self._get_last_written_hash = get_last_written_hash
        self._debounce_seconds = debounce_seconds
        self._observer: Any = None
        self._debounce_timer: threading.Timer | None = None
        self._last_known_hash: str | None = self._compute_file_hash()
        self._cached_config: dict | None = self._load_yaml_safe()

    def start(self) -> None:
        """启动文件监听"""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                if Path(event.src_path).resolve() == watcher._config_path.resolve():
                    watcher._schedule_debounce()

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self._config_path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        """停止文件监听"""
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    def _schedule_debounce(self) -> None:
        """防抖：取消上次定时器，重新计时"""
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(
            self._debounce_seconds, self._on_debounced
        )
        self._debounce_timer.start()

    def _on_debounced(self) -> None:
        """防抖后的实际处理（在 OS 线程中执行）"""
        new_hash = self._compute_file_hash()
        if new_hash is None:
            return

        # hash 一致 → 无实质变更或自写
        if new_hash == self._last_known_hash:
            return

        # 检查是否为 ConfigManager 自写
        last_written = self._get_last_written_hash()
        if last_written and new_hash == last_written:
            self._last_known_hash = new_hash
            return

        self._last_known_hash = new_hash

        # 加载新配置
        new_config = self._load_yaml_safe()
        if new_config is None:
            logger.warning("config.yml YAML 解析失败，跳过本次变更")
            return

        # diff 出变更的 sections
        changed = self._diff_sections(new_config)
        self._cached_config = new_config

        if changed:
            asyncio.run_coroutine_threadsafe(
                self._on_change(changed), self._event_loop
            )

    def _compute_file_hash(self) -> str | None:
        """计算文件内容 md5"""
        try:
            content = self._config_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return None

    def _load_yaml_safe(self) -> dict | None:
        """安全加载 YAML，解析失败返回 None"""
        try:
            text = self._config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _diff_sections(self, new_config: dict) -> dict[str, dict]:
        """比较新旧配置，返回变更的 sections

        返回: {section_name: {path: {"new": value}}}
        """
        old = self._cached_config or {}
        changed: dict[str, dict] = {}

        all_sections = set(list(old.keys()) + list(new_config.keys()))
        for section in all_sections:
            old_val = old.get(section)
            new_val = new_config.get(section)
            if old_val != new_val:
                # 简化处理：标记整个 section 变更
                changes = {}
                if isinstance(new_val, dict):
                    flat = _flatten_for_diff(new_val, section)
                    for path, value in flat.items():
                        changes[path] = {"new": value}
                else:
                    changes[section] = {"new": new_val}
                changed[section] = changes

        return changed


def _flatten_for_diff(data: dict, prefix: str) -> dict:
    """展平用于 diff"""
    result = {}
    for key, value in data.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            result.update(_flatten_for_diff(value, path))
        else:
            result[path] = value
    return result
```

- [ ] **Step 5: Install watchdog and run tests**

Run: `uv add watchdog>=4.0.0 && python3 -m pytest tests/unit/test_config_file_watcher.py -v`
Expected: PASS (watcher tests may need timing adjustments)

- [ ] **Step 6: Commit**

```bash
git add agentos/platform/config/config_file_watcher.py tests/unit/test_config_file_watcher.py pyproject.toml uv.lock
git commit -m "feat: implement ConfigFileWatcher with debounce and hash-based self-write detection"
```

---

## Task 5: Module subscribers (LLMFactory, AgentRegistry, MemoryManager)

**Files:**
- Modify: `agentos/adapters/llm/factory.py`
- Modify: `agentos/capabilities/agents/registry.py`
- Modify: `agentos/capabilities/memory/manager.py`
- Append: `tests/unit/test_config_event_subscribers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config_event_subscribers.py`:

```python
from agentos.adapters.llm.factory import LLMFactory
from agentos.capabilities.agents.registry import AgentRegistry
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID


@pytest.mark.asyncio
async def test_llm_factory_reloads_on_config_event():
    """LLMFactory 收到 llm section 变更后应重建 provider 表"""
    bus = PublicEventBus()
    factory = LLMFactory()

    # 记录初始 lazy 状态
    initial_lazy_keys = set(factory._lazy.keys())

    task = asyncio.create_task(factory.start_config_listener(bus))
    await asyncio.sleep(0)

    # 发布 config.updated 事件
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "llm", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()

    # factory 应已重新注册（_providers 被清空后重建）
    # mock 始终存在
    assert "mock" in factory._providers


@pytest.mark.asyncio
async def test_llm_factory_ignores_non_llm_events():
    """LLMFactory 应忽略非 llm section 的事件"""
    bus = PublicEventBus()
    factory = LLMFactory()
    factory._providers["test"] = factory._providers["mock"]  # 添加一个标记

    task = asyncio.create_task(factory.start_config_listener(bus))
    await asyncio.sleep(0)

    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "agent", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()

    # "test" 标记应仍在（未触发重建）
    assert "test" in factory._providers


@pytest.mark.asyncio
async def test_agent_registry_reloads_on_config_event(tmp_path):
    """AgentRegistry 收到 agents section 变更后应重载"""
    bus = PublicEventBus()
    registry = AgentRegistry(agentos_home=tmp_path)

    # 初始 config 带一个 agent
    from agentos.platform.config.config import Config
    config_path = tmp_path / "config.yml"
    import yaml
    config_path.write_text(yaml.dump({
        "agent": {"temperature": 0.2},
        "agents": {"bot1": {"name": "Bot1", "description": "test"}},
    }), encoding="utf-8")
    cfg = Config(config_path=config_path)
    registry.load_from_config(cfg.data)
    assert registry.get("bot1") is not None

    # 更新 config 文件，添加 bot2
    new_data = {
        "agent": {"temperature": 0.2},
        "agents": {
            "bot1": {"name": "Bot1", "description": "test"},
            "bot2": {"name": "Bot2", "description": "new bot"},
        },
    }
    config_path.write_text(yaml.dump(new_data), encoding="utf-8")
    cfg.data = cfg._load_config()

    task = asyncio.create_task(registry.start_config_listener(bus, cfg))
    await asyncio.sleep(0)

    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "agents", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()

    assert registry.get("bot2") is not None


@pytest.mark.asyncio
async def test_memory_manager_reloads_on_config_event(tmp_path):
    """MemoryManager 收到 memory section 变更后应重建 MemoryConfig"""
    from agentos.capabilities.memory.config import MemoryConfig

    bus = PublicEventBus()
    mem_config = MemoryConfig.from_dict({"memory": {"enabled": False}})
    db_path = tmp_path / "mem.db"

    from agentos.capabilities.memory.manager import MemoryManager
    manager = MemoryManager(
        workspace_dir=str(tmp_path),
        config=mem_config,
        db_path=db_path,
    )
    assert manager.config.enabled is False

    # 模拟 config 更新
    config_data = {"memory": {"enabled": True}}

    task = asyncio.create_task(
        manager.start_config_listener(bus, lambda: config_data)
    )
    await asyncio.sleep(0)

    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "memory", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()

    assert manager.config.enabled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py::test_llm_factory_reloads_on_config_event -v`
Expected: FAIL with `AttributeError: 'LLMFactory' object has no attribute 'start_config_listener'`

- [ ] **Step 3: Add start_config_listener to LLMFactory**

In `agentos/adapters/llm/factory.py`, add after `get_provider()`:

```python
    async def start_config_listener(self, bus: PublicEventBus) -> None:
        """订阅 config.updated 事件，llm section 变更时重建 provider 表"""
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "llm":
                self._providers = {"mock": MockProvider()}
                self._lazy.clear()
                self._register_providers()
                logger.info("LLMFactory: providers reloaded due to config change")
```

Also add imports at the top:

```python
import logging
from agentos.kernel.events.bus import PublicEventBus

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Add start_config_listener to AgentRegistry**

In `agentos/capabilities/agents/registry.py`, add after the `update()` method:

```python
    async def start_config_listener(self, bus: PublicEventBus, config: Config) -> None:
        """订阅 config.updated 事件，agents section 变更时重载"""
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "agents":
                self._agents.clear()
                self.load_from_config(config.data)
                logger.info("AgentRegistry: agents reloaded due to config change")
```

Also add import:

```python
from agentos.kernel.events.bus import PublicEventBus
from agentos.platform.config.config import Config
```

- [ ] **Step 5: Add start_config_listener to MemoryManager**

In `agentos/capabilities/memory/manager.py`, add method:

```python
    async def start_config_listener(self, bus: PublicEventBus, config_data_getter) -> None:
        """订阅 config.updated 事件，memory section 变更时重建 MemoryConfig"""
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "memory":
                new_config = MemoryConfig.from_dict(config_data_getter())
                self.config = new_config
                logger.info("MemoryManager: config reloaded due to config change")
```

Also add import:

```python
from agentos.kernel.events.bus import PublicEventBus
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add agentos/adapters/llm/factory.py agentos/capabilities/agents/registry.py agentos/capabilities/memory/manager.py tests/unit/test_config_event_subscribers.py
git commit -m "feat: add config.updated event listeners to LLMFactory, AgentRegistry, MemoryManager"
```

---

## Task 6: Gateway broadcast config.* events

**Files:**
- Modify: `agentos/interfaces/ws/gateway.py:183-186`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_config_event_subscribers.py`:

```python
@pytest.mark.asyncio
async def test_gateway_broadcasts_config_events():
    """Gateway 应将 config.* 事件广播给所有 Channel"""
    from unittest.mock import AsyncMock, MagicMock
    from agentos.interfaces.ws.gateway import Gateway
    from agentos.kernel.events.bus import PublicEventBus

    bus = PublicEventBus()
    publisher = MagicMock()
    publisher.bus = bus

    gateway = Gateway(publisher=publisher, repo=None, agent_registry=None)

    # 注册两个 mock channel
    ch1 = MagicMock()
    ch1.send_event = AsyncMock()
    ch1.event_filter = MagicMock(return_value=None)
    ch1.start = AsyncMock()
    ch1.stop = AsyncMock()
    gateway._channels["ch1"] = ch1

    ch2 = MagicMock()
    ch2.send_event = AsyncMock()
    ch2.event_filter = MagicMock(return_value=None)
    ch2.start = AsyncMock()
    ch2.stop = AsyncMock()
    gateway._channels["ch2"] = ch2

    await gateway.start()

    # 发布 config.updated 事件
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "llm", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    await gateway.stop()

    # 两个 channel 都应收到
    ch1.send_event.assert_called_once()
    ch2.send_event.assert_called_once()
    assert ch1.send_event.call_args[0][0].type == CONFIG_UPDATED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py::test_gateway_broadcasts_config_events -v`
Expected: FAIL — Gateway 当前只调 `_dispatch_event`，不会广播

- [ ] **Step 3: Modify Gateway._loop**

In `agentos/interfaces/ws/gateway.py`, rename and modify the `_loop` method (lines 183-186).

Also update the call site in `start()` (line 170): change `self._loop()` to `self._event_loop()`.

From:

```python
    async def _loop(self) -> None:
        """订阅 PublicEventBus 并分发事件到对应的 Channel"""
        async for event in self.publisher.bus.subscribe():
            await self._dispatch_event(event)
```

To:

```python
    async def _event_loop(self) -> None:
        """订阅 PublicEventBus 并分发事件到对应的 Channel"""
        async for event in self.publisher.bus.subscribe():
            if event.type.startswith("config."):
                # 配置变更：广播给所有已连接的 Channel
                for channel in self._channels.values():
                    try:
                        await channel.send_event(event)
                    except Exception as exc:
                        logger.error("Failed to broadcast config event to channel: %s", exc)
            else:
                await self._dispatch_event(event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py::test_gateway_broadcasts_config_events -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentos/interfaces/ws/gateway.py tests/unit/test_config_event_subscribers.py
git commit -m "feat: Gateway broadcasts config.* events to all WebSocket channels"
```

---

## Task 7: Migrate config_api.py to use ConfigManager

**Files:**
- Modify: `agentos/interfaces/http/config_api.py`
- Modify: `tests/unit/test_config_api.py`

- [ ] **Step 1: Update config_api.py**

Replace imports and remove `EDITABLE_SECTIONS`, `SectionsUpdateBody`, `_flatten_updates`, `_sanitize_section`, `_mask_secret`, `_detect_secret_source` — these are now in ConfigManager.

Key changes to `config_api.py`:

1. Remove: `from agentos.interfaces.http.config_store import load_raw_config, persist_path_updates`
2. Remove: `EDITABLE_SECTIONS`, `SectionsUpdateBody`, `_flatten_updates`, `_sanitize_section`, `_mask_secret`, `_detect_secret_source`
3. Update `get_config_sections()`:

```python
@router.get("/sections")
async def get_config_sections(request: Request):
    """返回所有可编辑 section 的当前值"""
    config_manager = request.app.state.config_manager
    default_sections = ["llm", "agent", "plugins"]
    return config_manager.get_sections(default_sections)
```

4. Update `update_config_sections()`:

```python
@router.put("/sections")
async def update_config_sections(body: dict[str, Any], request: Request):
    """更新指定 section 并持久化到 config.yml，同时热更新运行时配置"""
    if not body:
        raise HTTPException(400, "未提供任何更新内容")

    config_manager = request.app.state.config_manager
    try:
        results = {}
        for section, data in body.items():
            if isinstance(data, dict):
                results[section] = await config_manager.update(section, data)
        return {"status": "saved", "sections": results}
    except Exception as e:
        raise HTTPException(500, f"写入配置文件失败: {e}")
```

Keep `ListModelsBody`, `TestLLMBody`, and all `list_models`/`test_llm` endpoints unchanged.

- [ ] **Step 2: Update test_config_api.py fixture**

Update the `app` fixture to create a ConfigManager and attach it to `app.state.config_manager`:

```python
from agentos.platform.config.config_manager import ConfigManager
from agentos.kernel.events.bus import PublicEventBus

@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    initial = {
        "llm": {
            "providers": {"openai": {"api_key": "sk-xxx"}},
            "models": {"gpt-5.4": {"provider": "openai", "model_id": "gpt-5.4"}},
            "default_model": "gpt-5.4",
        },
        "agent": {"model": "gpt-5.4", "temperature": 0.2},
        "plugins": {},
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)

    app.state.config = cfg
    app.state.secret_store = secret_store
    app.state.config_manager = config_manager
    return app
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_config_api.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add agentos/interfaces/http/config_api.py tests/unit/test_config_api.py
git commit -m "refactor: config_api.py uses ConfigManager instead of config_store"
```

---

## Task 8: Migrate notification_api.py and tools.py

**Files:**
- Modify: `agentos/interfaces/http/notification_api.py`
- Modify: `agentos/interfaces/http/tools.py`

- [ ] **Step 1: Update notification_api.py**

Replace the import and update endpoint. The current code constructs flat dotted paths (`{"notification.enabled": True}`), need to convert to nested dict form for `config_manager.update("notification", {...})`.

In `agentos/interfaces/http/notification_api.py`, change:

```python
from agentos.interfaces.http.config_store import persist_path_updates
```
To:
```python
# config_store 已移除，使用 ConfigManager
```

Replace the `update_notification_config` endpoint (lines 39-54):

```python
@router.put("/config")
async def update_notification_config(body: NotificationConfigBody, request: Request):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No notification config updates provided")

    # updates 已是嵌套格式（如 {"enabled": True, "channels": [...]}），
    # 直接作为 notification section 的数据传给 ConfigManager
    config_manager = request.app.state.config_manager
    try:
        await config_manager.update("notification", updates)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save notification config: {exc}")

    return request.app.state.services.notification_service.get_config()
```

- [ ] **Step 2: Update tools.py**

In `agentos/interfaces/http/tools.py`:

1. Replace import (line 16):
```python
# 旧：from agentos.interfaces.http.config_store import load_raw_config, persist_path_updates
# 新：（移除，改用 ConfigManager）
```

2. Replace `_api_key_status(cfg)` 函数（line 97-112）— 它需要读原始 YAML 来检测 secret source。改为从 ConfigManager 获取：

```python
def _api_key_status(request) -> dict[str, dict[str, Any]]:
    """获取工具 API key 状态。使用 ConfigManager 读取原始和已解析的配置。"""
    cfg = request.app.state.config
    config_manager = request.app.state.config_manager
    raw_config = config_manager._load_raw_yaml()
    result: dict[str, dict[str, Any]] = {}
    for tool_name, spec in TOOL_API_KEY_SPECS.items():
        value = cfg.get(spec["config_path"], "")
        raw_value = _read_raw_value(raw_config, spec["config_path"])
        result[tool_name] = {
            "configured": bool(value),
            "masked_key": _mask_secret(value),
            "source": _detect_secret_source(raw_value),
            "docs_url": spec["docs_url"],
            "description": spec["description"],
            "setup_guide": spec["setup_guide"],
            "example_format": spec["example_format"],
        }
    return result
```

3. 更新 `_api_key_status` 的所有调用点，传 `request` 而非 `cfg`：
   - `get_tool_api_keys` (line 252): `_api_key_status(request.app.state.config)` → `_api_key_status(request)`
   - `update_tool_api_keys` (line 278): 同上

4. Replace `update_tool_api_keys` 中的 `persist_path_updates` 调用（lines 268-275）：

```python
    # 将 flat path_updates 转为 per-section nested dict
    # path_updates 格式如: {"tools.serper_search.api_key": "sk-xxx"}
    # 需要转为: update("tools", {"serper_search": {"api_key": "sk-xxx"}})
    tools_nested: dict[str, Any] = {}
    for path, value in path_updates.items():
        # path 形如 "tools.serper_search.api_key"，去掉 "tools." 前缀
        keys = path.split(".")
        section = keys[0]  # "tools"
        sub_path = keys[1:]  # ["serper_search", "api_key"]
        current = tools_nested
        for k in sub_path[:-1]:
            current = current.setdefault(k, {})
        current[sub_path[-1]] = value

    config_manager = request.app.state.config_manager
    try:
        await config_manager.update("tools", tools_nested)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save API keys: {exc}")
```

- [ ] **Step 3: Run existing tests**

Run: `python3 -m pytest tests/unit/ -v -k "config or notification or tool"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add agentos/interfaces/http/notification_api.py agentos/interfaces/http/tools.py
git commit -m "refactor: notification_api and tools.py use ConfigManager"
```

---

## Task 9: Delete config_store.py and update test

**Files:**
- Delete: `agentos/interfaces/http/config_store.py`
- Modify: `tests/unit/test_config_store_secrets.py` → migrate to use ConfigManager

- [ ] **Step 1: Migrate test_config_store_secrets.py**

Rewrite tests to use `ConfigManager.update()` instead of `persist_path_updates()` directly. The test logic stays the same, just the call target changes.

Rename file to `tests/unit/test_config_manager_secrets.py` for clarity:

```python
"""ConfigManager 的 secret-aware 写入单测"""
import asyncio
import pytest
import yaml

from agentos.kernel.events.bus import PublicEventBus
from agentos.platform.config.config import Config
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.secrets.store import InMemorySecretStore


@pytest.mark.asyncio
async def test_update_writes_secret_ref_for_sensitive_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("tools: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("tools", {"serper_search": {"api_key": "sk-secret-123"}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == (
        "${secret:agentos/tools.serper_search.api_key}"
    )
    assert store.get("agentos/tools.serper_search.api_key") == "sk-secret-123"


@pytest.mark.asyncio
async def test_update_writes_plain_value_for_non_secret_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("agent: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("agent", {"model": "gpt-5.4"})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["model"] == "gpt-5.4"


@pytest.mark.asyncio
async def test_update_deletes_secret_when_value_is_empty(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "tools:\n  serper_search:\n    api_key: ${secret:agentos/tools.serper_search.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    store.set("agentos/tools.serper_search.api_key", "sk-old")
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("tools", {"serper_search": {"api_key": ""}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == ""
    assert store.get("agentos/tools.serper_search.api_key") is None
```

- [ ] **Step 2: Verify no imports of config_store remain**

Run: `grep -r "config_store" agentos/ tests/`
Expected: No results (all migrated)

- [ ] **Step 3: Delete config_store.py**

```bash
rm agentos/interfaces/http/config_store.py
rm tests/unit/test_config_store_secrets.py
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/unit/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: delete config_store.py, migrate secret tests to ConfigManager"
```

---

## Task 10: Gateway lifespan integration

**Files:**
- Modify: `agentos/app/gateway/main.py`

- [ ] **Step 1: Add ConfigManager initialization to lifespan**

In `agentos/app/gateway/main.py`, after line 101 (`bus = PublicEventBus()`), add:

```python
    from agentos.platform.config.config_manager import ConfigManager
    config_manager = ConfigManager(config=config, event_bus=bus, secret_store=secret_store)
    config_manager.start_file_watcher()
```

After line 248 (`await heartbeat_runtime.start()`), add the listener tasks:

```python
    # 配置变更监听
    asyncio.create_task(llm_factory.start_config_listener(bus))
    asyncio.create_task(agent_registry.start_config_listener(bus, config))
    if memory_manager:
        asyncio.create_task(memory_manager.start_config_listener(bus, lambda: config.data))
```

Add to `app.state`:

```python
    app.state.config_manager = config_manager
```

In the `finally` block, add before other shutdowns:

```python
        config_manager.stop_file_watcher()
```

- [ ] **Step 2: Run backend startup smoke test**

Run: `python3 -c "from agentos.app.gateway.main import app; print('import ok')"`
Expected: `import ok` (no import errors)

- [ ] **Step 3: Run all unit tests**

Run: `python3 -m pytest tests/unit/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add agentos/app/gateway/main.py
git commit -m "feat: integrate ConfigManager into Gateway lifespan with file watcher and listeners"
```

---

## Task 11: Final verification

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Verify config_store.py is deleted**

Run: `test -f agentos/interfaces/http/config_store.py && echo "STILL EXISTS" || echo "DELETED"`
Expected: `DELETED`

- [ ] **Step 3: Verify no broken imports**

Run: `python3 -c "from agentos.platform.config.config_manager import ConfigManager; from agentos.platform.config.config_file_watcher import ConfigFileWatcher; print('all imports ok')"`
Expected: `all imports ok`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: ConfigManager implementation complete"
```
