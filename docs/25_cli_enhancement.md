# CLI 全功能客户端 (v1.4)

> 前置: v0.5（双总线 + Session 持久化 + 工具权限）, v0.8（Cron + Heartbeat）, v1.0（多 Agent + Workflow）, v1.2（PathPolicy）

---

## 1. 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 通信协议 | 纯 WebSocket | 后端 WS 已有 `create_session`/`list_sessions`/`load_session`/`run_workflow`，无需引入 `httpx` |
| 跨平台输入 | `termios` 条件导入 + `input()` 降级 | 零新依赖；`prompt_toolkit` 作为 P2 可选 |
| 模块拆分 | 4 个文件（app/commands/display + 入口） | ~700 行代码，12 文件过度拆分 |
| 命令范围 | ~12 个核心命令 | Skills/Cron/Config 管理在终端无独特优势，留给 Web/REST |
| 确认交互 | `asyncio.Queue` + `Event` 协调 | 确认请求不阻死主循环 |
| 脚本模式退出 | `turn_completed`/`error`/超时；确认自动拒绝 | exit code: 0=成功, 1=错误, 2=超时 |
| 调试模式 | 显示所有 WS 消息（含 `agent_thinking`） | CLI 收到的是映射后消息，非原始事件 |

---

## 2. 文件结构

```
backend/
├── cli_client.py          # 入口（argparse + CLIApp 调用，~30 行）
└── cli/
    ├── __init__.py
    ├── app.py             # CLIApp 主类 + WebSocket 管理 + 主循环（~200 行）
    ├── commands.py         # CommandDispatcher + 所有 / 命令（~250 行）
    └── display.py          # DisplayEngine + 确认交互 + 跨平台输入（~200 行）
```

---

## 3. 命令清单

**P0 核心命令**

| 命令 | 别名 | 说明 | 后端协议 |
|------|------|------|---------|
| *(直接输入)* | | 发送消息 | WS: `user_input` |
| `/new [agent_id]` | | 创建新会话 | WS: `create_session` |
| `/sessions` | `/ls` | 列出历史会话 | WS: `list_sessions` |
| `/switch <id>` | `/sw` | 切换会话 | WS: `load_session` |
| `/history` | `/h` | 当前会话消息历史 | WS 新增: `get_messages` |
| `/debug on\|off` | | 调试模式 | 本地 |
| `/help` | `/` | 帮助 | 本地 |
| `/quit` | | 退出 | 本地 |

被动触发：工具确认（`tool_confirmation_requested`）、路径授权（`need_grant`）

**P1 扩展命令**

| 命令 | 说明 | 后端协议 |
|------|------|---------|
| `/agents` | 列出 Agent | WS 新增: `list_agents` |
| `/run <wf_id> <input>` | 触发 Workflow | WS: `run_workflow`（已有） |
| `/cancel` | 取消当前轮次 | WS: `cancel_turn`（已有） |
| `/current` | 当前会话信息 | 本地 |

---

## 4. CLIApp 实现

