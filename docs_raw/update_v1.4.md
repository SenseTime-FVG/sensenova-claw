# CLI 工具增强

> 版本: v1.4
> 日期: 2026-03-12
> 状态: Draft
> 前置: v1.0（多 Agent & Workflow）, v1.1（Skills 市场）, v1.2（PathPolicy）, v1.3（Per-Agent 目录）, v0.5（双总线 + Session 持久化）, v0.8（Cron & Heartbeat）

---

## 1. 问题陈述

### 1.1 现状

当前 `cli_client.py` 是一个极简的 WebSocket 客户端：

- 连接 WebSocket，创建**单个匿名 session**
- 发送文本消息，接收 `tool_execution` / `tool_result` / `turn_completed`
- 命令仅有 `/quit` 和 `/`
- **依赖 `termios`，无法在 Windows 运行**
- 无会话管理、无 Agent 选择、无 Workflow 支持、无权限确认

### 1.2 差距分析

| 系统能力（已设计/已实现） | CLI 现状 | 差距 |
|--------------------------|---------|------|
| Session 持久化 + 恢复（v0.5） | 单个匿名 session，退出即丢 | 无法列出/切换/恢复历史会话 |
| 多 Agent（v1.0） | 只用 default agent | 无法选择 Agent 创建会话 |
| Workflow 编排（v1.0） | 不支持 | 无法触发/监控 Workflow |
| 工具权限确认（v0.5 工具增强） | 不支持 | HIGH 风险工具无法确认 |
| PathPolicy 路径授权（v1.2） | 不支持 | `need_grant` 无交互 |
| Skills 管理（v1.1） | 不支持 | 无法查看/搜索/安装 |
| Cron / Heartbeat（v0.8） | 不支持 | 无法管理定时任务 |
| 事件标准化 + 双总线（v0.5） | 仅展示 3 种事件 | 无调试模式 |
| Per-Agent 目录（v1.3） | 不感知 | 无法查看 Agent 文件 |
| Windows 兼容 | `termios` Unix-only | 完全不可用 |

### 1.3 目标

将 CLI 从"能聊天"提升到**与 Web 前端对等的全功能客户端**，同时利用终端特有的效率优势（快捷键、管道、脚本化）。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **命令即 API** | 每个 `/` 命令对应一个后端 REST API 或 WebSocket 消息 |
| **渐进披露** | 基础用户只需 `/new`、`/quit`；高级命令在 `/` 菜单中发现 |
| **跨平台** | Windows / macOS / Linux 均可运行 |
| **脚本友好** | 支持 `--non-interactive` 模式，stdin/stdout 可管道 |
| **事件驱动显示** | 所有展示内容基于 WebSocket 事件，不轮询 REST API |

---

## 3. 架构改造

### 3.1 从单文件到模块

当前 `cli_client.py` 是一个 220 行的单文件。随着功能增加需要拆分：

```
backend/
├── cli_client.py                  # 入口（保持向后兼容）
└── cli/
    ├── __init__.py
    ├── app.py                     # CLIApp 主类（生命周期、WebSocket 连接）
    ├── commands.py                # 命令注册与分发
    ├── session_commands.py        # 会话管理命令
    ├── agent_commands.py          # Agent 相关命令
    ├── workflow_commands.py       # Workflow 相关命令
    ├── tool_commands.py           # 工具/Skills 相关命令
    ├── system_commands.py         # 配置/Cron/调试命令
    ├── event_handler.py           # WebSocket 事件处理与显示
    ├── confirmation.py            # 工具确认 + 路径授权交互
    ├── display.py                 # Rich 格式化输出
    └── input.py                   # 跨平台输入（替代 termios）
```

### 3.2 CLIApp 主类

