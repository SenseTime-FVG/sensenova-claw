# AgentOS v1.2 — 路径安全策略 (PathPolicy)

> 版本: v1.2 · 日期: 2026-03-12 · 前置: v0.4（工具系统）, v0.5（双总线 + 权限确认）

---

## 1. 问题与设计决策

当前 `read_file` / `write_file` / `bash_command` 无路径边界保护，LLM 幻觉或 Prompt Injection 可操作任意文件。

**三区路径模型**：

```
GREEN  = workspace 内，自由读写，零摩擦
YELLOW = 用户已授权的外部目录（config 预授权 + 运行时 grant）
RED    = 未授权目录 → NEED_GRANT | 系统目录 → DENY（永远）
```

**关键决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| 维护 cwd？ | **否** | 可变状态可被 prompt injection 腐蚀；LLM 自行追踪目录上下文 |
| 授权触发方 | **LLM 协商**（方案 A） | `grant_path` 的 HIGH risk 复用已有确认流程；系统拦截作为 P2 迭代 |
| 策略执行点 | **Tool 内部检查** | 不同工具路径语义不同；ToolWorker 统一注入 `_path_policy`，Tool 自行消费 |
| 授权生命周期 | **双轨制** | config 预授权（持久化）+ 运行时 grant（进程级，重启清零） |
| 黑名单范围 | **仅 OS 核心目录** | `/tmp`、`~/.ssh` 等通过 RED 区授权保护，不在黑名单中 |

---

## 2. 架构集成

```
config.yml (granted_paths)
       │ 加载
       ▼
  PathPolicy (workspace + granted[])
       │ 挂载到 app.state
       ▼
  ToolRuntime → ToolSessionWorker
    _handle_tool_requested:
      arguments["_path_policy"] = policy   ← 注入
       │
  ┌────┼────────┬──────────────┐
  ▼    ▼        ▼              ▼
ReadFile WriteFile BashCommand GrantPath
.check_  .check_  .check_cwd  .grant()
 read()   write()
```

判定流程：
```
输入路径 → expanduser() → resolve() → resolved_path
  ├─ is_within(workspace)?  → GREEN  → ALLOW
  ├─ is_within(granted[])?  → YELLOW → ALLOW
  ├─ is_system_path()?      → RED    → DENY
  └─ else                   → RED    → NEED_GRANT
```

---

## 3. 新增文件

```
backend/app/security/
├── __init__.py
├── path_policy.py
└── deny_list.py
```

### 3.1 `path_policy.py`

```python
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from app.security.deny_list import is_system_path

logger = logging.getLogger(__name__)


class PathZone(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class PathVerdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEED_GRANT = "need_grant"


class PathPolicy:
    """无状态路径策略判定器。相对路径一律基于 workspace 解析。"""

    def __init__(self, workspace: Path, granted_paths: list[str] | None = None):
        self.workspace = workspace.expanduser().resolve()
        self._granted: list[Path] = []
        for p in granted_paths or []:
            try:
                resolved = Path(p).expanduser().resolve()
                if resolved.is_dir():
                    self._granted.append(resolved)
            except (OSError, ValueError):
                logger.warning("Invalid granted path, skipping: %s", p)

    def grant(self, dir_path: str) -> Path:
        resolved = Path(dir_path).expanduser().resolve()
        if is_system_path(resolved):
            raise ValueError(f"系统目录不允许授权: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"目录不存在: {resolved}")
        if resolved not in self._granted:
            self._granted.append(resolved)
            logger.info("Path granted: %s", resolved)
        return resolved

    def revoke(self, dir_path: str) -> None:
        resolved = Path(dir_path).expanduser().resolve()
        self._granted = [p for p in self._granted if p != resolved]

    @property
    def granted_paths(self) -> list[str]:
        return [str(p) for p in self._granted]

    def classify(self, target: Path) -> PathZone:
        resolved = target.expanduser().resolve()
        if _is_within(resolved, self.workspace):
            return PathZone.GREEN
        for granted in self._granted:
            if _is_within(resolved, granted):
                return PathZone.YELLOW
        return PathZone.RED

    def check_read(self, file_path: str) -> PathVerdict:
        return self._check(self._resolve(file_path))

    def check_write(self, file_path: str) -> PathVerdict:
        return self._check(self._resolve(file_path))

    def check_cwd(self, dir_path: str) -> PathVerdict:
        return self._check(self._resolve(dir_path))

    def safe_resolve(self, file_path: str) -> Path:
        return self._resolve(file_path)

    def _resolve(self, user_path: str) -> Path:
        p = Path(user_path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace / p).resolve()

    def _check(self, resolved: Path) -> PathVerdict:
        zone = self.classify(resolved)
        if zone in (PathZone.GREEN, PathZone.YELLOW):
            return PathVerdict.ALLOW
        if is_system_path(resolved):
            return PathVerdict.DENY
        return PathVerdict.NEED_GRANT


def _is_within(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False
```

