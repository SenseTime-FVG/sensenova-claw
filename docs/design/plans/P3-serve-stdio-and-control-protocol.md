# P3: `sensenova-claw serve --stdio` + Control Protocol Server 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `sensenova-claw` 增加 `serve --stdio` 子命令，启动一个基于 JSON-RPC 2.0 的 Control Protocol Server（stdio 传输），覆盖 spec §5.3 中除 `mcp.register_server` / `mcp.invoke` 外所有 method，让外部 SDK（P4 实现）能通过 spawn core CLI 子进程的方式驱动 harness。

**Architecture:** 在 `sensenova_claw/interfaces/control/` 新增独立的协议层 —— `protocol.py` 提供 JSON-RPC 编解码与 id 关联，`server.py` 持有 stdio 读写 loop + method 路由 + EventBus 桥接，`methods.py` 注册具体 handler。Server 复用现有 `Repository` / `PublicEventBus` / `BusRouter` / `AgentRuntime` / `LLMRuntime` / `ToolRuntime` / `ConfigManager` / `ToolRegistry` / `AgentRegistry` / `SkillRegistry` / `PluginRegistry`，在内部装配一份"无 HTTP 的"runtime stack。Identity 用 `Identity.default_local()` 占位，P5 接入后替换。Permission 流水复用现有 `tool.confirmation_requested` / `tool.confirmation_response` 事件 —— Control Server 监听到 `tool.confirmation_requested` 时向 client 发 `permission.request`，client 回 `permission.respond` 时 server 把它转换成 `tool.confirmation_response` 事件回流到总线，**无需修改 tool_worker**。`run` / `cli` 子命令保持不变。

**Tech Stack:**
- Python 3.12 + asyncio + pydantic
- pytest（单元 + 集成；不引入 Playwright / 真 LLM）
- 仅 stdlib JSON（无 jsonrpc 第三方库）

---

## 已知前提与冻结约定

1. **Wire 格式**（来自 decomposition §3.5，本 plan 落地为 server 端权威实现）：
   - 每行一个 JSON 对象（`\n` 分隔），`utf-8`
   - Request：`{ "jsonrpc": "2.0", "id": <int|str>, "method": "<name>", "params": { ... } }`
   - Response（成功）：`{ "jsonrpc": "2.0", "id": <same>, "result": { ... } }`
   - Response（失败）：`{ "jsonrpc": "2.0", "id": <same>, "error": { "code": <int>, "message": "...", "data": { ... } } }`
   - Notification（无 `id`）：`{ "jsonrpc": "2.0", "method": "event", "params": { "envelope": { ... } } }`
2. **错误码**（spec §5.4）：`-32700/-32600/-32601/-32602/-32603` JSON-RPC 标准；`-32000` permission_denied；`-32001` plugin_not_loaded；`-32002` session_not_found；`-32003` tool_execution_failed；`-32004` config_validation_failed；`-32005` identity_mismatch；`-32006` capability_unavailable。
3. **Identity 占位**：本期使用 `Identity.default_local()`（spec §3.4，P5 提供真实类，P3 用 dataclass 占位 + 注释 TODO）。
4. **Plugin 列表占位**：`plugin.list` / `plugin.enable` / `plugin.disable` / `plugin.reload` 在 P1 / P2 完成后会有真 PluginManifest；P3 需要支持现有 `PluginRegistry`（`sensenova_claw/adapters/plugins/`，已有），返回的字段以 spec §4.1 子集为准（`id` / `name` / `version` / `enabled` / `visibility`）；找不到字段时填 `"unknown"` 并写明 TODO。
5. **不在范围（重申）**：
   - 不实现 SDK 客户端（P4）
   - 不实现 identity 过滤（P5；本期都对 `local-team` 可见）
   - 不实现 `mcp.register_server` / `mcp.invoke`（P4 反向 RPC）
   - 不实现 hook 子进程（P6）
   - 不实现 WebSocket / TCP 传输（M1+ 蓝图）
   - 不动 `run` / `cli` / `version` / `migrate-secrets` 子命令的行为

---

## 文件结构

### 新增

| 文件 | 责任 |
|---|---|
| `sensenova_claw/interfaces/control/__init__.py` | 包导出 |
| `sensenova_claw/interfaces/control/errors.py` | spec §5.4 错误码常量 + `ControlError` 异常类 |
| `sensenova_claw/interfaces/control/protocol.py` | JSON-RPC 2.0 codec：`Request` / `Response` / `Notification` 数据类、`encode_line()` / `decode_line()` 函数、id 关联（`PendingRequests`） |
| `sensenova_claw/interfaces/control/server.py` | `ControlServer` 类：拥有 stdio reader/writer、method 路由表、EventBus 订阅 → notification 推送、permission 桥接 |
| `sensenova_claw/interfaces/control/methods.py` | 各 method handler 函数（按 spec §5.3 域分组：session / turn / event / permission / plugin / capability / config / ping） |
| `sensenova_claw/interfaces/control/runtime_factory.py` | `build_serve_runtime()`：组装一份不启 HTTP/WS 的最小 runtime stack（Repository、Bus、各 Runtime、Registry），返回 `ServeContext` |
| `tests/unit/interfaces/control/__init__.py` | 包占位 |
| `tests/unit/interfaces/control/test_protocol.py` | codec 单元测试 |
| `tests/unit/interfaces/control/test_server_handshake.py` | initialize 握手 |
| `tests/unit/interfaces/control/test_server_session.py` | session.* method |
| `tests/unit/interfaces/control/test_server_turn_events.py` | turn.send_input + event.subscribe + permission 双向 |
| `tests/unit/interfaces/control/test_server_capabilities.py` | tool.list / agent.list / skill.list / config.* / plugin.list / ping |
| `tests/unit/interfaces/control/conftest.py` | 共享 fixture：内存 stdio + mock runtime |
| `tests/unit/test_app_main_serve.py` | `serve` 子命令 argparse 单元测试（不真启 server） |

### 修改

| 文件 | 改什么 |
|---|---|
| `sensenova_claw/app/main.py` | 在 `main()` 的子命令分发里加 `serve` 分支 + `cmd_serve()` 函数 |

### 不动

- `sensenova_claw/app/gateway/main.py`（HTTP/WS 入口）
- `sensenova_claw/interfaces/ws/gateway.py`（前端 / TUI 通信）
- 任何 `kernel/runtime/`、`kernel/events/`、`capabilities/`、`adapters/` 下的代码

---

## 命令速查

```bash
# 全量 P3 测试
python3 -m pytest tests/unit/interfaces/control/ tests/unit/test_app_main_serve.py -v

# 单个文件
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v

# 验证 run 子命令仍可正常 import / 解析参数
python3 -m pytest tests/unit/test_app_main.py -v

# 手动冒烟（生产闭环验证；本期可选）
python3 -m sensenova_claw.app.main serve --stdio < /dev/null
```

---

## Task 1: 错误码与异常类

**Files:**
- Create: `sensenova_claw/interfaces/control/__init__.py`
- Create: `sensenova_claw/interfaces/control/errors.py`
- Test: `tests/unit/interfaces/control/__init__.py`
- Test: `tests/unit/interfaces/control/test_protocol.py`（先建文件占位，后续 task 填充）

- [ ] **Step 1: 写失败测试**

`tests/unit/interfaces/control/__init__.py`：留空。

`tests/unit/interfaces/control/test_protocol.py`：

```python
"""Control Protocol codec / errors 单元测试"""
from __future__ import annotations

import pytest

from sensenova_claw.interfaces.control.errors import (
    ControlError,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    PERMISSION_DENIED,
    PLUGIN_NOT_LOADED,
    SESSION_NOT_FOUND,
    TOOL_EXECUTION_FAILED,
    CONFIG_VALIDATION_FAILED,
    IDENTITY_MISMATCH,
    CAPABILITY_UNAVAILABLE,
)


class TestErrorCodes:
    def test_jsonrpc_codes_match_spec(self):
        assert PARSE_ERROR == -32700
        assert INVALID_REQUEST == -32600
        assert METHOD_NOT_FOUND == -32601
        assert INVALID_PARAMS == -32602
        assert INTERNAL_ERROR == -32603

    def test_application_codes_match_spec(self):
        assert PERMISSION_DENIED == -32000
        assert PLUGIN_NOT_LOADED == -32001
        assert SESSION_NOT_FOUND == -32002
        assert TOOL_EXECUTION_FAILED == -32003
        assert CONFIG_VALIDATION_FAILED == -32004
        assert IDENTITY_MISMATCH == -32005
        assert CAPABILITY_UNAVAILABLE == -32006

    def test_control_error_carries_code_message_data(self):
        err = ControlError(SESSION_NOT_FOUND, "no such session", data={"sid": "x"})
        assert err.code == SESSION_NOT_FOUND
        assert err.message == "no such session"
        assert err.data == {"sid": "x"}
        assert isinstance(err, Exception)

    def test_control_error_to_dict_omits_none_data(self):
        err = ControlError(METHOD_NOT_FOUND, "no method")
        assert err.to_dict() == {"code": METHOD_NOT_FOUND, "message": "no method"}
        err2 = ControlError(INVALID_PARAMS, "bad", data={"field": "x"})
        assert err2.to_dict() == {
            "code": INVALID_PARAMS,
            "message": "bad",
            "data": {"field": "x"},
        }
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v
```

预期：`ModuleNotFoundError: No module named 'sensenova_claw.interfaces.control'`

- [ ] **Step 3: 实现 errors.py**

`sensenova_claw/interfaces/control/__init__.py`：

```python
"""Control Protocol Server (JSON-RPC 2.0 over stdio)

P3 实现，参见 docs/design/2026-04-27-agent-harness-sdk-design.md §5。
"""

from sensenova_claw.interfaces.control.errors import ControlError

__all__ = ["ControlError"]
```

`sensenova_claw/interfaces/control/errors.py`：

```python
"""Control Protocol 错误码 + 异常类（spec §5.4）"""
from __future__ import annotations

# JSON-RPC 2.0 标准错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# 应用层错误码（spec §5.4）
PERMISSION_DENIED = -32000
PLUGIN_NOT_LOADED = -32001
SESSION_NOT_FOUND = -32002
TOOL_EXECUTION_FAILED = -32003
CONFIG_VALIDATION_FAILED = -32004
IDENTITY_MISMATCH = -32005
CAPABILITY_UNAVAILABLE = -32006


class ControlError(Exception):
    """Control Protocol 协议级错误，会被 server 转成 JSON-RPC error response"""

    def __init__(self, code: int, message: str, *, data: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        out: dict = {"code": self.code, "message": self.message}
        if self.data is not None:
            out["data"] = self.data
        return out
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v
```

预期：4 passed。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/control/__init__.py \
        sensenova_claw/interfaces/control/errors.py \
        tests/unit/interfaces/control/__init__.py \
        tests/unit/interfaces/control/test_protocol.py
git commit -m "feat(control): P3.1 add ControlError + spec §5.4 error codes"
```

---

## Task 2: JSON-RPC codec

**Files:**
- Create: `sensenova_claw/interfaces/control/protocol.py`
- Modify: `tests/unit/interfaces/control/test_protocol.py`

### 2.1 codec 类型定义

- [ ] **Step 1: 在已有测试文件追加测试**

把以下测试 **追加** 到 `tests/unit/interfaces/control/test_protocol.py` 末尾：

```python
from sensenova_claw.interfaces.control.protocol import (
    Request,
    Response,
    Notification,
    encode_line,
    decode_line,
    new_response_ok,
    new_response_err,
)