```python
class CLIApp:
    """CLI 客户端主类，管理 WebSocket 连接和命令循环"""

    def __init__(self, host: str, port: int, agent_id: str | None = None):
        self.host = host
        self.port = port
        self.default_agent_id = agent_id
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.current_session_id: str | None = None
        self.current_agent_id: str = agent_id or "default"
        self.debug_mode: bool = False
        self.command_registry: CommandRegistry = CommandRegistry()
        self.event_handler: EventHandler = EventHandler(self)
        self.console: Console = Console()

    async def connect(self) -> None:
        """建立 WebSocket 连接"""
        pass

    async def create_session(self, agent_id: str | None = None) -> str:
        """创建新会话（指定 Agent）"""
        pass

    async def switch_session(self, session_id: str) -> None:
        """切换到已有会话"""
        pass

    async def send_message(self, content: str) -> None:
        """发送用户消息"""
        pass

    async def send_ws(self, msg: dict) -> None:
        """发送 WebSocket 消息"""
        pass

    async def call_api(self, method: str, path: str, **kwargs) -> dict:
        """调用后端 REST API（用于管理操作）"""
        pass

    async def run(self) -> None:
        """主循环：读取输入 → 解析命令 → 执行"""
        pass
```

### 3.3 命令注册机制

```python
class CommandRegistry:
    """命令注册表，支持命令分组和自动补全"""

    def register(self, name: str, handler: Callable, *,
                 group: str = "general",
                 description: str = "",
                 usage: str = "",
                 aliases: list[str] | None = None) -> None:
        pass

    def dispatch(self, raw_input: str, app: CLIApp) -> Coroutine:
        """解析输入并分派到对应命令处理器"""
        pass

    def get_completions(self, prefix: str) -> list[str]:
        """Tab 自动补全"""
        pass

    def render_help(self, group: str | None = None) -> str:
        """渲染帮助菜单"""
        pass
```

### 3.4 跨平台输入

```python
# cli/input.py

async def read_user_input(prompt: str = "You") -> str:
    """跨平台用户输入
    
    - Unix (isatty): raw mode 即时命令菜单（现有逻辑）
    - Windows / 非 TTY: prompt_toolkit 或 fallback 到 input()
    """
    if sys.platform == "win32":
        return await _read_windows(prompt)
    if sys.stdin.isatty():
        return await _read_unix_raw(prompt)
    return await _read_fallback(prompt)


async def _read_windows(prompt: str) -> str:
    """Windows 输入：使用 msvcrt 或 prompt_toolkit"""
    try:
        from prompt_toolkit import PromptSession
        session = PromptSession()
        return await session.prompt_async(f"{prompt}: ")
    except ImportError:
        return await asyncio.to_thread(input, f"{prompt}: ")


async def _read_unix_raw(prompt: str) -> str:
    """Unix raw mode 输入（现有 termios 逻辑）"""
    # 移植现有 read_user_input 逻辑
    pass
```

---

## 4. 命令清单

### 4.1 会话管理

| 命令 | 别名 | 说明 | 实现方式 |
|------|------|------|----------|
| `/new [agent_id]` | - | 创建新会话，可选指定 Agent | WS: `create_session` |
| `/sessions` | `/ls` | 列出历史会话（ID + 标题 + Agent + 最后活跃） | REST: `GET /api/sessions` |
| `/switch <session_id>` | `/sw` | 切换到已有会话，加载历史消息 | WS: `switch_session` |
| `/delete <session_id>` | `/del` | 删除指定会话 | REST: `DELETE /api/sessions/{id}` |
| `/rename <title>` | - | 重命名当前会话 | REST: `PATCH /api/sessions/{id}` |
| `/history [n]` | `/h` | 显示当前会话最近 n 条消息（默认 20） | REST: `GET /api/sessions/{id}/messages` |
| `/current` | - | 显示当前会话信息 | 本地状态 |

**`/sessions` 输出格式**：

```
 ID              Agent           标题                     最后活跃
─────────────────────────────────────────────────────────────────────
 sess_abc123 *   default         帮我搜索英超联赛...       2 分钟前
 sess_def456     research-agent  RAG 技术方案调研          1 小时前
 sess_ghi789     default         代码审查                  3 天前
```

