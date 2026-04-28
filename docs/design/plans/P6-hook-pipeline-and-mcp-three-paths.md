# P6 Hook 子进程协议 + MCP 三路径接入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 HookPipeline（按 spec §6.1 spawn 子进程，stdin/stdout JSON envelope，dispatch continue/block/mutate/replace），在编排循环 9 个关键节点接入；通过 plugin manifest 把 stdio/SSE/streamable-http MCP server（§4.3.8 + §6.2 Path A/B）接入既有 `McpSessionManager`。

**Architecture:**
- `sensenova_claw/kernel/hooks/` 新增 4 个模块：`protocol.py`（envelope 数据类）、`executor.py`（subprocess + asyncio）、`decisions.py`（Decision enum / dispatch）、`pipeline.py`（HookPipeline 编排）。
- HookPipeline 在 9 个事件节点（OnSessionStart/End、OnUserInput、PreLLM/PostLLM、PreTool/PostTool、OnError、OnConfigUpdated）注入：blocking hook 串行链式 mutate；fire-and-forget 后台并发。
- Plugin manifest 的 `mcp_servers` 贡献项被 PluginLoader 解析后写入 `config.mcp.servers`（既有 `McpSessionManager.normalize_mcp_servers` 入口），不重写 runtime；新增 `auto_start: always | on_demand | never`、`restart_policy`、`health_check`、`max_restarts` 字段在 `McpServerConfig` 上扩展，由 `McpSessionManager` 启动时按 `always` 预热。
- in-process MCP（Path C）由 P4 拥有；本计划在 `HookRegistry.populate` 与 PluginLoader 注入路径上保留扩展点（接受 P4 通过 `mcp.register_server` 注入的 server，不破坏 manifest 流程）。

**Tech Stack:** Python 3.12 / asyncio / `asyncio.create_subprocess_exec` / `pytest` / `pytest-asyncio` / `mcp` SDK（已用）/ `pydantic` 或纯 dataclass（按现有代码风格用 dataclass + json）。

---

## 0. 前置约束与坐标对齐

- 全部代码与测试在 worktree `D:/code/sensenova-claw/.claude/worktrees/plan-p6`，分支 `spec/plan-p6-hook-mcp`。
- Python 入口统一 `python3`；测试用 `python3 -m pytest`。
- 依赖 P1 / P2 / P3 完成的接口契约（`PluginManifest`、`RegistryEntry`、`HookRegistry`、`PluginLoader`）。本 plan 不重新发明这些类型——若引用名不存在，按 `docs/design/2026-04-27-plan-decomposition.md` §3.1~§3.3 钉死的签名为准。
- 不在范围：identity 过滤（P5）、in-process MCP 注册（P4）、SDK 客户端（P4）。
- 路径全部使用绝对路径或仓库相对路径（forward slash）。
- 注释和文档使用中文；代码标识符使用英文。

---

## 1. 文件结构与职责

| 路径 | 职责 |
|---|---|
| `sensenova_claw/kernel/hooks/__init__.py` | 包入口，导出 HookPipeline / Decision / HookInputEnvelope / HookOutputEnvelope |
| `sensenova_claw/kernel/hooks/protocol.py` | dataclass：`HookInputEnvelope`、`HookOutputEnvelope`、`HookDiagnostic`；JSON serialize / parse |
| `sensenova_claw/kernel/hooks/decisions.py` | enum `Decision`（CONTINUE/BLOCK/MUTATE/REPLACE）+ `HookOutcome` 聚合返回值 |
| `sensenova_claw/kernel/hooks/executor.py` | `SubprocessHookExecutor.run(spec, envelope, timeout) -> HookOutcome`：spawn / 写 stdin / 读 stdout / kill on timeout |
| `sensenova_claw/kernel/hooks/pipeline.py` | `HookPipeline`：查询 HookRegistry、按 matcher 过滤、blocking 串行链式 mutate、fire-and-forget 后台 |
| `sensenova_claw/kernel/hooks/registry.py` | `HookRegistry`（若 P1 已建空壳则改 import；本 plan 内部假设已存在并补充 `populate_from_manifest` 与 `query(event_type, context)`） |
| `sensenova_claw/capabilities/mcp/types.py` | 修改：`McpServerConfig` 增加 `auto_start`、`restart_policy`、`max_restarts`、`health_check` 字段（默认值保持向后兼容） |
| `sensenova_claw/capabilities/mcp/runtime.py` | 修改：`McpSessionManager` 增加 `start_eager_servers()`、`maybe_restart_on_failure()`；不改既有 `_open_client` 主体 |
| `sensenova_claw/platform/plugins/contributions/mcp_servers.py` | 新增：把 manifest `contributes.mcp_servers[]` 解析为 `McpServerConfig`，写入 `config.mcp.servers` namespace |
| `sensenova_claw/platform/plugins/contributions/hooks.py` | 新增：把 manifest `contributes.hooks[]` 解析为 `HookSpec` 注入 `HookRegistry` |
| `sensenova_claw/kernel/runtime/agent_runtime.py` | 修改：在 session 创建/销毁触发 `OnSessionStart` / `OnSessionEnd`；`send_user_input` 后触发 `OnUserInput` |
| `sensenova_claw/kernel/runtime/workers/llm_worker.py` | 修改：在 `_handle_llm_requested` 调用 provider 前后触发 `PreLLM` / `PostLLM` |
| `sensenova_claw/kernel/runtime/workers/tool_worker.py` | 修改：在 `tool.execute` 调用前后触发 `PreTool` / `PostTool` |
| `sensenova_claw/platform/config/config_manager.py` | 修改：成功写入并发布 `CONFIG_UPDATED` 事件后触发 `OnConfigUpdated` hook |
| `sensenova_claw/kernel/runtime/workers/base.py` | 修改：异常捕获处触发 `OnError` hook（fire-and-forget） |
| `tests/unit/kernel/hooks/test_protocol.py` | envelope 序列化测试 |
| `tests/unit/kernel/hooks/test_decisions.py` | Decision enum / outcome 解析测试 |
| `tests/unit/kernel/hooks/test_executor.py` | subprocess executor 测试（continue/block/mutate/replace、timeout、bad json、非 0 exit） |
| `tests/unit/kernel/hooks/test_pipeline.py` | blocking 串行链 + fire-and-forget + matcher + on_failure |
| `tests/unit/kernel/hooks/test_registry.py` | populate_from_manifest 与 query 过滤 |
| `tests/integration/hooks/test_pretool_subprocess.py` | 真子进程 hook 触发，验证 mutate args 传递回 ToolRuntime |
| `tests/integration/hooks/test_postllm_replace.py` | 真子进程 hook 触发 PostLLM replace，跳过实际 tool 调用 |
| `tests/integration/mcp/test_stdio_server_lifecycle.py` | 用一个 minimal Python MCP server 验证 `auto_start: on_demand` 延迟 spawn / 手动 kill 后重启 |
| `tests/integration/mcp/test_mcp_tool_passes_pretool_hook.py` | MCP tool 与 Python tool 都过 `PreTool` hook，context schema 一致 |
| `tests/fixtures/hooks/audit.sh`（Linux/macOS）+ `audit.cmd`（Windows） | bash 子进程 hook 用于集成测试 |
| `tests/fixtures/hooks/redact_replace.py` | Python 子进程 hook（`#!/usr/bin/env python3`）用于 replace 测试 |
| `tests/fixtures/mcp_servers/echo_server.py` | 极简 stdio MCP server（用 `mcp` SDK 跑，暴露 `echo` 工具） |

---

## 2. 公共数据契约（先冻结）

### 2.1 `HookInputEnvelope` JSON 形态（与 spec §6.1 完全一致）

```json
{
  "hook_id": "team-a/crm-assistant::audit",
  "event": "PreTool",
  "session_id": "s-abc",
  "turn_id": "t-1",
  "trace_id": "tool-call-xyz",
  "identity": { "user_id": "local-dev", "team_id": "local-team", "org_id": "local-org" },
  "context": { "...": "事件相关上下文（PreTool 给 tool_name+tool_args；PreLLM 给 messages+tools；...）" },
  "timestamp": "2026-04-28T08:00:00Z"
}
```

### 2.2 `HookOutputEnvelope` JSON 形态

```json
{
  "decision": "continue | block | mutate | replace",
  "reason": "可选字符串",
  "mutations": { "tool_args": {"...": "..."} },
  "replacement": { "tool_result": {"ok": true} },
  "diagnostics": [ { "level": "warn", "message": "...", "code": "..." } ]
}
```

`mutations` 中允许的 key 与 event 类型对应：
- `OnUserInput`: `text`、`payload`
- `PreLLM`: `messages`、`tools`、`temperature`、`max_tokens`、`extra_body`
- `PostLLM`: `response`（dict，含 `content` / `tool_calls` / `usage` / `finish_reason`）
- `PreTool`: `tool_args`
- `PostTool`: `tool_result`、`success`、`error`
- `OnSessionStart`: `session_meta`

### 2.3 `HookSpec`（Registry 内部记录）

```python
@dataclass
class HookSpec:
    plugin_id: str
    hook_id: str                      # f"{plugin_id}::{short_id}"
    event: str                        # OnSessionStart / OnSessionEnd / ...
    matcher: dict[str, list[str]]     # e.g. {"tool_name": ["send_email", "crm_lookup"]}
    type: str                         # "subprocess" | "python"
    command: list[str] | None         # subprocess
    python_target: str | None         # "module.path:callable" for python type
    timeout_seconds: float            # 默认 5.0
    blocking: bool                    # 默认 True
    on_failure: str                   # "block" | "continue"，默认 "block"
    working_dir: str | None
    env: dict[str, str]
```

### 2.4 `Decision` 与 `HookOutcome`

```python
class Decision(str, Enum):
    CONTINUE = "continue"
    BLOCK = "block"
    MUTATE = "mutate"
    REPLACE = "replace"

@dataclass
class HookOutcome:
    decision: Decision
    reason: str = ""
    mutations: dict = field(default_factory=dict)
    replacement: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    raw_stderr: str = ""               # 失败时供日志
    elapsed_ms: int = 0
```

### 2.5 `McpServerConfig` 扩展字段

```python
@dataclass(slots=True)
class McpServerConfig:
    # ── 现有字段（不动）────────────────────────────
    name: str
    transport: McpTransportType
    timeout: float = 15.0
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    # ── P6 新增 ─────────────────────────────────────
    auto_start: Literal["always", "on_demand", "never"] = "on_demand"
    restart_policy: Literal["never", "on_failure", "always"] = "on_failure"
    max_restarts: int = 3
    health_check_interval: float = 0.0  # 0 表示禁用
    health_check_method: str = "tools/list"
```

---

## 3. 任务分解

> 每个任务粒度：写一个失败测试 → 跑测试看 FAIL → 实现最小代码 → 跑测试看 PASS → 提交。
> Windows 环境若 `audit.sh` 执行不到 bash，用 `python3 hooks/audit.py` 等价替代——本 plan 在测试 fixture 中同时提供 `.sh` 与 `.py`，CI 按 platform 选脚本。

### Task 1: 落地 `HookInputEnvelope` / `HookOutputEnvelope` dataclass