class TestEncodeDecode:
    def test_encode_request_round_trip(self):
        req = Request(id=1, method="initialize", params={"protocol_version": "1"})
        line = encode_line(req)
        assert line.endswith("\n")
        # 仅一行，无内嵌换行
        assert line.count("\n") == 1
        decoded = decode_line(line)
        assert isinstance(decoded, Request)
        assert decoded.id == 1
        assert decoded.method == "initialize"
        assert decoded.params == {"protocol_version": "1"}

    def test_encode_response_ok_round_trip(self):
        resp = new_response_ok(id_="abc", result={"ok": True})
        line = encode_line(resp)
        decoded = decode_line(line)
        assert isinstance(decoded, Response)
        assert decoded.id == "abc"
        assert decoded.result == {"ok": True}
        assert decoded.error is None

    def test_encode_response_err_round_trip(self):
        resp = new_response_err(id_=2, code=-32601, message="no method")
        line = encode_line(resp)
        decoded = decode_line(line)
        assert isinstance(decoded, Response)
        assert decoded.id == 2
        assert decoded.result is None
        assert decoded.error == {"code": -32601, "message": "no method"}

    def test_encode_notification_no_id(self):
        notif = Notification(method="event", params={"envelope": {"type": "x"}})
        line = encode_line(notif)
        decoded = decode_line(line)
        assert isinstance(decoded, Notification)
        assert decoded.method == "event"
        assert decoded.params == {"envelope": {"type": "x"}}

    def test_decode_invalid_json_raises(self):
        from sensenova_claw.interfaces.control.errors import ControlError, PARSE_ERROR

        with pytest.raises(ControlError) as exc:
            decode_line("{not json}\n")
        assert exc.value.code == PARSE_ERROR

    def test_decode_missing_jsonrpc_raises_invalid_request(self):
        from sensenova_claw.interfaces.control.errors import ControlError, INVALID_REQUEST
        import json

        bad = json.dumps({"id": 1, "method": "x"}) + "\n"
        with pytest.raises(ControlError) as exc:
            decode_line(bad)
        assert exc.value.code == INVALID_REQUEST

    def test_decode_wrong_jsonrpc_version_raises(self):
        from sensenova_claw.interfaces.control.errors import ControlError, INVALID_REQUEST
        import json

        bad = json.dumps({"jsonrpc": "1.0", "id": 1, "method": "x"}) + "\n"
        with pytest.raises(ControlError) as exc:
            decode_line(bad)
        assert exc.value.code == INVALID_REQUEST

    def test_decode_response_with_neither_result_nor_error_raises(self):
        from sensenova_claw.interfaces.control.errors import ControlError, INVALID_REQUEST
        import json

        bad = json.dumps({"jsonrpc": "2.0", "id": 1}) + "\n"
        with pytest.raises(ControlError) as exc:
            decode_line(bad)
        assert exc.value.code == INVALID_REQUEST
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v
```

预期：8 个新增测试均 ImportError。

- [ ] **Step 3: 实现 protocol.py（数据类 + 编解码）**

`sensenova_claw/interfaces/control/protocol.py`：

```python
"""JSON-RPC 2.0 codec for Control Protocol（spec §5.1, decomposition §3.5）

Wire format: each line is one JSON object, UTF-8, terminated by '\n'.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Union

from sensenova_claw.interfaces.control.errors import (
    ControlError,
    INVALID_REQUEST,
    PARSE_ERROR,
)


@dataclass
class Request:
    """JSON-RPC request：可由 C→S 或 S→C 发起"""
    id: int | str
    method: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    """JSON-RPC response：result 与 error 二选一"""
    id: int | str
    result: Any = None
    error: dict | None = None


@dataclass
class Notification:
    """JSON-RPC notification：无 id，常用于 event 推送"""
    method: str
    params: dict[str, Any] = field(default_factory=dict)


Message = Union[Request, Response, Notification]


def new_response_ok(id_: int | str, result: Any) -> Response:
    return Response(id=id_, result=result, error=None)


def new_response_err(
    id_: int | str | None,
    code: int,
    message: str,
    *,
    data: dict | None = None,
) -> Response:
    """构造错误响应。id 允许为 None（解析失败时 id 不可知）"""
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    # JSON-RPC 规定 error response 必须有 id 字段；解析失败时按 spec 用 null
    return Response(id=id_ if id_ is not None else None, result=None, error=err)  # type: ignore[arg-type]


def encode_line(msg: Message) -> str:
    """把消息编码为单行 JSON + '\n'"""
    if isinstance(msg, Request):
        obj = {
            "jsonrpc": "2.0",
            "id": msg.id,
            "method": msg.method,
            "params": msg.params,
        }
    elif isinstance(msg, Response):
        obj = {"jsonrpc": "2.0", "id": msg.id}
        if msg.error is not None:
            obj["error"] = msg.error
        else:
            obj["result"] = msg.result
    elif isinstance(msg, Notification):
        obj = {
            "jsonrpc": "2.0",
            "method": msg.method,
            "params": msg.params,
        }
    else:
        raise TypeError(f"unsupported message type: {type(msg).__name__}")
    # ensure_ascii=False：保留中文；separators 去多余空白；末尾必须 \n
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode_line(line: str) -> Message:
    """把单行 JSON 解码为 Request / Response / Notification

    失败抛 ControlError(PARSE_ERROR | INVALID_REQUEST)。
    """
    text = line.strip()
    if not text:
        raise ControlError(PARSE_ERROR, "empty line")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ControlError(PARSE_ERROR, f"invalid json: {exc}") from exc

    if not isinstance(obj, dict):
        raise ControlError(INVALID_REQUEST, "top level must be object")
    if obj.get("jsonrpc") != "2.0":
        raise ControlError(INVALID_REQUEST, "jsonrpc must be '2.0'")

    has_method = "method" in obj
    has_id = "id" in obj
    has_result = "result" in obj
    has_error = "error" in obj

    if has_method and has_id:
        # Request
        method = obj["method"]
        if not isinstance(method, str):
            raise ControlError(INVALID_REQUEST, "method must be string")
        params = obj.get("params", {}) or {}
        if not isinstance(params, dict):
            raise ControlError(INVALID_REQUEST, "params must be object")
        return Request(id=obj["id"], method=method, params=params)

    if has_method and not has_id:
        # Notification
        method = obj["method"]
        if not isinstance(method, str):
            raise ControlError(INVALID_REQUEST, "method must be string")
        params = obj.get("params", {}) or {}
        if not isinstance(params, dict):
            raise ControlError(INVALID_REQUEST, "params must be object")
        return Notification(method=method, params=params)

    if has_id and (has_result or has_error):
        return Response(
            id=obj["id"],
            result=obj.get("result"),
            error=obj.get("error"),
        )

    raise ControlError(
        INVALID_REQUEST,
        "message must be a request, response or notification",
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v
```

预期：12 passed。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/control/protocol.py \
        tests/unit/interfaces/control/test_protocol.py
git commit -m "feat(control): P3.2 add JSON-RPC 2.0 codec (Request/Response/Notification)"
```

### 2.2 PendingRequests：S→C request 的 id 关联

- [ ] **Step 1: 在 test_protocol.py 末尾追加测试**

```python
from sensenova_claw.interfaces.control.protocol import PendingRequests


@pytest.mark.asyncio
class TestPendingRequests:
    async def test_register_and_resolve(self):
        pending = PendingRequests()
        future = pending.register("perm-1")
        assert not future.done()

        pending.resolve("perm-1", {"decision": "allow"})
        assert future.done()
        assert (await future) == {"decision": "allow"}

    async def test_resolve_unknown_id_is_noop(self):
        pending = PendingRequests()
        # 不应抛
        pending.resolve("nope", {"x": 1})

    async def test_reject_sets_exception(self):
        pending = PendingRequests()
        future = pending.register("perm-2")
        pending.reject("perm-2", RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await future

    async def test_next_id_is_monotonic_string(self):
        pending = PendingRequests()
        a = pending.next_id()
        b = pending.next_id()
        assert isinstance(a, str)
        assert isinstance(b, str)
        assert a != b
```

`tests/unit/interfaces/control/test_protocol.py` 顶部如果还没有，加：

```python
import pytest
pytestmark_for_async = pytest.mark.asyncio
```

（注：`asyncio` 测试需要 `pytest-asyncio`，项目已经在 dev 依赖里使用过——见 `tests/unit/test_event_bus.py` 顶部的 `pytestmark = pytest.mark.asyncio`。如果当前文件还没有声明 asyncio fixture，按 `tests/unit/test_event_bus.py` 的方式加 `pytestmark = pytest.mark.asyncio`，但要确保只对 async 测试生效——稳妥做法是给单条 async 测试加 `@pytest.mark.asyncio` 装饰器，如上方代码所示。）

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v -k PendingRequests
```

预期：ImportError on `PendingRequests`。

- [ ] **Step 3: 在 protocol.py 末尾追加 PendingRequests**

```python
import asyncio
import itertools


class PendingRequests:
    """登记 S→C request 的 id → Future 映射

    用于：core 主动发 permission.request / mcp.invoke 时，等 client 回 response。
    """

    def __init__(self) -> None:
        self._pending: dict[int | str, asyncio.Future] = {}
        self._counter = itertools.count(1)

    def next_id(self) -> str:
        """生成自增 id（带 'srv-' 前缀，避免与 client 的 id 空间冲突）"""
        return f"srv-{next(self._counter)}"

    def register(self, request_id: int | str) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        return future

    def resolve(self, request_id: int | str, result: Any) -> None:
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(result)

    def reject(self, request_id: int | str, exc: BaseException) -> None:
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_exception(exc)

    def cancel_all(self, exc: BaseException) -> None:
        """server 退出时调用，唤醒所有等待者"""
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_protocol.py -v
```

预期：16 passed（4 新增 + 12 旧）。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/control/protocol.py \
        tests/unit/interfaces/control/test_protocol.py
git commit -m "feat(control): P3.2b add PendingRequests for S→C request id correlation"
```

---

## Task 3: ServeContext + runtime_factory（不启 HTTP/WS 的最小 stack）

**Files:**
- Create: `sensenova_claw/interfaces/control/runtime_factory.py`
- Test: `tests/unit/interfaces/control/conftest.py`

`build_serve_runtime()` 的**职责边界**：装配
1. `Repository`（用 `:memory:` 或临时 SQLite，由调用方传入 `db_path`）
2. `PublicEventBus` + `EventPublisher` + `BusRouter` + `EventPersister`
3. `ToolRegistry` / `SkillRegistry` / `AgentRegistry` / `PluginRegistry`（按现有 `app/gateway/main.py` lifespan 的方式构造，但 **跳过** `Gateway` / `WebSocketChannel` / `auth_service` / `cron_runtime` / `heartbeat_runtime` / `proactive_runtime`）
4. `AgentRuntime` / `LLMRuntime` / `ToolRuntime` / `TitleRuntime`
5. `ConfigManager`

返回 `ServeContext`（dataclass）持有上述所有引用。

- [ ] **Step 1: 写 conftest 提供 fixture**

`tests/unit/interfaces/control/conftest.py`：

```python
"""Control Protocol 测试共享 fixture"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class _ScriptedStream:
    """模拟 stdio 的 in-memory 双向管道"""
    inbox: asyncio.Queue = field(default_factory=asyncio.Queue)
    outbox: list[str] = field(default_factory=list)
    closed: bool = False

    async def feed(self, line: str) -> None:
        await self.inbox.put(line if line.endswith("\n") else line + "\n")

    async def read_line(self) -> str:
        if self.closed and self.inbox.empty():
            return ""
        line = await self.inbox.get()
        if line == "":
            self.closed = True
        return line

    async def write_line(self, line: str) -> None:
        self.outbox.append(line)

    async def close(self) -> None:
        await self.inbox.put("")  # EOF 哨兵


