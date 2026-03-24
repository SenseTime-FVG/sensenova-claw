"""DisplayEngine + 确认交互 + 跨平台输入 + spinner"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import unicodedata
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from sensenova_claw.app.cli.app import CLIApp

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_CYAN = "\033[36m"
ANSI_YELLOW = "\033[33m"
ANSI_DIM = "\033[2m"
ANSI_BG_DARK = "\033[48;5;236m"  # 深灰背景
ANSI_WHITE = "\033[37m"

# 跨平台 termios 导入
HAS_TERMIOS = False
if sys.platform != "win32":
    try:
        import termios
        import tty
        HAS_TERMIOS = True
    except ImportError:
        pass


# ── 终端状态管理（线程安全） ──────────────────────────

class TerminalGuard:
    """管理终端 raw/cooked 模式切换，确保异步打印不会在 raw mode 下输出。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._original: list | None = None
        self._in_raw = False
        self._buffer: list[str] = []  # 当前输入缓冲区引用

    def enter_raw(self, fd: int, original_settings: list, buffer: list[str]) -> None:
        with self._lock:
            self._fd = fd
            self._original = original_settings
            self._in_raw = True
            self._buffer = buffer

    def exit_raw(self) -> None:
        with self._lock:
            self._in_raw = False
            self._fd = None
            self._original = None
            self._buffer = []

    def cooked(self) -> "_CookedContext":
        """上下文管理器：临时恢复 cooked mode 用于安全打印"""
        return _CookedContext(self)


class _CookedContext:
    def __init__(self, guard: TerminalGuard):
        self._guard = guard
        self._was_raw = False

    def __enter__(self):
        self._guard._lock.acquire()
        if self._guard._in_raw and self._guard._fd is not None and HAS_TERMIOS:
            self._was_raw = True
            # 清除当前输入行
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            termios.tcsetattr(self._guard._fd, termios.TCSADRAIN, self._guard._original)
        return self

    def __exit__(self, *args):
        if self._was_raw and self._guard._fd is not None and HAS_TERMIOS:
            tty.setraw(self._guard._fd)
            # 重绘提示符和输入内容
            sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: {''.join(self._guard._buffer)}")
            sys.stdout.flush()
        self._guard._lock.release()


# 全局单例
terminal_guard = TerminalGuard()


def char_display_width(char: str) -> int:
    """计算单个字符在终端中的显示宽度。"""
    if not char:
        return 0
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def _show_completions(completions: list[str]) -> None:
    """在终端中显示补全项列表（raw mode 下使用 \r\n）"""
    sys.stdout.write(f"\r\n{ANSI_CYAN}可选:{ANSI_RESET} ")
    sys.stdout.write(f"  ".join(f"{ANSI_YELLOW}{c}{ANSI_RESET}" for c in completions))
    sys.stdout.write("\r\n")


def _redraw_prompt(buffer: list[str]) -> None:
    """重绘提示符和当前输入内容"""
    sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: {''.join(buffer)}")
    sys.stdout.flush()


