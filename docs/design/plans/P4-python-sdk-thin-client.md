# P4: Python SDK 瘦客户端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `sensenova_claw/sdk/` Python 瘦客户端：spawn `sensenova-claw serve --stdio` 子进程，通过 Control Protocol（JSON-RPC over stdio）和 core 通信，并提供 `Harness / query / tool / create_sdk_mcp_server` 公开 API；支持 in-process MCP server 反向 RPC（`mcp.register_server` + `mcp.invoke`）。

**Architecture:** 模仿 `@anthropic-ai/claude-agent-sdk`：SDK 自身不实现任何 agent 循环，仅做"spawn 子进程 + 协议编解码 + 高层 facade"。由 `client.Harness` 启动 core CLI 子进程，`transport.StdioTransport` 负责按行读写 JSON，`protocol.py` 用 dataclass 定义 Request/Response/Notification 消息体，`query.py` 提供 async iterator API，`mcp.py` 把业务进程内的 Python 工具组装成 in-process MCP server 并通过反向 RPC 暴露给 core，`permissions.py` 处理 core 反向发来的 `permission.request`，`errors.py` 把协议 error code 映射为客户端异常。

**Tech Stack:** Python 3.12 / asyncio / dataclasses / `pytest` / `pytest-asyncio`（已在 dev extra）。仅依赖标准库 + 已有依赖。本期不发布 PyPI——SDK 代码留在 monorepo 同仓库，未来可以拆包发布。

**契约依赖（来自 `docs/design/2026-04-27-plan-decomposition.md` §3，必须严格引用）：**
- §3.4 `Identity`：本 plan 使用 `Identity.default_local()` 作为占位（P5 上线后无需改动 SDK 代码即可改用真实 identity）
- §3.5 Control Protocol wire 格式：JSON-RPC 2.0 over stdio，每行一个 JSON 对象。Request `{jsonrpc, id, method, params}`、Response `{jsonrpc, id, result|error}`、Notification `{jsonrpc, method, params}`
- 协议 method 名称由 spec §5.3 定义；P3 已实现 server 端

**严格的范围边界（与 decomposition §2 一致）：**
- ✓ `sensenova_claw/sdk/` 完整实现
- ✓ `examples/sdk_minimal.py` 与 `examples/sdk_inprocess_tool.py`
- ✓ 单元 + 集成 + 失败路径测试
- ✗ **不**发布 PyPI、不写 setup pipeline
- ✗ **不**实现 server 端 method（P3 已完成）
- ✗ **不**实现 visibility 过滤（P5 做）
- ✗ **不**做 WebSocket 传输（蓝图）

---

## 文件结构总览

实现完成后的目录布局：

```
sensenova_claw/sdk/
├── __init__.py           # 公开 API 出口：Harness, query, tool, create_sdk_mcp_server, ToolDef, McpServer, errors
├── errors.py             # 客户端异常类型（HarnessError, PermissionDenied, PluginNotLoaded, …）
├── protocol.py           # Request / Response / Notification dataclass + 编解码
├── transport.py          # StdioTransport：spawn subprocess + 按行读/写 JSON + EOF/SIGTERM 处理
├── permissions.py        # PermissionHandler 协议（接收 permission.request，回 allow/deny/edit）
├── mcp.py                # @tool 装饰器 + ToolDef / McpServer / create_sdk_mcp_server
├── query.py              # async def query(...) -> AsyncIterator[EventEnvelope]
└── client.py             # Harness 类：组合上述模块，提供高层方法

examples/
├── sdk_minimal.py        # ~30 行 hello world
└── sdk_inprocess_tool.py # @tool + custom MCP server end-to-end

tests/unit/sdk/
├── __init__.py
├── test_protocol.py      # 编解码 + 边界
├── test_transport.py     # 用 mock subprocess 验证读写
├── test_errors.py        # 错误码到异常的映射
└── test_mcp_decorator.py # @tool / create_sdk_mcp_server 元数据收集

tests/integration/sdk/
├── __init__.py
├── test_harness_handshake.py  # 真起 core CLI，跑 initialize 握手
├── test_harness_query.py      # 真起 core CLI，跑一次完整 turn
├── test_harness_inprocess_tool.py  # 完整 in-process MCP 流
└── test_harness_failure.py    # subprocess 崩溃 / 卡死场景

tests/e2e/
└── test_sdk_minimal_smoke.py  # CI smoke：跑 examples/sdk_minimal.py 端到端
```

每个文件单一职责，聚焦小且可独立测试。

---

## Task 1: 包脚手架 + 公开 API 占位

**Files:**
- Create: `sensenova_claw/sdk/__init__.py`
- Create: `tests/unit/sdk/__init__.py`
- Create: `tests/integration/sdk/__init__.py`

- [ ] **Step 1: 写失败的导入测试**

`tests/unit/sdk/test_public_api.py`：

```python
def test_public_api_exports():
    from sensenova_claw.sdk import (
        Harness,
        query,
        tool,
        create_sdk_mcp_server,
        HarnessError,
    )
    assert callable(query)
    assert callable(tool)
    assert callable(create_sdk_mcp_server)
    assert isinstance(Harness, type)
    assert issubclass(HarnessError, Exception)
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_public_api.py -v
```

预期：`ModuleNotFoundError: No module named 'sensenova_claw.sdk'`

- [ ] **Step 3: 创建空 `sensenova_claw/sdk/__init__.py`**

```python
"""Sensenova-Claw Python SDK：core CLI 瘦客户端。

模仿 @anthropic-ai/claude-agent-sdk：SDK 自身不实现 agent 循环，
只 spawn `sensenova-claw serve --stdio` 子进程并做 Control Protocol 编解码。
"""
from sensenova_claw.sdk.client import Harness
from sensenova_claw.sdk.query import query
from sensenova_claw.sdk.mcp import tool, create_sdk_mcp_server
from sensenova_claw.sdk.errors import HarnessError

__all__ = [
    "Harness",
    "query",
    "tool",
    "create_sdk_mcp_server",
    "HarnessError",
]
```

- [ ] **Step 4: 创建依赖文件占位（防导入错误）**

`sensenova_claw/sdk/errors.py`：

```python
class HarnessError(Exception):
    """SDK 顶层异常基类。"""
```

`sensenova_claw/sdk/client.py`：

```python
class Harness:
    """占位，后续 task 实现。"""
```

`sensenova_claw/sdk/query.py`：

```python
async def query(*args, **kwargs):
    """占位，后续 task 实现。"""
    raise NotImplementedError
```

`sensenova_claw/sdk/mcp.py`：

```python
def tool(*args, **kwargs):
    """占位，后续 task 实现。"""
    raise NotImplementedError


def create_sdk_mcp_server(*args, **kwargs):
    """占位，后续 task 实现。"""
    raise NotImplementedError
```

- [ ] **Step 5: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_public_api.py -v
```

预期：PASS

- [ ] **Step 6: 提交**

```
git add sensenova_claw/sdk/__init__.py sensenova_claw/sdk/errors.py sensenova_claw/sdk/client.py sensenova_claw/sdk/query.py sensenova_claw/sdk/mcp.py tests/unit/sdk/__init__.py tests/integration/sdk/__init__.py tests/unit/sdk/test_public_api.py
git commit -m "feat(sdk): scaffold sensenova_claw/sdk package with public API surface"
```

---

## Task 2: 错误类型映射

**Files:**
- Modify: `sensenova_claw/sdk/errors.py`
- Test: `tests/unit/sdk/test_errors.py`

protocol error code（spec §5.4）→ Python 异常的对应关系：

| code | 异常 |
|---|---|
| -32700 ~ -32603 | `ProtocolError`（兜底） |
| -32000 | `PermissionDenied` |
| -32001 | `PluginNotLoaded` |
| -32002 | `SessionNotFound` |
| -32003 | `ToolExecutionFailed` |
| -32004 | `ConfigValidationFailed` |
| -32005 | `IdentityMismatch` |
| -32006 | `CapabilityUnavailable` |

并定义两个非协议异常：`TransportError`（stdio 读写失败）、`HarnessTimeoutError`（请求超时）。

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_errors.py`：

```python
import pytest

from sensenova_claw.sdk.errors import (
    HarnessError,
    HarnessTimeoutError,
    TransportError,
    ProtocolError,
    PermissionDenied,
    PluginNotLoaded,
    SessionNotFound,
    ToolExecutionFailed,
    ConfigValidationFailed,
    IdentityMismatch,
    CapabilityUnavailable,
    error_from_code,
)


@pytest.mark.parametrize(
    "code,exc_type",
    [
        (-32000, PermissionDenied),
        (-32001, PluginNotLoaded),
        (-32002, SessionNotFound),
        (-32003, ToolExecutionFailed),
        (-32004, ConfigValidationFailed),
        (-32005, IdentityMismatch),
        (-32006, CapabilityUnavailable),
        (-32700, ProtocolError),
        (-32600, ProtocolError),
        (-32603, ProtocolError),
    ],
)
def test_error_from_code(code, exc_type):
    err = error_from_code(code, "msg", {"k": "v"})
    assert isinstance(err, exc_type)
    assert isinstance(err, HarnessError)
    assert err.code == code
    assert "msg" in str(err)
    assert err.data == {"k": "v"}


def test_error_from_unknown_code_falls_back():
    err = error_from_code(-99999, "boom", None)
    assert isinstance(err, ProtocolError)
    assert err.code == -99999


def test_transport_and_timeout_are_harness_errors():
    assert issubclass(TransportError, HarnessError)
    assert issubclass(HarnessTimeoutError, HarnessError)
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_errors.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `errors.py`**

```python
"""客户端异常类型，映射 Control Protocol error code（spec §5.4）。"""
from __future__ import annotations

from typing import Any


class HarnessError(Exception):
    """SDK 顶层异常基类。所有 SDK 内部抛出的异常都继承自它。"""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class TransportError(HarnessError):
    """stdio 传输层异常：管道关闭、读写失败、解码失败等。"""


class HarnessTimeoutError(HarnessError):
    """请求等待响应超时。"""


class ProtocolError(HarnessError):
    """JSON-RPC 协议错误（含 -32700~-32603 标准错误，以及未识别的业务码）。"""


class PermissionDenied(HarnessError):
    """code=-32000：core 拒绝执行（未通过 visibility / hook 校验）。"""


class PluginNotLoaded(HarnessError):
    """code=-32001：引用的 plugin 未加载。"""


class SessionNotFound(HarnessError):
    """code=-32002：session_id 不存在。"""