@pytest.fixture
def scripted_stream():
    return _ScriptedStream()
```

- [ ] **Step 2: 写 runtime_factory 测试**

`tests/unit/interfaces/control/test_runtime_factory.py`：

```python
"""build_serve_runtime 装配测试"""
from __future__ import annotations

import pytest

from sensenova_claw.interfaces.control.runtime_factory import (
    ServeContext,
    build_serve_runtime,
    teardown_serve_runtime,
)


@pytest.mark.asyncio
async def test_build_serve_runtime_returns_context_with_required_components(tmp_path):
    db = tmp_path / "test.db"
    ctx = await build_serve_runtime(db_path=str(db))
    try:
        assert isinstance(ctx, ServeContext)
        # 必备组件都已装配
        assert ctx.repo is not None
        assert ctx.bus is not None
        assert ctx.publisher is not None
        assert ctx.bus_router is not None
        assert ctx.agent_runtime is not None
        assert ctx.llm_runtime is not None
        assert ctx.tool_runtime is not None
        assert ctx.tool_registry is not None
        assert ctx.skill_registry is not None
        assert ctx.agent_registry is not None
        assert ctx.config_manager is not None
        # 不应装 HTTP/WS 组件
        assert not hasattr(ctx, "gateway") or ctx.gateway is None
        assert not hasattr(ctx, "ws_channel") or ctx.ws_channel is None
    finally:
        await teardown_serve_runtime(ctx)


@pytest.mark.asyncio
async def test_build_serve_runtime_publishes_user_input_through_bus(tmp_path):
    """烟雾测试：bus 能正常接收事件"""
    from sensenova_claw.kernel.events.envelope import EventEnvelope

    db = tmp_path / "test.db"
    ctx = await build_serve_runtime(db_path=str(db))
    try:
        received: list[EventEnvelope] = []

        async def _listen():
            async for ev in ctx.bus.subscribe():
                received.append(ev)
                return

        import asyncio

        task = asyncio.create_task(_listen())
        await asyncio.sleep(0)
        await ctx.bus.publish(EventEnvelope(type="probe", session_id="s1"))
        await asyncio.wait_for(task, timeout=1)
        assert len(received) == 1
        assert received[0].type == "probe"
    finally:
        await teardown_serve_runtime(ctx)
```

- [ ] **Step 3: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_runtime_factory.py -v
```

预期：ImportError。

- [ ] **Step 4: 实现 runtime_factory.py**

`sensenova_claw/interfaces/control/runtime_factory.py`：

```python
"""装配 serve --stdio 模式专用的最小 runtime stack（不启 HTTP/WS）"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.plugins import PluginRegistry
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.adapters.storage.session_jsonl import SessionJsonlWriter
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.persister import EventPersister
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.title_runtime import TitleRuntime
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.platform.config.config import config as global_config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.config.workspace import (
    ensure_sensenova_claw_home,
    resolve_sensenova_claw_home,
)
from sensenova_claw.platform.secrets.store import build_default_secret_store

logger = logging.getLogger(__name__)


@dataclass
class ServeContext:
    """serve --stdio 模式装配出来的 runtime 容器"""
    repo: Repository
    bus: PublicEventBus
    publisher: EventPublisher
    bus_router: BusRouter
    persister: EventPersister
    agent_runtime: AgentRuntime
    llm_runtime: LLMRuntime
    tool_runtime: ToolRuntime
    title_runtime: TitleRuntime
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry
    agent_registry: AgentRegistry
    plugin_registry: PluginRegistry
    config_manager: ConfigManager
    sensenova_claw_home: str


async def build_serve_runtime(
    *,
    db_path: str | None = None,
    config_overrides: dict | None = None,
) -> ServeContext:
    """装配 serve --stdio 用的最小 runtime（无 HTTP/WS、无 cron/heartbeat）

    config_overrides 是 P3 占位，本期暂未应用（P5 接入后用于按 identity 覆盖）。
    """
    secret_store = getattr(global_config, "_secret_store", None) or build_default_secret_store()
    global_config._secret_store = secret_store

    from sensenova_claw.platform.config.config import PROJECT_ROOT
    sensenova_claw_home = resolve_sensenova_claw_home(global_config)
    await ensure_sensenova_claw_home(sensenova_claw_home, project_root=PROJECT_ROOT)
    sensenova_claw_home_str = str(sensenova_claw_home)

    if not db_path:
        db_path = global_config.get("system.database_path", "")
        if not db_path:
            db_path = str(sensenova_claw_home / "data" / "sensenova-claw.db")

    repo = Repository(db_path=db_path)
    await repo.init()

    bus = PublicEventBus()
    config_manager = ConfigManager(config=global_config, event_bus=bus, secret_store=secret_store)
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(
        public_bus=bus,
        ttl_seconds=int(global_config.get("bus.private_bus_ttl", 3600)),
        gc_interval=int(global_config.get("bus.gc_interval", 60)),
    )

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()

    skills_dir = sensenova_claw_home / "skills"
    state_file = sensenova_claw_home / "skills_state.json"
    builtin_skills_dir = PROJECT_ROOT / ".sensenova-claw" / "skills"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=builtin_skills_dir,
    )
    skill_registry.load_skills(global_config.data)

    context_builder = ContextBuilder(
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        sensenova_claw_home=sensenova_claw_home_str,
    )
    llm_factory = LLMFactory()

    agent_registry = AgentRegistry(sensenova_claw_home=sensenova_claw_home)
    agent_registry.load_from_config(global_config.data)
    context_builder.agent_registry = agent_registry

    jsonl_writer = SessionJsonlWriter(base_dir=sensenova_claw_home / "agents")

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
        agent_registry=agent_registry,
        memory_manager=None,
        jsonl_writer=jsonl_writer,
        context_compressor=None,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=llm_factory, state_store=state_store)
    tool_runtime = ToolRuntime(
        bus_router=bus_router,
        registry=tool_registry,
        agent_registry=agent_registry,
        state_store=state_store,
    )
    title_runtime = TitleRuntime(bus=bus, repo=repo, agent_registry=agent_registry)

    plugin_registry = PluginRegistry()
    # P3 暂不在 serve 模式下加载 channel 插件（飞书等需要外部网络 / 鉴权，
    # 由 P4 SDK 通过 mcp.register_server 反向注入。）

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()

    return ServeContext(
        repo=repo,
        bus=bus,
        publisher=publisher,
        bus_router=bus_router,
        persister=persister,
        agent_runtime=agent_runtime,
        llm_runtime=llm_runtime,
        tool_runtime=tool_runtime,
        title_runtime=title_runtime,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        agent_registry=agent_registry,
        plugin_registry=plugin_registry,
        config_manager=config_manager,
        sensenova_claw_home=sensenova_claw_home_str,
    )


async def teardown_serve_runtime(ctx: ServeContext) -> None:
    """关闭顺序：runtimes → bus_router → persister"""
    await ctx.title_runtime.stop()
    await ctx.tool_runtime.stop()
    await ctx.llm_runtime.stop()
    await ctx.agent_runtime.stop()
    await ctx.bus_router.stop()
    await ctx.persister.stop()
```

- [ ] **Step 5: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_runtime_factory.py -v
```

预期：2 passed。

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/interfaces/control/runtime_factory.py \
        tests/unit/interfaces/control/conftest.py \
        tests/unit/interfaces/control/test_runtime_factory.py
git commit -m "feat(control): P3.3 add ServeContext + build_serve_runtime (no HTTP/WS)"
```

---

## Task 4: ControlServer 骨架 + initialize handshake

**Files:**
- Create: `sensenova_claw/interfaces/control/server.py`
- Create: `sensenova_claw/interfaces/control/methods.py`
- Test: `tests/unit/interfaces/control/test_server_handshake.py`

### 4.1 ControlServer + initialize

- [ ] **Step 1: 写测试**

`tests/unit/interfaces/control/test_server_handshake.py`：

```python
"""Initialize 握手 + ping/pong"""
from __future__ import annotations

import asyncio
import json

import pytest

from sensenova_claw.interfaces.control.runtime_factory import (
    build_serve_runtime,
    teardown_serve_runtime,
)
from sensenova_claw.interfaces.control.server import ControlServer


@pytest.mark.asyncio
async def test_initialize_returns_capabilities_and_inventory(tmp_path, scripted_stream):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    server_task = asyncio.create_task(server.run())
    try:
        await scripted_stream.feed(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocol_version": "1",
                "client_info": {"name": "py-sdk", "version": "0.1.0"},
                "identity": None,
                "config_overrides": {},
            },
        }))
        # 等 outbox 第一条
        for _ in range(50):
            if scripted_stream.outbox:
                break
            await asyncio.sleep(0.02)
        assert scripted_stream.outbox, "no response received"
        resp = json.loads(scripted_stream.outbox[0])
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        result = resp["result"]
        assert result["protocol_version"] == "1"
        assert "core_version" in result
        assert "capabilities" in result
        caps = result["capabilities"]
        assert caps["streaming"] is True
        assert caps["permissions"] is True
        assert "available_plugins" in result
        assert "available_agents" in result
        assert "available_models" in result
        assert isinstance(result["available_agents"], list)
    finally:
        await scripted_stream.close()
        server.stop()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=2)
        await teardown_serve_runtime(ctx)


@pytest.mark.asyncio
async def test_ping_returns_pong(tmp_path, scripted_stream):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    task = asyncio.create_task(server.run())
    try:
        # 先 initialize（很多 server 实现要求先握手；本期允许 ping 在握手前）
        await scripted_stream.feed(json.dumps({
            "jsonrpc": "2.0", "id": 99, "method": "ping", "params": {},
        }))
        for _ in range(50):
            if scripted_stream.outbox:
                break
            await asyncio.sleep(0.02)
        assert scripted_stream.outbox
        resp = json.loads(scripted_stream.outbox[0])
        assert resp["id"] == 99
        assert resp["result"] == {"pong": True}
    finally:
        await scripted_stream.close()
        server.stop()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        await teardown_serve_runtime(ctx)


@pytest.mark.asyncio
async def test_unknown_method_returns_method_not_found(tmp_path, scripted_stream):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    task = asyncio.create_task(server.run())
    try:
        await scripted_stream.feed(json.dumps({
            "jsonrpc": "2.0", "id": 5, "method": "no.such.method", "params": {},
        }))
        for _ in range(50):
            if scripted_stream.outbox:
                break
            await asyncio.sleep(0.02)
        resp = json.loads(scripted_stream.outbox[0])
        assert resp["id"] == 5
        assert resp["error"]["code"] == -32601
    finally:
        await scripted_stream.close()
        server.stop()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        await teardown_serve_runtime(ctx)
```

测试文件顶部加：

```python
import contextlib
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_handshake.py -v
```

预期：ImportError。

- [ ] **Step 3: 实现 methods.py（仅 initialize / ping）**

`sensenova_claw/interfaces/control/methods.py`：