```python
class CLIApp:
    def __init__(self, host: str, port: int, *,
                 agent_id: str | None = None,
                 session_id: str | None = None,
                 debug: bool = False,
                 execute: str | None = None):
        self.host = host
        self.port = port
        self.initial_agent_id = agent_id
        self.initial_session_id = session_id
        self.debug = debug
        self.execute = execute

        self.ws: websockets.WebSocketClientProtocol | None = None
        self.current_session_id: str | None = None
        self.current_agent_id: str = agent_id or "default"

        self._waiting = asyncio.Event()
        self._confirm_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._last_response: str = ""

        self.console = Console()
        self.dispatcher = CommandDispatcher(self)
        self.display = DisplayEngine(self)

    async def run(self) -> int:
        """返回退出码 0/1/2"""
        ws_url = f"ws://{self.host}:{self.port}/ws"
        async with websockets.connect(ws_url) as ws:
            self.ws = ws
            if self.initial_session_id:
                await self._load_session(self.initial_session_id)
            else:
                await self._create_session(self.initial_agent_id)

            recv_task = asyncio.create_task(self._receive_loop())
            try:
                if self.execute:
                    return await self._run_execute_mode()
                return await self._run_interactive_mode()
            finally:
                recv_task.cancel()

    async def _receive_loop(self) -> None:
        async for raw in self.ws:
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if self.debug:
                self.display.show_debug(data)

            if msg_type == "tool_confirmation_requested":
                await self._confirm_queue.put(data)
                self._waiting.set()
                continue

            if msg_type in ("turn_completed", "error"):
                if msg_type == "turn_completed":
                    self._last_response = data.get("payload", {}).get("final_response", "")
                    self.display.show_response(self._last_response)
                else:
                    self.display.show_error(data)
                self._waiting.set()
                continue

            self.display.handle_event(data)

    async def _wait_for_turn(self) -> None:
        """等待 turn 完成，期间处理确认请求"""
        while True:
            self._waiting.clear()
            await self._waiting.wait()

            while not self._confirm_queue.empty():
                confirm_data = await self._confirm_queue.get()
                if self.execute:
                    approved = False  # 脚本模式自动拒绝
                else:
                    approved = await self.display.prompt_confirmation(confirm_data)
                await self._send_confirmation_response(confirm_data, approved)
                continue

            if self._confirm_queue.empty():
                break

    async def _send(self, msg: dict) -> None:
        await self.ws.send(json.dumps(msg))

    async def _create_session(self, agent_id: str | None = None) -> str:
        await self._send({
            "type": "create_session",
            "payload": {"agent_id": agent_id or "default"},
        })
        resp = json.loads(await self.ws.recv())
        self.current_session_id = resp.get("session_id")
        return self.current_session_id

    async def _load_session(self, session_id: str) -> None:
        await self._send({
            "type": "load_session",
            "payload": {"session_id": session_id},
        })
        await self.ws.recv()
        self.current_session_id = session_id

    async def _send_user_input(self, content: str) -> None:
        await self._send({
            "type": "user_input",
            "session_id": self.current_session_id,
            "payload": {"content": content},
        })

    async def _send_confirmation_response(self, data: dict, approved: bool) -> None:
        payload = data.get("payload", {})
        await self._send({
            "type": "tool_confirmation_response",
            "session_id": self.current_session_id,
            "payload": {
                "tool_call_id": payload.get("tool_call_id"),
                "approved": approved,
            },
        })

    async def _run_execute_mode(self) -> int:
        await self._send_user_input(self.execute)
        try:
            await asyncio.wait_for(self._wait_for_turn(), timeout=300)
        except asyncio.TimeoutError:
            sys.stderr.write("Error: timeout\n")
            return 2
        sys.stdout.write(self._last_response + "\n")
        return 0

    async def _run_interactive_mode(self) -> int:
        self.display.show_welcome()
        while True:
            try:
                raw = await asyncio.to_thread(read_user_input)
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]提示: 使用 /quit 退出[/dim]")
                continue

            text = raw.strip()
            if not text:
                continue

            if text.startswith("/"):
                action = await self.dispatcher.dispatch(text)
                if action == "quit":
                    return 0
                continue

            await self._send_user_input(text)
            await self._wait_for_turn()
```

---

## 5. CommandDispatcher 实现