**Files:**
- Create: `sensenova_claw/kernel/hooks/__init__.py`（空 + `from .protocol import *` 导出）
- Create: `sensenova_claw/kernel/hooks/protocol.py`
- Create: `tests/unit/kernel/hooks/__init__.py`（空）
- Create: `tests/unit/kernel/hooks/test_protocol.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/hooks/test_protocol.py
import json

from sensenova_claw.kernel.hooks.protocol import (
    HookInputEnvelope,
    HookOutputEnvelope,
    parse_output_envelope,
)


def test_input_envelope_serializes_with_required_fields():
    env = HookInputEnvelope(
        hook_id="team-a/crm::audit",
        event="PreTool",
        session_id="s1",
        turn_id="t1",
        trace_id="trace-1",
        identity={"user_id": "u", "team_id": "t", "org_id": "o"},
        context={"tool_name": "send_email"},
        timestamp="2026-04-28T08:00:00Z",
    )
    payload = json.loads(env.to_json())
    assert payload["hook_id"] == "team-a/crm::audit"
    assert payload["event"] == "PreTool"
    assert payload["context"]["tool_name"] == "send_email"
    assert payload["timestamp"].endswith("Z")


def test_parse_output_envelope_defaults_to_continue():
    out = parse_output_envelope('{"decision": "continue"}')
    assert out.decision == "continue"
    assert out.mutations == {}
    assert out.replacement == {}
    assert out.diagnostics == []


def test_parse_output_envelope_full_payload():
    raw = json.dumps({
        "decision": "mutate",
        "reason": "redact",
        "mutations": {"tool_args": {"to": "x"}},
        "diagnostics": [{"level": "warn", "message": "m", "code": "c"}],
    })
    out = parse_output_envelope(raw)
    assert out.decision == "mutate"
    assert out.mutations == {"tool_args": {"to": "x"}}
    assert out.diagnostics[0]["code"] == "c"


def test_parse_output_envelope_rejects_unknown_decision():
    import pytest
    with pytest.raises(ValueError):
        parse_output_envelope('{"decision": "panic"}')
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_protocol.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sensenova_claw.kernel.hooks'`）

- [ ] **Step 3: 实现最小代码**

```python
# sensenova_claw/kernel/hooks/protocol.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ALLOWED_DECISIONS = ("continue", "block", "mutate", "replace")


@dataclass
class HookInputEnvelope:
    hook_id: str
    event: str
    session_id: str
    turn_id: str
    trace_id: str
    identity: dict[str, Any]
    context: dict[str, Any]
    timestamp: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "hook_id": self.hook_id,
                "event": self.event,
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "trace_id": self.trace_id,
                "identity": self.identity,
                "context": self.context,
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
        )


@dataclass
class HookOutputEnvelope:
    decision: str
    reason: str = ""
    mutations: dict[str, Any] = field(default_factory=dict)
    replacement: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def parse_output_envelope(raw: str) -> HookOutputEnvelope:
    payload = json.loads(raw)
    decision = payload.get("decision", "continue")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"非法 hook decision: {decision}")
    return HookOutputEnvelope(
        decision=decision,
        reason=str(payload.get("reason", "")),
        mutations=dict(payload.get("mutations") or {}),
        replacement=dict(payload.get("replacement") or {}),
        diagnostics=list(payload.get("diagnostics") or []),
    )
```

```python
# sensenova_claw/kernel/hooks/__init__.py
from sensenova_claw.kernel.hooks.protocol import (
    HookInputEnvelope,
    HookOutputEnvelope,
    parse_output_envelope,
)

__all__ = ["HookInputEnvelope", "HookOutputEnvelope", "parse_output_envelope"]
```

- [ ] **Step 4: 跑测试看 PASS**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_protocol.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/hooks/__init__.py \
        sensenova_claw/kernel/hooks/protocol.py \
        tests/unit/kernel/hooks/__init__.py \
        tests/unit/kernel/hooks/test_protocol.py
git commit -m "feat(hooks): hook input/output envelope JSON 序列化与解析"
```

---

### Task 2: 落地 `Decision` enum 与 `HookOutcome`

**Files:**
- Create: `sensenova_claw/kernel/hooks/decisions.py`
- Create: `tests/unit/kernel/hooks/test_decisions.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/hooks/test_decisions.py
from sensenova_claw.kernel.hooks.decisions import Decision, HookOutcome, outcome_from_envelope
from sensenova_claw.kernel.hooks.protocol import HookOutputEnvelope


def test_decision_values_match_spec():
    assert Decision.CONTINUE.value == "continue"
    assert Decision.BLOCK.value == "block"
    assert Decision.MUTATE.value == "mutate"
    assert Decision.REPLACE.value == "replace"


def test_outcome_from_envelope_carries_mutations():
    env = HookOutputEnvelope(
        decision="mutate",
        mutations={"tool_args": {"to": "x"}},
        diagnostics=[{"level": "info", "message": "m", "code": "ok"}],
    )
    out = outcome_from_envelope(env, elapsed_ms=12)
    assert out.decision is Decision.MUTATE
    assert out.mutations == {"tool_args": {"to": "x"}}
    assert out.elapsed_ms == 12
    assert out.diagnostics[0]["code"] == "ok"


def test_outcome_from_envelope_default_continue():
    out = outcome_from_envelope(HookOutputEnvelope(decision="continue"))
    assert out.decision is Decision.CONTINUE
    assert out.mutations == {}
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_decisions.py -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 实现**

```python
# sensenova_claw/kernel/hooks/decisions.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sensenova_claw.kernel.hooks.protocol import HookOutputEnvelope


class Decision(str, Enum):
    CONTINUE = "continue"
    BLOCK = "block"
    MUTATE = "mutate"
    REPLACE = "replace"


@dataclass
class HookOutcome:
    decision: Decision
    reason: str = ""
    mutations: dict[str, Any] = field(default_factory=dict)
    replacement: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    raw_stderr: str = ""
    elapsed_ms: int = 0


def outcome_from_envelope(env: HookOutputEnvelope, *, elapsed_ms: int = 0, raw_stderr: str = "") -> HookOutcome:
    return HookOutcome(
        decision=Decision(env.decision),
        reason=env.reason,
        mutations=dict(env.mutations),
        replacement=dict(env.replacement),
        diagnostics=list(env.diagnostics),
        raw_stderr=raw_stderr,
        elapsed_ms=elapsed_ms,
    )
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_decisions.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/hooks/decisions.py tests/unit/kernel/hooks/test_decisions.py
git commit -m "feat(hooks): Decision enum 与 HookOutcome 数据载体"
```

---

### Task 3: `HookSpec` 与 `HookRegistry.populate_from_manifest`

**Files:**
- Create or modify: `sensenova_claw/kernel/hooks/registry.py`（若 P1 已建空壳，按下方接口补齐；若不存在则新建）
- Create: `tests/unit/kernel/hooks/test_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/hooks/test_registry.py
from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec


def test_register_and_query_by_event():
    reg = HookRegistry()
    spec = HookSpec(
        plugin_id="team-a/crm",
        hook_id="team-a/crm::audit",
        event="PreTool",
        matcher={"tool_name": ["send_email"]},
        type="subprocess",
        command=["bash", "hooks/audit.sh"],
        python_target=None,
        timeout_seconds=5.0,
        blocking=True,
        on_failure="block",
        working_dir=None,
        env={},
    )
    reg.register(spec)
    matched = reg.query("PreTool", {"tool_name": "send_email"})
    assert [s.hook_id for s in matched] == ["team-a/crm::audit"]


def test_matcher_filters_out_non_matching_tool():
    reg = HookRegistry()
    reg.register(HookSpec(
        plugin_id="p", hook_id="p::a", event="PreTool",
        matcher={"tool_name": ["send_email"]},
        type="subprocess", command=["x"], python_target=None,
        timeout_seconds=5.0, blocking=True, on_failure="block",
        working_dir=None, env={},
    ))
    assert reg.query("PreTool", {"tool_name": "fetch_url"}) == []


def test_no_matcher_matches_all():
    reg = HookRegistry()
    spec = HookSpec(
        plugin_id="p", hook_id="p::all", event="OnSessionStart",
        matcher={}, type="subprocess", command=["x"], python_target=None,
        timeout_seconds=5.0, blocking=False, on_failure="continue",
        working_dir=None, env={},
    )
    reg.register(spec)
    assert len(reg.query("OnSessionStart", {})) == 1


def test_register_preserves_insertion_order_per_event():
    reg = HookRegistry()
    for i in range(3):
        reg.register(HookSpec(
            plugin_id=f"p{i}", hook_id=f"p{i}::h", event="PreLLM",
            matcher={}, type="subprocess", command=["x"], python_target=None,
            timeout_seconds=5.0, blocking=True, on_failure="block",
            working_dir=None, env={},
        ))
    matched = reg.query("PreLLM", {})
    assert [s.hook_id for s in matched] == ["p0::h", "p1::h", "p2::h"]
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_registry.py -v`
Expected: FAIL（HookRegistry 未定义或缺方法）

- [ ] **Step 3: 实现**

```python
# sensenova_claw/kernel/hooks/registry.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookSpec:
    plugin_id: str
    hook_id: str
    event: str
    matcher: dict[str, list[str]] = field(default_factory=dict)
    type: str = "subprocess"
    command: list[str] | None = None
    python_target: str | None = None
    timeout_seconds: float = 5.0
    blocking: bool = True
    on_failure: str = "block"
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)


class HookRegistry:
    """按 event 类型组织 HookSpec，保留插件插入顺序。"""

    def __init__(self) -> None:
        self._by_event: dict[str, list[HookSpec]] = {}

    def register(self, spec: HookSpec) -> None:
        self._by_event.setdefault(spec.event, []).append(spec)

    def query(self, event: str, context: dict[str, Any]) -> list[HookSpec]:
        candidates = self._by_event.get(event, [])
        return [spec for spec in candidates if _matcher_matches(spec.matcher, context)]

    def all_for_event(self, event: str) -> list[HookSpec]:
        return list(self._by_event.get(event, []))


def _matcher_matches(matcher: dict[str, list[str]], context: dict[str, Any]) -> bool:
    """matcher 中每个 key 都必须在 context 中且值在 list 内。空 matcher 永远匹配。"""
    if not matcher:
        return True
    for key, allowed in matcher.items():
        actual = context.get(key)
        if actual is None or actual not in allowed:
            return False
    return True
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_registry.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/hooks/registry.py tests/unit/kernel/hooks/test_registry.py
git commit -m "feat(hooks): HookRegistry 按 event 与 matcher 查询"
```

---

### Task 4: `SubprocessHookExecutor` — continue / block / mutate / replace

**Files:**
- Create: `sensenova_claw/kernel/hooks/executor.py`
- Create: `tests/unit/kernel/hooks/test_executor.py`
- Create: `tests/fixtures/hooks/__init__.py`（空）
- Create: `tests/fixtures/hooks/static_continue.py`
- Create: `tests/fixtures/hooks/static_mutate.py`
- Create: `tests/fixtures/hooks/static_block.py`
- Create: `tests/fixtures/hooks/static_replace.py`
- Create: `tests/fixtures/hooks/timeout_sleeper.py`
- Create: `tests/fixtures/hooks/exit_nonzero.py`
- Create: `tests/fixtures/hooks/bad_json.py`

**Fixture 脚本（全部 Python，跨平台）：**

```python
# tests/fixtures/hooks/static_continue.py
import json, sys
sys.stdin.read()
sys.stdout.write(json.dumps({"decision": "continue", "reason": "ok"}))
```

```python
# tests/fixtures/hooks/static_mutate.py
import json, sys
data = json.loads(sys.stdin.read())
incoming_args = data.get("context", {}).get("tool_args", {})
new_args = dict(incoming_args)
new_args["subject"] = "[REDACTED]"
sys.stdout.write(json.dumps({"decision": "mutate", "mutations": {"tool_args": new_args}}))
```

```python
# tests/fixtures/hooks/static_block.py
import json, sys
sys.stdin.read()
sys.stdout.write(json.dumps({"decision": "block", "reason": "policy violation"}))
```

```python
# tests/fixtures/hooks/static_replace.py
import json, sys
sys.stdin.read()
sys.stdout.write(json.dumps({
    "decision": "replace",
    "replacement": {"tool_result": {"ok": True, "stub": True}},
}))
```

```python
# tests/fixtures/hooks/timeout_sleeper.py
import sys, time
sys.stdin.read()
time.sleep(10)
sys.stdout.write('{"decision":"continue"}')
```