### 4.2 Agent 管理

| 命令 | 说明 | 实现方式 |
|------|------|----------|
| `/agents` | 列出所有可用 Agent | REST: `GET /api/agents` |
| `/agent <id>` | 查看某 Agent 详情（model / prompt / tools / skills） | REST: `GET /api/agents/{id}` |

**`/agents` 输出格式**：

```
 ID                名称              模型              描述
───────────────────────────────────────────────────────────────
 default           Default Agent     gpt-4o-mini       默认 AI Agent
 research-agent    Research Agent    gpt-4o            专注于信息调研
 code-reviewer     Code Reviewer     gpt-4o            代码审查专家
```

### 4.3 Workflow 管理

| 命令 | 说明 | 实现方式 |
|------|------|----------|
| `/workflows` | 列出所有可用 Workflow | REST: `GET /api/workflows` |
| `/workflow <id>` | 查看 Workflow 定义（节点 + 边） | REST: `GET /api/workflows/{id}` |
| `/run <wf_id> <input>` | 触发 Workflow 执行 | WS: `run_workflow` |
| `/runs [wf_id]` | 查看执行记录 | REST: `GET /api/workflows/runs` |

**Workflow 实时状态显示**：

事件处理器需监听 Workflow 事件并实时渲染：

```python
# cli/event_handler.py

async def handle_workflow_event(self, data: dict) -> None:
    msg_type = data["type"]
    payload = data["payload"]

    if msg_type == "workflow.node_started":
        self.console.print(
            f"  🔄 [{payload['node_id']}] {payload.get('agent_id', '')} 开始执行..."
        )
    elif msg_type == "workflow.node_completed":
        status = payload["status"]
        icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏭️"
        self.console.print(
            f"  {icon} [{payload['node_id']}] {status}"
        )
        if payload.get("output_preview"):
            self.console.print(
                f"     {payload['output_preview'][:100]}...", style="dim"
            )
    elif msg_type == "workflow.run_completed":
        self.console.print(
            f"\n📋 Workflow {payload.get('status', '')} (run: {payload['run_id']})"
        )
```

### 4.4 工具权限确认

当后端发送 `tool.confirmation_requested` 事件时，CLI 需要中断当前等待，向用户展示确认请求并收集响应。

```python
# cli/confirmation.py

class ConfirmationHandler:
    """处理工具执行确认和路径授权"""

    def __init__(self, app: CLIApp):
        self.app = app
        self._pending: dict[str, asyncio.Future] = {}

    async def handle_confirmation_requested(self, payload: dict) -> None:
        """收到确认请求，向用户展示并等待输入"""
        tool_call_id = payload["tool_call_id"]
        tool_name = payload["tool_name"]
        risk_level = payload.get("risk_level", "high")
        arguments = payload.get("arguments", {})

        self.app.console.print()
        self.app.console.print(
            f"  ⚠️  [bold yellow]{tool_name}[/] 请求执行 ({risk_level} 风险):"
        )
        for k, v in arguments.items():
            if k.startswith("_"):
                continue
            v_str = str(v)
            if len(v_str) > 200:
                v_str = v_str[:200] + "..."
            self.app.console.print(f"     {k}: {v_str}", style="dim")

        response = await asyncio.to_thread(input, "  是否批准？[y/N]: ")
        approved = response.strip().lower() in ("y", "yes")

        await self.app.send_ws({
            "type": "tool_confirmation_response",
            "session_id": self.app.current_session_id,
            "payload": {
                "tool_call_id": tool_call_id,
                "approved": approved,
            },
        })

        icon = "✅" if approved else "❌"
        self.app.console.print(f"  {icon} {'已批准' if approved else '已拒绝'}")
```

### 4.5 路径授权交互

当工具返回 `need_grant` 错误时，CLI 应自动提示用户是否授权。