### 3.2 `deny_list.py`

```python
from __future__ import annotations

import platform
from pathlib import Path

_UNIX_DENY = [
    "/etc", "/usr", "/bin", "/sbin", "/boot",
    "/proc", "/sys", "/dev", "/var/run", "/var/log",
    "/lib", "/lib64",
]

_WIN_DENY = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
]


def is_system_path(target: Path) -> bool:
    resolved = str(target.resolve())
    deny_list = _WIN_DENY if platform.system() == "Windows" else _UNIX_DENY
    for deny in deny_list:
        if platform.system() == "Windows":
            if resolved.lower().startswith(deny.lower()):
                return True
        else:
            if resolved == deny or resolved.startswith(deny + "/"):
                return True
    return False
```

---

## 4. 现有代码改造

### 4.1 `config.py` — DEFAULT_CONFIG 扩展

```python
"system": {
    "workspace_dir": "~/.agentos/workspace",   # 改为绝对路径
    "database_path": "~/.agentos/agentos.db",
    "granted_paths": [],                         # 新增：预授权目录列表
    # ...
},
```

### 4.2 `main.py` — PathPolicy 初始化

```python
from app.security.path_policy import PathPolicy

# lifespan() 内，ensure_workspace 之后
workspace_path = Path(workspace_dir).expanduser().resolve()
granted_paths = config.get("system.granted_paths", [])
path_policy = PathPolicy(workspace=workspace_path, granted_paths=granted_paths)
app.state.path_policy = path_policy

# ToolRuntime 传入 path_policy
tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry,
                           path_policy=path_policy)
```

### 4.3 `tool_runtime.py` — 持有 PathPolicy

```python
class ToolRuntime:
    def __init__(self, bus_router: BusRouter, registry: ToolRegistry,
                 path_policy: PathPolicy | None = None):       # 新增
        self.bus_router = bus_router
        self.registry = registry
        self.path_policy = path_policy                          # 新增
        self._workers: dict[str, ToolSessionWorker] = {}
```

### 4.4 `tool_worker.py` — 注入 `_path_policy`

在 `_handle_tool_requested` 中，`tool.execute()` 调用前加一行：

```python
# 注入 path_policy
if self.rt.path_policy:
    arguments["_path_policy"] = self.rt.path_policy

result = await asyncio.wait_for(
    tool.execute(**arguments, _session_id=event.session_id),
    timeout=timeout,
)
```

### 4.5 `builtin.py` — ReadFileTool 改造

```python
async def execute(self, **kwargs: Any) -> Any:
    from app.security.path_policy import PathPolicy, PathVerdict

    policy: PathPolicy | None = kwargs.pop("_path_policy", None)
    raw_path = str(kwargs["file_path"])

    if policy:
        verdict = policy.check_read(raw_path)
        if verdict == PathVerdict.DENY:
            return {"success": False, "error": f"系统目录禁止读取: {raw_path}"}
        if verdict == PathVerdict.NEED_GRANT:
            return {
                "success": False,
                "error": f"该目录未授权，请先获得用户许可: {raw_path}",
                "action": "need_grant", "path": raw_path,
            }
        file_path = policy.safe_resolve(raw_path)
    else:
        file_path = Path(raw_path)

    if not file_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    encoding = str(kwargs.get("encoding", "utf-8"))
    start_line = int(kwargs.get("start_line", 1))
    num_lines = kwargs.get("num_lines")
    lines = file_path.read_text(encoding=encoding).splitlines()
    start = max(start_line - 1, 0)
    end = None if num_lines is None else start + int(num_lines)
    selected = lines[start:end]
    return {"file_path": str(file_path), "content": "\n".join(selected)}
```