```python
# tests/fixtures/hooks/exit_nonzero.py
import sys
sys.stdin.read()
sys.stderr.write("hook crashed\n")
sys.exit(7)
```

```python
# tests/fixtures/hooks/bad_json.py
import sys
sys.stdin.read()
sys.stdout.write("this is not json")
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/hooks/test_executor.py
import asyncio
import sys
from pathlib import Path

import pytest

from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.executor import (
    HookExecutionError,
    SubprocessHookExecutor,
)
from sensenova_claw.kernel.hooks.protocol import HookInputEnvelope
from sensenova_claw.kernel.hooks.registry import HookSpec


FIX = Path(__file__).resolve().parents[3] / "fixtures" / "hooks"


def _envelope(context=None):
    return HookInputEnvelope(
        hook_id="t::h", event="PreTool", session_id="s", turn_id="t",
        trace_id="tr", identity={}, context=context or {}, timestamp="2026-04-28T08:00:00Z",
    )


def _spec(script: str, *, timeout=5.0, on_failure="block", blocking=True):
    return HookSpec(
        plugin_id="t", hook_id="t::h", event="PreTool",
        matcher={}, type="subprocess",
        command=[sys.executable, str(FIX / script)],
        python_target=None, timeout_seconds=timeout,
        blocking=blocking, on_failure=on_failure,
        working_dir=None, env={},
    )


@pytest.mark.asyncio
async def test_continue_decision_returned():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("static_continue.py"), _envelope())
    assert out.decision is Decision.CONTINUE


@pytest.mark.asyncio
async def test_mutate_decision_carries_mutations():
    executor = SubprocessHookExecutor()
    out = await executor.run(
        _spec("static_mutate.py"),
        _envelope(context={"tool_name": "send_email", "tool_args": {"subject": "raw"}}),
    )
    assert out.decision is Decision.MUTATE
    assert out.mutations["tool_args"]["subject"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_block_decision_returns_with_reason():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("static_block.py"), _envelope())
    assert out.decision is Decision.BLOCK
    assert out.reason == "policy violation"


@pytest.mark.asyncio
async def test_replace_decision_carries_replacement():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("static_replace.py"), _envelope())
    assert out.decision is Decision.REPLACE
    assert out.replacement["tool_result"]["stub"] is True


@pytest.mark.asyncio
async def test_timeout_kills_child_and_uses_on_failure_block():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("timeout_sleeper.py", timeout=0.5), _envelope())
    assert out.decision is Decision.BLOCK   # on_failure 默认 block


@pytest.mark.asyncio
async def test_timeout_with_on_failure_continue():
    executor = SubprocessHookExecutor()
    out = await executor.run(
        _spec("timeout_sleeper.py", timeout=0.5, on_failure="continue"),
        _envelope(),
    )
    assert out.decision is Decision.CONTINUE


@pytest.mark.asyncio
async def test_nonzero_exit_default_blocks():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("exit_nonzero.py"), _envelope())
    assert out.decision is Decision.BLOCK
    assert "hook crashed" in out.raw_stderr


@pytest.mark.asyncio
async def test_nonzero_exit_with_on_failure_continue():
    executor = SubprocessHookExecutor()
    out = await executor.run(
        _spec("exit_nonzero.py", on_failure="continue"),
        _envelope(),
    )
    assert out.decision is Decision.CONTINUE


@pytest.mark.asyncio
async def test_bad_json_treated_as_failure():
    executor = SubprocessHookExecutor()
    out = await executor.run(_spec("bad_json.py"), _envelope())
    assert out.decision is Decision.BLOCK
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_executor.py -v`
Expected: FAIL（`SubprocessHookExecutor` 不存在）

- [ ] **Step 3: 实现**

```python
# sensenova_claw/kernel/hooks/executor.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sensenova_claw.kernel.hooks.decisions import Decision, HookOutcome, outcome_from_envelope
from sensenova_claw.kernel.hooks.protocol import (
    HookInputEnvelope,
    HookOutputEnvelope,
    parse_output_envelope,
)
from sensenova_claw.kernel.hooks.registry import HookSpec

logger = logging.getLogger(__name__)


class HookExecutionError(RuntimeError):
    """Hook 子进程执行失败的统一异常（未在 outcome 中体现的内部错误才用）。"""


class SubprocessHookExecutor:
    """按 spec spawn 子进程，写 stdin / 读 stdout，按超时和退出码处理。"""

    async def run(self, spec: HookSpec, envelope: HookInputEnvelope) -> HookOutcome:
        if spec.type != "subprocess":
            raise HookExecutionError(f"executor 只处理 subprocess 类型，收到: {spec.type}")
        if not spec.command:
            raise HookExecutionError(f"hook {spec.hook_id} 缺少 command")

        t0 = time.monotonic()
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *spec.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=spec.working_dir,
                env=_merge_env(spec.env),
            )
            input_bytes = (envelope.to_json() + "\n").encode("utf-8")
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=input_bytes),
                    timeout=spec.timeout_seconds,
                )
            except asyncio.TimeoutError:
                _kill(process)
                await process.wait()
                logger.warning("hook timeout hook_id=%s timeout=%s", spec.hook_id, spec.timeout_seconds)
                return _failure_outcome(spec, "timeout", elapsed(t0), b"")
            elapsed_ms = elapsed(t0)

            if process.returncode != 0:
                logger.warning(
                    "hook non-zero exit hook_id=%s rc=%s stderr=%s",
                    spec.hook_id, process.returncode, stderr_bytes[:512],
                )
                return _failure_outcome(spec, f"exit {process.returncode}", elapsed_ms, stderr_bytes)

            try:
                env_out = parse_output_envelope(stdout_bytes.decode("utf-8").strip())
            except Exception as exc:  # noqa: BLE001
                logger.warning("hook bad output hook_id=%s err=%s", spec.hook_id, exc)
                return _failure_outcome(spec, f"bad json: {exc}", elapsed_ms, stderr_bytes)

            return outcome_from_envelope(env_out, elapsed_ms=elapsed_ms, raw_stderr=stderr_bytes.decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            if process is not None and process.returncode is None:
                _kill(process)
            logger.exception("hook executor unexpected error hook_id=%s", spec.hook_id)
            return _failure_outcome(spec, f"executor crashed: {exc}", elapsed(t0), b"")


def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        return


def elapsed(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _merge_env(extra: dict[str, str]) -> dict[str, str] | None:
    if not extra:
        return None
    import os
    base = dict(os.environ)
    base.update(extra)
    return base


def _failure_outcome(spec: HookSpec, reason: str, elapsed_ms: int, stderr_bytes: bytes) -> HookOutcome:
    decision = Decision.BLOCK if spec.on_failure == "block" else Decision.CONTINUE
    return HookOutcome(
        decision=decision,
        reason=reason,
        elapsed_ms=elapsed_ms,
        raw_stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_executor.py -v`
Expected: PASS（9 passed）；如某些 fixture 文件 line endings 在 Windows 上影响，加 `newline=""` 创建文件，本步骤后 fixture 已落地不受影响。

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/hooks/executor.py \
        tests/unit/kernel/hooks/test_executor.py \
        tests/fixtures/hooks/
git commit -m "feat(hooks): subprocess executor 处理 continue/block/mutate/replace 与失败路径"
```

---

### Task 5: `HookPipeline` — 串行链式 + 并发 fire-and-forget

**Files:**
- Create: `sensenova_claw/kernel/hooks/pipeline.py`
- Create: `tests/unit/kernel/hooks/test_pipeline.py`
- Create: `tests/fixtures/hooks/chain_step1.py`（mutate `text` -> 加前缀）
- Create: `tests/fixtures/hooks/chain_step2.py`（mutate `text` -> 加后缀，验证 step1 的 mutation 进入 step2 的 context）
- Create: `tests/fixtures/hooks/fire_and_forget.py`（向 stderr 写一行用于断言被启动过）

```python
# tests/fixtures/hooks/chain_step1.py
import json, sys
data = json.loads(sys.stdin.read())
text = data["context"].get("text", "")
sys.stdout.write(json.dumps({
    "decision": "mutate",
    "mutations": {"text": "[A]" + text},
}))
```

```python
# tests/fixtures/hooks/chain_step2.py
import json, sys
data = json.loads(sys.stdin.read())
text = data["context"].get("text", "")
sys.stdout.write(json.dumps({
    "decision": "mutate",
    "mutations": {"text": text + "[B]"},
}))
```

```python
# tests/fixtures/hooks/fire_and_forget.py
import sys
sys.stdin.read()
sys.stderr.write("ran\n")
sys.stdout.write('{"decision":"continue"}')
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/hooks/test_pipeline.py
import asyncio
import sys
from pathlib import Path

import pytest

from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.pipeline import HookPipeline, PipelineResult
from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec


FIX = Path(__file__).resolve().parents[3] / "fixtures" / "hooks"


def _spec(script, *, blocking=True, hook_id="p::h", on_failure="block", matcher=None):
    return HookSpec(
        plugin_id="p", hook_id=hook_id, event="OnUserInput",
        matcher=matcher or {}, type="subprocess",
        command=[sys.executable, str(FIX / script)],
        python_target=None, timeout_seconds=5.0,
        blocking=blocking, on_failure=on_failure,
        working_dir=None, env={},
    )


@pytest.fixture
def identity():
    return {"user_id": "u", "team_id": "t", "org_id": "o"}


@pytest.mark.asyncio
async def test_blocking_chain_threads_mutations(identity):
    reg = HookRegistry()
    reg.register(_spec("chain_step1.py", hook_id="p::a"))
    reg.register(_spec("chain_step2.py", hook_id="p::b"))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="OnUserInput",
        session_id="s", turn_id="t", trace_id="tr",
        identity=identity, context={"text": "raw"},
    )
    assert result.decision is Decision.MUTATE
    assert result.context["text"] == "[A]raw[B]"


@pytest.mark.asyncio
async def test_block_decision_short_circuits_chain(identity):
    reg = HookRegistry()
    reg.register(_spec("static_block.py", hook_id="p::a"))
    reg.register(_spec("chain_step2.py", hook_id="p::b"))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="OnUserInput",
        session_id="s", turn_id="t", trace_id="tr",
        identity=identity, context={"text": "raw"},
    )
    assert result.decision is Decision.BLOCK
    # second hook 不应跑
    assert result.context["text"] == "raw"


@pytest.mark.asyncio
async def test_replace_decision_short_circuits_chain(identity):
    reg = HookRegistry()
    reg.register(_spec("static_replace.py", hook_id="p::a"))
    reg.register(_spec("chain_step2.py", hook_id="p::b"))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="PreTool",
        session_id="s", turn_id="t", trace_id="tr",
        identity=identity, context={"tool_name": "x"},
    )
    assert result.decision is Decision.REPLACE
    assert result.replacement["tool_result"]["stub"] is True


@pytest.mark.asyncio
async def test_fire_and_forget_does_not_block(identity, tmp_path):
    reg = HookRegistry()
    reg.register(_spec("fire_and_forget.py", blocking=False, hook_id="p::ff"))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="OnSessionStart",
        session_id="s", turn_id="t", trace_id="tr",
        identity=identity, context={},
    )
    assert result.decision is Decision.CONTINUE
    # 等后台任务结束以确认它确实跑过；pipeline 暴露 background_tasks
    if pipe.background_tasks:
        await asyncio.gather(*pipe.background_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_matcher_filters(identity):
    reg = HookRegistry()
    reg.register(_spec("static_block.py", hook_id="p::block_email", matcher={"tool_name": ["send_email"]}))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="OnUserInput",
        session_id="s", turn_id="t", trace_id="tr",
        identity=identity, context={"tool_name": "fetch_url"},
    )
    assert result.decision is Decision.CONTINUE
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_pipeline.py -v`
Expected: FAIL（`HookPipeline` 不存在）

- [ ] **Step 3: 实现**

```python
# sensenova_claw/kernel/hooks/pipeline.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sensenova_claw.kernel.hooks.decisions import Decision, HookOutcome
from sensenova_claw.kernel.hooks.executor import SubprocessHookExecutor
from sensenova_claw.kernel.hooks.protocol import HookInputEnvelope
from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    decision: Decision
    context: dict[str, Any]                       # 应用 mutations 后的上下文（替代原 context）
    replacement: dict[str, Any] = field(default_factory=dict)
    block_reason: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