```python
# cli/confirmation.py（续）

async def handle_need_grant(self, payload: dict) -> None:
    """处理路径授权请求"""
    path = payload.get("path", "")
    tool_name = payload.get("tool_name", "")

    self.app.console.print()
    self.app.console.print(
        f"  🔒 [bold]{tool_name}[/] 请求访问目录: [cyan]{path}[/]"
    )
    response = await asyncio.to_thread(input, "  是否授权？[y/N]: ")

    if response.strip().lower() in ("y", "yes"):
        self.app.console.print(f"  ✅ 用户同意授权 {path}")
    else:
        self.app.console.print(f"  🚫 用户拒绝授权 {path}")
```

### 4.6 Skills 管理

| 命令 | 说明 | 实现方式 |
|------|------|----------|
| `/skills` | 列出已安装 skills（按 builtin/workspace/installed 分组） | REST: `GET /api/skills` |
| `/skills search <query>` | 搜索本地 + 远程市场 | REST: `GET /api/skills/search?q=...` |
| `/skills install <source> <id>` | 从市场安装 skill | REST: `POST /api/skills/install` |
| `/skills uninstall <name>` | 卸载已安装的 skill | REST: `POST /api/skills/uninstall` |
| `/skills toggle <name>` | 启用/禁用 skill | REST: `POST /api/skills/{name}/toggle` |

### 4.7 Cron / Heartbeat 管理

| 命令 | 说明 | 实现方式 |
|------|------|----------|
| `/cron list` | 列出定时任务 | REST: `GET /api/cron/jobs` |
| `/cron add <name> --every <interval> --message <msg>` | 创建定时任务 | REST: `POST /api/cron/jobs` |
| `/cron remove <id>` | 删除定时任务 | REST: `DELETE /api/cron/jobs/{id}` |
| `/cron enable <id>` | 启用定时任务 | REST: `PATCH /api/cron/jobs/{id}` |
| `/cron disable <id>` | 禁用定时任务 | REST: `PATCH /api/cron/jobs/{id}` |
| `/cron runs [job_id]` | 查看执行历史 | REST: `GET /api/cron/runs` |
| `/heartbeat status` | 查看心跳状态 | REST: `GET /api/heartbeat/status` |
| `/heartbeat trigger` | 手动触发一次心跳 | REST: `POST /api/heartbeat/trigger` |

### 4.8 系统与调试

| 命令 | 说明 | 实现方式 |
|------|------|----------|
| `/config` | 查看当前配置摘要 | REST: `GET /api/config` |
| `/tools` | 列出已注册工具 | REST: `GET /api/tools` |
| `/debug on/off` | 开启/关闭事件调试模式 | 本地状态 |
| `/events [n]` | 显示当前 session 最近 n 条事件 | REST: `GET /api/sessions/{id}/events` |
| `/memory` | 查看 MEMORY.md 内容摘要 | REST: `GET /api/agents/{id}/files/MEMORY.md` |
| `/memory search <query>` | 搜索记忆 | REST: `GET /api/memory/search?q=...` |
| `/workspace` | 查看当前 Agent 的 workspace 文件列表 | REST: `GET /api/workspace/{agent_id}/files` |
| `/quit` | 退出 CLI | 本地 |
| `/help` | 显示完整帮助 | 本地 |

**调试模式**：

开启 `/debug on` 后，所有 WebSocket 事件以灰色前缀显示：

```python
# cli/event_handler.py

async def handle_event(self, data: dict) -> None:
    msg_type = data.get("type", "")

    if self.app.debug_mode:
        trace_id = data.get("trace_id", "")[:8]
        payload_preview = str(data.get("payload", {}))[:80]
        self.app.console.print(
            f"  [dim][DEBUG] {msg_type}  trace={trace_id}  {payload_preview}[/dim]"
        )

    if msg_type == "tool_execution":
        await self._handle_tool_execution(data)
    elif msg_type == "tool_result":
        await self._handle_tool_result(data)
    elif msg_type == "turn_completed":
        await self._handle_turn_completed(data)
    elif msg_type == "tool_confirmation_requested":
        await self.confirmation.handle_confirmation_requested(data.get("payload", {}))
    elif msg_type.startswith("workflow."):
        await self.handle_workflow_event(data)
    elif msg_type == "delegate_started":
        await self._handle_delegate_started(data)
    elif msg_type == "delegate_completed":
        await self._handle_delegate_completed(data)
```