### 4.6 `builtin.py` — WriteFileTool 改造

`execute` 开头加相同的 policy 检查模式（`check_write`），路径解析改为 `policy.safe_resolve()`。其余写入逻辑不变。

### 4.7 `builtin.py` — BashCommandTool 改造

```python
async def execute(self, **kwargs: Any) -> Any:
    from app.security.path_policy import PathPolicy, PathVerdict

    policy: PathPolicy | None = kwargs.pop("_path_policy", None)
    command = str(kwargs.get("command", ""))
    cwd_raw = kwargs.get("working_dir")

    if policy:
        if cwd_raw:
            verdict = policy.check_cwd(cwd_raw)
            if verdict == PathVerdict.DENY:
                return {"success": False, "error": f"系统目录禁止作为工作目录: {cwd_raw}"}
            if verdict == PathVerdict.NEED_GRANT:
                return {
                    "success": False,
                    "error": f"该目录未授权，请先获得用户许可: {cwd_raw}",
                    "action": "need_grant", "path": cwd_raw,
                }
            cwd = str(policy.safe_resolve(cwd_raw))
        else:
            cwd = str(policy.workspace)    # 默认在 workspace 执行
    else:
        cwd = cwd_raw or "."

    def _run() -> dict[str, Any]:
        proc = subprocess.run(command, cwd=cwd, shell=True,
                              capture_output=True, timeout=300)
        return {
            "return_code": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
        }
    return await asyncio.to_thread(_run)
```

### 4.8 `builtin.py` — 新增 GrantPathTool

```python
class GrantPathTool(Tool):
    """授权工具。risk_level=HIGH → 自动触发 _needs_confirmation。"""

    name = "grant_path"
    description = "授权 Agent 访问指定目录（需先征得用户同意）"
    risk_level = ToolRiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要授权的目录路径"},
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from app.security.path_policy import PathPolicy
        policy: PathPolicy | None = kwargs.pop("_path_policy", None)
        path_str = str(kwargs["path"])
        if not policy:
            return {"success": False, "error": "PathPolicy 未初始化"}
        try:
            resolved = policy.grant(path_str)
            return {"success": True, "granted": str(resolved)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
```

### 4.9 `prompt_builder.py` — Workspace Section

```python
# SystemPromptParams 新增
workspace_dir: str | None = None

# build_system_prompt sections 列表中插入
_build_workspace(params.workspace_dir),    # 在 _build_identity 之后

def _build_workspace(workspace_dir: str | None) -> list[str]:
    if not workspace_dir:
        return []
    return [
        "",
        "## Workspace",
        f"Your working directory is: {workspace_dir}",
        "Relative paths resolve against this directory.",
        "To access files outside workspace, use absolute paths — you may need user permission.",
        "Do NOT maintain a 'current directory' state — each tool call is independent.",
    ]
```

### 4.10 `context_builder.py` — 传入 workspace_dir

构造函数新增 `workspace_dir: str | None = None`，传入 `SystemPromptParams`。

`main.py` 中对应修改：
```python
context_builder = ContextBuilder(
    skill_registry=skill_registry,
    tool_registry=tool_registry,
    workspace_dir=str(workspace_path),    # 新增
)
```

---

## 5. 配置示例

```yaml
# 最小配置
system:
  workspace_dir: "~/.agentos/workspace"

# 预授权常用目录
system:
  workspace_dir: "~/.agentos/workspace"
  granted_paths:
    - "~/projects"
    - "D:\\code"
```

---

## 6. 改动清单

| 文件 | 改动 | 优先级 |
|------|------|:------:|
| `backend/app/security/__init__.py` | 新建空文件 | P0 |
| `backend/app/security/path_policy.py` | 新建 PathPolicy | P0 |
| `backend/app/security/deny_list.py` | 新建黑名单 | P0 |
| `backend/app/core/config.py` | `workspace_dir` 改路径 + `granted_paths` | P0 |
| `backend/app/main.py` | 初始化 PathPolicy，传入 ToolRuntime | P0 |
| `backend/app/runtime/tool_runtime.py` | 构造函数加 `path_policy` | P0 |
| `backend/app/runtime/workers/tool_worker.py` | 注入 `_path_policy` | P0 |
| `backend/app/tools/builtin.py` | 改造 read/write/bash + 新增 GrantPathTool | P0 |
| `backend/app/runtime/prompt_builder.py` | `_build_workspace` section | P1 |
| `backend/app/runtime/context_builder.py` | 传入 `workspace_dir` | P1 |
| `backend/app/workspace/manager.py` | 路径统一 `expanduser().resolve()` | P2 |