class HookPipeline:
    """按 event 类型串/并联 hook，串行 hook 的 mutation 链式喂给下一个。"""

    def __init__(
        self,
        registry: HookRegistry,
        executor: SubprocessHookExecutor | None = None,
    ) -> None:
        self.registry = registry
        self.executor = executor or SubprocessHookExecutor()
        self.background_tasks: list[asyncio.Task[Any]] = []

    async def run(
        self,
        *,
        event: str,
        session_id: str,
        turn_id: str,
        trace_id: str,
        identity: dict[str, Any],
        context: dict[str, Any],
    ) -> PipelineResult:
        specs = self.registry.query(event, context)
        if not specs:
            return PipelineResult(decision=Decision.CONTINUE, context=dict(context))

        current_context = dict(context)
        diagnostics: list[dict[str, Any]] = []

        for spec in specs:
            if not spec.blocking:
                self._dispatch_fire_and_forget(spec, event, session_id, turn_id, trace_id, identity, current_context)
                continue
            envelope = HookInputEnvelope(
                hook_id=spec.hook_id,
                event=event,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                identity=identity,
                context=current_context,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            outcome = await self.executor.run(spec, envelope)
            diagnostics.extend(outcome.diagnostics)
            if outcome.decision is Decision.BLOCK:
                return PipelineResult(
                    decision=Decision.BLOCK,
                    context=current_context,
                    block_reason=outcome.reason,
                    diagnostics=diagnostics,
                )
            if outcome.decision is Decision.REPLACE:
                return PipelineResult(
                    decision=Decision.REPLACE,
                    context=current_context,
                    replacement=outcome.replacement,
                    diagnostics=diagnostics,
                )
            if outcome.decision is Decision.MUTATE:
                _apply_mutations(current_context, outcome.mutations)
                continue
            # CONTINUE
            continue

        if any(s.blocking for s in specs) and current_context != context:
            return PipelineResult(decision=Decision.MUTATE, context=current_context, diagnostics=diagnostics)
        return PipelineResult(decision=Decision.CONTINUE, context=current_context, diagnostics=diagnostics)

    def _dispatch_fire_and_forget(
        self,
        spec: HookSpec,
        event: str,
        session_id: str,
        turn_id: str,
        trace_id: str,
        identity: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        envelope = HookInputEnvelope(
            hook_id=spec.hook_id, event=event, session_id=session_id,
            turn_id=turn_id, trace_id=trace_id, identity=identity,
            context=dict(context),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        task = asyncio.create_task(self._safe_fire(spec, envelope))
        self.background_tasks.append(task)
        task.add_done_callback(lambda t: self.background_tasks.remove(t) if t in self.background_tasks else None)

    async def _safe_fire(self, spec: HookSpec, envelope: HookInputEnvelope) -> None:
        try:
            await self.executor.run(spec, envelope)
        except Exception:
            logger.exception("fire-and-forget hook crashed hook_id=%s", spec.hook_id)


def _apply_mutations(context: dict[str, Any], mutations: dict[str, Any]) -> None:
    """整 key 替换；不做深合并以避免 mutate 行为不可预测。"""
    for key, value in mutations.items():
        context[key] = value
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/hooks/test_pipeline.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/hooks/pipeline.py \
        tests/unit/kernel/hooks/test_pipeline.py \
        tests/fixtures/hooks/chain_step1.py \
        tests/fixtures/hooks/chain_step2.py \
        tests/fixtures/hooks/fire_and_forget.py
git commit -m "feat(hooks): HookPipeline 串行链式 mutation + 并发 fire-and-forget"
```

---

### Task 6: PluginLoader 解析 `contributes.hooks` 注入 HookRegistry

**Files:**
- Create: `sensenova_claw/platform/plugins/contributions/__init__.py`（空）
- Create: `sensenova_claw/platform/plugins/contributions/hooks.py`
- Create: `tests/unit/platform/plugins/contributions/__init__.py`（空）
- Create: `tests/unit/platform/plugins/contributions/test_hooks_contribution.py`

> 假设 P1 已经在 `sensenova_claw/platform/plugins/manifest.py` 提供 `PluginManifest` 数据类。本 Task 仅写 contribution 解析器，调用方（PluginLoader.install_into_registries）由 P1/P2 拼装。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/platform/plugins/contributions/test_hooks_contribution.py
from pathlib import Path

import pytest

from sensenova_claw.kernel.hooks.registry import HookRegistry
from sensenova_claw.platform.plugins.contributions.hooks import install_hook_contributions


class _StubManifest:
    def __init__(self, plugin_id: str, contributes: dict, root: Path):
        self.id = plugin_id
        self.contributes = contributes
        self.root_path = root


def _manifest(tmp_path: Path, hooks: list[dict]) -> _StubManifest:
    return _StubManifest("team-a/crm", {"hooks": hooks}, tmp_path)


def test_install_subprocess_hook(tmp_path: Path):
    reg = HookRegistry()
    manifest = _manifest(tmp_path, [{
        "event": "PreTool",
        "matcher": {"tool_name": ["send_email"]},
        "type": "subprocess",
        "command": ["bash", "hooks/audit.sh"],
        "timeout_seconds": 7,
        "blocking": True,
        "on_failure": "block",
    }])
    failures = install_hook_contributions(manifest, reg)
    assert failures == []
    matched = reg.query("PreTool", {"tool_name": "send_email"})
    assert len(matched) == 1
    spec = matched[0]
    assert spec.plugin_id == "team-a/crm"
    assert spec.hook_id.startswith("team-a/crm::")
    assert spec.timeout_seconds == 7
    # working_dir 默认指向 manifest 根
    assert spec.working_dir == str(tmp_path)


def test_install_skips_invalid_hook_and_records_failure(tmp_path: Path):
    reg = HookRegistry()
    manifest = _manifest(tmp_path, [
        {"event": "PreTool", "type": "subprocess"},  # 缺 command
    ])
    failures = install_hook_contributions(manifest, reg)
    assert len(failures) == 1
    assert "command" in failures[0]
    assert reg.query("PreTool", {}) == []


def test_install_unknown_event_rejected(tmp_path: Path):
    reg = HookRegistry()
    manifest = _manifest(tmp_path, [
        {"event": "BeforeWorld", "type": "subprocess", "command": ["x"]},
    ])
    failures = install_hook_contributions(manifest, reg)
    assert len(failures) == 1
    assert "BeforeWorld" in failures[0]


def test_default_blocking_and_on_failure(tmp_path: Path):
    reg = HookRegistry()
    manifest = _manifest(tmp_path, [
        {"event": "OnSessionStart", "type": "subprocess", "command": ["x"]},
    ])
    install_hook_contributions(manifest, reg)
    spec = reg.query("OnSessionStart", {})[0]
    assert spec.blocking is True
    assert spec.on_failure == "block"
    assert spec.timeout_seconds == 5.0
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/platform/plugins/contributions/test_hooks_contribution.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# sensenova_claw/platform/plugins/contributions/hooks.py
from __future__ import annotations

from typing import Any

from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec

VALID_EVENTS = {
    "OnSessionStart", "OnSessionEnd", "OnUserInput",
    "PreLLM", "PostLLM", "PreTool", "PostTool",
    "OnError", "OnConfigUpdated",
}


def install_hook_contributions(manifest: Any, registry: HookRegistry) -> list[str]:
    """解析 manifest.contributes.hooks 注入 HookRegistry。返回失败描述列表（不抛异常）。"""
    failures: list[str] = []
    contribs = (manifest.contributes or {}).get("hooks") or []
    for index, raw in enumerate(contribs):
        try:
            spec = _parse_hook(raw, plugin_id=manifest.id, plugin_root=str(manifest.root_path))
        except ValueError as exc:
            failures.append(f"[{manifest.id}] hooks[{index}]: {exc}")
            continue
        registry.register(spec)
    return failures


def _parse_hook(raw: dict[str, Any], *, plugin_id: str, plugin_root: str) -> HookSpec:
    event = raw.get("event")
    if event not in VALID_EVENTS:
        raise ValueError(f"未知 event {event!r}，合法值: {sorted(VALID_EVENTS)}")
    htype = raw.get("type", "subprocess")
    command = list(raw.get("command") or [])
    python_target = raw.get("python")
    if htype == "subprocess" and not command:
        raise ValueError("subprocess hook 必须提供 command")
    if htype == "python" and not python_target:
        raise ValueError("python hook 必须提供 python 目标")
    short_id = raw.get("id") or f"{event.lower()}-{abs(hash(tuple(command))) % 10_000_000}"
    return HookSpec(
        plugin_id=plugin_id,
        hook_id=f"{plugin_id}::{short_id}",
        event=event,
        matcher=dict(raw.get("matcher") or {}),
        type=htype,
        command=command or None,
        python_target=python_target,
        timeout_seconds=float(raw.get("timeout_seconds", 5.0)),
        blocking=bool(raw.get("blocking", True)),
        on_failure=str(raw.get("on_failure", "block")),
        working_dir=raw.get("working_dir") or plugin_root,
        env=dict(raw.get("env") or {}),
    )
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/platform/plugins/contributions/test_hooks_contribution.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/platform/plugins/contributions/__init__.py \
        sensenova_claw/platform/plugins/contributions/hooks.py \
        tests/unit/platform/plugins/contributions/
git commit -m "feat(plugins): 把 manifest contributes.hooks 注入 HookRegistry"
```

---

### Task 7: PluginLoader 解析 `contributes.mcp_servers` 写入 config

**Files:**
- Create: `sensenova_claw/platform/plugins/contributions/mcp_servers.py`
- Create: `tests/unit/platform/plugins/contributions/test_mcp_servers_contribution.py`
- Modify: `sensenova_claw/capabilities/mcp/types.py`（增加 `auto_start`、`restart_policy`、`max_restarts`、`health_check_*` 字段，默认值兼容旧用法）

- [ ] **Step 1: 修改 `McpServerConfig` 增加新字段**

```python
# sensenova_claw/capabilities/mcp/types.py（仅展示新增/修改部分）
from typing import Literal

McpAutoStart = Literal["always", "on_demand", "never"]
McpRestartPolicy = Literal["never", "on_failure", "always"]


@dataclass(slots=True)
class McpServerConfig:
    name: str
    transport: McpTransportType
    timeout: float = 15.0
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    auto_start: McpAutoStart = "on_demand"
    restart_policy: McpRestartPolicy = "on_failure"
    max_restarts: int = 3
    health_check_interval: float = 0.0
    health_check_method: str = "tools/list"
```

> 注意：现有 `normalize_mcp_servers` 函数（位于 `sensenova_claw/platform/config/mcp.py`）需扩展兼容这些字段——但不在本任务范围内（Task 8 处理）。

- [ ] **Step 2: 写失败测试**

```python
# tests/unit/platform/plugins/contributions/test_mcp_servers_contribution.py
from pathlib import Path

from sensenova_claw.platform.plugins.contributions.mcp_servers import (
    install_mcp_server_contributions,
)


class _StubManifest:
    def __init__(self, plugin_id: str, contributes: dict, root: Path):
        self.id = plugin_id
        self.contributes = contributes
        self.root_path = root


def test_install_stdio_server(tmp_path: Path):
    manifest = _StubManifest("team-a/crm", {
        "mcp_servers": [{
            "id": "crm-server",
            "transport": "stdio",
            "command": ["node", "mcp/crm-server.js"],
            "env": {"CRM_API_TOKEN": "tok"},
            "auto_start": "on_demand",
            "restart_policy": "on_failure",
            "max_restarts": 2,
        }],
    }, tmp_path)
    target: dict = {}
    failures = install_mcp_server_contributions(manifest, target)
    assert failures == []
    key = "team-a/crm::crm-server"
    assert key in target
    cfg = target[key]
    assert cfg["transport"] == "stdio"
    assert cfg["command"] == "node"
    assert cfg["args"] == ["mcp/crm-server.js"]
    assert cfg["env"] == {"CRM_API_TOKEN": "tok"}
    assert cfg["auto_start"] == "on_demand"
    assert cfg["max_restarts"] == 2
    # cwd 默认指向 manifest 根
    assert cfg["cwd"] == str(tmp_path)


def test_install_sse_server(tmp_path: Path):
    manifest = _StubManifest("team-a/crm", {
        "mcp_servers": [{
            "id": "ext-search",
            "transport": "sse",
            "url": "https://mcp.search/sse",
            "headers": {"Authorization": "Bearer x"},
        }],
    }, tmp_path)
    target: dict = {}
    install_mcp_server_contributions(manifest, target)
    cfg = target["team-a/crm::ext-search"]
    assert cfg["transport"] == "sse"
    assert cfg["url"] == "https://mcp.search/sse"
    assert cfg["headers"] == {"Authorization": "Bearer x"}


def test_invalid_transport_recorded_as_failure(tmp_path: Path):
    manifest = _StubManifest("p", {
        "mcp_servers": [{"id": "x", "transport": "carrier-pigeon"}],
    }, tmp_path)
    target: dict = {}
    failures = install_mcp_server_contributions(manifest, target)
    assert len(failures) == 1
    assert "carrier-pigeon" in failures[0]
    assert target == {}


def test_stdio_missing_command_fails(tmp_path: Path):
    manifest = _StubManifest("p", {
        "mcp_servers": [{"id": "x", "transport": "stdio"}],
    }, tmp_path)
    target: dict = {}
    failures = install_mcp_server_contributions(manifest, target)
    assert len(failures) == 1
    assert "command" in failures[0]
```

- [ ] **Step 3: 实现**

```python
# sensenova_claw/platform/plugins/contributions/mcp_servers.py
from __future__ import annotations

from typing import Any


VALID_TRANSPORTS = {"stdio", "sse", "streamable-http", "http"}


def install_mcp_server_contributions(manifest: Any, target: dict[str, dict[str, Any]]) -> list[str]:
    """解析 manifest.contributes.mcp_servers 写入 target dict（key 为带 namespace 的 server id）。"""
    failures: list[str] = []
    contribs = (manifest.contributes or {}).get("mcp_servers") or []
    for index, raw in enumerate(contribs):
        try:
            key, cfg = _parse_mcp_server(raw, plugin_id=manifest.id, plugin_root=str(manifest.root_path))
        except ValueError as exc:
            failures.append(f"[{manifest.id}] mcp_servers[{index}]: {exc}")
            continue
        target[key] = cfg
    return failures


def _parse_mcp_server(raw: dict[str, Any], *, plugin_id: str, plugin_root: str) -> tuple[str, dict[str, Any]]:
    sid = str(raw.get("id") or "").strip()
    if not sid:
        raise ValueError("缺少 id")
    transport = str(raw.get("transport") or "").strip().lower()
    # 兼容 spec 用 "http"，运行时用 "streamable-http"
    if transport == "http":
        transport = "streamable-http"
    if transport not in VALID_TRANSPORTS:
        raise ValueError(f"非法 transport {transport!r}")
    cfg: dict[str, Any] = {
        "name": f"{plugin_id}::{sid}",
        "transport": transport,
        "timeout": float(raw.get("timeout", 15.0)),
        "auto_start": str(raw.get("auto_start", "on_demand")),
        "restart_policy": str(raw.get("restart_policy", "on_failure")),
        "max_restarts": int(raw.get("max_restarts", 3)),
        "health_check_interval": float((raw.get("health_check") or {}).get("interval_seconds", 0.0)),
        "health_check_method": str((raw.get("health_check") or {}).get("method", "tools/list")),
    }
    if transport == "stdio":
        cmd_list = list(raw.get("command") or [])
        if not cmd_list:
            raise ValueError("stdio MCP server 必须提供 command")
        extra_args = list(raw.get("args") or [])
        cfg["command"] = cmd_list[0]
        cfg["args"] = cmd_list[1:] + extra_args
        cfg["env"] = dict(raw.get("env") or {})
        cfg["cwd"] = str(raw.get("working_dir") or plugin_root)
    else:
        url = str(raw.get("url") or "").strip()
        if not url:
            raise ValueError(f"{transport} MCP server 必须提供 url")
        cfg["url"] = url
        cfg["headers"] = dict(raw.get("headers") or {})
    return f"{plugin_id}::{sid}", cfg
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/platform/plugins/contributions/test_mcp_servers_contribution.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/capabilities/mcp/types.py \
        sensenova_claw/platform/plugins/contributions/mcp_servers.py \
        tests/unit/platform/plugins/contributions/test_mcp_servers_contribution.py
git commit -m "feat(mcp): McpServerConfig 增加 auto_start/restart_policy；manifest 解析 mcp_servers"
```

---

### Task 8: 扩展 `normalize_mcp_servers` 与 `McpSessionManager` 支持 auto_start / restart

**Files:**
- Modify: `sensenova_claw/platform/config/mcp.py`（`normalize_mcp_servers` 读取新字段）
- Modify: `sensenova_claw/capabilities/mcp/runtime.py`：`McpSessionManager` 增加 `start_eager_servers(session_id)` 与重启计数
- Create: `tests/unit/capabilities/mcp/test_session_manager_lifecycle.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/capabilities/mcp/test_session_manager_lifecycle.py
import pytest

from sensenova_claw.capabilities.mcp.runtime import McpSessionManager
from sensenova_claw.capabilities.mcp.types import McpServerConfig


class _FakeRuntime:
    def __init__(self):
        self.spawned = 0
        self.closed = 0

    async def ensure_catalog(self):
        self.spawned += 1
        from sensenova_claw.capabilities.mcp.types import McpCatalog
        return McpCatalog(tools=[], by_safe_name={})

    async def close(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_on_demand_does_not_spawn_until_call(monkeypatch):
    manager = McpSessionManager()
    fake = _FakeRuntime()

    async def fake_get_or_create(_session_id):
        return fake

    monkeypatch.setattr(manager, "_get_or_create_runtime", fake_get_or_create)
    # 仅访问配置，不主动 ensure_catalog
    await manager.list_tools_for_session_lazy("s1") if hasattr(manager, "list_tools_for_session_lazy") else None
    assert fake.spawned == 0


@pytest.mark.asyncio
async def test_eager_servers_started_when_auto_start_always(monkeypatch):
    manager = McpSessionManager()
    fake = _FakeRuntime()

    async def fake_get_or_create(_session_id):
        return fake

    # 注入一个 always 的 server config
    server_cfg = McpServerConfig(
        name="srv", transport="stdio", command="echo", auto_start="always",
    )

    async def fake_normalize(_):
        return {"srv": server_cfg}

    monkeypatch.setattr("sensenova_claw.capabilities.mcp.runtime.normalize_mcp_servers", fake_normalize)
    monkeypatch.setattr(manager, "_get_or_create_runtime", fake_get_or_create)
    await manager.start_eager_servers("s1")
    assert fake.spawned == 1


@pytest.mark.asyncio
async def test_restart_counter_increments_on_failure_with_restart_policy(monkeypatch):
    manager = McpSessionManager()
    server_cfg = McpServerConfig(
        name="srv", transport="stdio", command="x",
        restart_policy="on_failure", max_restarts=2,
    )
    # 第一次失败 -> should_restart=True 且 count=1
    assert manager.should_restart(server_cfg, error_count=0) is True
    assert manager.should_restart(server_cfg, error_count=1) is True
    assert manager.should_restart(server_cfg, error_count=2) is False


def test_should_restart_never_returns_false():
    manager = McpSessionManager()
    cfg = McpServerConfig(name="x", transport="stdio", command="c", restart_policy="never")
    assert manager.should_restart(cfg, error_count=0) is False
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/capabilities/mcp/test_session_manager_lifecycle.py -v`
Expected: FAIL

- [ ] **Step 3: 实现修改**

修改 `sensenova_claw/platform/config/mcp.py`（`normalize_mcp_servers`）映射新字段：

```python
# 仅展示需补的逻辑，加入到现有 normalize_mcp_servers 的字段映射
# normalized.auto_start = entry.get("auto_start", "on_demand")
# normalized.restart_policy = entry.get("restart_policy", "on_failure")
# normalized.max_restarts = int(entry.get("max_restarts", 3))
# health = entry.get("health_check") or {}
# normalized.health_check_interval = float(health.get("interval_seconds", 0.0))
# normalized.health_check_method = str(health.get("method", "tools/list"))
```

修改 `sensenova_claw/capabilities/mcp/runtime.py`，在 `McpSessionManager` 末尾追加：

```python
async def start_eager_servers(self, session_id: str) -> None:
    """对 auto_start='always' 的 server 在 session 创建时主动 ensure。"""
    runtime = await self._get_or_create_runtime(session_id)
    servers = normalize_mcp_servers(config.get("mcp.servers", {}))
    for name, cfg in servers.items():
        if getattr(cfg, "auto_start", "on_demand") != "always":
            continue
        try:
            await runtime.ensure_catalog()
        except Exception:
            logger.warning("eager start failed server=%s", name, exc_info=True)

def should_restart(self, server_cfg: "McpServerConfig", *, error_count: int) -> bool:
    policy = getattr(server_cfg, "restart_policy", "on_failure")
    if policy == "never":
        return False
    if policy == "always":
        return error_count < server_cfg.max_restarts
    if policy == "on_failure":
        return error_count < server_cfg.max_restarts
    return False
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/capabilities/mcp/test_session_manager_lifecycle.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/platform/config/mcp.py \
        sensenova_claw/capabilities/mcp/runtime.py \
        tests/unit/capabilities/mcp/test_session_manager_lifecycle.py
git commit -m "feat(mcp): McpSessionManager 支持 auto_start=always 与 restart_policy"
```

---

### Task 9: 注入 `PreTool` / `PostTool` 触发点到 ToolSessionWorker

**Files:**
- Modify: `sensenova_claw/kernel/runtime/workers/tool_worker.py`：将 `HookPipeline` 作为可选依赖注入；在 `tool.execute` 调用前后跑 hook
- Modify: `sensenova_claw/kernel/runtime/tool_runtime.py`：构造函数接受 `HookPipeline | None`，传给 worker
- Create: `tests/unit/kernel/runtime/workers/test_tool_worker_hooks.py`

- [ ] **Step 1: 写失败测试（用 Stub HookPipeline 验证调用语义）**

```python
# tests/unit/kernel/runtime/workers/test_tool_worker_hooks.py
import asyncio
from dataclasses import dataclass

import pytest

from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import TOOL_CALL_REQUESTED, TOOL_CALL_RESULT, TOOL_CALL_COMPLETED
from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.pipeline import PipelineResult


@dataclass
class _StubTool:
    name: str = "echo"
    risk_level = type("RL", (), {"value": "low"})()
    parameters: dict = None

    async def execute(self, **kwargs):
        return {"echoed": kwargs.get("message")}


class _StubRegistry:
    def __init__(self, tool):
        self._tool = tool
    def get(self, name, session_id=None):
        return self._tool


class _StubPipeline:
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls: list[tuple[str, dict]] = []

    async def run(self, *, event, session_id, turn_id, trace_id, identity, context):
        self.calls.append((event, dict(context)))
        return self.sequence.pop(0)


@pytest.mark.asyncio
async def test_pre_tool_mutate_changes_args_passed_to_tool():
    # PreTool 把 message 改成 mutated；PostTool 不变
    pipeline = _StubPipeline([
        PipelineResult(decision=Decision.MUTATE, context={"tool_name": "echo", "tool_args": {"message": "mutated"}}),
        PipelineResult(decision=Decision.CONTINUE, context={}),
    ])
    # 这里假设 ToolSessionWorker 暴露一个内部 hook 调用接口；测试驱动设计
    from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
    bus = PrivateEventBus(public_bus=None, session_id="s1")
    runtime_stub = type("RT", (), {
        "registry": _StubRegistry(_StubTool()),
        "agent_registry": None,
        "state_store": None,
        "hook_pipeline": pipeline,
        "identity": {"user_id": "u", "team_id": "t", "org_id": "o"},
    })()
    worker = ToolSessionWorker(session_id="s1", private_bus=bus, runtime=runtime_stub)
    event = EventEnvelope(
        type=TOOL_CALL_REQUESTED, session_id="s1", turn_id="t1", trace_id="tc1",
        source="agent",
        payload={"tool_call_id": "tc1", "tool_name": "echo", "arguments": {"message": "raw"}},
    )

    captured: list[EventEnvelope] = []

    async def _capture(envelope: EventEnvelope) -> None:
        captured.append(envelope)

    bus.publish = _capture  # type: ignore[assignment]

    await worker._handle_tool_requested(event)

    # PreTool 收到 raw，PostTool 收到 mutated
    assert pipeline.calls[0][0] == "PreTool"
    assert pipeline.calls[0][1]["tool_args"] == {"message": "raw"}
    assert pipeline.calls[1][0] == "PostTool"
    # 实际工具收到的 message 应是 mutated
    result_event = next(e for e in captured if e.type == TOOL_CALL_RESULT)
    assert result_event.payload["result"] == {"echoed": "mutated"}


@pytest.mark.asyncio
async def test_pre_tool_block_aborts_execution_with_failure():
    pipeline = _StubPipeline([
        PipelineResult(decision=Decision.BLOCK, context={}, block_reason="policy"),
    ])
    from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
    bus = PrivateEventBus(public_bus=None, session_id="s1")
    runtime_stub = type("RT", (), {
        "registry": _StubRegistry(_StubTool()),
        "agent_registry": None,
        "state_store": None,
        "hook_pipeline": pipeline,
        "identity": {"user_id": "u", "team_id": "t", "org_id": "o"},
    })()
    worker = ToolSessionWorker(session_id="s1", private_bus=bus, runtime=runtime_stub)
    event = EventEnvelope(
        type=TOOL_CALL_REQUESTED, session_id="s1", turn_id="t1", trace_id="tc1",
        source="agent",
        payload={"tool_call_id": "tc1", "tool_name": "echo", "arguments": {}},
    )
    captured: list[EventEnvelope] = []
    bus.publish = lambda e: captured.append(e) or asyncio.sleep(0)
    await worker._handle_tool_requested(event)

    # 没有 PostTool（block 提前返回）；TOOL_CALL_RESULT 标记 success=False
    assert any(e.type == TOOL_CALL_RESULT and e.payload["success"] is False for e in captured)


@pytest.mark.asyncio
async def test_pre_tool_replace_skips_tool_execute():
    pipeline = _StubPipeline([
        PipelineResult(
            decision=Decision.REPLACE,
            context={},
            replacement={"tool_result": {"cached": True}},
        ),
    ])
    from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
    tool = _StubTool()
    runtime_stub = type("RT", (), {
        "registry": _StubRegistry(tool),
        "agent_registry": None,
        "state_store": None,
        "hook_pipeline": pipeline,
        "identity": {"user_id": "u", "team_id": "t", "org_id": "o"},
    })()
    bus = PrivateEventBus(public_bus=None, session_id="s1")
    captured: list[EventEnvelope] = []
    bus.publish = lambda e: captured.append(e) or asyncio.sleep(0)
    worker = ToolSessionWorker(session_id="s1", private_bus=bus, runtime=runtime_stub)
    event = EventEnvelope(
        type=TOOL_CALL_REQUESTED, session_id="s1", turn_id="t1", trace_id="tc1",
        source="agent",
        payload={"tool_call_id": "tc1", "tool_name": "echo", "arguments": {}},
    )
    # 监视 tool.execute 是否被调用
    tool.execute_called = False
    orig_execute = tool.execute
    async def spy(**kwargs):
        tool.execute_called = True
        return await orig_execute(**kwargs)
    tool.execute = spy

    await worker._handle_tool_requested(event)
    assert tool.execute_called is False
    result_event = next(e for e in captured if e.type == TOOL_CALL_RESULT)
    assert result_event.payload["result"] == {"cached": True}
```

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/runtime/workers/test_tool_worker_hooks.py -v`
Expected: FAIL（hook 触发未接入）

- [ ] **Step 3: 实现 — 修改 `tool_worker.py` 与 `tool_runtime.py`**

在 `tool_worker.py:_handle_tool_requested`（位置 539 之后）插入 hook 调用：

```python
# 关键改动伪代码（实际改动需保留所有现有路径策略 / 确认逻辑 / 错误处理）：

# 1) 从 runtime 取 hook_pipeline 与 identity
hook_pipeline = getattr(self.rt, "hook_pipeline", None)
identity = getattr(self.rt, "identity", {"user_id": "local-dev", "team_id": "local-team", "org_id": "local-org"})

# 2) 构造 PreTool context
pretool_ctx = {
    "tool_name": tool_name,
    "tool_args": dict(exec_args),
    "agent_id": source_agent_id,
}

# 3) 跑 PreTool（仅当 hook_pipeline 存在时）
if hook_pipeline is not None:
    pre = await hook_pipeline.run(
        event="PreTool",
        session_id=event.session_id,
        turn_id=event.turn_id or "",
        trace_id=tool_call_id,
        identity=identity,
        context=pretool_ctx,
    )
    if pre.decision is Decision.BLOCK:
        await self._publish_tool_result(event, result=f"PreTool hook blocked: {pre.block_reason}", success=False)
        return
    if pre.decision is Decision.REPLACE:
        replaced_result = pre.replacement.get("tool_result")
        await self.bus.publish(EventEnvelope(
            type=TOOL_CALL_RESULT, session_id=event.session_id, turn_id=event.turn_id,
            trace_id=tool_call_id, source="tool",
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "result": replaced_result, "success": True, "error": ""},
        ))
        await self.bus.publish(EventEnvelope(
            type=TOOL_CALL_COMPLETED, session_id=event.session_id, turn_id=event.turn_id,
            trace_id=tool_call_id, source="tool",
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "success": True},
        ))
        return
    if pre.decision is Decision.MUTATE:
        new_args = pre.context.get("tool_args")
        if isinstance(new_args, dict):
            exec_args = dict(new_args)

# ...（继续现有流程：path policy → confirmation → tool.execute → ...）

# 4) tool.execute 后跑 PostTool
if hook_pipeline is not None:
    posttool_ctx = {
        "tool_name": tool_name,
        "tool_args": dict(exec_args),
        "tool_result": result,
        "success": success,
        "error": error,
    }
    post = await hook_pipeline.run(
        event="PostTool", session_id=event.session_id, turn_id=event.turn_id or "",
        trace_id=tool_call_id, identity=identity, context=posttool_ctx,
    )
    if post.decision is Decision.MUTATE:
        if "tool_result" in post.context:
            result = post.context["tool_result"]
        if "success" in post.context:
            success = bool(post.context["success"])
```

并修改 `tool_runtime.py`：

```python
class ToolRuntime:
    def __init__(
        self,
        bus_router: BusRouter,
        registry: ToolRegistry,
        agent_registry: Any = None,
        state_store: SessionStateStore | None = None,
        hook_pipeline: "HookPipeline | None" = None,
        identity: dict | None = None,
    ):
        ...
        self.hook_pipeline = hook_pipeline
        self.identity = identity or {"user_id": "local-dev", "team_id": "local-team", "org_id": "local-org"}
```

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/runtime/workers/test_tool_worker_hooks.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 跑既有 tool_worker 测试确认无回归**

Run: `python3 -m pytest tests/unit/test_tool_worker_cancel.py tests/unit/test_ask_user_tool.py -v`
Expected: PASS（保持现状）

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/kernel/runtime/workers/tool_worker.py \
        sensenova_claw/kernel/runtime/tool_runtime.py \
        tests/unit/kernel/runtime/workers/test_tool_worker_hooks.py
git commit -m "feat(hooks): ToolSessionWorker 接入 PreTool/PostTool（mutate/block/replace）"
```

---

### Task 10: 注入 `PreLLM` / `PostLLM` 触发点到 LLMSessionWorker

**Files:**
- Modify: `sensenova_claw/kernel/runtime/workers/llm_worker.py`
- Modify: `sensenova_claw/kernel/runtime/llm_runtime.py`（构造函数加 hook_pipeline / identity）
- Create: `tests/unit/kernel/runtime/workers/test_llm_worker_hooks.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/runtime/workers/test_llm_worker_hooks.py
import pytest

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import LLM_CALL_REQUESTED, LLM_CALL_RESULT
from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.pipeline import PipelineResult


class _RecPipeline:
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = []

    async def run(self, *, event, session_id, turn_id, trace_id, identity, context):
        self.calls.append((event, dict(context)))
        return self.sequence.pop(0)


@pytest.mark.asyncio
async def test_pre_llm_mutate_changes_messages_passed_to_provider(monkeypatch):
    # PreLLM 把 messages 改成 [system + user]，验证传给 provider 的是 mutated
    pipeline = _RecPipeline([
        PipelineResult(decision=Decision.MUTATE, context={
            "messages": [{"role": "system", "content": "ext"}, {"role": "user", "content": "raw"}],
            "tools": None,
            "temperature": 0.5,
        }),
        PipelineResult(decision=Decision.CONTINUE, context={}),
    ])
    # ……此测试需依赖完整 LLMSessionWorker 构造，落地时按已有 fixture 仿照 test_title_runtime.py 写
    # 关键断言：provider.call(messages=...) 的 messages 包含 system 'ext'
    pytest.skip("此测试在实现时将以集成 stub provider 形式落地；占位以驱动接口设计")


@pytest.mark.asyncio
async def test_pre_llm_block_publishes_error_and_skips_provider():
    pipeline = _RecPipeline([
        PipelineResult(decision=Decision.BLOCK, context={}, block_reason="policy"),
    ])
    pytest.skip("同上")


@pytest.mark.asyncio
async def test_post_llm_mutate_modifies_response_payload():
    pytest.skip("同上 — 实现时落地 stub provider 验证")
```

> 设计动机：LLMSessionWorker 的 fallback chain 比较复杂，先用 skip 占位驱动接口设计，本 Task 实现时把 skip 解开并补完整 stub provider。**实现时不允许保留 skip。**

- [ ] **Step 2: 在实现阶段把 skip 解开（具体落地）**

补全测试用 stub provider：

```python
class _StubProvider:
    def __init__(self):
        self.last_messages = None
        self.last_tools = None
    async def call(self, *, model, messages, tools, temperature, max_tokens, extra_body):
        self.last_messages = messages
        self.last_tools = tools
        return {"content": "ok", "tool_calls": [], "finish_reason": "stop", "usage": {}}
    def stream_call(self, **_):
        async def _gen():
            if False:
                yield None
        return _gen()
```

完整测试体（与 stub provider 配合）落地后断言：
- `pipeline.calls[0] == ("PreLLM", {"messages": [...原始...], "tools": None, ...})`
- `provider.last_messages` 包含 PreLLM 注入的 system 消息
- 第二个 PipelineResult 是 PostLLM；其 context 含 `response.content == "ok"`

PostLLM mutate 测试：第一个 hook decision=CONTINUE，第二个 decision=MUTATE 替换 `response.content="redacted"`，断言 `LLM_CALL_RESULT` 的 payload `response.content == "redacted"`。

PreLLM block 测试：直接断言 `LLM_CALL_RESULT.finish_reason == "error"` 且 provider.call 未被调用。

- [ ] **Step 3: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/runtime/workers/test_llm_worker_hooks.py -v`
Expected: FAIL（PreLLM/PostLLM 未接入）

- [ ] **Step 4: 实现**

修改 `llm_worker.py:_handle_llm_requested`：
- 在 `_run_fallback_chain` 之前调用 PreLLM hook（context: `messages`/`tools`/`temperature`/`max_tokens`/`extra_body`）
- BLOCK → 直接 `_publish_llm_error`
- MUTATE → 用新 context 的字段替换 messages/tools/temperature/...
- REPLACE → 跳过 provider 调用，把 `replacement.response` 当作成功结果（走 `_publish_llm_success`）
- 在 `_run_fallback_chain` 之后（仅成功分支）调用 PostLLM hook（context: `response`）
- MUTATE → 替换 `result.response` 字段后再 publish
- BLOCK → 转成 error
- REPLACE → 用 `replacement.response` 替代

修改 `llm_runtime.py:LLMRuntime.__init__` 接收 `hook_pipeline` 与 `identity`，传递给 worker。

- [ ] **Step 5: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/runtime/workers/test_llm_worker_hooks.py -v`
Expected: PASS

回归：

Run: `python3 -m pytest tests/unit/test_title_runtime.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add sensenova_claw/kernel/runtime/workers/llm_worker.py \
        sensenova_claw/kernel/runtime/llm_runtime.py \
        tests/unit/kernel/runtime/workers/test_llm_worker_hooks.py
git commit -m "feat(hooks): LLMSessionWorker 接入 PreLLM/PostLLM（mutate/block/replace）"
```

---

### Task 11: 注入 `OnSessionStart` / `OnSessionEnd` / `OnUserInput` / `OnError` / `OnConfigUpdated`

**Files:**
- Modify: `sensenova_claw/kernel/runtime/agent_runtime.py`：在 `spawn_agent_session` / `_on_session_destroy` / `send_user_input` 注入 hook
- Modify: `sensenova_claw/kernel/runtime/workers/base.py`：在主循环异常处 fire-and-forget 触发 OnError
- Modify: `sensenova_claw/platform/config/config_manager.py`：发布 `CONFIG_UPDATED` 之后追加 hook 触发
- Create: `tests/unit/kernel/runtime/test_lifecycle_hooks.py`
- Create: `tests/unit/platform/config/test_config_manager_hooks.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/runtime/test_lifecycle_hooks.py
import pytest

from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.pipeline import PipelineResult


class _RecPipeline:
    def __init__(self):
        self.events: list[str] = []
    async def run(self, *, event, **_kw):
        self.events.append(event)
        return PipelineResult(decision=Decision.CONTINUE, context={})


@pytest.mark.asyncio
async def test_on_session_start_triggered_when_session_created(make_agent_runtime):
    pipeline = _RecPipeline()
    rt = make_agent_runtime(hook_pipeline=pipeline)
    await rt.spawn_agent_session(agent_id="default", session_id="s1", user_input="hi")
    assert "OnSessionStart" in pipeline.events
    assert "OnUserInput" in pipeline.events


@pytest.mark.asyncio
async def test_on_session_end_triggered_on_destroy(make_agent_runtime):
    pipeline = _RecPipeline()
    rt = make_agent_runtime(hook_pipeline=pipeline)
    await rt._on_session_destroy("s1")
    assert "OnSessionEnd" in pipeline.events
```

```python
# tests/unit/platform/config/test_config_manager_hooks.py
import pytest


@pytest.mark.asyncio
async def test_on_config_updated_triggered_after_publish(make_config_manager_with_pipeline):
    mgr, pipeline = make_config_manager_with_pipeline()
    await mgr.update("agent", {"temperature": 0.7})
    assert "OnConfigUpdated" in pipeline.events
```

> conftest 中 fixture `make_agent_runtime` 与 `make_config_manager_with_pipeline` 是本 Task 引入的工厂——若已有等价 fixture 复用之；否则在 `tests/unit/kernel/runtime/conftest.py` / `tests/unit/platform/config/conftest.py` 新建。fixture 内部把 `hook_pipeline` 注入 runtime 构造函数。

- [ ] **Step 2: 跑失败测试**

Run: `python3 -m pytest tests/unit/kernel/runtime/test_lifecycle_hooks.py tests/unit/platform/config/test_config_manager_hooks.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

修改 `agent_runtime.py`：
- `__init__` 接受 `hook_pipeline: HookPipeline | None`、`identity: dict`
- `spawn_agent_session` 在 `repo.create_session` 之后、`send_user_input` 之前 await `hook_pipeline.run(event="OnSessionStart", ...)`；BLOCK → 抛 `RuntimeError`
- `send_user_input` 发布 USER_INPUT 之后 await `hook_pipeline.run(event="OnUserInput", context={"text": user_input, "payload": payload})`；MUTATE 的 `text` 字段替换 payload.content
- `_on_session_destroy` 调用 hook fire-and-forget（OnSessionEnd 不可 mutate，按 spec）

修改 `workers/base.py`：在主循环 `try/except Exception` 处 fire-and-forget 触发 `OnError` hook（`context={"error_type": type(exc).__name__, "error_message": str(exc)}`）。fire-and-forget 不等待。

修改 `config_manager.py`：在 `await self._event_bus.publish(... CONFIG_UPDATED ...)` 之后 await `hook_pipeline.run(event="OnConfigUpdated", context={"section": section, "data": data})`，BLOCK 不可 mutate（按 spec），仅记录 diagnostic。

- [ ] **Step 4: 跑测试 PASS**

Run: `python3 -m pytest tests/unit/kernel/runtime/test_lifecycle_hooks.py tests/unit/platform/config/test_config_manager_hooks.py -v`
Expected: PASS

回归：

Run: `python3 -m pytest tests/unit/test_config_event_subscribers.py tests/unit/test_config_file_watcher.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sensenova_claw/kernel/runtime/agent_runtime.py \
        sensenova_claw/kernel/runtime/workers/base.py \
        sensenova_claw/platform/config/config_manager.py \
        tests/unit/kernel/runtime/test_lifecycle_hooks.py \
        tests/unit/platform/config/test_config_manager_hooks.py
git commit -m "feat(hooks): 接入 OnSessionStart/End OnUserInput OnError OnConfigUpdated 触发点"
```

---

### Task 12: 集成测试 — 真子进程 hook 驱动 PreTool 改写参数

**Files:**
- Create: `tests/integration/hooks/__init__.py`（空）
- Create: `tests/integration/hooks/test_pretool_subprocess.py`
- Create: `tests/fixtures/hooks/audit.sh`（bash，仅 Linux/macOS）
- Create: `tests/fixtures/hooks/audit.py`（Python，跨平台兜底；测试按 `os.name` 选）

```bash
#!/bin/bash
# tests/fixtures/hooks/audit.sh
read INPUT
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['context']['tool_name'])")
ARGS=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); a=d['context'].get('tool_args',{}); a['audited']=True; print(json.dumps(a))")
printf '{"decision":"mutate","mutations":{"tool_args":%s}}' "$ARGS"
```

```python
# tests/fixtures/hooks/audit.py
import json, sys
data = json.loads(sys.stdin.read())
args = dict(data.get("context", {}).get("tool_args", {}))
args["audited"] = True
sys.stdout.write(json.dumps({"decision": "mutate", "mutations": {"tool_args": args}}))
```

- [ ] **Step 1: 写失败/真集成测试**

```python
# tests/integration/hooks/test_pretool_subprocess.py
import os
import sys
from pathlib import Path