---

## 5. 命令行参数

```python
# cli_client.py 入口

import argparse

parser = argparse.ArgumentParser(description="AgentOS CLI Client")
parser.add_argument("--host", default="localhost", help="后端主机地址")
parser.add_argument("--port", type=int, default=8000, help="后端端口")
parser.add_argument("--agent", default=None, help="默认 Agent ID")
parser.add_argument("--session", default=None, help="恢复指定 session")
parser.add_argument("--debug", action="store_true", help="启动时开启调试模式")
parser.add_argument("--non-interactive", action="store_true",
                    help="非交互模式：从 stdin 读取，结果输出到 stdout")
parser.add_argument("--execute", "-e", default=None,
                    help="执行单条消息后退出（脚本模式）")
```

**使用示例**：

```bash
# 基础使用
python cli_client.py

# 指定 Agent
python cli_client.py --agent research-agent

# 恢复会话
python cli_client.py --session sess_abc123

# 脚本模式：执行单条指令
python cli_client.py -e "搜索最新的 AI 论文" --agent research-agent

# 管道模式
echo "帮我总结这段代码" | python cli_client.py --non-interactive

# 远程连接
python cli_client.py --host 192.168.1.100 --port 8000
```

---

## 6. WebSocket 协议扩展

CLI 需要后端 WebSocket 支持以下新消息类型：

### 6.1 会话管理

```python
# 创建会话（扩展：支持 agent_id）
{"type": "create_session", "payload": {"agent_id": "research-agent"}}

# 切换会话
{"type": "switch_session", "payload": {"session_id": "sess_abc123"}}
# → 响应：{"type": "session_switched", "session_id": "...", "history": [...]}

# 列出会话（也可走 REST）
{"type": "list_sessions"}
# → 响应：{"type": "session_list", "sessions": [...]}
```

### 6.2 Workflow 触发

```python
# 触发 Workflow
{
    "type": "run_workflow",
    "session_id": "sess_xxx",
    "payload": {
        "workflow_id": "plan-execute-review",
        "input": "帮我调研 RAG 技术方案"
    }
}
```

### 6.3 工具确认响应

```python
# 用户确认响应
{
    "type": "tool_confirmation_response",
    "session_id": "sess_xxx",
    "payload": {
        "tool_call_id": "call_abc",
        "approved": true
    }
}
```

---

## 7. `/help` 菜单设计

```
📋 AgentOS CLI — 可用命令

  会话
    /new [agent_id]         创建新会话（可选指定 Agent）
    /sessions               列出历史会话
    /switch <id>            切换到指定会话
    /delete <id>            删除会话
    /rename <title>         重命名当前会话
    /history [n]            显示最近 n 条消息
    /current                当前会话信息

  Agent & Workflow
    /agents                 列出所有 Agent
    /agent <id>             查看 Agent 详情
    /workflows              列出所有 Workflow
    /workflow <id>          查看 Workflow 详情
    /run <wf_id> <input>    触发 Workflow

  工具 & Skills
    /tools                  列出已注册工具
    /skills                 列出已安装 Skills
    /skills search <q>      搜索 Skills
    /skills install <s> <id> 安装 Skill
    /skills toggle <name>   启用/禁用 Skill

  记忆
    /memory                 查看 MEMORY.md
    /memory search <q>      搜索记忆

  系统
    /config                 查看配置摘要
    /workspace              查看 workspace 文件
    /cron list              定时任务列表
    /heartbeat status       心跳状态
    /debug on|off           事件调试模式
    /events [n]             查看最近事件

  通用
    /help                   显示此帮助
    /quit                   退出

  💡 输入 / 即时弹出命令菜单；直接输入文本发送消息
```

---

## 8. 新增依赖