class ToolExecutionFailed(HarnessError):
    """code=-32003：工具执行失败。"""


class ConfigValidationFailed(HarnessError):
    """code=-32004：写入的 config 不符合 schema。"""


class IdentityMismatch(HarnessError):
    """code=-32005：身份与 plugin visibility 不匹配。"""


class CapabilityUnavailable(HarnessError):
    """code=-32006：当前 core 版本不支持该能力。"""


_CODE_MAP: dict[int, type[HarnessError]] = {
    -32000: PermissionDenied,
    -32001: PluginNotLoaded,
    -32002: SessionNotFound,
    -32003: ToolExecutionFailed,
    -32004: ConfigValidationFailed,
    -32005: IdentityMismatch,
    -32006: CapabilityUnavailable,
}


def error_from_code(code: int, message: str, data: Any) -> HarnessError:
    """根据协议 error code 构造对应的 SDK 异常。未知码兜底为 ProtocolError。"""
    cls = _CODE_MAP.get(code, ProtocolError)
    return cls(message, code=code, data=data)
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_errors.py -v
```

预期：所有 case PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/errors.py tests/unit/sdk/test_errors.py
git commit -m "feat(sdk): error types mapping protocol codes"
```

---

## Task 3: 协议消息 dataclass 和 codec

**Files:**
- Create: `sensenova_claw/sdk/protocol.py`
- Test: `tests/unit/sdk/test_protocol.py`

参考 wire 格式（decomposition §3.5）：每行一个 JSON 对象，字段固定。Codec 负责 dataclass ↔ dict ↔ JSON 三向转换，并校验 jsonrpc 版本号 == "2.0"。

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_protocol.py`：

```python
import json
import pytest

from sensenova_claw.sdk.protocol import (
    Request,
    Response,
    Notification,
    encode,
    decode,
    ProtocolDecodeError,
)


def test_encode_request_round_trip():
    req = Request(id=1, method="initialize", params={"protocol_version": "1"})
    line = encode(req)
    assert line.endswith("\n")
    parsed = json.loads(line)
    assert parsed == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocol_version": "1"},
    }


def test_encode_notification_has_no_id():
    note = Notification(method="event", params={"envelope": {"type": "user.input"}})
    parsed = json.loads(encode(note))
    assert "id" not in parsed
    assert parsed["method"] == "event"


def test_encode_response_with_result():
    resp = Response(id="abc", result={"session_id": "s-1"})
    parsed = json.loads(encode(resp))
    assert parsed == {"jsonrpc": "2.0", "id": "abc", "result": {"session_id": "s-1"}}


def test_encode_response_with_error():
    resp = Response(id=2, error={"code": -32002, "message": "no session"})
    parsed = json.loads(encode(resp))
    assert parsed["error"]["code"] == -32002
    assert "result" not in parsed


def test_decode_request():
    line = '{"jsonrpc":"2.0","id":7,"method":"turn.send_input","params":{"text":"hi"}}'
    msg = decode(line)
    assert isinstance(msg, Request)
    assert msg.id == 7
    assert msg.method == "turn.send_input"
    assert msg.params == {"text": "hi"}


def test_decode_notification():
    line = '{"jsonrpc":"2.0","method":"event","params":{"envelope":{"type":"x"}}}'
    msg = decode(line)
    assert isinstance(msg, Notification)
    assert msg.method == "event"


def test_decode_response_result():
    msg = decode('{"jsonrpc":"2.0","id":3,"result":{"ok":true}}')
    assert isinstance(msg, Response)
    assert msg.result == {"ok": True}
    assert msg.error is None


def test_decode_response_error():
    msg = decode('{"jsonrpc":"2.0","id":3,"error":{"code":-32600,"message":"bad"}}')
    assert isinstance(msg, Response)
    assert msg.error == {"code": -32600, "message": "bad"}


def test_decode_rejects_wrong_jsonrpc_version():
    with pytest.raises(ProtocolDecodeError):
        decode('{"jsonrpc":"1.0","id":1,"method":"x"}')


def test_decode_rejects_invalid_json():
    with pytest.raises(ProtocolDecodeError):
        decode("{not json")


def test_decode_rejects_missing_jsonrpc():
    with pytest.raises(ProtocolDecodeError):
        decode('{"id":1,"method":"x"}')
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_protocol.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `protocol.py`**

```python
"""Control Protocol wire 格式（JSON-RPC 2.0 over stdio）。

权威定义在 docs/design/2026-04-27-plan-decomposition.md §3.5。
P3 实现 server 端、本模块实现 client 端编解码，双方共享同一份 wire 格式。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Union

from sensenova_claw.sdk.errors import HarnessError


JSONRPC_VERSION = "2.0"


class ProtocolDecodeError(HarnessError):
    """收到的行不是合法的 Control Protocol 消息。"""


@dataclass(slots=True)
class Request:
    """C→S 或 S→C 请求消息。"""
    id: Union[int, str]
    method: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Response:
    """对 Request 的响应（result 与 error 二选一）。"""
    id: Union[int, str]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


@dataclass(slots=True)
class Notification:
    """无 id，单向通知（典型：core → client 推送 event）。"""
    method: str
    params: dict[str, Any] = field(default_factory=dict)


Message = Union[Request, Response, Notification]


def encode(msg: Message) -> str:
    """把消息序列化为单行 JSON（结尾自动带 `\n`）。"""
    if isinstance(msg, Request):
        body = {"jsonrpc": JSONRPC_VERSION, "id": msg.id, "method": msg.method, "params": msg.params}
    elif isinstance(msg, Response):
        body: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "id": msg.id}
        if msg.error is not None:
            body["error"] = msg.error
        else:
            body["result"] = msg.result if msg.result is not None else {}
    elif isinstance(msg, Notification):
        body = {"jsonrpc": JSONRPC_VERSION, "method": msg.method, "params": msg.params}
    else:
        raise TypeError(f"Unknown message type: {type(msg)!r}")
    return json.dumps(body, ensure_ascii=False) + "\n"


def decode(line: str) -> Message:
    """把单行 JSON 反序列化为 Request / Response / Notification。"""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise ProtocolDecodeError(f"invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ProtocolDecodeError("message must be a JSON object")
    if obj.get("jsonrpc") != JSONRPC_VERSION:
        raise ProtocolDecodeError(f"unsupported jsonrpc version: {obj.get('jsonrpc')!r}")

    if "method" in obj and "id" in obj:
        return Request(id=obj["id"], method=obj["method"], params=obj.get("params") or {})
    if "method" in obj:
        return Notification(method=obj["method"], params=obj.get("params") or {})
    if "id" in obj:
        return Response(id=obj["id"], result=obj.get("result"), error=obj.get("error"))
    raise ProtocolDecodeError(f"unrecognized message shape: keys={list(obj)}")
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_protocol.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/protocol.py tests/unit/sdk/test_protocol.py
git commit -m "feat(sdk): protocol Request/Response/Notification dataclasses + codec"
```

---

## Task 4: stdio 传输层

**Files:**
- Create: `sensenova_claw/sdk/transport.py`
- Test: `tests/unit/sdk/test_transport.py`

`StdioTransport` 职责：
- spawn subprocess（命令可定制，默认 `["sensenova-claw", "serve", "--stdio"]`）
- 把 subprocess.stdin / stdout 包装成 asyncio 流
- 提供 `async send(msg: Message)` 写一行
- 提供 `async receive() -> Message` 读一行（EOF 抛 `TransportError`）
- `aclose()` 优雅关闭：发 stdin EOF → 等 1 秒 → SIGTERM → 等 3 秒 → SIGKILL

不直接测试真实 subprocess（留给集成测试），单元测试用 mock duplex pipe（`asyncio.StreamReader` + `asyncio.StreamWriter` 的 in-memory 替身）。

- [ ] **Step 1: 写失败的测试（mock pipe 模式）**

`tests/unit/sdk/test_transport.py`：

```python
import asyncio
import pytest

from sensenova_claw.sdk.protocol import Request, Notification, encode
from sensenova_claw.sdk.transport import StdioTransport
from sensenova_claw.sdk.errors import TransportError


class _MemoryPipe:
    """轻量替身：把 send/receive 接到内存 BytesIO，模拟 stdio 双工。"""

    def __init__(self) -> None:
        self.from_core_buf: list[bytes] = []
        self.to_core_buf: list[bytes] = []
        self.closed = False

    async def write_line(self, line: str) -> None:
        self.from_core_buf.append(line.encode("utf-8"))

    async def read_outbound(self) -> str:
        # 等下一帧（轮询，限时 1s）
        for _ in range(100):
            if self.to_core_buf:
                return self.to_core_buf.pop(0).decode("utf-8")
            await asyncio.sleep(0.01)
        raise AssertionError("nothing written by SDK in 1s")


@pytest.mark.asyncio
async def test_send_writes_one_line_per_message():
    pipe = _MemoryPipe()
    transport = StdioTransport.from_pipes(
        reader=_async_reader([encode(Notification("event", {"x": 1}))]),
        writer_callback=lambda data: pipe.to_core_buf.append(data),
    )
    await transport.send(Request(id=1, method="initialize", params={}))
    line = await pipe.read_outbound()
    assert line.endswith("\n")
    assert '"method":"initialize"' in line
    await transport.aclose()


@pytest.mark.asyncio
async def test_receive_parses_one_line():
    line = encode(Notification("event", {"foo": "bar"}))
    transport = StdioTransport.from_pipes(
        reader=_async_reader([line]),
        writer_callback=lambda data: None,
    )
    msg = await transport.receive()
    assert isinstance(msg, Notification)
    assert msg.params == {"foo": "bar"}
    await transport.aclose()


@pytest.mark.asyncio
async def test_receive_raises_transport_error_on_eof():
    transport = StdioTransport.from_pipes(
        reader=_async_reader([]),  # 立即 EOF
        writer_callback=lambda data: None,
    )
    with pytest.raises(TransportError):
        await transport.receive()
    await transport.aclose()


def _async_reader(lines: list[str]):
    """返回一个能 readline() 出 `lines` 后 EOF 的 asyncio.StreamReader。"""
    reader = asyncio.StreamReader()
    for ln in lines:
        reader.feed_data(ln.encode("utf-8"))
    reader.feed_eof()
    return reader
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_transport.py -v
```

预期：`ImportError: cannot import name 'StdioTransport'`

- [ ] **Step 3: 实现 `transport.py`**