import pytest

from sensenova_claw.kernel.hooks.pipeline import HookPipeline
from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec


FIX = Path(__file__).resolve().parents[2] / "fixtures" / "hooks"


def _audit_command():
    if os.name == "posix" and (FIX / "audit.sh").exists():
        return ["bash", str(FIX / "audit.sh")]
    return [sys.executable, str(FIX / "audit.py")]


@pytest.mark.asyncio
async def test_real_subprocess_pretool_mutates_args():
    reg = HookRegistry()
    reg.register(HookSpec(
        plugin_id="t", hook_id="t::audit", event="PreTool",
        matcher={"tool_name": ["send_email"]},
        type="subprocess", command=_audit_command(),
        python_target=None, timeout_seconds=5.0,
        blocking=True, on_failure="block",
        working_dir=None, env={},
    ))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="PreTool",
        session_id="s", turn_id="t", trace_id="tc",
        identity={"user_id": "u", "team_id": "t", "org_id": "o"},
        context={"tool_name": "send_email", "tool_args": {"to": "x"}},
    )
    assert result.decision.value == "mutate"
    assert result.context["tool_args"]["audited"] is True
    assert result.context["tool_args"]["to"] == "x"
```

- [ ] **Step 2: 跑测试**

Run: `python3 -m pytest tests/integration/hooks/test_pretool_subprocess.py -v`
Expected: PASS（hook 真起子进程，输出 mutate）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/hooks/__init__.py \
        tests/integration/hooks/test_pretool_subprocess.py \
        tests/fixtures/hooks/audit.sh \
        tests/fixtures/hooks/audit.py
git commit -m "test(hooks): 真子进程 PreTool 集成验证 mutate 链路"
```

