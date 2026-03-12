# 实现文档：路径安全策略 (PathPolicy)

> 版本: 1.0
> 日期: 2026-03-11
> 状态: Draft
> 前置: 基于 openclaw 路径安全模型分析得出

---

## 1. 问题陈述

### 1.1 现状

当前 agentos 的文件系统工具（`read_file`、`write_file`、`bash_command`）**没有任何路径边界保护**：

| 工具 | 当前行为 | 风险 |
|------|---------|------|
| `read_file` | `Path(file_path).read_text()` 直接读取 | LLM 可读任意文件（如 `/etc/passwd`） |
| `write_file` | `Path(file_path)` + `mkdir(parents=True)` | LLM 可在任意位置创建文件 |
| `bash_command` | `subprocess.run(cwd=working_dir)` | LLM 可在任意目录执行命令 |

### 1.2 威胁模型

agentos 是**个人助手**，用户即管理员。核心威胁不是"防用户"，而是：

1. **LLM 幻觉**：模型虚构路径，误操作到不相关的文件
2. **Prompt injection**：恶意内容（网页、文档）诱导 LLM 操作系统目录
3. **误解意图**：用户说"删除测试文件"，LLM 误删了系统文件

### 1.3 设计目标

- workspace（`~/.agentos/workspace`）内自由操作，无摩擦
- workspace 外需要用户显式授权，不由 LLM 自行决定
- 系统关键目录永远拒绝访问
- 不引入可变的"当前目录"状态（避免状态腐蚀）

---

## 2. 设计：三区路径模型

### 2.1 概念

```
┌──────────────────────────────────────────┐
│  GREEN Zone (workspace)                   │
│  ~/.agentos/workspace                     │
│  读写自由，无需确认                         │
├──────────────────────────────────────────┤
│  YELLOW Zone (granted paths)              │
│  用户显式授权的外部目录                      │
│  读写允许（授权后自动放行）                   │
├──────────────────────────────────────────┤
│  RED Zone (everything else)               │
│  未授权路径 → 返回 NEED_GRANT 让 Agent 请求授权 │
│  系统目录   → 永远 DENY                     │
└──────────────────────────────────────────┘
```

### 2.2 关键决策

**不维护"当前工作目录"状态。**

参考 openclaw 的设计：系统不维护 cwd，LLM 自己通过对话上下文记住用户想操作的目录，每次工具调用传入完整路径或 workdir 参数。原因：

1. 无可变状态 = 无法被 prompt injection 腐蚀
2. 每次工具调用的路径在日志中清晰可见
3. 现代 LLM 完全有能力在对话窗口内追踪目录上下文

**授权由用户触发，不由 LLM 触发。**

LLM 没有 `grant_path` 工具。当 LLM 尝试操作未授权目录时，PathPolicy 返回 NEED_GRANT，ToolWorker 通过已有的人机确认流程（`confirm_request` 事件）请求用户授权。

---

## 3. 实现方案

### 3.1 新增文件

```
backend/app/security/
├── __init__.py
├── path_policy.py      # PathPolicy 类
└── deny_list.py        # 系统目录黑名单
```

### 3.2 `path_policy.py`

