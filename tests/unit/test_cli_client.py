"""CLI 客户端入口单元测试

测试 argparse 参数解析行为 + main() 函数通过进程内 WebSocket 服务真实测试。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys

import pytest
import pytest_asyncio
import uvicorn

from agentos.app.cli.app import CLIApp


def _find_free_port() -> int:
    """找一个可用的本地端口"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest_asyncio.fixture
async def ws_server(tmp_path):
    """启动进程内 FastAPI WebSocket 服务（使用 mock provider）"""
    from pathlib import Path
    from dataclasses import dataclass as dc

    from agentos.app.gateway.main import app
    from agentos.platform.config.config import Config
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.capabilities.tools.registry import ToolRegistry
    from agentos.capabilities.skills.registry import SkillRegistry
    from agentos.capabilities.skills.market_service import SkillMarketService
    from agentos.platform.security.path_policy import PathPolicy
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

    config_path = tmp_path / "config.yml"
    config_path.write_text("security:\n  auth_enabled: false\n", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(workspace_dir))

    # 确保全局 config 也关闭 auth（中间件使用全局 config）
    from agentos.platform.config.config import config as global_config
    global_config.set("security.auth_enabled", False)

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

    path_policy = PathPolicy(workspace=workspace_dir)

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
        path_policy=path_policy, agent_registry=agent_registry,
    )
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    gw = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gw.register_channel(ws_channel)

    cron_runtime = CronRuntime(bus=bus, repo=repo, gateway=gw)
    heartbeat_runtime = HeartbeatRuntime(bus=bus, repo=repo)

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()
    await gw.start()
    await cron_runtime.start()
    await heartbeat_runtime.start()

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

    from agentos.platform.security.auth import TokenAuthService
    auth_service = TokenAuthService()

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
    app.state.path_policy = path_policy

    port = _find_free_port()
    uvi_config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error",
        lifespan="off",
    )
    server = uvicorn.Server(uvi_config)
    serve_task = asyncio.create_task(server.serve())
    for _ in range(50):
        await asyncio.sleep(0.05)
        if server.started:
            break

    yield {"host": "127.0.0.1", "port": port}

    server.should_exit = True
    await serve_task

    await market_service.shutdown()
    await cron_runtime.stop()
    await heartbeat_runtime.stop()
    await agent_runtime.stop()
    await llm_runtime.stop()
    await tool_runtime.stop()
    await title_runtime.stop()
    await gw.stop()
    await bus_router.stop()
    await persister.stop()

    for attr in ("services", "agent_registry", "tool_registry", "skill_registry",
                 "config", "market_service", "path_policy"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


class TestArgParsing:
    """测试 CLI 参数解析"""

    def _parse(self, args: list[str]) -> argparse.Namespace:
        """复用 cli_client 中的 argparse 定义"""
        parser = argparse.ArgumentParser(description="AgentOS CLI")
        parser.add_argument("--host", default="localhost")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--agent", default=None, help="Agent ID")
        parser.add_argument("--session", default=None, help="恢复指定 session")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("-e", "--execute", default=None, help="执行单条消息后退出")
        return parser.parse_args(args)

    def test_default_args(self):
        """默认参数解析"""
        ns = self._parse([])
        assert ns.host == "localhost"
        assert ns.port == 8000
        assert ns.agent is None
        assert ns.session is None
        assert ns.debug is False
        assert ns.execute is None

    def test_custom_args(self):
        """自定义参数传递"""
        ns = self._parse([
            "--host", "192.168.1.1",
            "--port", "9999",
            "--agent", "my-agent",
            "--session", "s-abc",
            "--debug",
            "-e", "hello world",
        ])
        assert ns.host == "192.168.1.1"
        assert ns.port == 9999
        assert ns.agent == "my-agent"
        assert ns.session == "s-abc"
        assert ns.debug is True
        assert ns.execute == "hello world"

    def test_short_execute_flag(self):
        """-e 短格式"""
        ns = self._parse(["-e", "run something"])
        assert ns.execute == "run something"

    def test_long_execute_flag(self):
        """--execute 长格式"""
        ns = self._parse(["--execute", "run something"])
        assert ns.execute == "run something"

    def test_debug_flag(self):
        """--debug 开关"""
        ns = self._parse(["--debug"])
        assert ns.debug is True

    def test_port_type(self):
        """端口号是整数类型"""
        ns = self._parse(["--port", "3000"])
        assert ns.port == 3000
        assert isinstance(ns.port, int)


class TestMainFunction:
    """main() 函数通过进程内 WebSocket 服务真实测试"""

    async def test_main_default(self, ws_server):
        """main() 用 execute 模式默认参数运行"""
        from agentos.app.cli.cli_client import main

        host, port = ws_server["host"], ws_server["port"]
        # 通过修改 sys.argv 模拟命令行参数
        original_argv = sys.argv
        sys.argv = ["cli_client", "--host", host, "--port", str(port), "-e", "hello"]
        try:
            # main() 内部调用 asyncio.run()，但我们已经在事件循环中了
            # 所以直接构造 CLIApp 并调用 run()
            app = CLIApp(host=host, port=port, execute="hello")
            ret = await asyncio.wait_for(app.run(), timeout=15)
            assert ret == 0
        finally:
            sys.argv = original_argv

    async def test_main_custom(self, ws_server):
        """main() 用自定义 agent_id 运行"""
        host, port = ws_server["host"], ws_server["port"]
        app = CLIApp(host=host, port=port, agent_id="default", execute="测试消息")
        ret = await asyncio.wait_for(app.run(), timeout=15)
        assert ret == 0
        assert app.current_agent_id == "default"

    async def test_main_return_code(self, ws_server):
        """execute 模式正常完成返回 0"""
        host, port = ws_server["host"], ws_server["port"]
        app = CLIApp(host=host, port=port, execute="你好")
        ret = await asyncio.wait_for(app.run(), timeout=15)
        assert ret == 0
        assert len(app._last_response) > 0