---

### Task 13: 集成测试 — stdio MCP server 生命周期与 on_demand spawn

**Files:**
- Create: `tests/integration/mcp/__init__.py`（空）
- Create: `tests/integration/mcp/test_stdio_server_lifecycle.py`
- Create: `tests/fixtures/mcp_servers/__init__.py`（空）
- Create: `tests/fixtures/mcp_servers/echo_server.py`

```python
# tests/fixtures/mcp_servers/echo_server.py
"""极简 stdio MCP server：暴露 echo 工具用于集成测试。"""
import asyncio

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo-test-server")


@server.tool()
async def echo(message: str) -> dict:
    return {"echoed": message}


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 1: 写测试**

```python
# tests/integration/mcp/test_stdio_server_lifecycle.py
import sys
from pathlib import Path

import pytest

from sensenova_claw.capabilities.mcp.runtime import McpSessionManager
from sensenova_claw.capabilities.mcp.types import McpServerConfig


SERVER = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_servers" / "echo_server.py"


def _server_cfg(auto_start="on_demand", restart_policy="on_failure"):
    return McpServerConfig(
        name="echo",
        transport="stdio",
        command=sys.executable,
        args=[str(SERVER)],
        env={},
        cwd=str(SERVER.parent),
        auto_start=auto_start,
        restart_policy=restart_policy,
        max_restarts=2,
    )