```python
"""Control Protocol method handlers（按 spec §5.3 域分组）"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from sensenova_claw.interfaces.control.server import ControlServer

logger = logging.getLogger(__name__)

CORE_VERSION = "1.2.0"
PROTOCOL_VERSION = "1"


# 一个 handler：async (server, params) -> result_dict
Handler = Callable[["ControlServer", dict], Awaitable[dict]]


# ─── 握手 / 心跳 ──────────────────────────────────────────────

async def initialize(server: "ControlServer", params: dict) -> dict:
    """spec §5.2 握手"""
    server.client_info = params.get("client_info", {}) or {}
    # P3：identity 用占位；P5 接入真实 Identity 类后替换
    server.identity = params.get("identity") or {
        "user_id": "local-dev",
        "team_id": "local-team",
        "org_id": "local-org",
    }

    available_agents = [
        {"id": a.id, "name": a.name, "description": a.description, "model": a.model}
        for a in server.ctx.agent_registry.list_all()
    ]

    # available_models：从 LLMFactory / config 反射；本期取 config.llm.models keys
    from sensenova_claw.platform.config.config import config as _cfg

    models_cfg = _cfg.get("llm.models", {}) or {}
    available_models = [
        {"id": k, "provider": (v or {}).get("provider", "unknown")}
        for k, v in models_cfg.items()
    ]

    available_plugins = [
        {
            "id": getattr(plugin, "id", "unknown"),
            "name": getattr(plugin, "name", "unknown"),
            "version": getattr(plugin, "version", "unknown"),
            "enabled": True,
        }
        for plugin in getattr(server.ctx.plugin_registry, "_plugins", []) or []
    ]

    return {
        "core_version": CORE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": {
            "streaming": True,
            "permissions": True,
            "config_subscribe": True,
            "session_fork": True,
        },
        "available_plugins": available_plugins,
        "available_agents": available_agents,
        "available_models": available_models,
    }


async def ping(server: "ControlServer", params: dict) -> dict:
    return {"pong": True}


# ─── HANDLER 注册表 ───────────────────────────────────────────

HANDLERS: dict[str, Handler] = {
    "initialize": initialize,
    "ping": ping,
}
```

- [ ] **Step 4: 实现 server.py 骨架**

`sensenova_claw/interfaces/control/server.py`：

```python
"""ControlServer：JSON-RPC 2.0 over stdio 主循环

- 持有 stdio reader/writer 抽象（StdioStream / ScriptedStream 双向兼容）
- 路由 method → methods.HANDLERS
- 桥接 PublicEventBus → event notifications（按 session 订阅过滤）
- 桥接 tool.confirmation_requested ↔ permission.request / permission.respond
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from sensenova_claw.interfaces.control.errors import (
    ControlError,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)
from sensenova_claw.interfaces.control.protocol import (
    Notification,
    PendingRequests,
    Request,
    Response,
    decode_line,
    encode_line,
    new_response_err,
    new_response_ok,
)

logger = logging.getLogger(__name__)


class StreamLike(Protocol):
    async def read_line(self) -> str: ...
    async def write_line(self, line: str) -> None: ...
    async def close(self) -> None: ...


class ControlServer:
    """JSON-RPC 2.0 server 主循环。stream 抽象使其在测试 / 生产用相同代码"""

    def __init__(self, *, ctx: Any, stream: StreamLike) -> None:
        from sensenova_claw.interfaces.control.runtime_factory import ServeContext

        self.ctx: ServeContext = ctx
        self.stream = stream
        self.client_info: dict = {}
        self.identity: dict | None = None

        # 事件订阅：session_id -> True（订阅；空集表示已不订阅任何 session）
        self.subscribed_sessions: set[str] = set()

        # S→C pending（permission.request 等待 client 回 permission.respond）
        self.pending = PendingRequests()

        # tool_call_id -> permission_request_id 的映射，用于在 client 响应时
        # 把 permission.respond 转回 tool.confirmation_response 事件
        self._tool_call_to_perm_id: dict[str, str | int] = {}

        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._write_lock = asyncio.Lock()

    async def run(self) -> None:
        """主循环：1. 启动 EventBus → notification 推送任务；2. 读 stdin 处理 request"""
        bridge_task = asyncio.create_task(self._event_bridge_loop())
        self._tasks.append(bridge_task)
        try:
            while not self._stop.is_set():
                line = await self.stream.read_line()
                if line == "":
                    # EOF
                    logger.info("Control stream EOF, server stopping")
                    break
                await self._handle_line(line)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ControlServer main loop crashed")
        finally:
            self._stop.set()
            for t in self._tasks:
                t.cancel()
            for t in self._tasks:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            self.pending.cancel_all(RuntimeError("control server stopped"))

    def stop(self) -> None:
        """外部触发优雅退出"""
        self._stop.set()

    # ── 入站消息处理 ────────────────────────────────────────

    async def _handle_line(self, line: str) -> None:
        try:
            msg = decode_line(line)
        except ControlError as exc:
            await self._send(new_response_err(None, exc.code, exc.message, data=exc.data))
            return

        if isinstance(msg, Request):
            asyncio.create_task(self._dispatch_request(msg))
        elif isinstance(msg, Response):
            # client 对 server 主动发的 request 的回复
            if msg.error is not None:
                self.pending.reject(msg.id, RuntimeError(msg.error.get("message", "client error")))
            else:
                self.pending.resolve(msg.id, msg.result)
        elif isinstance(msg, Notification):
            # client 端主动 notification：当前协议没有此类，忽略并记日志
            logger.debug("Ignoring client notification: %s", msg.method)

    async def _dispatch_request(self, req: Request) -> None:
        from sensenova_claw.interfaces.control.methods import HANDLERS

        handler = HANDLERS.get(req.method)
        if handler is None:
            await self._send(new_response_err(req.id, METHOD_NOT_FOUND, f"unknown method: {req.method}"))
            return

        try:
            result = await handler(self, req.params)
            await self._send(new_response_ok(req.id, result))
        except ControlError as exc:
            await self._send(new_response_err(req.id, exc.code, exc.message, data=exc.data))
        except Exception as exc:
            logger.exception("handler %s crashed", req.method)
            await self._send(new_response_err(req.id, INTERNAL_ERROR, str(exc) or type(exc).__name__))

    # ── 出站消息 ───────────────────────────────────────────

    async def _send(self, msg: Request | Response | Notification) -> None:
        line = encode_line(msg)
        async with self._write_lock:
            await self.stream.write_line(line)

    async def send_notification(self, method: str, params: dict) -> None:
        await self._send(Notification(method=method, params=params))

    async def send_request_and_wait(
        self, method: str, params: dict, *, timeout: float = 60.0
    ) -> Any:
        """主动发 request 给 client，等待对应 response"""
        rid = self.pending.next_id()
        future = self.pending.register(rid)
        await self._send(Request(id=rid, method=method, params=params))
        return await asyncio.wait_for(future, timeout=timeout)

    # ── EventBus → notification 桥接 ───────────────────────

    async def _event_bridge_loop(self) -> None:
        """订阅 PublicEventBus，对订阅的 session 发 event notification"""
        from sensenova_claw.kernel.events.types import TOOL_CONFIRMATION_REQUESTED

        async for envelope in self.ctx.bus.subscribe():
            if self._stop.is_set():
                return
            sid = envelope.session_id
            if sid not in self.subscribed_sessions:
                # 只对订阅的 session 推送
                continue

            # 推普通事件
            await self.send_notification(
                "event",
                {"envelope": envelope.model_dump()},
            )

            # 同时拦截 tool.confirmation_requested → permission.request（S→C）
            if envelope.type == TOOL_CONFIRMATION_REQUESTED:
                asyncio.create_task(self._bridge_permission_request(envelope))

    async def _bridge_permission_request(self, envelope: Any) -> None:
        """把 tool.confirmation_requested 转成 permission.request 发给 client，
        client 回 permission.respond 后转成 tool.confirmation_response 事件回流。
        """
        from sensenova_claw.kernel.events.envelope import EventEnvelope
        from sensenova_claw.kernel.events.types import TOOL_CONFIRMATION_RESPONSE

        tool_call_id = envelope.payload.get("tool_call_id")
        if not tool_call_id:
            logger.warning("tool.confirmation_requested missing tool_call_id, skipping bridge")
            return
        try:
            response = await self.send_request_and_wait(
                "permission.request",
                {
                    "session_id": envelope.session_id,
                    "turn_id": envelope.turn_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": envelope.payload.get("tool_name"),
                    "arguments": envelope.payload.get("arguments", {}),
                    "risk_level": envelope.payload.get("risk_level"),
                    "message": envelope.payload.get("message"),
                },
                timeout=float(envelope.payload.get("timeout") or 60.0) + 5.0,
            )
        except asyncio.TimeoutError:
            # client 超时未响应：让现有 timeout_action 自然兜底，无需主动发 response
            return
        except Exception as exc:
            logger.warning("permission bridge wait failed: %s", exc)
            return

        decision = (response or {}).get("decision", "deny")
        approved = decision == "allow"
        await self.ctx.publisher.publish(
            EventEnvelope(
                type=TOOL_CONFIRMATION_RESPONSE,
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
                source="control_server",
                payload={"tool_call_id": tool_call_id, "approved": approved},
            )
        )
```

- [ ] **Step 5: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_handshake.py -v
```

预期：3 passed。

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/interfaces/control/methods.py \
        sensenova_claw/interfaces/control/server.py \
        tests/unit/interfaces/control/test_server_handshake.py
git commit -m "feat(control): P3.4 add ControlServer + initialize/ping handlers"
```

---

## Task 5: Session method 域

`session.create` / `session.list` / `session.get_info` / `session.fork` / `session.delete` / `session.resume`。

**Files:**
- Modify: `sensenova_claw/interfaces/control/methods.py`
- Test: `tests/unit/interfaces/control/test_server_session.py`

- [ ] **Step 1: 写测试**

`tests/unit/interfaces/control/test_server_session.py`：