```python
"""三区路径安全策略

GREEN  = workspace 内，自由读写
YELLOW = 用户已授权的外部目录
RED    = 未授权目录 (NEED_GRANT) 或系统目录 (DENY)
"""

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
    """无状态路径策略判定器。

    不持有可变的 project_dir / cwd。
    相对路径一律基于 workspace 解析。
    """

    def __init__(
        self,
        workspace: Path,
        granted_paths: list[str] | None = None,
    ):
        self.workspace = workspace.expanduser().resolve()
        self._granted: list[Path] = []
        for p in granted_paths or []:
            try:
                resolved = Path(p).expanduser().resolve()
                if resolved.is_dir():
                    self._granted.append(resolved)
            except (OSError, ValueError):
                logger.warning("Invalid granted path, skipping: %s", p)

    # ── 授权管理 ──

    def grant(self, dir_path: str) -> Path:
        """用户显式授权一个目录（经 confirm_request 流程后调用）。"""
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
        logger.info("Path revoked: %s", resolved)

    @property
    def granted_paths(self) -> list[str]:
        return [str(p) for p in self._granted]

    # ── 区域判定 ──

    def classify(self, target: Path) -> PathZone:
        resolved = target.expanduser().resolve()
        if _is_within(resolved, self.workspace):
            return PathZone.GREEN
        for granted in self._granted:
            if _is_within(resolved, granted):
                return PathZone.YELLOW
        return PathZone.RED

    # ── 操作判定 ──

    def check_read(self, file_path: str) -> PathVerdict:
        resolved = self._resolve(file_path)
        zone = self.classify(resolved)
        if zone in (PathZone.GREEN, PathZone.YELLOW):
            return PathVerdict.ALLOW
        if is_system_path(resolved):
            return PathVerdict.DENY
        return PathVerdict.NEED_GRANT

    def check_write(self, file_path: str) -> PathVerdict:
        resolved = self._resolve(file_path)
        zone = self.classify(resolved)
        if zone in (PathZone.GREEN, PathZone.YELLOW):
            return PathVerdict.ALLOW
        if is_system_path(resolved):
            return PathVerdict.DENY
        return PathVerdict.NEED_GRANT

    def check_cwd(self, dir_path: str) -> PathVerdict:
        """bash_command 的 working_dir 验证。"""
        resolved = self._resolve(dir_path)
        zone = self.classify(resolved)
        if zone in (PathZone.GREEN, PathZone.YELLOW):
            return PathVerdict.ALLOW
        if is_system_path(resolved):
            return PathVerdict.DENY
        return PathVerdict.NEED_GRANT

    def safe_resolve(self, file_path: str) -> Path:
        """将用户输入解析为绝对路径（不做策略判定）。"""
        return self._resolve(file_path)

    # ── 内部 ──

    def _resolve(self, user_path: str) -> Path:
        """相对路径基于 workspace 解析，绝对路径直接 resolve。"""
        p = Path(user_path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace / p).resolve()


def _is_within(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False
```

### 3.3 `deny_list.py`

```python
"""系统目录黑名单。

即使用户确认也永远拒绝访问这些路径。
"""

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
    """判断路径是否在系统目录黑名单中。"""
    resolved = str(target.resolve())

    deny_list = _WIN_DENY if platform.system() == "Windows" else _UNIX_DENY

    for deny in deny_list:
        if platform.system() == "Windows":
            if resolved.lower().startswith(deny.lower()):
                return True
        else:
            if resolved.startswith(deny):
                return True

    return False
```

---

## 4. 改造现有代码

### 4.1 配置扩展 (`config.py`)

在 `DEFAULT_CONFIG` 中新增：

```python
DEFAULT_CONFIG = {
    "system": {
        "workspace_dir": "~/.agentos/workspace",   # 改为绝对路径
        "database_path": "~/.agentos/agentos.db",
        "granted_paths": [],                         # 预授权目录列表
        # ...
    },
    # ...
}
```

同时在所有使用 `workspace_dir` 的地方统一加 `expanduser().resolve()`。

### 4.2 PathPolicy 初始化 (`main.py`)

在 `lifespan()` 中初始化 PathPolicy 并挂载到 `app.state`：

```python
from app.security.path_policy import PathPolicy

# 在 lifespan() 内，ensure_workspace 之后
workspace_path = Path(workspace_dir).expanduser().resolve()
granted_paths = config.get("system.granted_paths", [])
path_policy = PathPolicy(workspace=workspace_path, granted_paths=granted_paths)
app.state.path_policy = path_policy
```

### 4.3 ToolWorker 注入 PathPolicy (`tool_worker.py`)

改造 `_handle_tool_requested`，在执行工具前注入 PathPolicy 实例：

```python
async def _handle_tool_requested(self, event: EventEnvelope) -> None:
    # ... 现有逻辑 ...

    # 注入 path_policy（从 app.state 或 runtime 获取）
    arguments["_path_policy"] = self.rt.path_policy

    result = await asyncio.wait_for(
        tool.execute(**arguments, _session_id=event.session_id),
        timeout=timeout,
    )
```

### 4.4 改造 `ReadFileTool`