```python
class CommandDispatcher:
    def __init__(self, app: CLIApp):
        self.app = app

    async def dispatch(self, raw: str) -> str | None:
        """返回 "quit" 表示退出"""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/quit":
            return "quit"
        if cmd in ("/help", "/"):
            self._show_help()
        elif cmd == "/new":
            sid = await self.app._create_session(arg.strip() or None)
            self.app.console.print(f"[green]✓ 新会话: {sid} (Agent: {arg or 'default'})[/green]")
        elif cmd in ("/sessions", "/ls"):
            await self.app._send({"type": "list_sessions", "payload": {}})
        elif cmd in ("/switch", "/sw"):
            if not arg:
                self.app.console.print("[red]用法: /switch <session_id>[/red]")
            else:
                await self.app._load_session(arg.strip())
                self.app.console.print(f"[green]✓ 已切换到 {arg.strip()}[/green]")
        elif cmd in ("/history", "/h"):
            await self.app._send({
                "type": "get_messages",
                "payload": {"session_id": self.app.current_session_id},
            })
        elif cmd == "/debug":
            if arg.lower() == "on":
                self.app.debug = True
                self.app.console.print("[cyan]调试模式已开启[/cyan]")
            elif arg.lower() == "off":
                self.app.debug = False
                self.app.console.print("[cyan]调试模式已关闭[/cyan]")
            else:
                self.app.console.print(f"[cyan]调试模式: {'开启' if self.app.debug else '关闭'}[/cyan]")
        elif cmd == "/agents":
            await self.app._send({"type": "list_agents", "payload": {}})
        elif cmd == "/run":
            p = arg.split(maxsplit=1)
            if len(p) < 2:
                self.app.console.print("[red]用法: /run <workflow_id> <input>[/red]")
            else:
                await self.app._send({
                    "type": "run_workflow",
                    "session_id": self.app.current_session_id,
                    "payload": {"workflow_id": p[0], "input": p[1]},
                })
                self.app.console.print(f"[cyan]Workflow {p[0]} 启动中...[/cyan]")
                await self.app._wait_for_turn()
        elif cmd == "/cancel":
            await self.app._send({
                "type": "cancel_turn",
                "session_id": self.app.current_session_id,
                "payload": {"reason": "user_cancel"},
            })
            self.app.console.print("[yellow]已请求取消当前轮次[/yellow]")
        elif cmd == "/current":
            self.app.console.print(f"会话: {self.app.current_session_id}")
            self.app.console.print(f"Agent: {self.app.current_agent_id}")
            self.app.console.print(f"调试: {'开启' if self.app.debug else '关闭'}")
        else:
            self.app.console.print(f"[yellow]未知命令: {cmd}[/yellow]")
            self._show_help()
        return None

    def _show_help(self) -> None:
        self.app.console.print("""
[bold]AgentOS CLI[/bold]

  [cyan]会话[/cyan]
    /new [agent]       创建新会话
    /sessions          列出历史会话
    /switch <id>       切换会话
    /history           消息历史
    /current           当前会话信息
    /cancel            取消当前轮次

  [cyan]Agent & Workflow[/cyan]
    /agents            列出可用 Agent
    /run <wf> <input>  触发 Workflow

  [cyan]系统[/cyan]
    /debug on|off      调试模式
    /help              显示帮助
    /quit              退出
""")
```

---

## 6. DisplayEngine 实现

