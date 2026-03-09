#!/usr/bin/env python
"""简单的命令行客户端 - 使用 rich"""
import asyncio
import json
import signal
import sys
import termios
import tty
import unicodedata
from typing import Literal
import websockets
from rich.console import Console
from rich.prompt import Prompt

console = Console()

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_CYAN = "\033[36m"
ANSI_YELLOW = "\033[33m"


def show_command_menu() -> None:
    """显示可用命令菜单"""
    console.print("[cyan]可用命令:[/cyan]")
    console.print("  /quit - 退出")


InputAction = Literal["ignore", "quit", "show_menu", "unknown_command", "send"]


def should_trigger_menu_on_keypress(current_buffer: str, char: str) -> bool:
    """是否在按键阶段立即触发命令菜单"""
    return char == "/" and current_buffer == ""


def char_display_width(char: str) -> int:
    """计算单个字符在终端中的显示宽度。"""
    if not char:
        return 0
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def parse_user_input(raw_input: str) -> tuple[InputAction, str]:
    """解析用户输入并返回动作与规范化文本"""
    user_input = raw_input.strip()
    if not user_input:
        return "ignore", user_input
    if user_input == "/quit":
        return "quit", user_input
    if user_input == "/":
        return "show_menu", user_input
    if user_input.startswith("/"):
        return "unknown_command", user_input
    return "send", user_input


def read_user_input() -> str:
    """读取用户输入，支持在空输入时按 / 立即弹出命令菜单"""
    if not sys.stdin.isatty():
        return Prompt.ask("[green]You[/green]")

    # 避免与 Rich 渲染混用导致连续空输入时出现缩进漂移
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

            current = "".join(buffer)
            if should_trigger_menu_on_keypress(current, char):
                buffer.append(char)
                sys.stdout.write(char)
                sys.stdout.write(f"\r\n{ANSI_CYAN}可用命令:{ANSI_RESET}\r\n")
                sys.stdout.write(f"  {ANSI_YELLOW}/quit{ANSI_RESET} - 退出\r\n")
                sys.stdout.write(f"{ANSI_GREEN}You{ANSI_RESET}: {''.join(buffer)}")
                sys.stdout.flush()
                continue

            buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def main():
    ws_url = "ws://localhost:8000/ws"
    console.print(f"[cyan]连接到 {ws_url}...[/cyan]")

    async with websockets.connect(ws_url) as ws:
        console.print("[green]✓ 已连接[/green]")

        # 创建会话
        await ws.send(json.dumps({"type": "create_session", "payload": {}}))
        msg = json.loads(await ws.recv())
        session_id = msg.get("session_id")
        console.print(f"[green]✓ 会话: {session_id}[/green]\n")

        # 启动接收任务
        waiting_response = asyncio.Event()

        def on_sigint() -> None:
            """拦截 Ctrl+C，提示用户使用 /quit 退出"""
            console.print("\n[dim]提示: 使用 /quit 退出[/dim]")

        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, on_sigint)
        except NotImplementedError:
            # Windows 兼容：不支持 add_signal_handler 时保持原有兜底异常处理
            pass

        async def receive():
            async for message in ws:
                data = json.loads(message)
                msg_type = data.get("type")
                payload = data.get("payload", {})

                if msg_type == "tool_execution":
                    tool_name = payload.get('tool_name', '')
                    args = payload.get('arguments', {})
                    console.print(f"[yellow]🔧 {tool_name}[/yellow]")
                    console.print(f"[dim]   参数: {json.dumps(args, ensure_ascii=False)}[/dim]")
                elif msg_type == "tool_result":
                    tool_name = payload.get('tool_name', '')
                    result = payload.get('result', {})
                    result_str = json.dumps(result, ensure_ascii=False)
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "... (截断)"
                    console.print(f"[yellow]✓ {tool_name}[/yellow]")
                    console.print(f"[dim]   结果: {result_str}[/dim]")
                elif msg_type == "turn_completed":
                    response = payload.get("final_response") or payload.get("content", "")
                    if response:
                        console.print(f"\n[blue]Assistant:[/blue] {response}\n")
                    waiting_response.set()

        recv_task = asyncio.create_task(receive())

        try:
            # 主循环
            while True:
                try:
                    raw_input = await asyncio.to_thread(read_user_input)
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[dim]提示: 使用 /quit 退出[/dim]")
                    continue

                action, user_input = parse_user_input(raw_input)
                if action == "ignore":
                    continue

                # 处理命令
                if action == "quit":
                    console.print("[yellow]退出[/yellow]")
                    break

                if action == "show_menu":
                    show_command_menu()
                    continue

                if action == "unknown_command":
                    console.print(f"[yellow]未知命令: {user_input}[/yellow]")
                    show_command_menu()
                    continue

                waiting_response.clear()
                await ws.send(json.dumps({
                    "type": "user_input",
                    "session_id": session_id,
                    "payload": {"content": user_input}
                }))

                # 等待响应完成
                await waiting_response.wait()
        finally:
            recv_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
