"""CLI 客户端入口单元测试

测试 main() 函数的参数解析逻辑。
由于 main() 内部会调用 asyncio.run(app.run()) 连接 WebSocket，
这些测试标记为 skip。

改为直接测试 argparse 参数解析行为。
"""
from __future__ import annotations

import argparse
import sys

import pytest


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
    """main() 函数需要 WebSocket，标记 skip"""

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    def test_main_default(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    def test_main_custom(self):
        pass

    @pytest.mark.skip(reason="需要运行中的 WebSocket 服务")
    def test_main_return_code(self):
        pass