```python
class DisplayEngine:
    def __init__(self, app: CLIApp):
        self.app = app
        self.console = app.console

    def handle_event(self, data: dict) -> None:
        msg_type = data.get("type", "")
        payload = data.get("payload", {})

        if msg_type == "tool_execution":
            name = payload.get("tool_name", "")
            args = payload.get("arguments", {})
            self.console.print(f"[yellow]🔧 {name}[/yellow]")
            args_str = json.dumps(args, ensure_ascii=False)
            if len(args_str) > 300:
                args_str = args_str[:300] + "..."
            self.console.print(f"[dim]   参数: {args_str}[/dim]")

        elif msg_type == "tool_result":
            name = payload.get("tool_name", "")
            result = payload.get("result", {})
            success = payload.get("success", False)
            if isinstance(result, dict) and result.get("action") == "need_grant":
                self.console.print(f"[yellow]🔒 {name}: 目录未授权 {result.get('path', '')}[/yellow]")
                return
            icon = "✓" if success else "✗"
            self.console.print(f"[yellow]{icon} {name}[/yellow]")
            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > 500:
                result_str = result_str[:500] + "..."
            self.console.print(f"[dim]   结果: {result_str}[/dim]")

        elif msg_type == "agent_thinking":
            if self.app.debug:
                desc = payload.get("description", payload.get("step_type", ""))
                self.console.print(f"[dim]   ⏳ {desc}[/dim]")

        elif msg_type == "sessions_list":
            self._render_sessions(payload.get("sessions", []))

        elif msg_type == "agents_list":
            self._render_agents(payload.get("agents", []))

        elif msg_type == "workflow_run_completed":
            status = payload.get("status", "")
            icon = "✅" if status == "completed" else "❌"
            self.console.print(f"\n{icon} Workflow {status}")
            output = payload.get("output", "")
            if output:
                self.console.print(f"[blue]结果:[/blue] {output[:1000]}")

        elif msg_type == "notification":
            text = payload.get("text", "")
            self.console.print(f"\n[cyan]📢 通知:[/cyan] {text}")

    def show_response(self, text: str) -> None:
        if text:
            self.console.print(f"\n[blue]Assistant:[/blue] {text}\n")

    def show_error(self, data: dict) -> None:
        msg = data.get("payload", {}).get("message", "未知错误")
        self.console.print(f"\n[red]错误: {msg}[/red]\n")

    def show_debug(self, data: dict) -> None:
        msg_type = data.get("type", "?")
        payload_str = str(data.get("payload", {}))[:80]
        self.console.print(f"[dim]  [DEBUG] {msg_type}  {payload_str}[/dim]")

    def show_welcome(self) -> None:
        self.console.print(f"[green]✓ 已连接[/green]  会话: {self.app.current_session_id or '?'}")
        self.console.print("[dim]输入消息开始对话，输入 / 查看命令[/dim]\n")

    async def prompt_confirmation(self, data: dict) -> bool:
        payload = data.get("payload", {})
        tool_name = payload.get("tool_name", "")
        risk = payload.get("risk_level", "high")
        arguments = payload.get("arguments", {})

        self.console.print()
        self.console.print(f"  ⚠️  [bold yellow]{tool_name}[/] 请求执行 ({risk} 风险):")
        for k, v in arguments.items():
            if k.startswith("_"):
                continue
            self.console.print(f"     {k}: {str(v)[:200]}", style="dim")

        resp = await asyncio.to_thread(input, "  批准？[y/N]: ")
        approved = resp.strip().lower() in ("y", "yes")
        icon = "✅" if approved else "❌"
        self.console.print(f"  {icon} {'已批准' if approved else '已拒绝'}\n")
        return approved

    def _render_sessions(self, sessions: list[dict]) -> None:
        if not sessions:
            self.console.print("[dim]暂无会话[/dim]")
            return
        self.console.print(f"\n[bold]会话列表[/bold] ({len(sessions)} 个)\n")
        for s in sessions:
            sid = s.get("session_id", "?")
            title = s.get("title", "(无标题)")[:30]
            agent = s.get("agent_id", "default")
            marker = " *" if sid == self.app.current_session_id else ""
            self.console.print(f"  {sid}{marker}  {agent:16s}  {title}")
        self.console.print()

    def _render_agents(self, agents: list[dict]) -> None:
        if not agents:
            self.console.print("[dim]暂无 Agent[/dim]")
            return
        self.console.print(f"\n[bold]可用 Agent[/bold] ({len(agents)} 个)\n")
        for a in agents:
            aid = a.get("id", "?")
            model = a.get("model", "")
            desc = a.get("description", "")[:40]
            self.console.print(f"  {aid:20s}  {model:16s}  {desc}")
        self.console.print()
```

---

## 7. 跨平台输入

```python
import sys

HAS_TERMIOS = False
if sys.platform != "win32":
    try:
        import termios
        import tty
        HAS_TERMIOS = True
    except ImportError:
        pass

def read_user_input() -> str:
    if HAS_TERMIOS and sys.stdin.isatty():
        return _read_raw()   # 现有 termios 逻辑（即时菜单）
    return input("You: ")    # Windows / 非 TTY
```

---

## 8. 后端改动

### 8.1 `main.py` websocket_endpoint 新增

```python
# list_agents
if msg_type == "list_agents":
    agent_registry = app.state.agent_registry
    agents = [
        {"id": a.id, "name": a.name, "description": a.description,
         "model": a.model, "provider": a.provider}
        for a in agent_registry.list_all()
    ]
    await ws_channel.send_json(websocket, {
        "type": "agents_list",
        "payload": {"agents": agents},
        "timestamp": time.time(),
    })
    continue

# tool_confirmation_response
if msg_type == "tool_confirmation_response":
    await gateway.publish_from_channel(
        EventEnvelope(
            type=TOOL_CONFIRMATION_RESPONSE,
            session_id=session_id,
            source="websocket",
            payload={
                "tool_call_id": payload.get("tool_call_id"),
                "approved": payload.get("approved", False),
            },
        )
    )
    continue

# get_messages
if msg_type == "get_messages":
    sid = payload.get("session_id") or session_id
    messages = await repo.get_session_messages(sid) if sid else []
    await ws_channel.send_json(websocket, {
        "type": "messages_list",
        "payload": {"messages": messages},
        "timestamp": time.time(),
    })
    continue
```