```python
"""session.* method"""
from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

from sensenova_claw.interfaces.control.runtime_factory import (
    build_serve_runtime,
    teardown_serve_runtime,
)
from sensenova_claw.interfaces.control.server import ControlServer


async def _start_server(scripted_stream, tmp_path):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    task = asyncio.create_task(server.run())
    return ctx, server, task


async def _stop_server(ctx, server, task, scripted_stream):
    await scripted_stream.close()
    server.stop()
    with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=2)
    await teardown_serve_runtime(ctx)


async def _send_and_recv(scripted_stream, payload: dict, expected_id) -> dict:
    """发请求并取出对应 id 的响应（忽略 notification）"""
    await scripted_stream.feed(json.dumps(payload))
    for _ in range(200):
        for line in scripted_stream.outbox:
            obj = json.loads(line)
            if obj.get("id") == expected_id:
                return obj
        await asyncio.sleep(0.02)
    raise AssertionError(f"no response for id={expected_id}; outbox={scripted_stream.outbox}")


@pytest.mark.asyncio
async def test_session_create_returns_session_id(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        resp = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 10, "method": "session.create",
            "params": {"agent_id": "default"},
        }, expected_id=10)
        assert "result" in resp, resp
        assert resp["result"]["session_id"].startswith("sess_")
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_list_includes_created_session(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        create = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        }, expected_id=1)
        sid = create["result"]["session_id"]

        listed = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "session.list", "params": {},
        }, expected_id=2)
        ids = [s["session_id"] for s in listed["result"]["sessions"]]
        assert sid in ids
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_get_info_returns_meta(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        c = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create",
            "params": {"agent_id": "default"},
        }, expected_id=1)
        sid = c["result"]["session_id"]

        info = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "session.get_info",
            "params": {"session_id": sid},
        }, expected_id=2)
        assert info["result"]["session_id"] == sid
        assert info["result"]["agent_id"] == "default"
        assert "turn_count" in info["result"]
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_get_info_unknown_returns_session_not_found(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        resp = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.get_info",
            "params": {"session_id": "sess_nope"},
        }, expected_id=1)
        assert resp["error"]["code"] == -32002  # SESSION_NOT_FOUND
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_delete_removes_session(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        c = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        }, expected_id=1)
        sid = c["result"]["session_id"]

        d = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "session.delete",
            "params": {"session_id": sid},
        }, expected_id=2)
        assert d["result"] == {"deleted": True}

        info = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 3, "method": "session.get_info",
            "params": {"session_id": sid},
        }, expected_id=3)
        assert info["error"]["code"] == -32002
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_resume_existing_returns_ok(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        c = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        }, expected_id=1)
        sid = c["result"]["session_id"]

        r = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "session.resume",
            "params": {"session_id": sid},
        }, expected_id=2)
        assert r["result"]["session_id"] == sid
        assert r["result"]["resumed"] is True
    finally:
        await _stop_server(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_session_fork_creates_new_session_with_parent(tmp_path, scripted_stream):
    ctx, server, task = await _start_server(scripted_stream, tmp_path)
    try:
        c = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        }, expected_id=1)
        parent = c["result"]["session_id"]

        f = await _send_and_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "session.fork",
            "params": {"session_id": parent, "from_turn": None},
        }, expected_id=2)
        new_sid = f["result"]["session_id"]
        assert new_sid != parent
        assert new_sid.startswith("sess_")
    finally:
        await _stop_server(ctx, server, task, scripted_stream)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_session.py -v
```

预期：所有测试要么 method_not_found 要么 KeyError，全失败。

- [ ] **Step 3: 在 methods.py 追加 session 域 handler**

在 `sensenova_claw/interfaces/control/methods.py` 追加：

```python
import uuid

from sensenova_claw.interfaces.control.errors import (
    ControlError,
    INVALID_PARAMS,
    SESSION_NOT_FOUND,
)


# ─── Session 域 ──────────────────────────────────────────────

async def session_create(server: "ControlServer", params: dict) -> dict:
    agent_id = params.get("agent_id", "default")
    meta = params.get("meta") or {}
    if not isinstance(meta, dict):
        raise ControlError(INVALID_PARAMS, "meta must be object")

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session_meta = dict(meta)
    session_meta["agent_id"] = agent_id
    await server.ctx.repo.create_session(session_id=session_id, meta=session_meta)
    return {"session_id": session_id, "agent_id": agent_id}


async def session_list(server: "ControlServer", params: dict) -> dict:
    limit = int(params.get("limit", 50))
    sessions = await server.ctx.repo.list_sessions(limit=limit, include_hidden=False)
    return {"sessions": sessions}


async def session_get_info(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    meta = await server.ctx.repo.get_session_meta(sid)
    if meta is None:
        raise ControlError(SESSION_NOT_FOUND, f"session not found: {sid}")
    turns = await server.ctx.repo.get_session_turns(sid)
    return {
        "session_id": sid,
        "agent_id": (meta or {}).get("agent_id", "default"),
        "meta": meta or {},
        "turn_count": len(turns or []),
    }


async def session_fork(server: "ControlServer", params: dict) -> dict:
    parent = params.get("session_id")
    if not parent:
        raise ControlError(INVALID_PARAMS, "session_id required")
    parent_meta = await server.ctx.repo.get_session_meta(parent)
    if parent_meta is None:
        raise ControlError(SESSION_NOT_FOUND, f"parent session not found: {parent}")
    new_sid = f"sess_{uuid.uuid4().hex[:12]}"
    new_meta = dict(parent_meta or {})
    new_meta["parent_session_id"] = parent
    new_meta.setdefault("agent_id", "default")
    new_meta["from_turn"] = params.get("from_turn")
    await server.ctx.repo.create_session(session_id=new_sid, meta=new_meta)
    return {"session_id": new_sid, "parent_session_id": parent}


async def session_delete(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    meta = await server.ctx.repo.get_session_meta(sid)
    if meta is None:
        raise ControlError(SESSION_NOT_FOUND, f"session not found: {sid}")
    await server.ctx.repo.delete_session_cascade(sid)
    server.subscribed_sessions.discard(sid)
    return {"deleted": True}


async def session_resume(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    meta = await server.ctx.repo.get_session_meta(sid)
    if meta is None:
        raise ControlError(SESSION_NOT_FOUND, f"session not found: {sid}")
    return {"session_id": sid, "resumed": True, "meta": meta or {}}


HANDLERS.update({
    "session.create": session_create,
    "session.list": session_list,
    "session.get_info": session_get_info,
    "session.fork": session_fork,
    "session.delete": session_delete,
    "session.resume": session_resume,
})
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_session.py -v
```

预期：7 passed。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/control/methods.py \
        tests/unit/interfaces/control/test_server_session.py
git commit -m "feat(control): P3.5 add session.* methods (create/list/get_info/fork/delete/resume)"
```

---

## Task 6: Turn + event 域（含 permission 双向桥接的 happy path）

**Files:**
- Modify: `sensenova_claw/interfaces/control/methods.py`
- Test: `tests/unit/interfaces/control/test_server_turn_events.py`

### 6.1 turn.send_input / turn.cancel / turn.get_messages + event.subscribe / event.unsubscribe

- [ ] **Step 1: 写测试 — 主流程**

`tests/unit/interfaces/control/test_server_turn_events.py`：

```python
"""turn.* + event.* 单元测试"""
from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

from sensenova_claw.interfaces.control.runtime_factory import (
    build_serve_runtime,
    teardown_serve_runtime,
)
from sensenova_claw.interfaces.control.server import ControlServer
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESPONSE,
)


async def _start(scripted_stream, tmp_path):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    task = asyncio.create_task(server.run())
    return ctx, server, task


async def _stop(ctx, server, task, scripted_stream):
    await scripted_stream.close()
    server.stop()
    with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=2)
    await teardown_serve_runtime(ctx)


async def _wait_response(scripted_stream, expected_id):
    for _ in range(200):
        for line in scripted_stream.outbox:
            obj = json.loads(line)
            if obj.get("id") == expected_id:
                return obj
        await asyncio.sleep(0.02)
    raise AssertionError(f"no response id={expected_id}; outbox={scripted_stream.outbox}")


async def _wait_notification(scripted_stream, predicate, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    seen = set()
    while asyncio.get_running_loop().time() < deadline:
        for i, line in enumerate(scripted_stream.outbox):
            if i in seen:
                continue
            seen.add(i)
            obj = json.loads(line)
            if "method" in obj and obj["method"] == "event":
                env = obj["params"]["envelope"]
                if predicate(env):
                    return env
        await asyncio.sleep(0.02)
    raise AssertionError("notification not received")


@pytest.mark.asyncio
async def test_event_subscribe_then_publish_user_input_sees_event(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        # create + subscribe
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]

        await scripted_stream.feed(json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "event.subscribe",
            "params": {"session_id": sid},
        }))
        sub_resp = await _wait_response(scripted_stream, 2)
        assert sub_resp["result"] == {"subscribed": True}

        # 直接通过 bus 发布一个 user.input 事件，应被订阅推送
        await ctx.publisher.publish(
            EventEnvelope(type="user.input", session_id=sid, payload={"content": "hi"})
        )
        env = await _wait_notification(scripted_stream, lambda e: e["type"] == "user.input")
        assert env["session_id"] == sid
        assert env["payload"]["content"] == "hi"
    finally:
        await _stop(ctx, server, task, scripted_stream)


async def _wait_response_after_send(scripted_stream, payload):
    await scripted_stream.feed(json.dumps(payload))
    return await _wait_response(scripted_stream, payload["id"])


@pytest.mark.asyncio
async def test_turn_send_input_returns_turn_id_and_publishes_event(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]

        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "event.subscribe",
            "params": {"session_id": sid},
        })

        send = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 3, "method": "turn.send_input",
            "params": {"session_id": sid, "text": "你好"},
        })
        assert send["result"]["turn_id"].startswith("turn_")
        # 应同步收到 user.input 事件 notification
        env = await _wait_notification(scripted_stream, lambda e: e["type"] == "user.input")
        assert env["payload"]["content"] == "你好"
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_event_unsubscribe_stops_notifications(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]

        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "event.subscribe",
            "params": {"session_id": sid},
        })
        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 3, "method": "event.unsubscribe",
            "params": {"session_id": sid},
        })

        # 发事件后不应被推
        await ctx.publisher.publish(
            EventEnvelope(type="probe.x", session_id=sid, payload={})
        )
        # 给点时间，确保不会出现
        await asyncio.sleep(0.2)
        # 收件箱里不应有 type=probe.x 的 event notification
        for line in scripted_stream.outbox:
            obj = json.loads(line)
            if "method" in obj and obj["method"] == "event":
                assert obj["params"]["envelope"]["type"] != "probe.x"
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_turn_cancel_publishes_user_turn_cancel_requested(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]
        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "event.subscribe",
            "params": {"session_id": sid},
        })

        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 3, "method": "turn.cancel",
            "params": {"session_id": sid, "reason": "user"},
        })
        env = await _wait_notification(
            scripted_stream,
            lambda e: e["type"] == "user.turn_cancel_requested",
            timeout=3.0,
        )
        assert env["payload"]["reason"] == "user"
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_turn_get_messages_returns_history(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]

        msgs = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "turn.get_messages",
            "params": {"session_id": sid},
        })
        assert isinstance(msgs["result"]["messages"], list)


    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_permission_round_trip_flips_to_tool_confirmation_response(tmp_path, scripted_stream):
    """server 收到 tool.confirmation_requested → 发 permission.request 给 client →
    client 模拟回 permission allow → server 把它转成 tool.confirmation_response 事件回流"""
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        # 先 subscribe（让 server 监听 sid）
        c = await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {},
        })
        sid = c["result"]["session_id"]
        await _wait_response_after_send(scripted_stream, {
            "jsonrpc": "2.0", "id": 2, "method": "event.subscribe",
            "params": {"session_id": sid},
        })

        # 收集 bus 上的 tool.confirmation_response 事件
        responses: list[EventEnvelope] = []

        async def _bus_listener():
            async for env in ctx.bus.subscribe():
                if env.type == TOOL_CONFIRMATION_RESPONSE:
                    responses.append(env)
                    return

        listener = asyncio.create_task(_bus_listener())
        await asyncio.sleep(0)

        # 模拟 tool_worker 发出 confirmation_requested
        await ctx.publisher.publish(EventEnvelope(
            type=TOOL_CONFIRMATION_REQUESTED,
            session_id=sid,
            turn_id="turn_test",
            trace_id="tc_1",
            source="tool",
            payload={
                "tool_call_id": "tc_1",
                "tool_name": "send_email",
                "arguments": {"to": "x@y.com"},
                "risk_level": "high",
                "timeout": 5,
                "timeout_action": "reject",
                "message": "确认？",
            },
        ))

        # 等 client 端收到 permission.request
        for _ in range(200):
            for line in scripted_stream.outbox:
                obj = json.loads(line)
                if obj.get("method") == "permission.request":
                    perm_id = obj["id"]
                    break
            else:
                await asyncio.sleep(0.02)
                continue
            break
        else:
            raise AssertionError(f"no permission.request seen; outbox={scripted_stream.outbox}")

        # client 模拟 allow
        await scripted_stream.feed(json.dumps({
            "jsonrpc": "2.0", "id": perm_id, "result": {"decision": "allow"},
        }))

        # bus 上应出现 tool.confirmation_response
        await asyncio.wait_for(listener, timeout=3)
        assert responses
        assert responses[0].payload["tool_call_id"] == "tc_1"
        assert responses[0].payload["approved"] is True
    finally:
        await _stop(ctx, server, task, scripted_stream)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_turn_events.py -v