```python
class ReadFileTool(Tool):
    name = "read_file"
    description = "读取文本文件"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径（相对路径基于 workspace 解析）"},
            "encoding": {"type": "string", "default": "utf-8"},
            "start_line": {"type": "integer", "default": 1},
            "num_lines": {"type": "integer"},
        },
        "required": ["file_path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        policy: PathPolicy = kwargs.pop("_path_policy", None)
        raw_path = str(kwargs["file_path"])

        if policy:
            verdict = policy.check_read(raw_path)
            if verdict == PathVerdict.DENY:
                return {"success": False, "error": f"系统目录禁止读取: {raw_path}"}
            if verdict == PathVerdict.NEED_GRANT:
                return {
                    "success": False,
                    "error": f"该目录未授权，请先获得用户许可: {raw_path}",
                    "action": "need_grant",
                    "path": raw_path,
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

### 4.5 改造 `WriteFileTool`

```python
class WriteFileTool(Tool):
    name = "write_file"
    description = "写入文本文件"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径（相对路径基于 workspace 解析）"},
            "content": {"type": "string", "description": "要写入的内容"},
            "mode": {
                "type": "string",
                "enum": ["write", "append", "insert"],
                "default": "write",
            },
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["file_path", "content"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        policy: PathPolicy = kwargs.pop("_path_policy", None)
        raw_path = str(kwargs["file_path"])

        if policy:
            verdict = policy.check_write(raw_path)
            if verdict == PathVerdict.DENY:
                return {"success": False, "error": f"系统目录禁止写入: {raw_path}"}
            if verdict == PathVerdict.NEED_GRANT:
                return {
                    "success": False,
                    "error": f"该目录未授权，请先获得用户许可: {raw_path}",
                    "action": "need_grant",
                    "path": raw_path,
                }
            file_path = policy.safe_resolve(raw_path)
        else:
            file_path = Path(raw_path)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = str(kwargs.get("content", ""))
        mode = str(kwargs.get("mode", "write"))
        # ... 其余写入逻辑不变 ...
```

### 4.6 改造 `BashCommandTool`

```python
class BashCommandTool(Tool):
    name = "bash_command"
    description = "执行 shell 命令"
    risk_level = ToolRiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "working_dir": {"type": "string", "description": "工作目录（默认 workspace）"},
        },
        "required": ["command"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        policy: PathPolicy = kwargs.pop("_path_policy", None)
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
                        "action": "need_grant",
                        "path": cwd_raw,
                    }
                cwd = str(policy.safe_resolve(cwd_raw))
            else:
                cwd = str(policy.workspace)
        else:
            cwd = cwd_raw or "."

        def _run() -> dict[str, Any]:
            proc = subprocess.run(
                command, cwd=cwd, shell=True,
                capture_output=True, timeout=300,
            )
            return {
                "return_code": proc.returncode,
                "stdout": proc.stdout.decode("utf-8", errors="replace"),
                "stderr": proc.stderr.decode("utf-8", errors="replace"),
            }

        return await asyncio.to_thread(_run)