```python
"""stdio 传输层：spawn subprocess + 按行读写 JSON。"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from typing import Sequence

from sensenova_claw.sdk.errors import TransportError
from sensenova_claw.sdk.protocol import Message, decode, encode


DEFAULT_CMD: tuple[str, ...] = ("sensenova-claw", "serve", "--stdio")


class StdioTransport:
    """对 subprocess stdin/stdout 的薄封装，按行读写 JSON。"""

    def __init__(
        self,
        *,
        reader: asyncio.StreamReader,
        writer_callback: Callable[[bytes], None],
        process: asyncio.subprocess.Process | None = None,
    ) -> None:
        self._reader = reader
        self._writer_cb = writer_callback
        self._process = process
        self._closed = False

    # ── 工厂 ─────────────────────────────────────────────────
    @classmethod
    async def spawn(
        cls,
        cmd: Sequence[str] = DEFAULT_CMD,
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stderr_to: int | None = subprocess.DEVNULL,
    ) -> "StdioTransport":
        """启动 core CLI 子进程，返回连好 stdin/stdout 的 transport。

        stderr_to=subprocess.DEVNULL 默认丢弃 stderr，保持 stdout 仅走协议。
        测试时可传 sys.stderr.fileno() 或日志文件 fd。
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr_to,
                env=env or os.environ.copy(),
                cwd=cwd,
            )
        except FileNotFoundError as e:
            raise TransportError(f"core CLI not found: {cmd[0]!r}") from e

        if proc.stdin is None or proc.stdout is None:
            raise TransportError("subprocess did not provide stdin/stdout")

        writer = proc.stdin

        def _write(data: bytes) -> None:
            writer.write(data)

        return cls(reader=proc.stdout, writer_callback=_write, process=proc)

    @classmethod
    def from_pipes(
        cls,
        *,
        reader: asyncio.StreamReader,
        writer_callback: Callable[[bytes], None],
    ) -> "StdioTransport":
        """测试用工厂：跳过 subprocess。"""
        return cls(reader=reader, writer_callback=writer_callback, process=None)

    # ── 收发 ─────────────────────────────────────────────────
    async def send(self, msg: Message) -> None:
        if self._closed:
            raise TransportError("transport closed")
        line = encode(msg)
        try:
            self._writer_cb(line.encode("utf-8"))
            if self._process is not None and self._process.stdin is not None:
                await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise TransportError(f"write failed: {e}") from e

    async def receive(self) -> Message:
        if self._closed:
            raise TransportError("transport closed")
        try:
            line_bytes = await self._reader.readline()
        except asyncio.IncompleteReadError as e:
            raise TransportError("subprocess closed stdout") from e
        if not line_bytes:
            raise TransportError("EOF from subprocess stdout")
        return decode(line_bytes.decode("utf-8").rstrip("\n"))

    # ── 生命周期 ─────────────────────────────────────────────
    async def aclose(self) -> None:
        """优雅关闭：stdin EOF → SIGTERM → SIGKILL。"""
        if self._closed:
            return
        self._closed = True
        proc = self._process
        if proc is None:
            return
        # 1. 关 stdin → 触发 core 优雅退出
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception:
            pass
        # 2. 等 1s
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
            return
        except asyncio.TimeoutError:
            pass
        # 3. SIGTERM 等 3s
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
            return
        except asyncio.TimeoutError:
            pass
        # 4. SIGKILL 兜底
        try:
            proc.kill()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

    @property
    def returncode(self) -> int | None:
        return None if self._process is None else self._process.returncode
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_transport.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/transport.py tests/unit/sdk/test_transport.py
git commit -m "feat(sdk): stdio transport with subprocess lifecycle handling"
```

---

## Task 5: in-process MCP server 支持（@tool / create_sdk_mcp_server）

**Files:**
- Create: `sensenova_claw/sdk/mcp.py`（覆盖 Task 1 的占位）
- Test: `tests/unit/sdk/test_mcp_decorator.py`

参考 Claude Code SDK：`@tool(name, description, schema)` 装饰一个 `async def(args, extra)`，把其元数据 + handler 收集到 `ToolDef`；`create_sdk_mcp_server(name, version, tools)` 返回 `McpServer` 实例。`McpServer` 不立刻启动——它在 `Harness` 启动时通过反向 RPC 注册到 core，core 再通过 `mcp.invoke` 反向调进来。

字段约定（与 P3 server 端 `mcp.register_server` 对接）：
- `mcp.register_server` params：`{"server_id": str, "name": str, "version": str, "tools": [{"name", "description", "input_schema"}]}`
- `mcp.invoke` params（S→C request）：`{"server_id": str, "tool_name": str, "args": dict, "extra": dict}` → 期望 client 回 `{"content": ...}` 或 error

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_mcp_decorator.py`：

```python
import pytest

from sensenova_claw.sdk import tool, create_sdk_mcp_server
from sensenova_claw.sdk.mcp import ToolDef, McpServer


def test_tool_decorator_collects_metadata():
    @tool("get_weather", "Get weather for a city", {"city": str})
    async def get_weather(args, extra):
        return {"temp": 22}

    assert isinstance(get_weather, ToolDef)
    assert get_weather.name == "get_weather"
    assert get_weather.description == "Get weather for a city"
    # str → JSON Schema "string"
    assert get_weather.input_schema["properties"]["city"]["type"] == "string"
    assert "city" in get_weather.input_schema["required"]


def test_tool_decorator_with_explicit_json_schema():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}

    @tool("compute", "Compute", schema)
    async def compute(args, extra):
        return {"y": args["x"] * 2}

    assert compute.input_schema == schema


def test_create_sdk_mcp_server_bundles_tools():
    @tool("a", "A", {})
    async def a(args, extra):
        return {"r": "a"}

    @tool("b", "B", {})
    async def b(args, extra):
        return {"r": "b"}

    server = create_sdk_mcp_server(name="my-tools", version="0.1.0", tools=[a, b])
    assert isinstance(server, McpServer)
    assert server.name == "my-tools"
    assert server.version == "0.1.0"
    names = {t.name for t in server.tools}
    assert names == {"a", "b"}


def test_create_sdk_mcp_server_rejects_duplicate_tool_names():
    @tool("dup", "X", {})
    async def x(args, extra):
        return {}

    @tool("dup", "Y", {})
    async def y(args, extra):
        return {}

    with pytest.raises(ValueError, match="duplicate"):
        create_sdk_mcp_server(name="s", tools=[x, y])


@pytest.mark.asyncio
async def test_mcp_server_invoke_dispatches_to_handler():
    @tool("echo", "Echo", {"msg": str})
    async def echo(args, extra):
        return {"out": args["msg"], "session": extra.get("session_id")}

    server = create_sdk_mcp_server(name="s", tools=[echo])
    result = await server.invoke("echo", {"msg": "hi"}, {"session_id": "s-1"})
    assert result == {"out": "hi", "session": "s-1"}


@pytest.mark.asyncio
async def test_mcp_server_invoke_unknown_tool_raises():
    server = create_sdk_mcp_server(name="s", tools=[])
    with pytest.raises(KeyError):
        await server.invoke("nope", {}, {})


def test_mcp_server_descriptor_for_register_rpc():
    @tool("greet", "Greet", {"name": str})
    async def greet(args, extra):
        return {"hello": args["name"]}

    server = create_sdk_mcp_server(name="my-tools", version="1.0.0", tools=[greet])
    desc = server.describe()
    # 与 mcp.register_server params 对齐
    assert desc["name"] == "my-tools"
    assert desc["version"] == "1.0.0"
    assert len(desc["tools"]) == 1
    assert desc["tools"][0]["name"] == "greet"
    assert "input_schema" in desc["tools"][0]
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_mcp_decorator.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `mcp.py`**

```python
"""in-process MCP server：把 Python 函数装成 MCP tool 暴露给 core。

工作流：
  1. 业务用 @tool 装饰 async 函数 → ToolDef
  2. create_sdk_mcp_server(name, tools) → McpServer
  3. Harness 启动后通过反向 RPC `mcp.register_server` 把 McpServer 描述上报给 core
  4. core 把这些 tool 注入 ToolRegistry；LLM 调用时，core 发 `mcp.invoke` 反向 RPC 到本进程
  5. SDK 路由到 server.invoke(tool_name, args, extra)
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


# 把 Python 类型映射成最简 JSON Schema 类型。
_PY_TO_JSON_TYPE: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _coerce_schema(schema: dict[str, Any] | dict[str, type]) -> dict[str, Any]:
    """把 {"city": str} 等简写规整为 JSON Schema object；若已是 JSON Schema 原样返回。"""
    if "type" in schema and "properties" in schema:
        return schema  # already JSON Schema
    if not schema:
        return {"type": "object", "properties": {}, "required": []}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for key, value in schema.items():
        if isinstance(value, type):
            properties[key] = {"type": _PY_TO_JSON_TYPE.get(value, "string")}
            required.append(key)
        elif isinstance(value, dict):
            properties[key] = value
            required.append(key)
        else:
            raise TypeError(f"Unsupported schema value for {key!r}: {value!r}")
    return {"type": "object", "properties": properties, "required": required}


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[Any]]


@dataclass(slots=True)
class ToolDef:
    """单个 tool 的描述 + handler。"""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def __call__(self, args: dict[str, Any], extra: dict[str, Any]) -> Awaitable[Any]:
        # 允许装饰后仍像普通 async 函数一样被调用，便于业务自测
        return self.handler(args, extra)


def tool(
    name: str,
    description: str,
    schema: dict[str, Any],
) -> Callable[[ToolHandler], ToolDef]:
    """装饰器：把 async 函数包装成 ToolDef。

    schema 可写简写 `{"city": str}`，也可写完整 JSON Schema `{"type":"object", ...}`。
    """
    def decorator(fn: ToolHandler) -> ToolDef:
        return ToolDef(
            name=name,
            description=description,
            input_schema=_coerce_schema(schema),
            handler=fn,
        )
    return decorator


@dataclass(slots=True)
class McpServer:
    """in-process MCP server 的句柄。Harness 用它向 core 注册 + 路由调用。"""
    name: str
    version: str
    tools: list[ToolDef]
    _by_name: dict[str, ToolDef] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._by_name = {t.name: t for t in self.tools}

    def describe(self) -> dict[str, Any]:
        """生成 mcp.register_server 的 params 结构。"""
        return {
            "name": self.name,
            "version": self.version,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in self.tools
            ],
        }

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        extra: dict[str, Any],
    ) -> Any:
        """处理来自 core 的 mcp.invoke 反向 RPC。"""
        if tool_name not in self._by_name:
            raise KeyError(f"tool {tool_name!r} not registered in server {self.name!r}")
        return await self._by_name[tool_name].handler(args, extra)


def create_sdk_mcp_server(
    *,
    name: str,
    version: str = "0.1.0",
    tools: list[ToolDef],
) -> McpServer:
    """组装一个 in-process MCP server。"""
    seen: set[str] = set()
    for t in tools:
        if t.name in seen:
            raise ValueError(f"duplicate tool name {t.name!r} in server {name!r}")
        seen.add(t.name)
    return McpServer(name=name, version=version, tools=list(tools))
```