```

预期：method_not_found 失败。

- [ ] **Step 3: 在 methods.py 追加 turn / event handlers**

在 `sensenova_claw/interfaces/control/methods.py` 追加：

```python
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    USER_INPUT,
    USER_TURN_CANCEL_REQUESTED,
)


# ─── Turn 域 ─────────────────────────────────────────────────

async def turn_send_input(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    text = params.get("text", "")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    meta = await server.ctx.repo.get_session_meta(sid)
    if meta is None:
        raise ControlError(SESSION_NOT_FOUND, f"session not found: {sid}")

    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    payload = {
        "content": text,
        "attachments": params.get("attachments") or [],
        "context_files": params.get("context_files") or [],
    }
    if "meta" in params:
        payload["meta"] = params["meta"]
    await server.ctx.publisher.publish(EventEnvelope(
        type=USER_INPUT,
        session_id=sid,
        turn_id=turn_id,
        source="control_server",
        payload=payload,
    ))
    return {"turn_id": turn_id}


async def turn_cancel(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    reason = params.get("reason", "user_cancel")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    event = EventEnvelope(
        type=USER_TURN_CANCEL_REQUESTED,
        session_id=sid,
        source="control_server",
        payload={"reason": reason},
    )
    private_bus = server.ctx.bus_router.get(sid) if server.ctx.bus_router else None
    if private_bus:
        await private_bus.publish(event)
    else:
        await server.ctx.publisher.publish(event)
    return {"cancelled": True}


async def turn_get_messages(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    messages = await server.ctx.repo.get_session_messages(sid)
    return {"messages": messages or []}


# ─── Event 域 ────────────────────────────────────────────────

async def event_subscribe(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    server.subscribed_sessions.add(sid)
    return {"subscribed": True}


async def event_unsubscribe(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    if not sid:
        raise ControlError(INVALID_PARAMS, "session_id required")
    server.subscribed_sessions.discard(sid)
    return {"unsubscribed": True}


# ─── Permission 域（client → server 回应） ──────────────────

async def permission_respond(server: "ControlServer", params: dict) -> dict:
    """C→S。注意：本协议下 client 通常通过 Response 回 server.send_request_and_wait
    的 future（由 _handle_line 的 Response 分支处理）。permission.respond 作为显式
    method 提供，用于 client 选择不在 response 上回复、改用主动 method 的场景。
    P3 选择方式 A（response），保留此方法供未来扩展或显式回调。
    """
    tool_call_id = params.get("tool_call_id")
    decision = params.get("decision", "deny")
    if not tool_call_id:
        raise ControlError(INVALID_PARAMS, "tool_call_id required")
    from sensenova_claw.kernel.events.types import TOOL_CONFIRMATION_RESPONSE

    await server.ctx.publisher.publish(EventEnvelope(
        type=TOOL_CONFIRMATION_RESPONSE,
        session_id=params.get("session_id", ""),
        turn_id=params.get("turn_id"),
        source="control_server",
        payload={"tool_call_id": tool_call_id, "approved": decision == "allow"},
    ))
    return {"acked": True}


HANDLERS.update({
    "turn.send_input": turn_send_input,
    "turn.cancel": turn_cancel,
    "turn.get_messages": turn_get_messages,
    "event.subscribe": event_subscribe,
    "event.unsubscribe": event_unsubscribe,
    "permission.respond": permission_respond,
})
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_turn_events.py -v
```

预期：6 passed。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/interfaces/control/methods.py \
        tests/unit/interfaces/control/test_server_turn_events.py
git commit -m "feat(control): P3.6 add turn.* + event.* + permission.respond methods"
```

---

## Task 7: Capability + Plugin + Config 域

`tool.list` / `agent.list` / `skill.list` / `plugin.list` / `plugin.enable` / `plugin.disable` / `plugin.reload` / `config.get` / `config.set` / `config.subscribe`。

**Files:**
- Modify: `sensenova_claw/interfaces/control/methods.py`
- Test: `tests/unit/interfaces/control/test_server_capabilities.py`

- [ ] **Step 1: 写测试**

`tests/unit/interfaces/control/test_server_capabilities.py`：

```python
"""capability + plugin + config 域 method"""
from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

from sensenova_claw.interfaces.control.runtime_factory import (
    build_serve_runtime,
    teardown_serve_runtime,
)
from sensenova_claw.interfaces.control.server import ControlServer


async def _start(scripted_stream, tmp_path):
    ctx = await build_serve_runtime(db_path=str(tmp_path / "t.db"))
    server = ControlServer(ctx=ctx, stream=scripted_stream)
    task = asyncio.create_task(server.run())
    return ctx, server, task


async def _stop(ctx, server, task, scripted_stream):
    await scripted_stream.close()
    server.stop()
    with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=2)
    await teardown_serve_runtime(ctx)


async def _send_recv(scripted_stream, payload):
    await scripted_stream.feed(json.dumps(payload))
    for _ in range(200):
        for line in scripted_stream.outbox:
            obj = json.loads(line)
            if obj.get("id") == payload["id"]:
                return obj
        await asyncio.sleep(0.02)
    raise AssertionError(f"no response: {scripted_stream.outbox}")


@pytest.mark.asyncio
async def test_tool_list_returns_builtin_tools(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "tool.list", "params": {},
        })
        tools = r["result"]["tools"]
        assert any(t["name"] == "bash_command" for t in tools)
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_agent_list_returns_default(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "agent.list", "params": {},
        })
        agents = r["result"]["agents"]
        assert any(a["id"] == "default" for a in agents)
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_skill_list_returns_array(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "skill.list", "params": {},
        })
        assert isinstance(r["result"]["skills"], list)
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_plugin_list_returns_array(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "plugin.list", "params": {},
        })
        assert isinstance(r["result"]["plugins"], list)
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_plugin_enable_unknown_returns_plugin_not_loaded(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "plugin.enable",
            "params": {"plugin_id": "no/such"},
        })
        assert r["error"]["code"] == -32001  # PLUGIN_NOT_LOADED
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_config_get_returns_value(tmp_path, scripted_stream):
    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        r = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "config.get",
            "params": {"key": "agent.temperature"},
        })
        # 没配置时返回 null/None；只要 result 字段存在即可
        assert "result" in r
        assert r["result"]["key"] == "agent.temperature"
    finally:
        await _stop(ctx, server, task, scripted_stream)


@pytest.mark.asyncio
async def test_config_subscribe_then_event_emits_notification(tmp_path, scripted_stream):
    """直接通过 publisher 发 CONFIG_UPDATED，验证 server 桥接到 config.updated notification。
    （不调用 ConfigManager.update 是为了避免测试副作用写到全局 ~/.sensenova-claw/config.yml）"""
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    from sensenova_claw.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID

    ctx, server, task = await _start(scripted_stream, tmp_path)
    try:
        sub = await _send_recv(scripted_stream, {
            "jsonrpc": "2.0", "id": 1, "method": "config.subscribe", "params": {},
        })
        assert sub["result"] == {"subscribed": True}

        await ctx.publisher.publish(EventEnvelope(
            type=CONFIG_UPDATED,
            session_id=SYSTEM_SESSION_ID,
            source="test",
            payload={"section": "control_test", "changes": {"control_test.value": {"new": 42}}},
        ))

        # 验证有一条 method == "config.updated" 的 notification
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            for line in scripted_stream.outbox:
                obj = json.loads(line)
                if obj.get("method") == "config.updated":
                    return
            await asyncio.sleep(0.02)
        raise AssertionError(f"no config.updated notification; outbox={scripted_stream.outbox}")
    finally:
        await _stop(ctx, server, task, scripted_stream)
```

> **关于 `config.set`**：实现层只需调 `ctx.config_manager.update(section, data)`。`config.set` 接收 dotted key（如 `agent.temperature`），server 内部把它拆成 `section + nested-dict` 再调 `update`。本测试不直接覆盖 `config.set` 写入路径（避免污染全局 yml）；如要覆盖，需 monkeypatch `ctx.config_manager._write_raw_yaml` 与 `_load_raw_yaml`。

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_capabilities.py -v
```

预期：method_not_found / 缺 handler。

- [ ] **Step 3: 在 methods.py 追加 capability + plugin + config handlers**

在 `methods.py` 追加：

```python
from sensenova_claw.interfaces.control.errors import (
    CAPABILITY_UNAVAILABLE,
    CONFIG_VALIDATION_FAILED,
    PLUGIN_NOT_LOADED,
)


# ─── Capability 域 ────────────────────────────────────────────

async def tool_list(server: "ControlServer", params: dict) -> dict:
    sid = params.get("session_id")
    tools = server.ctx.tool_registry.as_llm_tools(session_id=sid)
    return {"tools": tools}


async def agent_list(server: "ControlServer", params: dict) -> dict:
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "model": a.model,
            }
            for a in server.ctx.agent_registry.list_all()
        ]
    }


async def skill_list(server: "ControlServer", params: dict) -> dict:
    skills = server.ctx.skill_registry.get_all()
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "source": s.source,
            }
            for s in skills
        ]
    }


# ─── Plugin 域 ────────────────────────────────────────────────

def _find_plugin(server: "ControlServer", plugin_id: str):
    """根据 PluginRegistry 实际 API 查找；找不到返回 None"""
    registry = server.ctx.plugin_registry
    # 优先尝试 .get()，其次扫描 _plugins 列表
    if hasattr(registry, "get") and callable(registry.get):
        try:
            return registry.get(plugin_id)
        except Exception:
            pass
    for plugin in getattr(registry, "_plugins", []) or []:
        if getattr(plugin, "id", None) == plugin_id or getattr(plugin, "name", None) == plugin_id:
            return plugin
    return None


async def plugin_list(server: "ControlServer", params: dict) -> dict:
    plugins = []
    for plugin in getattr(server.ctx.plugin_registry, "_plugins", []) or []:
        plugins.append({
            "id": getattr(plugin, "id", "unknown"),
            "name": getattr(plugin, "name", "unknown"),
            "version": getattr(plugin, "version", "unknown"),
            "enabled": True,
            "visibility": "public",  # P5 接入后由 manifest.visibility 提供
        })
    return {"plugins": plugins}


async def plugin_enable(server: "ControlServer", params: dict) -> dict:
    plugin_id = params.get("plugin_id")
    if not plugin_id:
        raise ControlError(INVALID_PARAMS, "plugin_id required")
    plugin = _find_plugin(server, plugin_id)
    if plugin is None:
        raise ControlError(PLUGIN_NOT_LOADED, f"plugin not loaded: {plugin_id}")
    # P3：plugin 启用/禁用语义在 P1/P2 落地后接入，这里只校验存在
    return {"plugin_id": plugin_id, "enabled": True}