```

### 4.7 授权流程（复用已有 confirm_request）

当工具返回 `"action": "need_grant"` 时，Agent 应请求用户确认。有两种接入方式：

**方式 A：LLM 自动处理（推荐，零改动）**

LLM 收到 `need_grant` 结果后，自然语言询问用户：

```
Agent: "我需要访问 D:\projects\my-app 目录来完成你的请求，是否允许？"
User:  "允许"
Agent: 调用内部授权 API → policy.grant("D:\\projects\\my-app")
Agent: 重试原工具调用 → 成功
```

需要给 Agent 一个授权工具：

```python
class GrantPathTool(Tool):
    """仅在用户明确同意后调用。"""
    name = "grant_path"
    description = "授权 Agent 访问指定目录（需先征得用户同意）"
    risk_level = ToolRiskLevel.HIGH  # 触发 confirm_request
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要授权的目录路径"},
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        policy: PathPolicy = kwargs.pop("_path_policy", None)
        path_str = str(kwargs["path"])
        if not policy:
            return {"success": False, "error": "PathPolicy not available"}
        try:
            resolved = policy.grant(path_str)
            return {"success": True, "granted": str(resolved)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
```

因为 `risk_level = HIGH`，已有的 `_needs_confirmation` 逻辑会自动弹出用户确认。用户拒绝 → 授权失败 → LLM 无法操作该目录。

**方式 B：系统级拦截（更安全，改动较大）**

在 ToolWorker 层拦截 `need_grant` 结果，自动发出 `confirm_request`，用户确认后自动重试。此方式下 LLM 无法绕过确认流程，但实现复杂度更高，建议后续迭代。

---

## 5. System Prompt 改造

在 `prompt_builder.py` 中添加 Workspace Section，告诉 LLM workspace 路径和行为规范：

```python
def _build_workspace(workspace_dir: str | None) -> list[str]:
    if not workspace_dir:
        return []
    return [
        "",
        "## Workspace",
        f"Your working directory is: {workspace_dir}",
        "Treat this as the default root for file operations.",
        "Relative paths resolve against this directory.",
        "To access files outside workspace, use absolute paths — you will be asked to get user permission if needed.",
        "Do NOT maintain a 'current directory' — each tool call is independent.",
    ]
```

在 `SystemPromptParams` 中加入 `workspace_dir: str | None = None`，在 `build_system_prompt` 中调用此 builder。

---

## 6. 配置示例

### 6.1 最小配置（仅 workspace）

```yaml
system:
  workspace_dir: "~/.agentos/workspace"
```

所有文件操作限制在 workspace 内。用户对话中授权的目录仅在 session 内有效。

### 6.2 预授权常用目录

```yaml
system:
  workspace_dir: "~/.agentos/workspace"
  granted_paths:
    - "~/projects"
    - "D:\\code"
```

这些目录启动即授权，无需每次对话确认。

---

## 7. 数据流

### 7.1 workspace 内操作（零摩擦）

```
User: "在 workspace 里创建 notes.md"
  → LLM: write_file(file_path="notes.md", content="...")
  → ToolWorker: inject _path_policy
  → WriteFileTool.execute:
      policy.check_write("notes.md") → ALLOW (GREEN zone)
      policy.safe_resolve("notes.md") → ~/.agentos/workspace/notes.md
      写入成功
```

### 7.2 外部目录操作（授权流程）

```
User: "帮我在 D:\projects\my-app 里创建 README.md"
  → LLM: write_file(file_path="D:\\projects\\my-app\\README.md", content="...")
  → WriteFileTool.execute:
      policy.check_write("D:\\projects\\my-app\\README.md") → NEED_GRANT
      return {"action": "need_grant", "path": "D:\\projects\\my-app\\README.md"}
  → LLM 收到结果，回复用户: "我需要访问 D:\projects\my-app 目录，是否允许？"
  → User: "允许"
  → LLM: grant_path(path="D:\\projects\\my-app")
      → _needs_confirmation → HIGH risk → confirm_request 事件
      → User 确认
      → policy.grant("D:\\projects\\my-app") → YELLOW zone
  → LLM: write_file(file_path="D:\\projects\\my-app\\README.md", content="...")
      → policy.check_write → ALLOW (YELLOW zone)
      → 写入成功
```

### 7.3 系统目录操作（永远拒绝）

```
User: "看看 /etc/passwd"（或被 prompt injection 诱导）
  → LLM: read_file(file_path="/etc/passwd")
  → ReadFileTool.execute:
      policy.check_read("/etc/passwd") → DENY (system path)
      return {"error": "系统目录禁止读取: /etc/passwd"}
```

### 7.4 后续操作自动放行

```
User: "再帮我看看那个项目的 package.json"
  → LLM 记住之前操作的目录，调用:
     read_file(file_path="D:\\projects\\my-app\\package.json")
  → policy.check_read → ALLOW (YELLOW zone，已授权)
  → 读取成功
```

---

## 8. 改动清单

| 文件 | 改动 | 优先级 |
|------|------|:------:|
| `backend/app/security/__init__.py` | 新建空文件 | P0 |
| `backend/app/security/path_policy.py` | 新建 PathPolicy 类 | P0 |
| `backend/app/security/deny_list.py` | 新建系统目录黑名单 | P0 |
| `backend/app/core/config.py` | `workspace_dir` 改为 `~/.agentos/workspace`，新增 `granted_paths` | P0 |
| `backend/app/tools/builtin.py` | 改造 read_file / write_file / bash_command | P0 |
| `backend/app/main.py` | 初始化 PathPolicy，挂载到 app.state | P0 |
| `backend/app/runtime/workers/tool_worker.py` | 注入 `_path_policy` 到工具参数 | P0 |
| `backend/app/tools/builtin.py` | 新增 `GrantPathTool` | P1 |
| `backend/app/runtime/prompt_builder.py` | 新增 workspace section | P1 |
| `backend/app/runtime/context_builder.py` | 传入 workspace_dir 给 prompt builder | P1 |
| `backend/app/api/workspace.py` | 使用 expanduser().resolve() | P2 |

---

## 9. 测试要点

### 9.1 单元测试 (`test_path_policy.py`)

```python
def test_green_zone_relative_path():
    """相对路径解析到 workspace 内 → ALLOW"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_write("notes.md") == PathVerdict.ALLOW

def test_green_zone_absolute_path():
    """workspace 内的绝对路径 → ALLOW"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_read("/home/user/.agentos/workspace/AGENTS.md") == PathVerdict.ALLOW

def test_red_zone_need_grant():
    """workspace 外的普通目录 → NEED_GRANT"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_write("/home/user/projects/foo.py") == PathVerdict.NEED_GRANT

def test_red_zone_system_deny():
    """系统目录 → DENY（永远）"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_read("/etc/passwd") == PathVerdict.DENY

def test_yellow_zone_after_grant():
    """授权后 → ALLOW"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    policy.grant("/home/user/projects")
    assert policy.check_write("/home/user/projects/app/main.py") == PathVerdict.ALLOW

def test_grant_system_path_rejected():
    """授权系统目录 → 抛异常"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    with pytest.raises(ValueError):
        policy.grant("/etc")

def test_symlink_escape():
    """symlink 逃逸 → resolve() 后判定"""
    # 创建 workspace/link -> /etc，resolve 后应落在 RED zone
    ...

def test_relative_path_escape():
    """../../etc/passwd 不应逃逸"""
    policy = PathPolicy(workspace=Path("/home/user/.agentos/workspace"))
    assert policy.check_read("../../etc/passwd") == PathVerdict.DENY

def test_config_granted_paths():
    """配置预授权的目录启动即可用"""
    policy = PathPolicy(
        workspace=Path("/home/user/.agentos/workspace"),
        granted_paths=["~/projects"],
    )
    assert policy.check_write("/home/user/projects/foo.py") == PathVerdict.ALLOW
```

### 9.2 集成测试

- 通过 WebSocket 发消息 → Agent 调用 write_file 写入 workspace → 成功
- 通过 WebSocket 发消息 → Agent 调用 write_file 写入外部目录 → 返回 need_grant → Agent 请求确认 → 用户确认 → 重试成功
- bash_command 不指定 working_dir → cwd 默认为 workspace

---

## 10. 不做的事

| 不做 | 原因 |
|------|------|
| 维护 session 级 cwd / project_dir | 引入可变状态，增加 prompt injection 攻击面 |
| 给 LLM 提供 `set_working_dir` 工具 | LLM 可自行切换 → 被 injection 利用 |
| 读写分级策略（只读 vs 读写） | 个人助手场景下过度设计，授权粒度够用 |
| Docker 沙箱 | 当前是单机部署，Docker 沙箱复杂度不匹配 |
| 按文件扩展名限制 | 现有 `allowed_extensions` 配置已有基本保护 |

---

## 11. 后续迭代

- **P2: 授权持久化**：当前 grant 仅在进程生命周期内有效。后续可将运行时 grant 写入 config.yml 或独立持久化文件。
- **P2: ToolWorker 自动重试**：系统级拦截 `need_grant`，自动发 confirm → grant → 重试，无需 LLM 参与。
- **P3: 审计日志**：记录每次路径判定结果（zone / verdict / path），用于安全审计。
- **P3: 按 session 隔离 grant**：非主 session（如 cron、group）使用独立的 grant 集合。
