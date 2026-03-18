"""CLIApp 主类 + WebSocket 管理 + HTTP 客户端 + 主循环"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import urllib.request
import urllib.error

import websockets
from rich.console import Console

from agentos.app.cli.commands import CommandDispatcher
from agentos.app.cli.display import DisplayEngine, read_user_input


class CLIApp:
    """AgentOS CLI 客户端"""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        debug: bool = False,
        execute: str | None = None,
    ):
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
        self._query_event = asyncio.Event()  # 查询命令响应完成信号
        self._interaction_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._last_response: str = ""
        self._turn_cancelled = False
        self._turn_terminal = False
        self._recv_loop_running = False

        self.console = Console()
        self.dispatcher = CommandDispatcher(self)
        self.display = DisplayEngine(self)

    async def run(self) -> int:
        """主入口，返回退出码 0/1/2"""
        ws_url = f"ws://{self.host}:{self.port}/ws"

        # 自动读取 token 文件，附加到 WebSocket URL
        from agentos.platform.security.auth import read_token_file
        token = read_token_file()
        if token:
            ws_url = f"{ws_url}?token={token}"

        self.console.print(f"[cyan]连接到 ws://{self.host}:{self.port}/ws...[/cyan]")

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
        """接收 WebSocket 消息的后台循环"""
        self._recv_loop_running = True
        async for raw in self.ws:
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if self.debug:
                self.display.show_debug(data)

            if msg_type == "tool_confirmation_requested":
                await self._interaction_queue.put({"kind": "confirmation", "data": data})
                self._waiting.set()
                continue

            if msg_type == "user_question_asked":
                await self._interaction_queue.put({"kind": "question", "data": data})
                self._waiting.set()
                continue

            if msg_type in ("turn_completed", "error", "turn_cancelled"):
                self._turn_terminal = True
                if msg_type == "turn_completed":
                    self._last_response = data.get("payload", {}).get("final_response", "")
                    self.display.show_response(self._last_response)
                elif msg_type == "error":
                    # 用户主动取消时，静默吞掉后端的 cancel error
                    if not self._turn_cancelled:
                        self.display.show_error(data)
                self._drain_interaction_queue()
                self._waiting.set()
                continue

            self.display.handle_event(data)

            # 查询/会话类响应：通知等待方
            if msg_type in (
                "sessions_list", "agents_list", "messages_list",
                "session_deleted", "session_renamed",
                "session_created", "session_loaded",
            ):
                self._query_event.set()

    async def _wait_for_turn(self) -> None:
        """等待 turn 完成，期间处理确认请求和问答请求。"""
        self._turn_terminal = False
        self.display.spinner.start()
        try:
            while True:
                self._waiting.clear()
                await self._waiting.wait()

                while not self._interaction_queue.empty():
                    item = await self._interaction_queue.get()
                    kind = item.get("kind")
                    interaction_data = item.get("data", {})
                    self.display.spinner.stop()
                    if kind == "confirmation":
                        if self.execute:
                            approved = False
                        else:
                            approved = await self.display.prompt_confirmation(interaction_data)
                        await self._send_confirmation_response(interaction_data, approved)
                    elif kind == "question":
                        if self.execute:
                            answer = None
                            cancelled = True
                        else:
                            answer, cancelled = await self._prompt_question(interaction_data)
                        await self._send_question_response(interaction_data, answer, cancelled)
                    else:
                        self.console.print(f"[yellow]Unknown interaction kind: {kind}[/yellow]")
                    self.display.spinner.start()
                    continue

                if self._turn_terminal and self._interaction_queue.empty():
                    break
        finally:
            self.display.spinner.stop()

    def _drain_interaction_queue(self) -> None:
        """清空交互队列，避免 turn 结束后遗留交互。"""
        while not self._interaction_queue.empty():
            try:
                self._interaction_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _cancel_current_turn(self) -> None:
        """发送取消请求并中止当前等待"""
        self._turn_cancelled = True
        self._turn_terminal = True
        self._drain_interaction_queue()
        await self._send({
            "type": "cancel_turn",
            "session_id": self.current_session_id,
            "payload": {"reason": "user_cancel"},
        })
        self.display.show_cancelled()
        self._waiting.set()

    async def _send(self, msg: dict) -> None:
        """发送 JSON 消息到 WebSocket"""
        await self.ws.send(json.dumps(msg))

    async def _send_query(self, msg: dict, timeout: float = 5.0) -> None:
        """发送查询命令并等待响应到达后再返回"""
        self._query_event.clear()
        await self._send(msg)
        try:
            await asyncio.wait_for(self._query_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass  # 超时就继续，不阻塞

    # ── HTTP 客户端辅助 ──────────────────────────────

    @property
    def _base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def _http(self, method: str, path: str, body: dict | None = None) -> dict:
        """发送 HTTP 请求到后端 REST API，返回 JSON 响应"""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            try:
                detail = json.loads(err_body).get("detail", err_body)
            except (json.JSONDecodeError, AttributeError):
                detail = err_body
            return {"_error": True, "status": e.code, "detail": detail}
        except Exception as e:
            return {"_error": True, "status": 0, "detail": str(e)}

    async def _http_get(self, path: str) -> dict:
        return await self._http("GET", path)

    async def _http_post(self, path: str, body: dict | None = None) -> dict:
        return await self._http("POST", path, body)

    async def _http_put(self, path: str, body: dict | None = None) -> dict:
        return await self._http("PUT", path, body)

    async def _http_delete(self, path: str) -> dict:
        return await self._http("DELETE", path)

    async def _fetch_agent_info(self, agent_id: str) -> dict:
        """获取 Agent 信息（名称、工作目录等），失败时返回空 dict"""
        resp = await self._http_get(f"/api/agents/{agent_id}")
        if isinstance(resp, dict) and not resp.get("_error"):
            return resp
        return {}

    async def _create_session(self, agent_id: str | None = None) -> str:
        """创建新会话。_receive_loop 运行前直接 recv，运行后走 _query_event。"""
        msg = {"type": "create_session", "payload": {"agent_id": agent_id or "default"}}
        if self._recv_loop_running:
            self._query_event.clear()
            await self._send(msg)
            try:
                await asyncio.wait_for(self._query_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
        else:
            await self._send(msg)
            resp = json.loads(await self.ws.recv())
            self.current_session_id = resp.get("session_id")
        self.current_agent_id = agent_id or "default"
        return self.current_session_id

    async def _load_session(self, session_id: str) -> None:
        """加载已有会话。_receive_loop 运行前直接 recv，运行后走 _query_event。"""
        msg = {"type": "load_session", "payload": {"session_id": session_id}}
        if self._recv_loop_running:
            await self._send_query(msg)
        else:
            await self._send(msg)
            await self.ws.recv()
        self.current_session_id = session_id

    async def _send_user_input(self, content: str) -> None:
        """发送用户输入"""
        await self._send({
            "type": "user_input",
            "session_id": self.current_session_id,
            "payload": {"content": content},
        })

    async def _send_confirmation_response(self, data: dict, approved: bool) -> None:
        """发送工具确认响应"""
        payload = data.get("payload", {})
        target_session_id = data.get("session_id") or self.current_session_id
        await self._send({
            "type": "tool_confirmation_response",
            "session_id": target_session_id,
            "payload": {
                "tool_call_id": payload.get("tool_call_id"),
                "approved": approved,
            },
        })

    async def _prompt_question(self, data: dict) -> tuple[str | list[str] | None, bool]:
        """提示用户回答问题"""
        payload = data.get("payload", {})
        question = payload.get("question", "")
        options = payload.get("options")
        multi_select = payload.get("multi_select", False)

        self.console.print(f"\n[yellow]Agent 问题：{question}[/yellow]")

        if options:
            for i, opt in enumerate(options, 1):
                self.console.print(f"  {i}. {opt}")
            if multi_select:
                self.console.print("[dim]请输入选项编号，用逗号分隔 (如: 1,3) 或输入 'c' 取消[/dim]")
            else:
                self.console.print("[dim]请输入选项编号或自定义输入 (输入 'c' 取消)[/dim]")
        else:
            self.console.print("[dim]请输入答案 (输入 'c' 取消)[/dim]")

        user_input = await asyncio.to_thread(input, "> ")
        user_input = user_input.strip()

        if user_input.lower() == "c":
            return None, True

        if not user_input:
            return None, True

        if options and multi_select:
            if "," in user_input:
                indices = [int(x.strip()) - 1 for x in user_input.split(",") if x.strip().isdigit()]
                selected = [options[i] for i in indices if 0 <= i < len(options)]
                if selected:
                    return selected, False
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(options):
                    return [options[idx]], False
        elif options and user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(options):
                return options[idx], False

        return user_input, False

    async def _send_question_response(self, data: dict, answer: str | list[str] | None, cancelled: bool) -> None:
        """发送问答响应"""
        payload = data.get("payload", {})
        target_session_id = data.get("session_id") or self.current_session_id
        await self._send({
            "type": "user_question_answered",
            "session_id": target_session_id,
            "payload": {
                "question_id": payload.get("question_id"),
                "answer": answer,
                "cancelled": cancelled,
            },
        })

    async def _run_execute_mode(self) -> int:
        """脚本模式：执行单条消息后退出"""
        await self._send_user_input(self.execute)
        try:
            await asyncio.wait_for(self._wait_for_turn(), timeout=300)
        except asyncio.TimeoutError:
            sys.stderr.write("Error: timeout\n")
            return 2
        sys.stdout.write(self._last_response + "\n")
        return 0

    async def _run_interactive_mode(self) -> int:
        """交互模式：REPL 循环"""
        # 获取 Agent 信息用于欢迎页
        agent_info = await self._fetch_agent_info(self.current_agent_id)
        agent_name = agent_info.get("name", "")
        # 构造工作目录显示
        workdir = ""
        if agent_info.get("id"):
            # 从后端获取 agentos_home 拼接 workdir 路径
            try:
                from pathlib import Path
                home = Path.home() / ".agentos"
                workdir = str(home / "workdir" / agent_info["id"])
            except Exception:
                pass

        self.display.show_welcome(agent_name=agent_name, workdir=workdir)

        while True:
            self.display.show_status_bar()
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

            # 等待回复，Ctrl+C 中止当前对话而非退出程序
            self._turn_cancelled = False
            wait_task = asyncio.create_task(self._wait_for_turn())
            loop = asyncio.get_event_loop()

            def _on_sigint():
                self._turn_cancelled = True
                if not wait_task.done():
                    wait_task.cancel()

            loop.add_signal_handler(signal.SIGINT, _on_sigint)
            try:
                await wait_task
            except asyncio.CancelledError:
                # 先发送取消、显示提示，再等后端 error 到达并被静默吞掉
                await self._cancel_current_turn()
                await asyncio.sleep(0.3)
            finally:
                loop.remove_signal_handler(signal.SIGINT)