async def plugin_disable(server: "ControlServer", params: dict) -> dict:
    plugin_id = params.get("plugin_id")
    if not plugin_id:
        raise ControlError(INVALID_PARAMS, "plugin_id required")
    plugin = _find_plugin(server, plugin_id)
    if plugin is None:
        raise ControlError(PLUGIN_NOT_LOADED, f"plugin not loaded: {plugin_id}")
    return {"plugin_id": plugin_id, "enabled": False}


async def plugin_reload(server: "ControlServer", params: dict) -> dict:
    plugin_id = params.get("plugin_id")
    if not plugin_id:
        raise ControlError(INVALID_PARAMS, "plugin_id required")
    plugin = _find_plugin(server, plugin_id)
    if plugin is None:
        raise ControlError(PLUGIN_NOT_LOADED, f"plugin not loaded: {plugin_id}")
    return {"plugin_id": plugin_id, "reloaded": True}


# ─── Config 域 ────────────────────────────────────────────────

async def config_get(server: "ControlServer", params: dict) -> dict:
    key = params.get("key")
    if not key:
        raise ControlError(INVALID_PARAMS, "key required")
    from sensenova_claw.platform.config.config import config as _cfg

    value = _cfg.get(key, None)
    # 简单脱敏：含 token / api_key 的字段返回 "***" 占位（P3 最简版本，
    # 真正脱敏 P5/Identity 接入后可以更细）
    if isinstance(key, str) and any(s in key.lower() for s in ("api_key", "token", "secret", "password")):
        if value is not None:
            value = "***"
    return {"key": key, "value": value}


async def config_set(server: "ControlServer", params: dict) -> dict:
    """key 是 dotted path（'agent.temperature'）；split 后第一段当 section、剩余构造嵌套 dict。
    依赖 ConfigManager.update(section, data)（仓库现存 API）。"""
    key = params.get("key")
    if not key or not isinstance(key, str):
        raise ControlError(INVALID_PARAMS, "key required (dotted string)")
    if "value" not in params:
        raise ControlError(INVALID_PARAMS, "value required")
    value = params["value"]

    parts = key.split(".")
    section = parts[0]
    if not parts[1:]:
        # 顶层 key（罕见）：把它当成 section 下的 _value 处理；
        # 这种用法不规范，直接拒绝即可
        raise ControlError(
            INVALID_PARAMS,
            "key must include a section, e.g. 'agent.temperature'",
        )
    # 构造嵌套 dict { parts[1]: { parts[2]: { ... value } } }
    data: dict = {}
    cursor = data
    for p in parts[1:-1]:
        cursor = cursor.setdefault(p, {})
    cursor[parts[-1]] = value

    try:
        await server.ctx.config_manager.update(section, data)
    except Exception as exc:
        raise ControlError(CONFIG_VALIDATION_FAILED, str(exc)) from exc
    return {"key": key, "set": True}


async def config_subscribe(server: "ControlServer", params: dict) -> dict:
    server.config_subscribed = True
    return {"subscribed": True}


HANDLERS.update({
    "tool.list": tool_list,
    "agent.list": agent_list,
    "skill.list": skill_list,
    "plugin.list": plugin_list,
    "plugin.enable": plugin_enable,
    "plugin.disable": plugin_disable,
    "plugin.reload": plugin_reload,
    "config.get": config_get,
    "config.set": config_set,
    "config.subscribe": config_subscribe,
})
```

- [ ] **Step 4: 在 server.py 给事件桥接增加 config 推送**

修改 `_event_bridge_loop`：

```python
async def _event_bridge_loop(self) -> None:
    from sensenova_claw.kernel.events.types import (
        CONFIG_UPDATED,
        TOOL_CONFIRMATION_REQUESTED,
    )

    async for envelope in self.ctx.bus.subscribe():
        if self._stop.is_set():
            return
        sid = envelope.session_id

        # config.* 事件：广播给所有订阅了 config 的 client
        if envelope.type == CONFIG_UPDATED or envelope.type.startswith("config."):
            if getattr(self, "config_subscribed", False):
                await self.send_notification(
                    "config.updated",
                    {"envelope": envelope.model_dump()},
                )
            continue

        if sid not in self.subscribed_sessions:
            continue

        await self.send_notification("event", {"envelope": envelope.model_dump()})

        if envelope.type == TOOL_CONFIRMATION_REQUESTED:
            asyncio.create_task(self._bridge_permission_request(envelope))
```

并在 `ControlServer.__init__` 加 `self.config_subscribed = False`。

- [ ] **Step 5: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/interfaces/control/test_server_capabilities.py -v
```

预期：7 passed。如果 `test_config_subscribe_then_set_emits_notification` 因 ConfigManager API 不同而失败，按 Step 1 注释提示改成实际方法。

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/interfaces/control/methods.py \
        sensenova_claw/interfaces/control/server.py \
        tests/unit/interfaces/control/test_server_capabilities.py
git commit -m "feat(control): P3.7 add tool/agent/skill/plugin/config method domains"
```

---

## Task 8: `serve --stdio` 子命令接入 `app/main.py`

**Files:**
- Modify: `sensenova_claw/app/main.py`
- Create: `sensenova_claw/interfaces/control/stdio_stream.py`
- Test: `tests/unit/test_app_main_serve.py`

### 8.1 真 stdio stream 适配器

- [ ] **Step 1: 创建 stdio_stream.py**

`sensenova_claw/interfaces/control/stdio_stream.py`：

```python
"""真 stdin/stdout 的 StreamLike 适配器（生产用）"""
from __future__ import annotations

import asyncio
import sys


class StdioStream:
    """asyncio 包装：用 run_in_executor 读 stdin、stdout 直接 write"""

    def __init__(self) -> None:
        self._stdin = sys.stdin
        self._stdout = sys.stdout
        self._closed = False

    async def read_line(self) -> str:
        if self._closed:
            return ""
        loop = asyncio.get_running_loop()
        # 阻塞 readline 放进线程池，避免阻塞 event loop
        line = await loop.run_in_executor(None, self._stdin.readline)
        if line == "":
            self._closed = True
        return line

    async def write_line(self, line: str) -> None:
        # stdout 是 line buffered；显式 flush 保证每条消息及时出去
        self._stdout.write(line)
        self._stdout.flush()

    async def close(self) -> None:
        self._closed = True
```

### 8.2 cmd_serve + argparse 接入

- [ ] **Step 2: 写 argparse 测试**

`tests/unit/test_app_main_serve.py`：

```python
"""serve 子命令 argparse + cmd_serve 单元测试"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import sensenova_claw.app.main as app_main


def test_argparse_serve_stdio_flag(monkeypatch: pytest.MonkeyPatch):
    """sensenova-claw serve --stdio 应被解析"""
    captured = {}

    def fake_serve(args):
        captured["args"] = args
        return 0

    monkeypatch.setattr(app_main, "cmd_serve", fake_serve)
    monkeypatch.setattr(app_main.sys, "argv", ["sensenova-claw", "serve", "--stdio"])
    rc = app_main.main()
    assert rc == 0
    assert captured["args"].command == "serve"
    assert captured["args"].stdio is True


def test_argparse_serve_without_transport_errors(monkeypatch: pytest.MonkeyPatch, capsys):
    """没指定 --stdio 等传输方式时应报错"""
    monkeypatch.setattr(app_main.sys, "argv", ["sensenova-claw", "serve"])
    rc = app_main.main()
    # 实现可以选择 rc=2 (argparse error) 或 rc=1 (自定义)
    assert rc != 0


def test_existing_run_subcommand_still_dispatches(monkeypatch: pytest.MonkeyPatch):
    """加 serve 后 run 子命令仍然走 cmd_run"""
    captured = {}

    def fake_run(args):
        captured["called"] = True
        return 0

    monkeypatch.setattr(app_main, "cmd_run", fake_run)
    monkeypatch.setattr(
        app_main.sys, "argv",
        ["sensenova-claw", "run", "--no-frontend", "--port", "9999"],
    )
    rc = app_main.main()
    assert rc == 0
    assert captured["called"] is True


@pytest.mark.asyncio
async def test_cmd_serve_stdio_runs_control_server(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """cmd_serve(--stdio) 应该装配 ServeContext + 跑 ControlServer 主循环到 EOF"""
    from sensenova_claw.interfaces.control.runtime_factory import ServeContext

    fake_ctx = SimpleNamespace()
    started = {}

    async def fake_build(**kw):
        started["build"] = kw
        return fake_ctx  # 类型不严格，stop 也 mock

    async def fake_teardown(ctx):
        started["teardown"] = True

    class FakeServer:
        def __init__(self, *, ctx, stream):
            started["server_ctor"] = (ctx, stream)
        async def run(self):
            started["run"] = True
        def stop(self):
            started["stopped"] = True

    monkeypatch.setattr(
        "sensenova_claw.interfaces.control.runtime_factory.build_serve_runtime",
        fake_build,
    )
    monkeypatch.setattr(
        "sensenova_claw.interfaces.control.runtime_factory.teardown_serve_runtime",
        fake_teardown,
    )
    monkeypatch.setattr(
        "sensenova_claw.interfaces.control.server.ControlServer",
        FakeServer,
    )

    args = SimpleNamespace(stdio=True)
    rc = await app_main._cmd_serve_async(args)
    assert rc == 0
    assert started.get("run") is True
    assert started.get("teardown") is True
```

- [ ] **Step 3: 跑测试确认失败**

```bash
python3 -m pytest tests/unit/test_app_main_serve.py -v
```

预期：`AttributeError: module 'sensenova_claw.app.main' has no attribute 'cmd_serve'`。

- [ ] **Step 4: 修改 `app/main.py` 加 `serve` 子命令**

在 `sensenova_claw/app/main.py`：

1. 顶部导入新增（与现有 imports 同区）：

```python
import logging
```

2. 在 `cmd_version(args)` 函数**之前**插入：

```python
# ── sensenova_claw serve ────────────────────────────

async def _cmd_serve_async(args: argparse.Namespace) -> int:
    """异步实现：装配 ServeContext + 启 ControlServer + 跑到 EOF"""
    from sensenova_claw.interfaces.control.runtime_factory import (
        build_serve_runtime,
        teardown_serve_runtime,
    )
    from sensenova_claw.interfaces.control.server import ControlServer
    from sensenova_claw.interfaces.control.stdio_stream import StdioStream

    # 重要约束：stdout 仅走协议，日志全部走 stderr
    # 这里只配 root logger 的 stream handler；不动现有 setup_logging 的 file handler
    _setup_serve_logging()

    ctx = await build_serve_runtime()
    stream = StdioStream()
    server = ControlServer(ctx=ctx, stream=stream)
    try:
        await server.run()
    finally:
        await teardown_serve_runtime(ctx)
    return 0


def _setup_serve_logging() -> None:
    """serve --stdio 模式：所有日志走 stderr，不污染 stdout"""
    root = logging.getLogger()
    # 移除任何输出到 stdout 的 handler，保留输出到 stderr 的
    for h in list(root.handlers):
        stream = getattr(h, "stream", None)
        if stream is sys.stdout:
            root.removeHandler(h)
    # 至少有一个 stderr handler
    if not any(getattr(h, "stream", None) is sys.stderr for h in root.handlers):
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        root.addHandler(h)
    if root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def cmd_serve(args: argparse.Namespace) -> int:
    """同步入口：仅支持 --stdio（M0）；--ws / --tcp 在 M1+ 蓝图"""
    if not getattr(args, "stdio", False):
        print(
            "错误: serve 子命令必须指定传输方式（本期仅支持 --stdio）",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_cmd_serve_async(args))
```

3. 在 `main()` 函数里，在 `subparsers.add_parser("version", ...)` **之前**插入：

```python
    # sensenova_claw serve（M0：仅 --stdio）
    serve_parser = subparsers.add_parser(
        "serve",
        help="启动 Control Protocol Server（供 SDK 子进程模式使用）",
    )
    serve_group = serve_parser.add_mutually_exclusive_group(required=True)
    serve_group.add_argument(
        "--stdio",
        action="store_true",
        help="使用 stdio 传输（每行一个 JSON-RPC 2.0 消息）",
    )
    # 占位：--ws HOST:PORT / --tcp HOST:PORT 在 M1+ 实现，本期仅打印
    # 不在此版本声明，避免误导用户
```

4. 在 `main()` 函数末尾的分发链里，在 `elif args.command == "version":` **之前**插入：

```python
    elif args.command == "serve":
        return cmd_serve(args)
```

- [ ] **Step 5: 跑测试确认通过**

```bash
python3 -m pytest tests/unit/test_app_main_serve.py -v
```

预期：4 passed。

- [ ] **Step 6: 跑现有 main 测试确保未回归**

```bash
python3 -m pytest tests/unit/test_app_main.py -v
```

预期：与 P3 之前一致全部通过（`run` / `cli` / port 工具未变）。

- [ ] **Step 7: 提交**

```bash
git add sensenova_claw/app/main.py \
        sensenova_claw/interfaces/control/stdio_stream.py \
        tests/unit/test_app_main_serve.py
git commit -m "feat(control): P3.8 add 'sensenova-claw serve --stdio' subcommand"
```

---

## Task 9: 端到端冒烟（真子进程）

**Files:**
- Test: `tests/integration/test_serve_stdio_smoke.py`

> 这是一个真起 `python3 -m sensenova_claw.app.main serve --stdio` 子进程的集成测试。在 mock provider 下跑（避免依赖外网 / 真 LLM）。

- [ ] **Step 1: 写测试**

`tests/integration/test_serve_stdio_smoke.py`：

```python
"""serve --stdio 子进程集成测试：跑完整握手流程"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest


@pytest.mark.asyncio
async def test_serve_stdio_full_handshake(tmp_path):
    """启动子进程 → initialize → ping → 关闭 stdin → 子进程退出"""
    env = os.environ.copy()
    # 数据库放临时目录，避免污染本机 ~/.sensenova-claw
    env["SENSENOVA_CLAW_HOME"] = str(tmp_path / "claw_home")
    env["PYTHONUNBUFFERED"] = "1"

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        # initialize
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocol_version": "1", "client_info": {"name": "smoke", "version": "0"}},
        }) + "\n").encode("utf-8"))
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        assert line, "no response on stdout"
        resp = json.loads(line.decode("utf-8"))
        assert resp["id"] == 1
        assert "result" in resp, resp

        # ping
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "ping", "params": {},
        }) + "\n").encode("utf-8"))
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
        resp = json.loads(line.decode("utf-8"))
        assert resp["id"] == 2
        assert resp["result"]["pong"] is True
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


@pytest.mark.asyncio
async def test_serve_stdio_does_not_open_http_port(tmp_path):
    """关键约束：serve --stdio 不应起 HTTP server"""
    import socket

    env = os.environ.copy()
    env["SENSENOVA_CLAW_HOME"] = str(tmp_path / "claw_home")
    env["PYTHONUNBUFFERED"] = "1"

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        # 等到 server 处理完 init（说明已启完）
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocol_version": "1"},
        }) + "\n").encode("utf-8"))
        await proc.stdin.drain()
        await asyncio.wait_for(proc.stdout.readline(), timeout=30)

        # 应当连不上 8000（默认 backend 端口）
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            connected = False
            try:
                s.connect(("127.0.0.1", 8000))
                connected = True
            except (ConnectionRefusedError, OSError):
                pass
            # 注意：如果开发者本机刚好已经有 sensenova-claw run 的后端在 8000，
            # 这个断言会误报。集成测试默认期待干净环境；CI 必须确保如此。
            assert not connected, "serve --stdio 不应开启 HTTP 端口 8000"
        finally:
            s.close()
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
```

- [ ] **Step 2: 跑测试确认通过**

```bash
python3 -m pytest tests/integration/test_serve_stdio_smoke.py -v
```

预期：2 passed（如 8000 端口被占需在 CI 文档里说明）。

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_serve_stdio_smoke.py
git commit -m "test(control): P3.9 add serve --stdio subprocess smoke test"
```

---

## Task 10: 文档：协议 wire 格式说明文件

**Files:**
- Create: `docs/protocols/control-protocol-stdio.md`

> 把 spec §5 + decomposition §3.5 的 wire 格式落成一份独立文档（P4 SDK 实现时可直接引用）。

- [ ] **Step 1: 创建文档**

`docs/protocols/control-protocol-stdio.md`：

```markdown
# Control Protocol over stdio（M0 / P3 实现）

> 此文档与 `docs/design/2026-04-27-agent-harness-sdk-design.md` §5 同步。`docs/design/2026-04-27-plan-decomposition.md` §3.5 是上游契约，本文档落实到 stdio 形态。

## 1. 帧（Framing）

- 一个 JSON-RPC 2.0 消息 = 一行 UTF-8 文本，以 `\n` 结尾
- 每行内不允许出现裸 `\n`（编码时使用紧凑 JSON：`json.dumps(obj, separators=(",", ":"), ensure_ascii=False)`）
- 任何非 JSON 输入应触发 `-32700 PARSE_ERROR`

## 2. 消息形态

```jsonc
// Request（双向）
{ "jsonrpc": "2.0", "id": <int|str>, "method": "<name>", "params": { ... } }

// Response
{ "jsonrpc": "2.0", "id": <same>, "result": { ... } }
{ "jsonrpc": "2.0", "id": <same>, "error": { "code": <int>, "message": "...", "data": { ... } } }

// Notification（无 id）
{ "jsonrpc": "2.0", "method": "<name>", "params": { ... } }
```

S→C request 的 id 由 server 维护独立空间（`srv-1`, `srv-2`, ...），不与 client 的 id 冲突。

## 3. 通道分配

| 流 | 用途 |
|---|---|
| stdin | 仅 client→server 消息；EOF 触发 server 优雅退出 |
| stdout | 仅 server→client 消息（response + notification + S→C request） |
| stderr | 日志、诊断输出；不属于协议 |

`sensenova-claw serve --stdio` 启动后 stdout 不可被任何模块写入非协议内容。

## 4. M0 已实现 method 列表

参见 spec §5.3，除 `mcp.register_server` / `mcp.invoke`（P4 引入）外全部已实现。

## 5. 错误码

参见 spec §5.4，与 `sensenova_claw.interfaces.control.errors` 中常量一一对应。

## 6. 进程生命周期

- stdin EOF → server flush 所有 outbox → 优雅退出
- SIGTERM → 同上
- 心跳 → 通过 `ping` method（C→S）验证
- 崩溃恢复 → client 检测到子进程退出后用 `session.resume` 继续

## 7. Permission 双向流

```
1. core 内部某个 tool 触发 tool.confirmation_requested 事件
2. ControlServer 拦截：发 S→C request "permission.request"，附带 tool_call_id / tool_name / arguments
3. client 必须用 Response 回 { "decision": "allow" | "deny" }
4. ControlServer 收到后 publish 一条 tool.confirmation_response 事件回总线
5. tool_worker 原有逻辑（已存在）继续放行 / 拒绝
```

任何对 tool_worker 的修改不属于 P3 范围。
```

- [ ] **Step 2: 提交**

```bash
git add docs/protocols/control-protocol-stdio.md
git commit -m "docs(control): P3.10 add Control Protocol stdio wire-format spec"
```

---

## Task 11: 全量回归

- [ ] **Step 1: 跑 P3 全量**

```bash
python3 -m pytest tests/unit/interfaces/control/ \
                  tests/unit/test_app_main_serve.py \
                  tests/integration/test_serve_stdio_smoke.py -v
```

- [ ] **Step 2: 跑 `app/main.py` 现有回归**

```bash
python3 -m pytest tests/unit/test_app_main.py -v
```

预期：所有原有 case 通过，证明 P3 没影响 `run` / `cli` / `version` 子命令。

- [ ] **Step 3: 跑全仓 unit + integration（可选，时间允许时）**

```bash
python3 -m pytest tests/unit/ tests/integration/ -q --timeout=60
```

预期：未引入新失败用例。新增 P3 测试全绿。

- [ ] **Step 4: 提交（如果有任何额外 fix）**

```bash
git status
# 如果有遗漏 fix，统一一次提交：
# git add -p
# git commit -m "fix(control): P3 follow-up fixes from regression"
```

---

## 自我评审清单

| spec / 拆分要求 | 对应 task |
|---|---|
| spec §5.1 wire 格式（行分隔 JSON） | Task 2.1 + Task 10 |
| spec §5.2 initialize 握手 | Task 4.1 |
| spec §5.3 session.* | Task 5 |
| spec §5.3 turn.* | Task 6 |
| spec §5.3 event.* + S→C event notification | Task 6 |
| spec §5.3 permission.request / permission.respond | Task 4.1 + Task 6 |
| spec §5.3 plugin.list / enable / disable / reload | Task 7 |
| spec §5.3 tool.list / agent.list / skill.list | Task 7 |
| spec §5.3 config.get / set / subscribe | Task 7 |
| spec §5.3 ping/pong | Task 4.1 |
| spec §5.3 mcp.register_server / mcp.invoke | **不在 P3 范围**（P4） |
| spec §5.4 错误码常量 | Task 1 |
| spec §5.6 stdin EOF / SIGTERM 优雅退出 | Task 4.1（`stop()` + EOF 检测）+ Task 8 |
| spec §3 架构：Control Server 在 core CLI 进程中作为 stdio 入口 | Task 8 |
| decomposition §3.5 wire 格式权威定义 | Task 2.1 + Task 10 |
| 现有 `run` / `cli` / `version` 子命令保持工作 | Task 8.2 + Task 11 |
| stdout 不污染、日志走 stderr | Task 8.2（`_setup_serve_logging`）+ Task 9（subprocess 不开 HTTP 验证） |
| `Identity.default_local()` 占位 | Task 4.1（`server.identity` 默认值） |
| 不实现 SDK / hook / mcp 反向 RPC / WS | 全文（每个 task 显式声明） |

## 风险与未尽事项（交接给后续 plan）

- `plugin.*` method 的真实语义依赖 P1/P2 完成的 PluginManifest；本期仅校验存在并返回占位字段。P5/P6 接入后需要回头丰富 `available_plugins`。
- `permission.respond` 既能作为 method 调用、也能作为 Response 回 server 的 request；P4 SDK 优先使用 Response 形式，method 形式保留。
- `config.set` 的脱敏策略 P3 仅对 key 名做粗匹配；P5 接入 secret_store 与 visibility 后需要重做。
- WebSocket / TCP 传输按 spec §3.1 蓝图，本 plan 不涉及。M1 时复用 `interfaces/ws/` 现有传输层即可，协议语义与 stdio 一致。
- 集成测试中假设 8000 端口干净；CI 必须保证执行此 plan 测试时无残留进程。
