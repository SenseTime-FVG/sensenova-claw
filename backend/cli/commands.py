"""CommandDispatcher - 所有 / 命令"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.app import CLIApp


class CommandDispatcher:
    """CLI 命令分派器"""

    def __init__(self, app: CLIApp):
        self.app = app

    async def dispatch(self, raw: str) -> str | None:
        """分派命令，返回 "quit" 表示退出"""
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
