"""CLI 客户端入口单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMain:
    """main() 函数测试"""

    def test_default_args(self):
        """默认参数解析并创建 CLIApp"""
        with patch("agentos.app.cli.cli_client.CLIApp") as MockApp, \
             patch("agentos.app.cli.cli_client.asyncio") as mock_asyncio, \
             patch("sys.argv", ["cli_client.py"]):
            mock_app_instance = MagicMock()
            MockApp.return_value = mock_app_instance
            mock_asyncio.run.return_value = 0

            from agentos.app.cli.cli_client import main
            result = main()

            MockApp.assert_called_once_with(
                host="localhost",
                port=8000,
                agent_id=None,
                session_id=None,
                debug=False,
                execute=None,
            )
            mock_asyncio.run.assert_called_once_with(mock_app_instance.run())
            assert result == 0

    def test_custom_args(self):
        """自定义参数传递"""
        with patch("agentos.app.cli.cli_client.CLIApp") as MockApp, \
             patch("agentos.app.cli.cli_client.asyncio") as mock_asyncio, \
             patch("sys.argv", [
                 "cli_client.py",
                 "--host", "192.168.1.1",
                 "--port", "9999",
                 "--agent", "my-agent",
                 "--session", "s-abc",
                 "--debug",
                 "-e", "hello world",
             ]):
            mock_app_instance = MagicMock()
            MockApp.return_value = mock_app_instance
            mock_asyncio.run.return_value = 0

            from agentos.app.cli.cli_client import main
            result = main()

            MockApp.assert_called_once_with(
                host="192.168.1.1",
                port=9999,
                agent_id="my-agent",
                session_id="s-abc",
                debug=True,
                execute="hello world",
            )
            assert result == 0

    def test_return_code_propagation(self):
        """asyncio.run 返回码正确传播"""
        with patch("agentos.app.cli.cli_client.CLIApp") as MockApp, \
             patch("agentos.app.cli.cli_client.asyncio") as mock_asyncio, \
             patch("sys.argv", ["cli_client.py"]):
            MockApp.return_value = MagicMock()
            mock_asyncio.run.return_value = 2

            from agentos.app.cli.cli_client import main
            result = main()
            assert result == 2