### 8.2 `websocket_channel.py` _map() 新增

```python
if event.type == TOOL_CONFIRMATION_REQUESTED:
    return {
        "type": "tool_confirmation_requested",
        "session_id": event.session_id,
        "payload": {
            "tool_call_id": event.payload.get("tool_call_id"),
            "tool_name": event.payload.get("tool_name"),
            "arguments": event.payload.get("arguments", {}),
            "risk_level": event.payload.get("risk_level", "high"),
        },
        "timestamp": event.ts,
    }

if event.type == WORKFLOW_NODE_STARTED:
    return {
        "type": "workflow.node_started",
        "session_id": event.session_id,
        "payload": event.payload,
        "timestamp": event.ts,
    }

if event.type == WORKFLOW_NODE_COMPLETED:
    return {
        "type": "workflow.node_completed",
        "session_id": event.session_id,
        "payload": event.payload,
        "timestamp": event.ts,
    }
```

---

## 9. 命令行参数

```python
parser = argparse.ArgumentParser(description="AgentOS CLI")
parser.add_argument("--host", default="localhost")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--agent", default=None, help="Agent ID")
parser.add_argument("--session", default=None, help="恢复指定 session")
parser.add_argument("--debug", action="store_true")
parser.add_argument("-e", "--execute", default=None, help="执行单条消息后退出")
```

```bash
python cli_client.py                                        # 交互
python cli_client.py --agent research-agent                 # 指定 Agent
python cli_client.py --session sess_abc123                  # 恢复会话
python cli_client.py -e "搜索最新 AI 论文"                   # 脚本模式
python cli_client.py --host 192.168.1.100 --port 8000       # 远程
```

---

## 10. 改动清单

| 文件 | 改动 | P |
|------|------|:-:|
| **新增** `backend/cli/__init__.py` | 空 | P0 |
| **新增** `backend/cli/app.py` | CLIApp | P0 |
| **新增** `backend/cli/commands.py` | CommandDispatcher | P0 |
| **新增** `backend/cli/display.py` | DisplayEngine + 跨平台输入 | P0 |
| **改造** `backend/cli_client.py` | 入口脚本 → import CLIApp | P0 |
| **改造** `backend/app/main.py` | WS 新增 `list_agents` / `tool_confirmation_response` / `get_messages` | P0 |
| **改造** `backend/app/gateway/channels/websocket_channel.py` | `_map()` 新增确认 + Workflow 事件 | P0 |

后端核心模块（事件总线、Runtime、AgentRegistry、ToolRuntime）无改动。前端、TUI 无改动。

---

## 11. 实施计划

| Phase | 内容 | 工期 |
|-------|------|------|
| 1 | 跨平台输入 + CLIApp 骨架 + 基础 REPL（Windows 可运行） | 1d |
| 2 | 会话管理（/new /sessions /switch /history）+ 调试模式 | 0.5d |
| 3 | 确认交互（Queue 机制 + 后端事件映射） | 1d |
| 4 | 脚本模式（-e 参数 + 退出码） | 0.5d |
| 5 | /agents + /run workflow + 后端 WS 扩展 | 0.5d |
| **总计** | | **3.5d** |

---

## 12. 验收标准

| # | 条件 | P |
|---|------|:-:|
| C1 | Windows + macOS + Linux 均可启动并对话 | P0 |
| C2 | `/new research-agent` 创建指定 Agent 会话 | P0 |
| C3 | `/sessions` 列出历史，`/switch` 切换后继续对话 | P0 |
| C4 | HIGH 风险工具弹出确认，批准/拒绝后 LLM 收到对应信息 | P0 |
| C5 | 确认不阻死主循环 | P0 |
| C6 | `/debug on` 显示所有 WS 消息 | P0 |
| C7 | `cli -e "问题"` 输出回答到 stdout，exit 0 | P1 |
| C8 | 脚本模式超时 exit 2 | P1 |
| C9 | `/agents` 列出可用 Agent | P1 |
| C10 | `/run <wf> <input>` 触发 Workflow | P1 |