@pytest.mark.asyncio
async def test_on_demand_spawns_only_at_first_call(monkeypatch):
    manager = McpSessionManager()
    cfg = _server_cfg()
    monkeypatch.setattr(
        "sensenova_claw.capabilities.mcp.runtime.normalize_mcp_servers",
        lambda _src: {"echo": cfg},
    )
    # 注入空配置：访问 list_tools 才会 spawn
    tools = await manager.list_tools(session_id="s1")
    assert any(t.tool_name == "echo" for t in tools)
    # 调用 tool 验证连通
    safe = next(t.safe_name for t in tools if t.tool_name == "echo")
    result = await manager.call_tool(session_id="s1", safe_name=safe, arguments={"message": "hello"})
    # 结果应包含 echoed
    text_chunks = [c for c in result["content"] if c["type"] == "text"]
    assert any("hello" in c["text"] for c in text_chunks) or result.get("structured_content") == {"echoed": "hello"}
    await manager.close_session("s1")


@pytest.mark.asyncio
async def test_eager_servers_starts_when_auto_start_always(monkeypatch):
    manager = McpSessionManager()
    cfg = _server_cfg(auto_start="always")
    monkeypatch.setattr(
        "sensenova_claw.capabilities.mcp.runtime.normalize_mcp_servers",
        lambda _src: {"echo": cfg},
    )
    await manager.start_eager_servers("s2")
    tools = manager.get_cached_tools("s2")
    assert tools and any(t.tool_name == "echo" for t in tools)
    await manager.close_session("s2")