def read_user_input() -> str:
    """读取用户输入，支持 Tab 补全和 / 即时菜单。
    Windows / 非 TTY 环境降级为 input()。
    """
    from sensenova_claw.app.cli.commands import get_completions

    if not (HAS_TERMIOS and sys.stdin.isatty()):
        return input("You: ")

    sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: ")
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buffer: list[str] = []
    try:
        tty.setraw(fd)
        terminal_guard.enter_raw(fd, old_settings, buffer)
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

            # Tab 补全
            if char == "\t":
                current = "".join(buffer)
                if current.startswith("/"):
                    completions = get_completions(current)
                    if len(completions) == 1:
                        # 唯一匹配：自动补全
                        match = completions[0]
                        if " " in current:
                            # 补全子命令部分
                            parts = current.split(maxsplit=1)
                            prefix = parts[1] if len(parts) > 1 else ""
                            suffix = match[len(prefix):]
                            # 补全后加空格方便继续输入
                            fill = suffix + " "
                        else:
                            # 补全顶层命令
                            fill = match[len(current):] + " "
                        for ch in fill:
                            buffer.append(ch)
                            sys.stdout.write(ch)
                        sys.stdout.flush()
                    elif completions:
                        # 多个匹配：显示列表
                        _show_completions(completions)
                        _redraw_prompt(buffer)
                continue

            # 空缓冲区按 / 即时触发命令菜单
            current = "".join(buffer)
            if char == "/" and current == "":
                buffer.append(char)
                sys.stdout.write(char)
                sys.stdout.write(f"\r\n{ANSI_CYAN}可用命令:{ANSI_RESET}\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/new{ANSI_RESET}        {ANSI_YELLOW}/session{ANSI_RESET}     {ANSI_YELLOW}/agent{ANSI_RESET}      {ANSI_YELLOW}/tool{ANSI_RESET}       {ANSI_YELLOW}/skill{ANSI_RESET}\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/history{ANSI_RESET}    {ANSI_YELLOW}/debug{ANSI_RESET}       {ANSI_YELLOW}/help{ANSI_RESET}       {ANSI_YELLOW}/quit{ANSI_RESET}\r\n")
                sys.stdout.write(f"  {ANSI_DIM}按 Tab 补全子命令{ANSI_RESET}\r\n")
                _redraw_prompt(buffer)
                continue

            buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()
    finally:
        terminal_guard.exit_raw()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ── Spinner ──────────────────────────────────────────