| 包名 | 版本 | 用途 | 必需 |
|------|------|------|:----:|
| `prompt_toolkit` | `>=3.0` | Windows 跨平台输入 + Tab 补全 | 推荐 |
| `httpx` | `>=0.27` | REST API 调用（async） | 是 |

`websockets` 和 `rich` 已在现有依赖中。

---

## 9. 实施计划

| Phase | 内容 | 工期 | 优先级 |
|-------|------|------|:------:|
| **1** | 模块化拆分 + CLIApp + CommandRegistry + 跨平台输入 | 1.5d | P0 |
| **2** | 会话管理命令（/new /sessions /switch /history） | 1d | P0 |
| **3** | 工具权限确认 + 路径授权交互 | 0.5d | P0 |
| **4** | 多 Agent 命令（/agents /agent /new agent_id） | 0.5d | P1 |
| **5** | Workflow 命令 + 实时状态显示 | 1d | P1 |
| **6** | 调试模式 + 委托事件显示 | 0.5d | P1 |
| **7** | Skills 管理命令 | 0.5d | P2 |
| **8** | Cron / Heartbeat 命令 | 0.5d | P2 |
| **9** | 命令行参数 + 脚本模式 + 非交互模式 | 0.5d | P2 |
| **10** | Memory / Workspace / Config 命令 | 0.5d | P2 |
| **总计** | | **7d** | |

---

## 10. 验收标准

| # | 条件 | P |
|---|------|---|
| C1 | CLI 在 Windows / macOS / Linux 均可启动并交互 | P0 |
| C2 | `/new` 创建会话，`/sessions` 列出历史，`/switch` 切换会话 | P0 |
| C3 | HIGH 风险工具弹出确认提示，用户可批准或拒绝 | P0 |
| C4 | 拒绝确认后 LLM 收到拒绝信息并调整策略 | P0 |
| C5 | `/new research-agent` 创建使用指定 Agent 的会话 | P1 |
| C6 | `/agents` 正确列出所有 Agent 配置 | P1 |
| C7 | `/run` 触发 Workflow 并实时显示节点执行状态 | P1 |
| C8 | `/debug on` 后所有事件以 [DEBUG] 前缀显示 | P1 |
| C9 | 委托事件（delegate_started/completed）正确显示 | P1 |
| C10 | `/skills` 按分类分组展示已安装 skills | P2 |
| C11 | `/cron list` 正确列出定时任务 | P2 |
| C12 | `--execute "消息"` 脚本模式正常工作 | P2 |
| C13 | 管道模式（stdin → CLI → stdout）正常工作 | P2 |

---

## 11. 否决方案

| 方案 | 原因 |
|------|------|
| 用 `click` 框架重写 CLI | 过重，且 click 面向一次性命令而非交互式 REPL |
| 用 `textual` 做全屏 TUI | 已有 `run_tui.py`，CLI 定位为轻量交互 |
| CLI 直接调后端函数（进程内） | 违反 Gateway 架构，CLI 应作为独立客户端通过网络连接 |
| 为每个命令创建独立子命令（如 `agentos session list`） | CLI 是交互式 REPL，不是 kubectl 风格的一次性命令 |
| 命令用 `!` 前缀而非 `/` | 现有代码已用 `/`，且 `/` 在聊天场景更常见 |

---

## 12. 后续迭代

| 特性 | 说明 | 优先级 |
|------|------|:------:|
| Tab 自动补全 | 命令名 + agent_id + session_id 补全 | P2 |
| 命令历史 | ↑↓ 键浏览历史命令（prompt_toolkit 内置） | P2 |
| 彩色 Markdown 渲染 | Assistant 回复中的代码块语法高亮 | P2 |
| 多行输入 | Shift+Enter 或 `"""` 包裹多行消息 | P3 |
| SSH 远程连接 | `agentos connect user@host:port` | P3 |
| 插件命令 | 允许用户在 `~/.agentos/cli_plugins/` 注册自定义命令 | P3 |