兼容性：所有现有子系统（事件总线、双总线、LLM/Agent Runtime、前端、插件）不受影响。无 PathPolicy 时工具行为与当前一致。

---

## 7. 测试

### 7.1 单元测试 (`tests/test_path_policy.py`)

```python
import pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict, PathZone

def test_green_zone_relative():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_write("notes.md") == PathVerdict.ALLOW

def test_green_zone_absolute():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_read("/home/user/.agentos/workspace/AGENTS.md") == PathVerdict.ALLOW

def test_red_zone_need_grant():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_write("/home/user/projects/foo.py") == PathVerdict.NEED_GRANT

def test_red_zone_system_deny():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_read("/etc/passwd") == PathVerdict.DENY

def test_yellow_zone_after_grant():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    policy._granted.append(Path("/home/user/projects").resolve())
    assert policy.check_write("/home/user/projects/app/main.py") == PathVerdict.ALLOW

def test_grant_system_path_rejected():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    with pytest.raises(ValueError):
        policy.grant("/etc")

def test_relative_path_escape():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    verdict = policy.check_read("../../etc/passwd")
    assert verdict in (PathVerdict.DENY, PathVerdict.NEED_GRANT)

def test_resolve_eliminates_dotdot():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    resolved = policy.safe_resolve("subdir/../../../etc/passwd")
    assert ".." not in str(resolved)

def test_revoke():
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    policy._granted.append(Path("/home/user/projects").resolve())
    assert policy.check_write("/home/user/projects/a.py") == PathVerdict.ALLOW
    policy.revoke("/home/user/projects")
    assert policy.check_write("/home/user/projects/a.py") == PathVerdict.NEED_GRANT
```

### 7.2 集成测试

| 场景 | 期望 |
|------|------|
| `write_file` 写入 workspace | 成功 |
| `read_file` 读取外部未授权目录 | 返回 `need_grant` |
| 用户授权后重试 `read_file` | 成功 |
| 读取 `/etc/passwd` 或 `C:\Windows\...` | DENY |
| `bash_command` 不指定 `working_dir` | cwd = workspace |
| `bash_command` 指定未授权 `working_dir` | `need_grant` |

---

## 8. 实施计划

| Phase | 内容 | 工期 |
|-------|------|------|
| 1 | PathPolicy + DenyList + config + main.py + ToolRuntime 注入 + 单测 | 1.5d |
| 2 | ReadFile/WriteFile/BashCommand 改造 + GrantPathTool + 集成测试 | 1d |
| 3 | Prompt workspace section + ContextBuilder 改造 | 0.5d |
| **总计** | | **3d** |

---

## 9. 验收标准

| # | 条件 | P |
|---|------|---|
| S1 | workspace 内 read/write 零摩擦 | P0 |
| S2 | 外部未授权目录返回 `need_grant` | P0 |
| S3 | 系统目录永远 DENY | P0 |
| S4 | `../../etc/passwd` 穿越攻击被 resolve 消解 | P0 |
| S5 | `bash_command` 默认 cwd = workspace | P0 |
| S6 | `grant_path` HIGH risk 触发确认流程 | P0 |
| S7 | 授权后同目录后续操作自动放行 | P0 |
| S8 | config 预授权启动即可用 | P0 |
| S9 | 无 PathPolicy 时行为向后兼容 | P1 |

---

## 10. 后续迭代

| 内容 | 优先级 |
|------|:------:|
| 授权持久化（运行时 grant 写入文件） | P2 |
| ToolWorker 自动拦截 `need_grant` → confirm → grant → 重试 | P2 |
| `GET/DELETE /api/security/grants` 管理端点 | P2 |
| 审计日志（每次判定记录 zone/verdict/path） | P3 |
| 按 session 隔离 grant（子 session/Cron 独立） | P3 |
