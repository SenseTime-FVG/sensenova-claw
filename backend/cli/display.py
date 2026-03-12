"""DisplayEngine + 确认交互 + 跨平台输入"""

from __future__ import annotations

import asyncio
import json
import sys
import unicodedata
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from cli.app import CLIApp

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_CYAN = "\033[36m"
ANSI_YELLOW = "\033[33m"

# 跨平台 termios 导入
HAS_TERMIOS = False
if sys.platform != "win32":
    try:
        import termios
        import tty
        HAS_TERMIOS = True
    except ImportError:
        pass


def char_display_width(char: str) -> int:
    """计算单个字符在终端中的显示宽度。"""
    if not char:
        return 0
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def read_user_input() -> str:
    """读取用户输入，支持在空输入时按 / 立即弹出命令菜单。
    Windows / 非 TTY 环境降级为 input()。
    """
    if not (HAS_TERMIOS and sys.stdin.isatty()):
        return input("You: ")

    sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: ")
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buffer: list[str] = []
    try:
        tty.setraw(fd)
        while True:
            char = sys.stdin.read(1)
            if not char:
                raise EOFError

            # Ctrl+C
            if char == "\x03":
                raise KeyboardInterrupt

            # Ctrl+D
            if char == "\x04":
                if not buffer:
                    raise EOFError
                continue

            # 回车提交
            if char in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(buffer)

            # 退格
            if char in ("\x7f", "\b"):
                if buffer:
                    deleted = buffer.pop()
                    width = char_display_width(deleted)
                    if width > 0:
                        sys.stdout.write("\b" * width)
                        sys.stdout.write(" " * width)
                        sys.stdout.write("\b" * width)
                    sys.stdout.flush()
                continue

            # 空缓冲区按 / 即时触发菜单提示
            current = "".join(buffer)
            if char == "/" and current == "":
                buffer.append(char)
                sys.stdout.write(char)
                sys.stdout.write(f"\r\n{ANSI_CYAN}可用命令:{ANSI_RESET}\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/new [agent]{ANSI_RESET}    创建新会话\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/sessions{ANSI_RESET}       列出历史会话\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/switch <id>{ANSI_RESET}    切换会话\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/history{ANSI_RESET}        消息历史\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/agents{ANSI_RESET}         列出 Agent\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/debug on|off{ANSI_RESET}   调试模式\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/help{ANSI_RESET}           帮助\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/quit{ANSI_RESET}           退出\r\n")
                sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: {''.join(buffer)}")
                sys.stdout.flush()
                continue

            buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class DisplayEngine:
    """CLI 显示引擎：处理事件展示和确认交互"""

    def __init__(self, app: CLIApp):
        self.app = app
        self.console: Console = app.console

    def handle_event(self, data: dict) -> None:
        """处理从 WebSocket 接收到的事件"""
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

        elif msg_type == "messages_list":
            self._render_messages(payload.get("messages", []))

        elif msg_type == "workflow_run_completed":
            status = payload.get("status", "")
            icon = "✅" if status == "completed" else "❌"
            self.console.print(f"\n{icon} Workflow {status}")
            output = payload.get("output", "")
            if output:
                self.console.print(f"[blue]结果:[/blue] {str(output)[:1000]}")

        elif msg_type == "notification":
            text = payload.get("text", "")
            self.console.print(f"\n[cyan]📢 通知:[/cyan] {text}")

        elif msg_type.startswith("workflow."):
            # workflow.node_started / workflow.node_completed
            node = payload.get("node_id", payload.get("node_type", ""))
            self.console.print(f"[dim]   ⚙️ {msg_type}: {node}[/dim]")

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
        """工具确认交互"""
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

    def _render_messages(self, messages: list[dict]) -> None:
        """渲染会话消息历史"""
        if not messages:
            self.console.print("[dim]暂无消息[/dim]")
            return
        self.console.print(f"\n[bold]消息历史[/bold] ({len(messages)} 条)\n")
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if role == "user":
                self.console.print(f"  [green]You:[/green] {content[:200]}")
            elif role == "assistant":
                self.console.print(f"  [blue]Assistant:[/blue] {content[:200]}")
            elif role == "tool":
                name = m.get("name", m.get("tool_name", ""))
                self.console.print(f"  [yellow]🔧 {name}[/yellow]: {content[:100]}")
        self.console.print()