并更新 `sensenova_claw/sdk/__init__.py` 多导出 `ToolDef` / `McpServer`：

```python
# 在已有 __all__ 后追加：
from sensenova_claw.sdk.mcp import ToolDef, McpServer

__all__ += ["ToolDef", "McpServer"]
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_mcp_decorator.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/mcp.py sensenova_claw/sdk/__init__.py tests/unit/sdk/test_mcp_decorator.py
git commit -m "feat(sdk): @tool decorator + in-process McpServer"
```

---

## Task 6: PermissionHandler 协议

**Files:**
- Create: `sensenova_claw/sdk/permissions.py`
- Test: `tests/unit/sdk/test_permissions.py`

业务可在 `Harness(permission_handler=...)` 注入。core 反向发 `permission.request` 时，SDK 调 handler，按返回值包出 `permission.respond` 回包。

返回值结构（与 spec §5.3 Permission 域一致）：
```python
{"decision": "allow"}
{"decision": "deny", "reason": "..."}
{"decision": "edit", "args": {...覆盖后的 tool_args...}}
```

默认 handler：全部 `allow`（开发友好）。

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_permissions.py`：

```python
import pytest

from sensenova_claw.sdk.permissions import (
    PermissionRequest,
    PermissionDecision,
    AllowAllHandler,
    PermissionHandler,
)


@pytest.mark.asyncio
async def test_allow_all_handler_returns_allow():
    handler: PermissionHandler = AllowAllHandler()
    req = PermissionRequest(tool="send_email", args={"to": "x@y.com"}, session_id="s", turn_id="t")
    decision = await handler.handle(req)
    assert isinstance(decision, PermissionDecision)
    assert decision.decision == "allow"


@pytest.mark.asyncio
async def test_decision_serializes_to_dict():
    d = PermissionDecision.allow()
    assert d.to_dict() == {"decision": "allow"}

    d2 = PermissionDecision.deny("nope")
    assert d2.to_dict() == {"decision": "deny", "reason": "nope"}

    d3 = PermissionDecision.edit({"to": "z@w.com"})
    assert d3.to_dict() == {"decision": "edit", "args": {"to": "z@w.com"}}


@pytest.mark.asyncio
async def test_custom_handler_can_deny():
    class DenyEmail:
        async def handle(self, req: PermissionRequest) -> PermissionDecision:
            if req.tool == "send_email":
                return PermissionDecision.deny("blocked")
            return PermissionDecision.allow()

    h: PermissionHandler = DenyEmail()
    d = await h.handle(PermissionRequest(tool="send_email", args={}, session_id="s", turn_id="t"))
    assert d.to_dict() == {"decision": "deny", "reason": "blocked"}
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_permissions.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `permissions.py`**

```python
"""Permission handler 接口：处理 core 反向发来的 permission.request。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


Decision = Literal["allow", "deny", "edit"]


@dataclass(slots=True)
class PermissionRequest:
    """core 发来的一次 permission.request。"""
    tool: str
    args: dict[str, Any]
    session_id: str
    turn_id: str


@dataclass(slots=True)
class PermissionDecision:
    """SDK 回给 core 的决策。"""
    decision: Decision
    reason: str | None = None
    args: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"decision": self.decision}
        if self.decision == "deny" and self.reason is not None:
            out["reason"] = self.reason
        if self.decision == "edit" and self.args is not None:
            out["args"] = self.args
        return out

    @classmethod
    def allow(cls) -> "PermissionDecision":
        return cls(decision="allow")

    @classmethod
    def deny(cls, reason: str = "") -> "PermissionDecision":
        return cls(decision="deny", reason=reason)

    @classmethod
    def edit(cls, args: dict[str, Any]) -> "PermissionDecision":
        return cls(decision="edit", args=args)


class PermissionHandler(Protocol):
    async def handle(self, request: PermissionRequest) -> PermissionDecision: ...


class AllowAllHandler:
    """默认 handler：全放行。生产环境应替换为业务自定义。"""

    async def handle(self, request: PermissionRequest) -> PermissionDecision:
        return PermissionDecision.allow()
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_permissions.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/permissions.py tests/unit/sdk/test_permissions.py
git commit -m "feat(sdk): PermissionHandler protocol with allow/deny/edit decisions"
```

---

## Task 7: Harness 类骨架（构造、async context manager、占位 connect）

**Files:**
- Modify: `sensenova_claw/sdk/client.py`
- Test: `tests/unit/sdk/test_client_lifecycle.py`

`Harness` 是公开 API 的核心。本 task 只做骨架：构造参数解析、`async with` 进出、占位 connect/close（不真起子进程）。后续 task 把 RPC 循环、handshake、query、reverse RPC 接进来。

构造参数：
- `command: Sequence[str] | None`：自定义启动命令；默认 `("sensenova-claw", "serve", "--stdio")`
- `cwd: str | None`
- `env: dict[str, str] | None`
- `mcp_servers: dict[str, McpServer] | None`：业务 in-process MCP server，键 = 注册到 core 的 `server_id`
- `permission_handler: PermissionHandler | None`：默认 `AllowAllHandler()`
- `identity: Identity | None`：默认 `Identity.default_local()`（P5 替换）
- `request_timeout: float`：单条请求等响应的默认超时，默认 30s

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_client_lifecycle.py`：

```python
import pytest

from sensenova_claw.sdk import Harness, create_sdk_mcp_server, tool
from sensenova_claw.sdk.permissions import AllowAllHandler


def test_harness_default_construction():
    h = Harness()
    assert h.command == ("sensenova-claw", "serve", "--stdio")
    assert isinstance(h.permission_handler, AllowAllHandler)
    assert h.identity is not None
    assert h.identity.team_id == "local-team"
    assert h.mcp_servers == {}


def test_harness_accepts_custom_command_and_mcp_servers():
    @tool("noop", "noop", {})
    async def noop(args, extra):
        return {}

    server = create_sdk_mcp_server(name="my-tools", tools=[noop])

    h = Harness(
        command=["python3", "-m", "sensenova_claw.app.main", "serve", "--stdio"],
        mcp_servers={"my-tools": server},
        request_timeout=5.0,
    )
    assert "my-tools" in h.mcp_servers
    assert h.request_timeout == 5.0