class Spinner:
    """终端动态 spinner，显示 Agent 正在处理"""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "思考中"):
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        # 清除 spinner 行
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def update_message(self, message: str) -> None:
        self._message = message

    def _spin(self) -> None:
        idx = 0
        while not self._stop_event.is_set():
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{ANSI_CYAN}{frame} {self._message}...{ANSI_RESET}\033[K")
            sys.stdout.flush()
            idx += 1
            self._stop_event.wait(0.1)


class DisplayEngine:
    """CLI 显示引擎：处理事件展示和确认交互。
    所有输出通过 _print 方法，确保在 raw mode 下安全打印。
    """

    def __init__(self, app: CLIApp):
        self.app = app
        self.console: Console = app.console
        self.spinner = Spinner()

    def _print(self, *args, **kwargs) -> None:
        """线程安全打印：临时退出 raw mode → 打印 → 恢复 raw mode"""
        with terminal_guard.cooked():
            self.console.print(*args, **kwargs)

    def handle_event(self, data: dict) -> None:
        """处理从 WebSocket 接收到的事件"""
        msg_type = data.get("type", "")
        payload = data.get("payload", {})

        if msg_type == "tool_execution":
            self.spinner.update_message("执行工具")
            name = payload.get("tool_name", "")
            args = payload.get("arguments", {})
            args_str = json.dumps(args, ensure_ascii=False)
            if len(args_str) > 300:
                args_str = args_str[:300] + "..."
            with terminal_guard.cooked():
                sys.stdout.write("\r\033[K")
                self.console.print(f"[yellow]🔧 {name}[/yellow]")
                self.console.print(f"[dim]   参数: {args_str}[/dim]")

        elif msg_type == "tool_result":
            name = payload.get("tool_name", "")
            result = payload.get("result", {})
            success = payload.get("success", False)
            with terminal_guard.cooked():
                sys.stdout.write("\r\033[K")
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
            desc = payload.get("description", payload.get("step_type", ""))
            self.spinner.update_message(desc or "思考中")
            if self.app.debug:
                with terminal_guard.cooked():
                    sys.stdout.write("\r\033[K")
                    self.console.print(f"[dim]   ⏳ {desc}[/dim]")

        elif msg_type == "sessions_list":
            self._render_sessions(payload.get("sessions", []))

        elif msg_type == "agents_list":
            self._render_agents(payload.get("agents", []))

        elif msg_type == "messages_list":
            self._render_messages(payload.get("messages", []))

        elif msg_type == "session_deleted":
            sid = payload.get("session_id", "")
            self._print(f"[green]✓ 会话已删除: {sid}[/green]")

        elif msg_type == "session_renamed":
            sid = payload.get("session_id", "")
            title = payload.get("title", "")
            self._print(f"[green]✓ 会话已重命名: {sid} -> {title}[/green]")

        elif msg_type == "session_created":
            sid = data.get("session_id", "")
            if sid:
                self.app.current_session_id = sid

        elif msg_type == "session_loaded":
            pass  # session_id 已在 _load_session 中设置

        elif msg_type == "notification":
            text = payload.get("text", "")
            self._print(f"\n[cyan]📢 通知:[/cyan] {text}")

    def show_response(self, text: str) -> None:
        self.spinner.stop()
        if text:
            self._print(f"\n[blue]Assistant:[/blue] {text}\n")

    def show_error(self, data: dict) -> None:
        self.spinner.stop()
        msg = data.get("payload", {}).get("message", "未知错误")
        self._print(f"\n[red]错误: {msg}[/red]\n")

    def show_debug(self, data: dict) -> None:
        msg_type = data.get("type", "?")
        payload_str = str(data.get("payload", {}))[:80]
        with terminal_guard.cooked():
            sys.stdout.write("\r\033[K")
            self.console.print(f"[dim]  [DEBUG] {msg_type}  {payload_str}[/dim]")

    def show_status_bar(self) -> None:
        """在输入提示符之前显示状态栏"""
        session = self.app.current_session_id or "无"
        agent = self.app.current_agent_id or "default"
        try:
            connected = self.app.ws is not None and self.app.ws.state.name == "OPEN"
        except Exception:
            connected = self.app.ws is not None
        conn_icon = f"{ANSI_GREEN}●{ANSI_RESET}" if connected else f"\033[31m●{ANSI_RESET}"
        conn_text = "已连接" if connected else "未连接"

        # 获取终端宽度
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            cols = 80

        # 构建状态栏内容
        left = f" {conn_icon} {conn_text}  │  Agent: {agent}  │  Session: {session[:20]}"
        # 用背景色填满整行
        visible_len = len(conn_text) + len(agent) + len(session[:20]) + 22  # 估算可见字符长度
        padding = max(0, cols - visible_len)
        bar = f"{ANSI_BG_DARK}{ANSI_WHITE}{left}{' ' * padding}{ANSI_RESET}"

        sys.stdout.write(f"{bar}\n")
        sys.stdout.flush()

    def show_welcome(self, agent_name: str = "", workdir: str = "") -> None:
        """显示欢迎信息，包含 Agent 名称和工作目录"""
        self.console.print()
        self.console.print(f"[green]✓ 已连接[/green]  会话: {self.app.current_session_id or '?'}")
        agent_display = agent_name or self.app.current_agent_id
        self.console.print(f"  Agent:  [bold cyan]{agent_display}[/bold cyan]")
        if workdir:
            self.console.print(f"  工作目录: [dim]{workdir}[/dim]")
        self.console.print("[dim]输入消息开始对话，输入 / 查看命令，Ctrl+C 中止当前对话[/dim]\n")

    def show_cancelled(self) -> None:
        """显示对话已中止"""
        self.spinner.stop()
        self._print("\n[yellow]⚠ 对话已中止[/yellow]\n")

    async def prompt_confirmation(self, data: dict) -> bool:
        """工具确认交互"""
        self.spinner.stop()
        payload = data.get("payload", {})
        tool_name = payload.get("tool_name", "")
        risk = payload.get("risk_level", "high")
        arguments = payload.get("arguments", {})

        self._print()
        self._print(f"  ⚠️  [bold yellow]{tool_name}[/] 请求执行 ({risk} 风险):")
        for k, v in arguments.items():
            if k.startswith("_"):
                continue
            self._print(f"     {k}: {str(v)[:200]}", style="dim")

        resp = await asyncio.to_thread(input, "  批准？[y/N]: ")
        approved = resp.strip().lower() in ("y", "yes")
        icon = "✅" if approved else "❌"
        self._print(f"  {icon} {'已批准' if approved else '已拒绝'}\n")
        return approved

    def _render_sessions(self, sessions: list[dict]) -> None:
        with terminal_guard.cooked():
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
        with terminal_guard.cooked():
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
        with terminal_guard.cooked():
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