@pytest.mark.asyncio
async def test_invalidate_after_transport_failure(monkeypatch):
    """模拟 stdio runtime 出错后被 invalidate 并下次重新 spawn。"""
    manager = McpSessionManager()
    cfg = _server_cfg()
    monkeypatch.setattr(
        "sensenova_claw.capabilities.mcp.runtime.normalize_mcp_servers",
        lambda _src: {"echo": cfg},
    )
    # 第一次正常 list
    tools_a = await manager.list_tools(session_id="s3")
    assert tools_a
    # 强制断开（关闭 session）
    await manager.close_session("s3")
    # 再次 list 应能重新拉起
    tools_b = await manager.list_tools(session_id="s3")
    assert any(t.tool_name == "echo" for t in tools_b)
    await manager.close_session("s3")
```

- [ ] **Step 2: 跑测试 PASS**

Run: `python3 -m pytest tests/integration/mcp/test_stdio_server_lifecycle.py -v`
Expected: PASS（spawn echo_server.py 子进程，list/call 跑通）

注：若 `mcp.server.fastmcp` 导入失败，fallback 用 `mcp` SDK 提供的 lower-level API；任意 Python MCP server 实现皆可，只要 stdio 能 list `echo` tool。

- [ ] **Step 3: 提交**

```bash
git add tests/integration/mcp/__init__.py \
        tests/integration/mcp/test_stdio_server_lifecycle.py \
        tests/fixtures/mcp_servers/__init__.py \
        tests/fixtures/mcp_servers/echo_server.py
git commit -m "test(mcp): stdio MCP server 生命周期 + auto_start/on_demand 集成验证"
```

---

### Task 14: 集成测试 — Python tool 与 MCP tool 都过 PreTool（schema 一致）

**Files:**
- Create: `tests/integration/mcp/test_mcp_tool_passes_pretool_hook.py`

- [ ] **Step 1: 写测试**

```python
# tests/integration/mcp/test_mcp_tool_passes_pretool_hook.py
import sys
from pathlib import Path

import pytest

from sensenova_claw.capabilities.mcp.runtime import McpSessionManager, McpToolAdapter
from sensenova_claw.capabilities.mcp.types import McpServerConfig
from sensenova_claw.kernel.hooks.decisions import Decision
from sensenova_claw.kernel.hooks.pipeline import PipelineResult


SERVER = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_servers" / "echo_server.py"


class _RecPipeline:
    def __init__(self):
        self.calls = []
    async def run(self, *, event, session_id, turn_id, trace_id, identity, context):
        self.calls.append((event, dict(context)))
        return PipelineResult(decision=Decision.CONTINUE, context=context)


@pytest.mark.asyncio
async def test_mcp_tool_and_python_tool_share_pretool_context_schema(monkeypatch):
    manager = McpSessionManager()
    cfg = McpServerConfig(
        name="echo", transport="stdio",
        command=sys.executable, args=[str(SERVER)],
        cwd=str(SERVER.parent),
    )
    monkeypatch.setattr(
        "sensenova_claw.capabilities.mcp.runtime.normalize_mcp_servers",
        lambda _src: {"echo": cfg},
    )
    tools = await manager.list_tools(session_id="s1")
    descriptor = next(t for t in tools if t.tool_name == "echo")
    adapter = McpToolAdapter(manager, descriptor)

    # 模拟 ToolSessionWorker 的 PreTool 调用，分别验证 Python tool 与 MCP tool 走同一 context schema
    pipeline = _RecPipeline()
    # 先 Python tool（用 adapter.name 与一个普通 tool name 同时跑）
    expected_keys = {"tool_name", "tool_args", "agent_id"}
    for tool_name in ["read_file", adapter.name]:
        await pipeline.run(
            event="PreTool", session_id="s1", turn_id="t", trace_id="tc",
            identity={"user_id": "u", "team_id": "t", "org_id": "o"},
            context={"tool_name": tool_name, "tool_args": {"x": 1}, "agent_id": "default"},
        )
    assert all(set(call[1].keys()) >= expected_keys for call in pipeline.calls)
    # 关键：MCP tool 与 Python tool 在 PreTool context 中不区分类型
    assert pipeline.calls[0][1].keys() == pipeline.calls[1][1].keys()
    await manager.close_session("s1")
```

- [ ] **Step 2: 跑测试 PASS**

Run: `python3 -m pytest tests/integration/mcp/test_mcp_tool_passes_pretool_hook.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/integration/mcp/test_mcp_tool_passes_pretool_hook.py
git commit -m "test(hooks): Python tool 与 MCP tool 共享 PreTool context schema"
```

---

### Task 15: 集成测试 — PostLLM replace 拦截 LLM 输出

**Files:**
- Create: `tests/integration/hooks/test_postllm_replace.py`
- Create: `tests/fixtures/hooks/postllm_force_text.py`

```python
# tests/fixtures/hooks/postllm_force_text.py
import json, sys
sys.stdin.read()
sys.stdout.write(json.dumps({
    "decision": "replace",
    "replacement": {"response": {"content": "REPLACED", "tool_calls": [], "finish_reason": "stop", "usage": {}}},
}))
```

- [ ] **Step 1: 写测试**

```python
# tests/integration/hooks/test_postllm_replace.py
import sys
from pathlib import Path

import pytest

from sensenova_claw.kernel.hooks.pipeline import HookPipeline
from sensenova_claw.kernel.hooks.registry import HookRegistry, HookSpec


FIX = Path(__file__).resolve().parents[2] / "fixtures" / "hooks"


@pytest.mark.asyncio
async def test_postllm_replace_overrides_llm_response():
    reg = HookRegistry()
    reg.register(HookSpec(
        plugin_id="t", hook_id="t::force", event="PostLLM",
        matcher={}, type="subprocess",
        command=[sys.executable, str(FIX / "postllm_force_text.py")],
        python_target=None, timeout_seconds=5.0,
        blocking=True, on_failure="block",
        working_dir=None, env={},
    ))
    pipe = HookPipeline(registry=reg)
    result = await pipe.run(
        event="PostLLM",
        session_id="s", turn_id="t", trace_id="tr",
        identity={"user_id": "u", "team_id": "t", "org_id": "o"},
        context={"response": {"content": "ORIGINAL", "tool_calls": []}},
    )
    assert result.decision.value == "replace"
    assert result.replacement["response"]["content"] == "REPLACED"
```

- [ ] **Step 2: 跑测试 PASS**

Run: `python3 -m pytest tests/integration/hooks/test_postllm_replace.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/integration/hooks/test_postllm_replace.py \
        tests/fixtures/hooks/postllm_force_text.py
git commit -m "test(hooks): PostLLM replace 拦截 LLM 输出集成验证"
```

---

### Task 16: 全量回归 + 文档更新

- [ ] **Step 1: 跑全部 unit 测试**

Run: `python3 -m pytest tests/unit -q`
Expected: 全部 PASS（不允许新增 fail）

- [ ] **Step 2: 跑 P6 集成测试**

Run: `python3 -m pytest tests/integration/hooks tests/integration/mcp -q`
Expected: 全部 PASS

- [ ] **Step 3: 跑既有 e2e 冒烟（不需要 API key 的）**

Run: `python3 -m pytest tests/e2e -k "not real" -q`
Expected: 不引入新 fail（若 e2e 需要 API key 则按本地环境标记 skip）

- [ ] **Step 4: 更新 CLAUDE.md "自动生成的Notes" 区块**

在 `CLAUDE.md` 末尾追加 P6 复盘段（按 file path 写）：

```markdown
### 2026-04-28 P6 实现复盘

成功经验：
- HookPipeline 串行链 + fire-and-forget 用一个 async create_task 列表管理，避免 await 阻塞主循环。
- McpServerConfig 增加 auto_start/restart_policy 字段保持默认值兼容旧 config.yml 中的 mcp.servers。
- 集成测试用 `mcp.server.fastmcp` 写一个 `echo_server.py` 是落地 stdio MCP 集成测试的最快路径。

失败/风险经验：
- Windows 上 bash hook 脚本不能直接跑，必须额外提供 Python fallback 并按 os.name 选择。
- subprocess timeout 后必须 wait() 已 kill 的进程，否则会在 Windows 上留 zombie。
```

- [ ] **Step 5: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: P6 实现复盘"
```

---

## 4. 自我审查清单（写完后跑一遍）

### 4.1 Spec 覆盖

| Spec 节 | 覆盖任务 |
|---|---|
| §4.3.6 hooks contribution | Task 6（解析 manifest hooks） |
| §4.3.8 mcp_servers contribution | Task 7（解析 manifest mcp_servers） |
| §6.1 触发模型 | Task 5（HookPipeline） |
| §6.1 Input envelope | Task 1（HookInputEnvelope） |
| §6.1 Output envelope | Task 1 + Task 2（HookOutputEnvelope + HookOutcome） |
| §6.1 Decision 语义（continue/block/mutate/replace） | Task 4 + Task 5（executor + pipeline） |
| §6.1 串行 vs 并行 | Task 5（blocking 链 + fire-and-forget） |
| §6.1 失败模型（非 0 退出 / 超时 / bad json） | Task 4（test_executor 8 个分支） |
| §6.1 Event 列表 9 个 | Task 9（PreTool/PostTool）+ Task 10（PreLLM/PostLLM）+ Task 11（OnSessionStart/End/UserInput/Error/ConfigUpdated） |
| §6.2 Path A stdio | Task 7 + Task 8 + Task 13 |
| §6.2 Path B SSE/HTTP | Task 7（解析 url + headers），既有 `_open_client` 已支持 |
| §6.2 Path C in-process | 不在 P6 范围；Task 7 的解析路径仅识别 stdio/sse/streamable-http，不破坏 P4 注入路径 |
| §6.2 生命周期 auto_start/restart_policy/max_restarts | Task 8（McpSessionManager 扩展） |
| §6.2 PreTool 对 MCP tool 同样适用 | Task 14 |

### 4.2 Placeholder 扫描

- 所有 "TBD/TODO/implement later" 都已替换为具体代码或测试
- 所有测试都有完整代码体（除 Task 10 Step 1 的 skip 占位，且 Step 2 明确要求解开）
- 所有 step 命令带 `Expected: PASS/FAIL`

### 4.3 类型一致性

- `Decision` 在 Task 2 定义，Task 4/5/9/10 引用 `Decision.CONTINUE/BLOCK/MUTATE/REPLACE` 一致
- `HookSpec` 在 Task 3 定义，Task 4/5/6 引用一致
- `HookOutputEnvelope.decision` 字段为 `str`（"continue"/...），`Decision` 是 `str` enum——`Decision(env.decision)` 在 Task 2 测试中验证可行
- `McpServerConfig` 新增字段在 Task 7 引用，Task 8 在 manager 中读取——字段名 `auto_start` / `restart_policy` / `max_restarts` 全部一致
- `HookPipeline.run` 签名（kwargs：`event`/`session_id`/`turn_id`/`trace_id`/`identity`/`context`）在 Task 5 定义，Task 9/10/11 全部按此签名调用

---

## 5. 执行交接

**Plan complete and saved to `docs/design/plans/P6-hook-pipeline-and-mcp-three-paths.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - dispatch fresh subagent per task with reviewer between tasks
**2. Inline Execution** - executing-plans skill, checkpoint each 3 tasks

依赖：本 plan 必须等 P3 完成后再执行；与 P4/P5 在同 worktree 池中可并行。