@pytest.mark.asyncio
async def test_harness_context_manager_calls_connect_and_close(monkeypatch):
    """async with Harness() 应触发 connect/close（用打桩 transport 验证）。"""

    calls = []

    class FakeTransport:
        async def send(self, msg):
            calls.append(("send", msg))
        async def receive(self):
            raise NotImplementedError
        async def aclose(self):
            calls.append(("close",))

    async def fake_handshake(self, transport):
        calls.append(("handshake",))

    async def fake_spawn(*args, **kwargs):
        return FakeTransport()

    monkeypatch.setattr(
        "sensenova_claw.sdk.client.StdioTransport.spawn",
        classmethod(lambda cls, *a, **kw: fake_spawn()),
    )
    monkeypatch.setattr(Harness, "_handshake", fake_handshake)

    async with Harness() as h:
        assert h.is_connected

    assert ("handshake",) in calls
    assert ("close",) in calls
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_client_lifecycle.py -v
```

预期：FAIL（`Harness` 还是占位）

- [ ] **Step 3: 实现骨架**

`sensenova_claw/sdk/client.py`：

```python
"""Harness：SDK 公开门面。spawn core CLI 子进程 + Control Protocol 编解码。"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sensenova_claw.sdk.errors import HarnessError, TransportError
from sensenova_claw.sdk.mcp import McpServer
from sensenova_claw.sdk.permissions import AllowAllHandler, PermissionHandler
from sensenova_claw.sdk.protocol import Notification, Request, Response
from sensenova_claw.sdk.transport import DEFAULT_CMD, StdioTransport

if TYPE_CHECKING:
    from sensenova_claw.platform.identity.identity import Identity


def _default_identity() -> "Identity":
    """占位：P5 上线后这里改导入真实 Identity。"""
    try:
        from sensenova_claw.platform.identity.identity import Identity  # noqa: WPS433
        return Identity.default_local()
    except ImportError:
        # P5 还没合入时，用一个最简 stub
        from dataclasses import dataclass

        @dataclass(slots=True)
        class _StubIdentity:
            user_id: str = "local-dev"
            team_id: str = "local-team"
            org_id: str = "local-org"

            def to_dict(self) -> dict[str, str]:
                return {"user_id": self.user_id, "team_id": self.team_id, "org_id": self.org_id}

        return _StubIdentity()  # type: ignore[return-value]


class Harness:
    """瘦客户端门面。

    用法 A：
        async with Harness() as h:
            async for ev in h.query("hello"):
                print(ev)

    用法 B：
        async with Harness(mcp_servers={"my-tools": server}) as h:
            async for ev in h.query("..."):
                ...
    """

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        mcp_servers: dict[str, McpServer] | None = None,
        permission_handler: PermissionHandler | None = None,
        identity: Any = None,
        request_timeout: float = 30.0,
    ) -> None:
        self.command: tuple[str, ...] = tuple(command) if command else DEFAULT_CMD
        self.cwd = cwd
        self.env = env
        self.mcp_servers: dict[str, McpServer] = dict(mcp_servers or {})
        self.permission_handler: PermissionHandler = permission_handler or AllowAllHandler()
        self.identity = identity if identity is not None else _default_identity()
        self.request_timeout = request_timeout

        self._transport: StdioTransport | None = None
        self._next_id: int = 1
        self._pending: dict[int | str, asyncio.Future] = {}
        self._event_subscribers: list[asyncio.Queue] = []
        self._reader_task: asyncio.Task | None = None
        self._connected: bool = False
        self._capabilities: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def capabilities(self) -> dict[str, Any]:
        return dict(self._capabilities)

    # ── 生命周期 ─────────────────────────────────────────────
    async def __aenter__(self) -> "Harness":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._connected:
            return
        self._transport = await StdioTransport.spawn(
            self.command,
            env=self.env,
            cwd=self.cwd,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        try:
            await self._handshake(self._transport)
        except Exception:
            await self.close()
            raise
        self._connected = True

    async def close(self) -> None:
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None
        # 清掉所有 pending future
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(TransportError("harness closed"))
        self._pending.clear()

    # ── 占位（后续 task 实现）─────────────────────────────────
    async def _handshake(self, transport: StdioTransport) -> None:
        """Task 9 实现。"""
        return None

    async def _reader_loop(self) -> None:
        """Task 8 实现。"""
        return None
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_client_lifecycle.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/client.py tests/unit/sdk/test_client_lifecycle.py
git commit -m "feat(sdk): Harness skeleton with construction + async context manager"
```

---

## Task 8: RPC reader loop + request/respond 关联

**Files:**
- Modify: `sensenova_claw/sdk/client.py`（替换 Task 7 中的占位 `_reader_loop`、加 `_send_request`）
- Test: `tests/unit/sdk/test_client_rpc.py`

reader loop 单线程读消息，按消息类型分发：
- `Response`：找 `_pending[id]` future，set_result/set_exception
- `Notification`：交给 `_event_subscribers` 队列（用于 query 流式）；若是反向 RPC（特殊 method 见 Task 10），由 `_handle_reverse_request` 处理
- `Request`（来自 server，反向 RPC）：调度到 `_handle_reverse_request`（Task 10 实现），本 task 仅打桩

`_send_request(method, params)`：
1. 分配自增 id
2. 注册 future 到 `_pending`
3. transport.send(Request)
4. `await asyncio.wait_for(future, timeout=request_timeout)`
5. 收到 error → `error_from_code` 抛
6. 超时 → `HarnessTimeoutError`

- [ ] **Step 1: 写失败的测试（用 in-memory transport 替身）**

`tests/unit/sdk/test_client_rpc.py`：

```python
import asyncio
import pytest

from sensenova_claw.sdk.client import Harness
from sensenova_claw.sdk.errors import (
    HarnessTimeoutError,
    PluginNotLoaded,
    SessionNotFound,
)
from sensenova_claw.sdk.protocol import Notification, Response


class _FakeTransport:
    def __init__(self) -> None:
        self.outbound: list = []
        self._inbound: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, msg) -> None:
        self.outbound.append(msg)

    async def receive(self):
        return await self._inbound.get()

    async def aclose(self) -> None:
        self.closed = True

    def feed(self, msg) -> None:
        self._inbound.put_nowait(msg)


def _make_harness_with_fake_transport(transport: _FakeTransport) -> Harness:
    h = Harness()
    h._transport = transport  # type: ignore[attr-defined]
    h._connected = True
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    return h


@pytest.mark.asyncio
async def test_send_request_returns_result_on_response():
    transport = _FakeTransport()
    h = _make_harness_with_fake_transport(transport)
    try:
        async def respond_async():
            # 等 send 写出后再喂 response
            for _ in range(50):
                if transport.outbound:
                    break
                await asyncio.sleep(0.01)
            sent = transport.outbound[0]
            transport.feed(Response(id=sent.id, result={"session_id": "s-1"}))

        responder = asyncio.create_task(respond_async())
        result = await h._send_request("session.create", {"agent_id": "default"})
        await responder
        assert result == {"session_id": "s-1"}
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_send_request_raises_mapped_error():
    transport = _FakeTransport()
    h = _make_harness_with_fake_transport(transport)
    try:
        async def respond_async():
            for _ in range(50):
                if transport.outbound:
                    break
                await asyncio.sleep(0.01)
            sent = transport.outbound[0]
            transport.feed(Response(id=sent.id, error={"code": -32002, "message": "no session"}))

        responder = asyncio.create_task(respond_async())
        with pytest.raises(SessionNotFound):
            await h._send_request("turn.send_input", {"session_id": "x", "text": "hi"})
        await responder
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_send_request_times_out():
    transport = _FakeTransport()
    h = Harness(request_timeout=0.05)
    h._transport = transport
    h._connected = True
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        with pytest.raises(HarnessTimeoutError):
            await h._send_request("ping", {})
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_event_notification_goes_to_subscribers():
    transport = _FakeTransport()
    h = _make_harness_with_fake_transport(transport)
    try:
        queue: asyncio.Queue = asyncio.Queue()
        h._event_subscribers.append(queue)

        transport.feed(Notification(method="event", params={"envelope": {"type": "user.input"}}))
        ev = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert ev["type"] == "user.input"
    finally:
        await h.close()
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_client_rpc.py -v
```

预期：FAIL（`_send_request` 不存在 / `_reader_loop` 是占位）

- [ ] **Step 3: 实现 reader loop + _send_request**

替换 `client.py` 中的 `_reader_loop`，新增 `_send_request` 和 `_handle_reverse_request` 占位。在 import 块加 `from sensenova_claw.sdk.errors import HarnessTimeoutError, error_from_code`：

```python
async def _reader_loop(self) -> None:
    """读取 transport，分发到 pending future / event 订阅 / 反向 RPC handler。"""
    assert self._transport is not None
    try:
        while True:
            msg = await self._transport.receive()
            if isinstance(msg, Response):
                fut = self._pending.pop(msg.id, None)
                if fut is None or fut.done():
                    continue
                if msg.error is not None:
                    err = error_from_code(
                        msg.error.get("code", -32603),
                        msg.error.get("message", "unknown error"),
                        msg.error.get("data"),
                    )
                    fut.set_exception(err)
                else:
                    fut.set_result(msg.result if msg.result is not None else {})
            elif isinstance(msg, Notification):
                if msg.method == "event":
                    envelope = msg.params.get("envelope", {})
                    for q in list(self._event_subscribers):
                        q.put_nowait(envelope)
                else:
                    # 其他 notification 暂时忽略，未来如 config.updated 可在此处理
                    pass
            else:  # Request 反向 RPC
                asyncio.create_task(self._handle_reverse_request(msg))
    except asyncio.CancelledError:
        raise
    except TransportError:
        # 子进程关闭：把所有 pending future fail 掉，让上层感知
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(TransportError("subprocess closed"))
        self._pending.clear()
    except Exception as e:  # 任何解码或其他异常都让 SDK 失败
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(HarnessError(f"reader loop failed: {e}"))
        self._pending.clear()


async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
    """发起一次 C→S RPC，等待并返回 result（或抛对应异常）。"""
    if self._transport is None:
        raise TransportError("not connected")
    req_id = self._next_id
    self._next_id += 1
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    self._pending[req_id] = fut
    await self._transport.send(Request(id=req_id, method=method, params=params))
    try:
        return await asyncio.wait_for(fut, timeout=self.request_timeout)
    except asyncio.TimeoutError as e:
        self._pending.pop(req_id, None)
        raise HarnessTimeoutError(f"request {method!r} timed out after {self.request_timeout}s") from e


async def _handle_reverse_request(self, request: Request) -> None:
    """Task 10 实现完整逻辑。"""
    # 默认回 method-not-found，避免 server 卡死
    assert self._transport is not None
    await self._transport.send(
        Response(id=request.id, error={"code": -32601, "message": f"method not found: {request.method}"})
    )
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_client_rpc.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/client.py tests/unit/sdk/test_client_rpc.py
git commit -m "feat(sdk): RPC reader loop + send_request with timeout and error mapping"
```

---

## Task 9: handshake（initialize）+ session 创建 + 事件订阅

**Files:**
- Modify: `sensenova_claw/sdk/client.py`
- Test: `tests/unit/sdk/test_client_handshake.py`

`_handshake`：发 `initialize` 请求，传 `protocol_version`、`client_info`、`identity`、`config_overrides`；存 `result.capabilities`。

加公开方法：
- `async def create_session(*, agent_id: str | None = None, **kwargs) -> str`：调 `session.create`，返回 `session_id`
- `async def send_input(session_id: str, text: str) -> str`：调 `turn.send_input`，返回 `turn_id`
- `async def subscribe_events(session_id: str) -> asyncio.Queue`：调 `event.subscribe`，把队列加到 `_event_subscribers`，返回队列

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_client_handshake.py`：

```python
import asyncio
import pytest

from sensenova_claw.sdk.client import Harness
from sensenova_claw.sdk.protocol import Request, Response


class _FakeTransport:
    def __init__(self) -> None:
        self.outbound: list = []
        self._inbound: asyncio.Queue = asyncio.Queue()
    async def send(self, msg):
        self.outbound.append(msg)
        # 自动响应 initialize / session.create / event.subscribe / turn.send_input
        if isinstance(msg, Request):
            if msg.method == "initialize":
                self._inbound.put_nowait(Response(id=msg.id, result={
                    "core_version": "1.2.0",
                    "protocol_version": "1",
                    "capabilities": {"streaming": True, "permissions": True},
                }))
            elif msg.method == "session.create":
                self._inbound.put_nowait(Response(id=msg.id, result={"session_id": "s-1"}))
            elif msg.method == "event.subscribe":
                self._inbound.put_nowait(Response(id=msg.id, result={"ok": True}))
            elif msg.method == "turn.send_input":
                self._inbound.put_nowait(Response(id=msg.id, result={"turn_id": "t-1"}))
    async def receive(self):
        return await self._inbound.get()
    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_handshake_sends_initialize_and_stores_capabilities():
    transport = _FakeTransport()
    h = Harness()
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        assert h.capabilities["streaming"] is True
        # 检查发出的 initialize 含 identity
        sent = next(m for m in transport.outbound if isinstance(m, Request) and m.method == "initialize")
        assert sent.params["protocol_version"] == "1"
        assert "identity" in sent.params
        assert sent.params["identity"]["team_id"] == "local-team"
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_create_session_and_send_input():
    transport = _FakeTransport()
    h = Harness()
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        h._connected = True
        sid = await h.create_session(agent_id="default")
        assert sid == "s-1"
        tid = await h.send_input(sid, "hello")
        assert tid == "t-1"
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_subscribe_events_returns_queue():
    transport = _FakeTransport()
    h = Harness()
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        h._connected = True
        q = await h.subscribe_events("s-1")
        assert isinstance(q, asyncio.Queue)
        assert q in h._event_subscribers
    finally:
        await h.close()
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_client_handshake.py -v
```

预期：FAIL（这些方法还不存在）

- [ ] **Step 3: 实现 handshake 与高层方法**

替换 `_handshake`，并加 `create_session` / `send_input` / `subscribe_events`：

```python
async def _handshake(self, transport: StdioTransport) -> None:
    identity_payload: dict[str, Any]
    if hasattr(self.identity, "to_dict"):
        identity_payload = self.identity.to_dict()
    else:
        identity_payload = {
            "user_id": getattr(self.identity, "user_id", "local-dev"),
            "team_id": getattr(self.identity, "team_id", "local-team"),
            "org_id": getattr(self.identity, "org_id", "local-org"),
        }
    result = await self._send_request(
        "initialize",
        {
            "protocol_version": "1",
            "client_info": {"name": "sensenova-claw-py-sdk", "version": "0.1.0"},
            "identity": identity_payload,
            "config_overrides": {},
        },
    )
    self._capabilities = result.get("capabilities", {})


async def create_session(self, *, agent_id: str | None = None, **kwargs) -> str:
    params: dict[str, Any] = {**kwargs}
    if agent_id is not None:
        params["agent_id"] = agent_id
    result = await self._send_request("session.create", params)
    return result["session_id"]


async def send_input(self, session_id: str, text: str) -> str:
    result = await self._send_request(
        "turn.send_input",
        {"session_id": session_id, "text": text},
    )
    return result["turn_id"]


async def subscribe_events(self, session_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    self._event_subscribers.append(queue)
    await self._send_request("event.subscribe", {"session_id": session_id})
    return queue
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_client_handshake.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/client.py tests/unit/sdk/test_client_handshake.py
git commit -m "feat(sdk): handshake + session.create + turn.send_input + event.subscribe"
```

---

## Task 10: 反向 RPC（permission.request + mcp.invoke + mcp.register_server）

**Files:**
- Modify: `sensenova_claw/sdk/client.py`
- Test: `tests/unit/sdk/test_client_reverse_rpc.py`

替换 `_handle_reverse_request`，并在 connect 流程中调 `mcp.register_server` 注册所有 `mcp_servers`：

支持的反向 method：
- `permission.request`：调 `permission_handler.handle(...)`，把 decision dict 作为 result 回
- `mcp.invoke`：按 `params["server_id"]` 找 server，调 `server.invoke(tool_name, args, extra)`，把结果包成 `{"content": result}` 回；找不到 → 错误码 `-32601`；handler 抛异常 → 错误码 `-32003`
- 其他 method → 错误码 `-32601`

注册时机：handshake 成功后立刻调 `mcp.register_server`，每个 in-process server 一次。

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_client_reverse_rpc.py`：

```python
import asyncio
import pytest

from sensenova_claw.sdk import Harness, create_sdk_mcp_server, tool
from sensenova_claw.sdk.protocol import Request, Response


class _FakeTransport:
    def __init__(self) -> None:
        self.outbound: list = []
        self._inbound: asyncio.Queue = asyncio.Queue()

    async def send(self, msg):
        self.outbound.append(msg)
        # 自动响应 initialize / mcp.register_server
        if isinstance(msg, Request):
            if msg.method == "initialize":
                self._inbound.put_nowait(Response(id=msg.id, result={"capabilities": {}}))
            elif msg.method == "mcp.register_server":
                self._inbound.put_nowait(Response(id=msg.id, result={"ok": True}))

    async def receive(self):
        return await self._inbound.get()

    async def aclose(self):
        pass

    def feed(self, msg) -> None:
        self._inbound.put_nowait(msg)


@pytest.mark.asyncio
async def test_mcp_register_server_called_after_handshake():
    @tool("noop", "noop", {})
    async def noop(args, extra):
        return {"ok": True}

    server = create_sdk_mcp_server(name="my-tools", tools=[noop])

    transport = _FakeTransport()
    h = Harness(mcp_servers={"my-tools": server})
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        await h._register_in_process_mcp_servers()
        register = next(
            m for m in transport.outbound
            if isinstance(m, Request) and m.method == "mcp.register_server"
        )
        assert register.params["server_id"] == "my-tools"
        assert register.params["name"] == "my-tools"
        assert {t["name"] for t in register.params["tools"]} == {"noop"}
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_reverse_mcp_invoke_routes_to_handler():
    @tool("echo", "Echo", {"msg": str})
    async def echo(args, extra):
        return {"out": args["msg"]}

    server = create_sdk_mcp_server(name="my-tools", tools=[echo])

    transport = _FakeTransport()
    h = Harness(mcp_servers={"my-tools": server})
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        # core 反向发 mcp.invoke
        transport.feed(Request(
            id=42,
            method="mcp.invoke",
            params={"server_id": "my-tools", "tool_name": "echo", "args": {"msg": "hi"}, "extra": {"session_id": "s"}},
        ))
        # 等 SDK 写回 response
        for _ in range(100):
            outs = [m for m in transport.outbound if isinstance(m, Response) and m.id == 42]
            if outs:
                break
            await asyncio.sleep(0.01)
        resp = next(m for m in transport.outbound if isinstance(m, Response) and m.id == 42)
        assert resp.error is None
        assert resp.result == {"content": {"out": "hi"}}
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_reverse_mcp_invoke_unknown_tool_returns_error():
    server = create_sdk_mcp_server(name="my-tools", tools=[])
    transport = _FakeTransport()
    h = Harness(mcp_servers={"my-tools": server})
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        transport.feed(Request(
            id=99,
            method="mcp.invoke",
            params={"server_id": "my-tools", "tool_name": "missing", "args": {}, "extra": {}},
        ))
        for _ in range(100):
            outs = [m for m in transport.outbound if isinstance(m, Response) and m.id == 99]
            if outs:
                break
            await asyncio.sleep(0.01)
        resp = next(m for m in transport.outbound if isinstance(m, Response) and m.id == 99)
        assert resp.error is not None
        assert resp.error["code"] == -32601
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_reverse_permission_request_invokes_handler():
    from sensenova_claw.sdk.permissions import PermissionDecision, PermissionRequest

    class DenyAll:
        async def handle(self, req: PermissionRequest) -> PermissionDecision:
            return PermissionDecision.deny("nope")

    transport = _FakeTransport()
    h = Harness(permission_handler=DenyAll())
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    try:
        await h._handshake(transport)
        transport.feed(Request(
            id=7,
            method="permission.request",
            params={"tool": "send_email", "args": {"to": "x@y.com"}, "session_id": "s", "turn_id": "t"},
        ))
        for _ in range(100):
            outs = [m for m in transport.outbound if isinstance(m, Response) and m.id == 7]
            if outs:
                break
            await asyncio.sleep(0.01)
        resp = next(m for m in transport.outbound if isinstance(m, Response) and m.id == 7)
        assert resp.result == {"decision": "deny", "reason": "nope"}
    finally:
        await h.close()
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_client_reverse_rpc.py -v
```

预期：FAIL

- [ ] **Step 3: 实现反向 RPC**

替换 `_handle_reverse_request` 并新增 `_register_in_process_mcp_servers`、并在 `connect()` 中 handshake 后调用：

```python
async def _register_in_process_mcp_servers(self) -> None:
    """把 self.mcp_servers 中所有 server 通过 mcp.register_server 注册到 core。"""
    for server_id, server in self.mcp_servers.items():
        params = {"server_id": server_id, **server.describe()}
        await self._send_request("mcp.register_server", params)


async def _handle_reverse_request(self, request: Request) -> None:
    assert self._transport is not None
    method = request.method
    params = request.params or {}
    try:
        if method == "permission.request":
            from sensenova_claw.sdk.permissions import PermissionRequest
            req = PermissionRequest(
                tool=params.get("tool", ""),
                args=params.get("args", {}),
                session_id=params.get("session_id", ""),
                turn_id=params.get("turn_id", ""),
            )
            decision = await self.permission_handler.handle(req)
            await self._transport.send(Response(id=request.id, result=decision.to_dict()))
            return
        if method == "mcp.invoke":
            server_id = params.get("server_id", "")
            tool_name = params.get("tool_name", "")
            server = self.mcp_servers.get(server_id)
            if server is None:
                await self._transport.send(Response(
                    id=request.id,
                    error={"code": -32601, "message": f"unknown server_id: {server_id}"},
                ))
                return
            try:
                result = await server.invoke(tool_name, params.get("args", {}), params.get("extra", {}))
            except KeyError as e:
                await self._transport.send(Response(
                    id=request.id,
                    error={"code": -32601, "message": str(e)},
                ))
                return
            except Exception as e:  # tool handler 抛 → 业务错误
                await self._transport.send(Response(
                    id=request.id,
                    error={"code": -32003, "message": f"tool execution failed: {e}"},
                ))
                return
            await self._transport.send(Response(id=request.id, result={"content": result}))
            return
        # 未知反向 method
        await self._transport.send(Response(
            id=request.id,
            error={"code": -32601, "message": f"method not found: {method}"},
        ))
    except Exception as e:
        # 兜底：不让反向 handler 异常崩掉 reader loop
        try:
            await self._transport.send(Response(
                id=request.id,
                error={"code": -32603, "message": f"internal error: {e}"},
            ))
        except Exception:
            pass
```

并修改 `connect()` 在 handshake 之后调用 `_register_in_process_mcp_servers`：

```python
# 替换 connect() 中 handshake 后的部分：
try:
    await self._handshake(self._transport)
    await self._register_in_process_mcp_servers()
except Exception:
    await self.close()
    raise
self._connected = True
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_client_reverse_rpc.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/client.py tests/unit/sdk/test_client_reverse_rpc.py
git commit -m "feat(sdk): reverse RPC for permission.request + mcp.invoke + mcp.register_server"
```

---

## Task 11: query() async iterator API

**Files:**
- Modify: `sensenova_claw/sdk/query.py`
- Modify: `sensenova_claw/sdk/client.py`（加 `Harness.query`）
- Test: `tests/unit/sdk/test_query.py`

参考 Claude Code SDK 的 `query()`：

签名：
```python
async def query(text: str, *, harness: Harness, session_id: str | None = None) -> AsyncIterator[dict]
```

`Harness.query(text, *, session_id=None)`：等价于 `query(text, harness=self, session_id=session_id)`，方便链式使用。

行为：
1. 若没有 `session_id`：调 `create_session()`
2. 调 `subscribe_events(session_id)` 拿队列
3. 调 `send_input(session_id, text)` 拿 `turn_id`
4. 不断从队列取 envelope yield 出去
5. 收到 `agent.step_completed` 且 `turn_id` 匹配时结束循环
6. 收到 `OnError` 或 `agent.step_failed` 也结束（但先 yield 出去）

- [ ] **Step 1: 写失败的测试**

`tests/unit/sdk/test_query.py`：

```python
import asyncio
import pytest

from sensenova_claw.sdk import Harness, query
from sensenova_claw.sdk.protocol import Notification, Request, Response


class _FakeTransport:
    def __init__(self) -> None:
        self.outbound: list = []
        self._inbound: asyncio.Queue = asyncio.Queue()

    async def send(self, msg):
        self.outbound.append(msg)
        if isinstance(msg, Request):
            if msg.method == "initialize":
                self._inbound.put_nowait(Response(id=msg.id, result={"capabilities": {}}))
            elif msg.method == "session.create":
                self._inbound.put_nowait(Response(id=msg.id, result={"session_id": "s-1"}))
            elif msg.method == "event.subscribe":
                self._inbound.put_nowait(Response(id=msg.id, result={"ok": True}))
            elif msg.method == "turn.send_input":
                self._inbound.put_nowait(Response(id=msg.id, result={"turn_id": "t-1"}))
                # 立即推几条事件 + 一条 step_completed
                async def push_events():
                    for ev in [
                        {"type": "user.input", "turn_id": "t-1"},
                        {"type": "agent.step_started", "turn_id": "t-1"},
                        {"type": "agent.step_completed", "turn_id": "t-1", "payload": {"final_text": "hi"}},
                    ]:
                        await asyncio.sleep(0.01)
                        self._inbound.put_nowait(Notification(method="event", params={"envelope": ev}))
                asyncio.create_task(push_events())

    async def receive(self):
        return await self._inbound.get()

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_harness_query_yields_until_step_completed():
    transport = _FakeTransport()
    h = Harness()
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    await h._handshake(transport)
    h._connected = True
    try:
        events = []
        async for ev in h.query("hello"):
            events.append(ev)
        types = [e["type"] for e in events]
        assert types == ["user.input", "agent.step_started", "agent.step_completed"]
    finally:
        await h.close()


@pytest.mark.asyncio
async def test_top_level_query_function_works():
    transport = _FakeTransport()
    h = Harness()
    h._transport = transport
    h._reader_task = asyncio.get_event_loop().create_task(h._reader_loop())
    await h._handshake(transport)
    h._connected = True
    try:
        events = []
        async for ev in query("hello", harness=h):
            events.append(ev)
        assert any(e["type"] == "agent.step_completed" for e in events)
    finally:
        await h.close()
```

- [ ] **Step 2: 跑测试确认失败**

```
python3 -m pytest tests/unit/sdk/test_query.py -v
```

预期：FAIL

- [ ] **Step 3: 实现 `query.py`**

替换 `sensenova_claw/sdk/query.py`：

```python
"""query() async iterator API：发用户输入并流式返回事件。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.sdk.client import Harness


