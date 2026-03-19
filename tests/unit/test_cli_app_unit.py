"""CLIApp 单元测试

启动进程内 WebSocket 服务进行真实测试，不使用 mock/patch。
"""
from __future__ import annotations

import asyncio
import json
import socket

import pytest
import pytest_asyncio
import uvicorn

from agentos.app.cli.app import CLIApp
from tests.conftest import load_gemini_config, skip_if_gemini_unavailable


def _find_free_port() -> int:
    """找一个可用的本地端口"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def _create_ws_server(tmp_path, provider_name: str = "mock"):
    """启动进程内 FastAPI WebSocket 服务，支持 mock 和 gemini provider。"""
    from pathlib import Path
    from dataclasses import dataclass as dc

    from agentos.app.gateway.main import app
    from agentos.platform.config.config import Config
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.capabilities.tools.registry import ToolRegistry
    from agentos.capabilities.skills.registry import SkillRegistry
    from agentos.capabilities.skills.market_service import SkillMarketService
    from agentos.adapters.storage.repository import Repository
    from agentos.kernel.events.bus import PublicEventBus
    from agentos.kernel.events.persister import EventPersister
    from agentos.kernel.events.router import BusRouter
    from agentos.kernel.runtime.publisher import EventPublisher
    from agentos.kernel.runtime.agent_runtime import AgentRuntime
    from agentos.kernel.runtime.llm_runtime import LLMRuntime
    from agentos.kernel.runtime.tool_runtime import ToolRuntime
    from agentos.kernel.runtime.title_runtime import TitleRuntime
    from agentos.kernel.runtime.context_builder import ContextBuilder
    from agentos.kernel.runtime.state import SessionStateStore
    from agentos.kernel.runtime.session_maintenance import SessionMaintenance
    from agentos.adapters.llm.factory import LLMFactory
    from agentos.adapters.channels.websocket_channel import WebSocketChannel
    from agentos.interfaces.ws.gateway import Gateway
    from agentos.kernel.heartbeat.runtime import HeartbeatRuntime
    from agentos.kernel.scheduler.runtime import CronRuntime
    from agentos.platform.config.workspace import ensure_workspace

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    # 基础配置
    config_path = tmp_path / "config.yml"
    config_path.write_text("security:\n  auth_enabled: false\n", encoding="utf-8")
    cfg = Config(config_path=config_path)

    # 确保全局 config 也关闭 auth（中间件使用全局 config）
    from agentos.platform.config.config import config as global_config
    global_config.set("security.auth_enabled", False)
    cfg.set("system.workspace_dir", str(workspace_dir))

    # 配置 provider
    if provider_name == "gemini":
        gemini_cfg = load_gemini_config()
        cfg.set("agent.model", "gemini_pro")
        cfg.set("llm.default_model", "gemini_pro")
        cfg.data["llm"]["providers"]["gemini"] = {
            **cfg.data["llm"]["providers"].get("gemini", {}),
            **gemini_cfg,
        }
    # mock 使用默认配置即可（Config 默认就是 mock）

    await ensure_workspace(str(workspace_dir))

    repo = Repository(db_path=str(tmp_path / "test.db"))
    await repo.init()

    await SessionMaintenance(repo=repo).run_maintenance()

    agent_config_dir = tmp_path / "agents"
    agent_config_dir.mkdir()
    agent_registry = AgentRegistry(config_dir=agent_config_dir)
    agent_registry.load_from_config(cfg.data)

    tool_registry = ToolRegistry()

    skills_dir = workspace_dir / "skills"
    skills_dir.mkdir()
    state_file = workspace_dir / "skills_state.json"
    builtin_skills_dir = Path(__file__).resolve().parent.parent.parent / "workspace" / "skills"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=builtin_skills_dir,
    )
    skill_registry.load_skills(cfg.data)

    market_service = SkillMarketService(
        skills_dir=skills_dir,
        skill_registry=skill_registry,
        config=cfg.data,
    )

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=60)
    state_store = SessionStateStore()

    context_builder = ContextBuilder(
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        workspace_dir=str(workspace_dir),
    )
    context_builder.agent_registry = agent_registry

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
        agent_registry=agent_registry,
        memory_manager=None,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(
        bus_router=bus_router, registry=tool_registry,
        agent_registry=agent_registry,
    )
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    from agentos.platform.security.auth import TokenAuthService
    auth_service = TokenAuthService()

    gw = Gateway(publisher=publisher, repo=repo, agent_registry=agent_registry)
    ws_channel = WebSocketChannel("websocket", auth_service=auth_service)
    gw.register_channel(ws_channel)

    cron_runtime = CronRuntime(bus=bus, repo=repo, gateway=gw)
    heartbeat_runtime = HeartbeatRuntime(bus=bus, repo=repo)

    # 启动所有 runtime
    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()
    await gw.start()
    await cron_runtime.start()
    await heartbeat_runtime.start()

    # 挂载到 app.state（和 lifespan 一致）
    @dc
    class Services:
        repo: Repository
        bus: PublicEventBus
        publisher: EventPublisher
        bus_router: BusRouter
        persister: EventPersister
        agent_runtime: AgentRuntime
        llm_runtime: LLMRuntime
        tool_runtime: ToolRuntime
        title_runtime: TitleRuntime
        gateway: Gateway
        ws_channel: WebSocketChannel
        cron_runtime: CronRuntime
        heartbeat_runtime: HeartbeatRuntime
        auth_service: object

    app.state.services = Services(
        repo=repo, bus=bus, publisher=publisher,
        bus_router=bus_router, persister=persister,
        agent_runtime=agent_runtime, llm_runtime=llm_runtime,
        tool_runtime=tool_runtime, title_runtime=title_runtime,
        gateway=gw, ws_channel=ws_channel,
        cron_runtime=cron_runtime, heartbeat_runtime=heartbeat_runtime,
        auth_service=auth_service,
    )
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.agent_registry = agent_registry
    app.state.config = cfg
    app.state.market_service = market_service

    # 使用 uvicorn 在后台任务中运行
    port = _find_free_port()
    uvi_config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error",
        lifespan="off",  # 手动管理 state，不触发 lifespan
    )
    server = uvicorn.Server(uvi_config)
    serve_task = asyncio.create_task(server.serve())
    # 等待服务就绪
    for _ in range(50):
        await asyncio.sleep(0.05)
        if server.started:
            break

    # 返回清理所需的所有对象
    return {
        "host": "127.0.0.1",
        "port": port,
        "server": server,
        "serve_task": serve_task,
        "market_service": market_service,
        "cron_runtime": cron_runtime,
        "heartbeat_runtime": heartbeat_runtime,
        "agent_runtime": agent_runtime,
        "llm_runtime": llm_runtime,
        "tool_runtime": tool_runtime,
        "title_runtime": title_runtime,
        "gw": gw,
        "bus_router": bus_router,
        "persister": persister,
        "app": app,
    }


async def _teardown_ws_server(ctx: dict):
    """关闭 ws_server 并清理 app.state。"""
    ctx["server"].should_exit = True
    await ctx["serve_task"]

    await ctx["market_service"].shutdown()
    await ctx["cron_runtime"].stop()
    await ctx["heartbeat_runtime"].stop()
    await ctx["agent_runtime"].stop()
    await ctx["llm_runtime"].stop()
    await ctx["tool_runtime"].stop()
    await ctx["title_runtime"].stop()
    await ctx["gw"].stop()
    await ctx["bus_router"].stop()
    await ctx["persister"].stop()

    app = ctx["app"]
    for attr in ("services", "agent_registry", "tool_registry", "skill_registry",
                 "config", "market_service"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


@pytest_asyncio.fixture
async def ws_server(tmp_path):
    """启动进程内 FastAPI WebSocket 服务（使用 mock provider）"""
    ctx = await _create_ws_server(tmp_path, provider_name="mock")
    yield {"host": ctx["host"], "port": ctx["port"]}
    await _teardown_ws_server(ctx)


@pytest_asyncio.fixture
async def ws_server_gemini(tmp_path):
    """启动进程内 FastAPI WebSocket 服务（使用 gemini provider）"""
    ctx = await _create_ws_server(tmp_path, provider_name="gemini")
    yield {"host": ctx["host"], "port": ctx["port"]}
    await _teardown_ws_server(ctx)


class TestCLIAppInit:
    """初始化参数测试"""

    def _make_app(self, **kwargs):
        defaults = dict(host="localhost", port=8000)
        defaults.update(kwargs)
        return CLIApp(**defaults)

    def test_default_init(self):
        """默认参数初始化"""
        app = self._make_app()
        assert app.host == "localhost"
        assert app.port == 8000
        assert app.initial_agent_id is None
        assert app.initial_session_id is None
        assert app.debug is False
        assert app.execute is None
        assert app.current_agent_id == "default"
        assert app.ws is None
        assert app._last_response == ""

    def test_custom_init(self):
        """自定义参数初始化"""
        app = self._make_app(
            host="127.0.0.1",
            port=9000,
            agent_id="test-agent",
            session_id="session-123",
            debug=True,
            execute="hello",
        )
        assert app.host == "127.0.0.1"
        assert app.port == 9000
        assert app.initial_agent_id == "test-agent"
        assert app.initial_session_id == "session-123"
        assert app.debug is True
        assert app.execute == "hello"
        assert app.current_agent_id == "test-agent"


class TestReceiveLoopParsing:
    """测试内部状态（不依赖 WebSocket）"""

    def _make_app(self):
        return CLIApp(host="localhost", port=8000)

    async def test_waiting_event_starts_unset(self):
        """_waiting 事件初始为未设置状态"""
        app = self._make_app()
        assert not app._waiting.is_set()

    async def test_confirm_queue_starts_empty(self):
        """确认队列初始为空"""
        app = self._make_app()
        assert app._confirm_queue.empty()

    async def test_confirm_queue_put_get(self):
        """确认队列可正常存取"""
        app = self._make_app()
        data = {"payload": {"tool_call_id": "tc-1"}}
        await app._confirm_queue.put(data)
        assert not app._confirm_queue.empty()
        got = await app._confirm_queue.get()
        assert got["payload"]["tool_call_id"] == "tc-1"


class TestWaitForTurn:
    """_wait_for_turn 方法测试"""

    def _make_app(self):
        return CLIApp(host="localhost", port=8000)

    async def test_simple_wait(self):
        """没有确认请求时直接等待完成"""
        app = self._make_app()

        async def set_waiting():
            await asyncio.sleep(0.01)
            app._waiting.set()

        asyncio.create_task(set_waiting())
        await asyncio.wait_for(app._wait_for_turn(), timeout=1.0)


class TestSendAndSessionMethods:
    """通过进程内 WebSocket 服务测试 _send/_create_session 等方法"""

    async def test_send_json(self, ws_server):
        """_send 发送 JSON 消息到服务端"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            # 发送 create_session，服务端会返回 session_created
            await app._send({
                "type": "create_session",
                "payload": {"agent_id": "default"},
            })
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)
            assert data["type"] == "session_created"
            assert "session_id" in data

    async def test_create_session_default(self, ws_server):
        """_create_session 创建默认会话并返回 session_id"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            sid = await app._create_session()
            assert sid is not None
            assert sid.startswith("sess_")
            assert app.current_session_id == sid
            assert app.current_agent_id == "default"

    async def test_create_session_custom_agent(self, ws_server):
        """_create_session 指定 agent_id"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port, agent_id="custom")
            app.ws = ws
            sid = await app._create_session("custom")
            assert sid is not None
            assert app.current_agent_id == "custom"

    async def test_load_existing_session(self, ws_server):
        """_load_session 加载已有会话"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            # 先创建会话
            sid = await app._create_session()
            # 再加载
            await app._load_session(sid)
            assert app.current_session_id == sid

    async def test_send_user_input(self, ws_server):
        """_send_user_input 发送用户消息"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            await app._create_session()
            # 发送用户输入
            await app._send_user_input("hello")
            # 应收到至少一条事件消息（agent_thinking / turn_completed 等）
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw)
            # 第一条消息通常是 agent_thinking
            assert data["type"] in ("agent_thinking", "turn_completed", "error")

    async def test_send_approved(self, ws_server):
        """_send_confirmation_response 发送批准"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            await app._create_session()
            # 发送确认响应（即使没有真实确认请求，也不应崩溃）
            confirm_data = {"payload": {"tool_call_id": "tc-fake"}}
            await app._send_confirmation_response(confirm_data, approved=True)
            # 服务端对 tool_confirmation_response 不返回直接响应，但不报错即通过

    async def test_send_rejected(self, ws_server):
        """_send_confirmation_response 发送拒绝"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            await app._create_session()
            confirm_data = {"payload": {"tool_call_id": "tc-fake"}}
            await app._send_confirmation_response(confirm_data, approved=False)

    async def test_receive_loop_turn_completed(self, ws_server):
        """_receive_loop 接收 turn_completed 后设置 _waiting"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            await app._create_session()

            # 启动 receive_loop 后台任务
            recv_task = asyncio.create_task(app._receive_loop())

            # 发送 user_input，mock provider 会返回 turn_completed
            await app._send_user_input("你好")
            # 等待 _waiting 被设置（turn_completed 触发）
            await asyncio.wait_for(app._waiting.wait(), timeout=10)
            assert app._waiting.is_set()
            assert app._last_response != ""

            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

    async def test_receive_loop_error(self, ws_server):
        """_receive_loop 接收 error 后设置 _waiting"""
        import websockets

        host, port = ws_server["host"], ws_server["port"]
        async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
            app = CLIApp(host=host, port=port)
            app.ws = ws
            await app._create_session()

            recv_task = asyncio.create_task(app._receive_loop())

            # 发送未知类型消息，服务端返回 error
            await app._send({"type": "unknown_type_xyz"})
            await asyncio.wait_for(app._waiting.wait(), timeout=5)
            assert app._waiting.is_set()

            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.parametrize("provider_name", ["mock", "gemini"])
    async def test_execute_mode(self, provider_name, tmp_path):
        """_run_execute_mode 脚本模式执行后返回 0"""
        skip_if_gemini_unavailable(provider_name)

        # 根据 provider 创建对应的 ws_server
        ctx = await _create_ws_server(tmp_path, provider_name=provider_name)
        timeout = 60 if provider_name == "gemini" else 15

        try:
            import websockets

            host, port = ctx["host"], ctx["port"]
            async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
                app = CLIApp(host=host, port=port, execute="你好")
                app.ws = ws
                await app._create_session()

                recv_task = asyncio.create_task(app._receive_loop())
                ret = await asyncio.wait_for(app._run_execute_mode(), timeout=timeout)
                assert ret == 0
                assert len(app._last_response) > 0, "应返回非空响应"

                recv_task.cancel()
                try:
                    await recv_task
                except asyncio.CancelledError:
                    pass
        finally:
            await _teardown_ws_server(ctx)


class TestMainFunction:
    """通过进程内 WebSocket 服务测试主函数相关逻辑"""

    @pytest.mark.parametrize("provider_name", ["mock", "gemini"])
    async def test_execute_mode_main(self, provider_name, tmp_path):
        """执行模式完整流程测试"""
        skip_if_gemini_unavailable(provider_name)

        ctx = await _create_ws_server(tmp_path, provider_name=provider_name)
        timeout = 60 if provider_name == "gemini" else 15

        try:
            import websockets

            host, port = ctx["host"], ctx["port"]
            async with websockets.connect(f"ws://{host}:{port}/ws") as ws:
                app = CLIApp(host=host, port=port, execute="hello")
                app.ws = ws
                await app._create_session()

                recv_task = asyncio.create_task(app._receive_loop())
                ret = await asyncio.wait_for(app._run_execute_mode(), timeout=timeout)
                assert ret == 0
                assert len(app._last_response) > 0

                recv_task.cancel()
                try:
                    await recv_task
                except asyncio.CancelledError:
                    pass
        finally:
            await _teardown_ws_server(ctx)