_TERMINAL_TYPES = frozenset({"agent.step_completed", "agent.step_failed"})


async def query(
    text: str,
    *,
    harness: "Harness",
    session_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """发一次用户输入，流式 yield core 推回的 EventEnvelope（dict）。

    遇到匹配 turn_id 的 agent.step_completed 或 agent.step_failed 即结束。
    若不指定 session_id，会先 create_session。
    """
    if session_id is None:
        session_id = await harness.create_session()
    queue = await harness.subscribe_events(session_id)
    turn_id = await harness.send_input(session_id, text)
    try:
        while True:
            envelope = await queue.get()
            yield envelope
            if (
                envelope.get("turn_id") == turn_id
                and envelope.get("type") in _TERMINAL_TYPES
            ):
                return
    finally:
        # 把队列从订阅列表移除，避免泄漏
        try:
            harness._event_subscribers.remove(queue)  # type: ignore[attr-defined]
        except ValueError:
            pass
```

并在 `client.py` 加方法：

```python
def query(self, text: str, *, session_id: str | None = None):
    """链式快捷方法：等价于 sdk.query(text, harness=self, session_id=...)。"""
    from sensenova_claw.sdk.query import query as _query
    return _query(text, harness=self, session_id=session_id)
```

- [ ] **Step 4: 跑测试确认通过**

```
python3 -m pytest tests/unit/sdk/test_query.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add sensenova_claw/sdk/query.py sensenova_claw/sdk/client.py tests/unit/sdk/test_query.py
git commit -m "feat(sdk): query() async iterator API streaming events until step_completed"
```

---

## Task 12: 集成测试 — 真起 core CLI 子进程跑握手

**Files:**
- Create: `tests/integration/sdk/test_harness_handshake.py`

依赖：P3 已实现 `sensenova-claw serve --stdio`。本 task 用 `python3 -m sensenova_claw.app.main serve --stdio` 启动真实子进程，验证 handshake 能跑通。

> 如果 P3 未合入主分支，本 task 在 CI 用 `pytest.importorskip` 或环境变量 `SDK_INTEGRATION=1` 守护跳过。本地开发执行 P4 时，把 `--from-merge` 提示说明：先合 P3 才能跑 integration。

- [ ] **Step 1: 写测试**

`tests/integration/sdk/test_harness_handshake.py`：

```python
"""集成测试：真起 sensenova-claw serve --stdio 子进程。

需要：
- P3 已合入（sensenova-claw serve --stdio 可用）
- 设置 SDK_INTEGRATION=1 才跑（本地默认跳过，CI 显式开启）
"""
import os
import sys

import pytest

from sensenova_claw.sdk import Harness


pytestmark = pytest.mark.skipif(
    os.environ.get("SDK_INTEGRATION") != "1",
    reason="set SDK_INTEGRATION=1 to enable integration tests against real core CLI",
)


@pytest.mark.asyncio
async def test_harness_handshake_against_real_core():
    cmd = [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]
    async with Harness(command=cmd) as h:
        assert h.is_connected
        # core 至少声明一些能力
        assert isinstance(h.capabilities, dict)
```

- [ ] **Step 2: 在 P3 已合入的环境跑**

```
SDK_INTEGRATION=1 python3 -m pytest tests/integration/sdk/test_harness_handshake.py -v
```

预期：PASS（若 FAIL：检查 P3 的 initialize 实现是否返回 `capabilities` 字段）

- [ ] **Step 3: 提交**

```
git add tests/integration/sdk/test_harness_handshake.py
git commit -m "test(sdk): integration handshake against real serve --stdio subprocess"
```

---

## Task 13: 集成测试 — 跑一次完整 turn

**Files:**
- Create: `tests/integration/sdk/test_harness_query.py`

验证：发用户输入 → 收 user.input / agent.step_started / agent.step_completed 事件序列。需要 core 配置了至少 mock LLM provider（默认 mock provider 永远可用）。

- [ ] **Step 1: 写测试**

`tests/integration/sdk/test_harness_query.py`：

```python
import os
import sys

import pytest

from sensenova_claw.sdk import Harness


pytestmark = pytest.mark.skipif(
    os.environ.get("SDK_INTEGRATION") != "1",
    reason="set SDK_INTEGRATION=1 to enable integration tests",
)


@pytest.mark.asyncio
async def test_query_full_turn_against_real_core():
    cmd = [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]
    async with Harness(command=cmd) as h:
        events = []
        async for ev in h.query("hello"):
            events.append(ev)
            if len(events) > 50:  # safety
                break
        types = [e.get("type") for e in events]
        assert "user.input" in types
        assert any(t == "agent.step_completed" for t in types)
```

- [ ] **Step 2: 跑测试**

```
SDK_INTEGRATION=1 python3 -m pytest tests/integration/sdk/test_harness_query.py -v
```

预期：PASS

- [ ] **Step 3: 提交**

```
git add tests/integration/sdk/test_harness_query.py
git commit -m "test(sdk): integration query end-to-end against real core"
```

---

## Task 14: 集成测试 — in-process MCP tool 端到端

**Files:**
- Create: `tests/integration/sdk/test_harness_inprocess_tool.py`

验证：业务用 `@tool` + `create_sdk_mcp_server` 注册一个 in-process tool，core 的 LLM 在 turn 中能通过反向 RPC 调到，并把结果作为 `tool.call_completed` 事件回流。

为了让 LLM 真的调这个 tool，本测试约定：
- 使用 mock LLM provider（默认就是 mock，会按规则触发 tool_call）
- 或在测试里直接通过 core 的 hook/工具调用 API 触发（如果 P3 暴露了便捷 method 用之；否则跳过此 case 留给 P6 完成后再扩）

最小可行验证：LLM 是否真的命中我们的 in-process tool 不是本 plan 的责任（那要看 mock provider 是否配合）。本 task 只需验证：**当 core 决定调 in-process MCP tool 时，反向 RPC 能正确到达 SDK 进程并取回结果**。如果 P3+P5 现状下没有"强制触发 in-process tool 调用"的 API，则验证另一个等价路径：让 core 通过 mcp.invoke 反向 RPC 直接调（P3 server 端必须支持手动触发 mcp.invoke 的测试钩子）。

如果 P3 当前不支持手动触发反向调，本 task 降级为：仅断言 `mcp.register_server` 被 core 接受、对端返回成功。完整端到端等 P3+P6 后联调。

- [ ] **Step 1: 写最小集成测试**

`tests/integration/sdk/test_harness_inprocess_tool.py`：

```python
"""集成测试：in-process MCP server 至少能注册成功。"""
import os
import sys

import pytest

from sensenova_claw.sdk import Harness, create_sdk_mcp_server, tool


pytestmark = pytest.mark.skipif(
    os.environ.get("SDK_INTEGRATION") != "1",
    reason="set SDK_INTEGRATION=1 to enable integration tests",
)


@pytest.mark.asyncio
async def test_inprocess_mcp_server_registers():
    @tool("get_weather", "Get weather", {"city": str})
    async def get_weather(args, extra):
        return {"temp": 22, "city": args.get("city", "?")}

    server = create_sdk_mcp_server(name="my-tools", tools=[get_weather])
    cmd = [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]
    async with Harness(command=cmd, mcp_servers={"my-tools": server}) as h:
        assert h.is_connected
        # 进一步：通过 plugin/tool 列表 method 验证 my-tools 已加载
        result = await h._send_request("tool.list", {})
        names = [t.get("name", "") for t in result.get("tools", [])]
        # core 应能看到 my-tools::get_weather（或等价命名约定）
        assert any("get_weather" in n for n in names)
```

> 注意：上述 `tool.list` 返回结构以 P3 实现为准。如 P3 用 `result["tools"]` 列表，则按此断言；如 P3 用其它结构则按真实结构调整。这个细节在 P3 完成后再来对齐。

- [ ] **Step 2: 跑测试**

```
SDK_INTEGRATION=1 python3 -m pytest tests/integration/sdk/test_harness_inprocess_tool.py -v
```

预期：PASS（若 P3 的 `tool.list` 返回结构不同，按真实结构调整断言后再跑）

- [ ] **Step 3: 提交**

```
git add tests/integration/sdk/test_harness_inprocess_tool.py
git commit -m "test(sdk): integration in-process MCP server registration"
```

---

## Task 15: 失败路径测试 — subprocess 崩溃 / 找不到命令 / 卡死

**Files:**
- Create: `tests/integration/sdk/test_harness_failure.py`

不依赖真 core，三个独立 case：
1. 命令不存在 → `TransportError`
2. 子进程启动后立即退出 → 第一个 `_send_request` 抛 `TransportError`
3. 子进程不响应 → `_send_request` 抛 `HarnessTimeoutError`

- [ ] **Step 1: 写测试**

`tests/integration/sdk/test_harness_failure.py`：

```python
import asyncio
import os
import sys

import pytest

from sensenova_claw.sdk import Harness
from sensenova_claw.sdk.errors import HarnessTimeoutError, TransportError


@pytest.mark.asyncio
async def test_harness_raises_when_command_not_found():
    h = Harness(command=["/nonexistent/command/that/does/not/exist"])
    with pytest.raises(TransportError):
        await h.connect()


@pytest.mark.asyncio
async def test_harness_raises_when_subprocess_exits_immediately():
    # 用 python3 -c 立即退出来模拟"启动即崩"
    cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
    h = Harness(command=cmd, request_timeout=2.0)
    with pytest.raises((TransportError, HarnessTimeoutError)):
        await h.connect()
    await h.close()


@pytest.mark.asyncio
async def test_harness_times_out_when_subprocess_hangs():
    # 用 python3 -c 不读 stdin、不写 stdout，模拟卡死
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    h = Harness(command=cmd, request_timeout=0.5)
    with pytest.raises((HarnessTimeoutError, TransportError)):
        await h.connect()
    await h.close()
```

- [ ] **Step 2: 跑测试**

```
python3 -m pytest tests/integration/sdk/test_harness_failure.py -v
```

预期：全部 PASS（这些 case 不需要 core，普通环境就能跑）

- [ ] **Step 3: 提交**

```
git add tests/integration/sdk/test_harness_failure.py
git commit -m "test(sdk): failure paths for subprocess crash, missing command, hang"
```

---

## Task 16: 例子 — sdk_minimal.py（hello world）

**Files:**
- Create: `examples/sdk_minimal.py`
- Create: `tests/e2e/test_sdk_minimal_smoke.py`

约 30 行，展示最简用法。

- [ ] **Step 1: 写示例**

`examples/sdk_minimal.py`：

```python
"""Sensenova-Claw Python SDK 最小示例：hello world。

依赖：
- 当前进程能找到 `sensenova-claw serve --stdio`（已安装）
  或可改成 [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]

跑法：
    python3 examples/sdk_minimal.py
"""
from __future__ import annotations

import asyncio
import sys

from sensenova_claw.sdk import Harness


async def main() -> int:
    cmd = [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]
    async with Harness(command=cmd) as h:
        async for event in h.query("write me a haiku about agents"):
            print(f"[{event.get('type')}] {event.get('payload', {})}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: 写 smoke 测试**

`tests/e2e/test_sdk_minimal_smoke.py`：

```python
"""Smoke：跑一遍 examples/sdk_minimal.py。CI 只在 SDK_E2E=1 时执行。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("SDK_E2E") != "1",
    reason="set SDK_E2E=1 to run SDK smoke tests",
)


def test_sdk_minimal_runs_to_completion():
    repo_root = Path(__file__).resolve().parents[2]
    example = repo_root / "examples" / "sdk_minimal.py"
    assert example.exists(), f"example missing: {example}"

    result = subprocess.run(
        [sys.executable, str(example)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"
    # 至少应输出一些事件
    assert "agent.step_completed" in result.stdout or "step_completed" in result.stdout
```

- [ ] **Step 3: 跑 smoke 测试（已配置环境）**

```
SDK_E2E=1 SDK_INTEGRATION=1 python3 -m pytest tests/e2e/test_sdk_minimal_smoke.py -v
```

预期：PASS

- [ ] **Step 4: 提交**

```
git add examples/sdk_minimal.py tests/e2e/test_sdk_minimal_smoke.py
git commit -m "feat(sdk): minimal hello-world example + smoke test"
```

---

## Task 17: 例子 — sdk_inprocess_tool.py

**Files:**
- Create: `examples/sdk_inprocess_tool.py`

展示 `@tool` + `create_sdk_mcp_server` + `Harness(mcp_servers=...)` 端到端。

- [ ] **Step 1: 写示例**

`examples/sdk_inprocess_tool.py`：

```python
"""展示 in-process MCP tool：业务用 @tool 装饰 Python 函数，core 通过反向 RPC 调它。

依赖：
- core CLI 可启动 serve --stdio
- core 配置允许使用 mcp_servers 注入的工具（M0 默认 visibility public 即可）

跑法：
    python3 examples/sdk_inprocess_tool.py
"""
from __future__ import annotations

import asyncio
import sys

from sensenova_claw.sdk import Harness, create_sdk_mcp_server, tool


@tool("get_weather", "Get current weather for a city", {"city": str})
async def get_weather(args: dict, extra: dict) -> dict:
    """模拟天气查询。args 由 LLM 填，extra 含 session_id 等元信息。"""
    city = args.get("city", "Unknown")
    return {"city": city, "temp_c": 22, "condition": "sunny", "session": extra.get("session_id")}


async def main() -> int:
    server = create_sdk_mcp_server(
        name="my-tools",
        version="0.1.0",
        tools=[get_weather],
    )
    cmd = [sys.executable, "-m", "sensenova_claw.app.main", "serve", "--stdio"]
    async with Harness(command=cmd, mcp_servers={"my-tools": server}) as h:
        async for event in h.query("what's the weather in Paris?"):
            etype = event.get("type", "")
            payload = event.get("payload", {})
            if etype == "tool.call_completed":
                print(f"[tool] {payload.get('tool_name')} -> {payload.get('result')}")
            elif etype == "agent.step_completed":
                print(f"[final] {payload.get('final_text', '')}")
                break
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: 手动 smoke（可选）**

```
SDK_INTEGRATION=1 python3 examples/sdk_inprocess_tool.py
```

预期：能看到事件流；具体是否触发 get_weather 取决于配置的 LLM 是否有工具调用能力（mock 模式可能不调）。

- [ ] **Step 3: 提交**

```
git add examples/sdk_inprocess_tool.py
git commit -m "feat(sdk): in-process MCP tool example"
```

---

## Task 18: 跑全套 P4 单元测试 + 整体 lint

**Files:**
- 无新文件

- [ ] **Step 1: 跑全部 P4 单元测试**

```
python3 -m pytest tests/unit/sdk/ -v
```

预期：全部 PASS

- [ ] **Step 2: 跑失败路径集成测试（不需 core）**

```
python3 -m pytest tests/integration/sdk/test_harness_failure.py -v
```

预期：全部 PASS

- [ ] **Step 3: 在 P3 已合入的环境跑全套集成测试**

```
SDK_INTEGRATION=1 python3 -m pytest tests/integration/sdk/ -v
SDK_E2E=1 SDK_INTEGRATION=1 python3 -m pytest tests/e2e/test_sdk_minimal_smoke.py -v
```

预期：全部 PASS（若失败按照具体错误回到对应 task 修复）

- [ ] **Step 4: 检查公开 API 完整性**

确认 `from sensenova_claw.sdk import ...` 能拿到：`Harness`、`query`、`tool`、`create_sdk_mcp_server`、`HarnessError`、`ToolDef`、`McpServer`。可手动跑：

```
python3 -c "from sensenova_claw.sdk import Harness, query, tool, create_sdk_mcp_server, HarnessError, ToolDef, McpServer; print('ok')"
```

预期：输出 `ok`

- [ ] **Step 5: 提交（如有调整）**

```
git status
# 如有调整：
git add -p
git commit -m "test(sdk): final P4 verification pass"
```

---

## 自检清单（写完后跑一遍）

- [ ] **Spec 覆盖**：
  - decomposition §3.5 wire 格式 → Task 3 实现
  - spec §5.2 handshake → Task 9
  - spec §5.3 session/turn/event domain → Task 9 + Task 11
  - spec §5.3 permission domain → Task 6 + Task 10
  - spec §5.3 mcp.register_server / mcp.invoke → Task 5 + Task 10
  - spec §5.4 错误码 → Task 2
  - spec §5.6 进程生命周期 (stdin EOF / SIGTERM / SIGKILL) → Task 4 `aclose`
  - spec §6.2 Path C in-process MCP → Task 5 + Task 10
  - decomposition §3.4 Identity 占位 → Task 7 `_default_identity()`

- [ ] **占位检查**：
  - 没有 "TBD" / "implement later"
  - 所有代码片段都是可直接复制粘贴的
  - 所有引用的类名/方法名前后一致（`Harness`、`Request`、`Response`、`Notification`、`StdioTransport`、`McpServer`、`ToolDef`、`PermissionDecision`、`PermissionRequest`、`error_from_code`）

- [ ] **类型一致性**：
  - `Request.id` 类型 `int | str` 在 protocol 和 client 中保持一致
  - `Notification.params` 默认 `{}`，编解码相符
  - `EventEnvelope` 在 SDK 中以 `dict` 表示（不重新定义类，与 spec 一致：协议 envelope 透传）
  - `tool` 装饰器返回 `ToolDef`，`create_sdk_mcp_server` 返回 `McpServer`

- [ ] **公开 API 暴露完整**：
  - `Harness`、`query`、`tool`、`create_sdk_mcp_server`、`HarnessError`、`ToolDef`、`McpServer`

- [ ] **示例**：
  - `examples/sdk_minimal.py` 30 行内
  - `examples/sdk_inprocess_tool.py` 端到端覆盖 @tool + create_sdk_mcp_server + Harness(mcp_servers=…)

- [ ] **测试覆盖**：
  - 单元：protocol 编解码、transport 读写、错误映射、@tool 元数据收集、Harness 生命周期、RPC 发送/接收/超时、handshake、反向 RPC、query
  - 集成：真子进程握手、真 turn、in-process MCP 注册
  - 失败：命令不存在、子进程崩溃、卡死
  - smoke：examples/sdk_minimal.py 跑通

如自检发现遗漏：直接回到对应 task 修补，无需重新自检。
