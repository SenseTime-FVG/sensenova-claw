#!/usr/bin/env python
"""TUI 端到端测试 - 模拟真实用户交互"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TUISimulator:
    """模拟TUI客户端的完整行为"""

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._session_id: str | None = None
        self._message_log = []

    async def connect(self) -> bool:
        """连接到Gateway"""
        try:
            self._ws = await websockets.connect(self._ws_url)
            logger.info("=" * 60)
            logger.info("✓ 已连接到 Gateway")
            logger.info("=" * 60)
            return True
        except Exception as e:
            logger.error(f"✗ 连接失败: {e}")
            return False

    async def create_session(self) -> bool:
        """创建会话"""
        try:
            await self._ws.send(json.dumps({
                "type": "create_session",
                "payload": {},
                "timestamp": time.time()
            }))

            response = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get("type") == "session_created":
                self._session_id = data.get("session_id")
                logger.info(f"✓ 会话已创建: {self._session_id}")
                logger.info("")
                return True
            else:
                logger.error(f"✗ 会话创建失败")
                return False
        except Exception as e:
            logger.error(f"✗ 会话创建异常: {e}")
            return False

    async def send_message(self, content: str) -> None:
        """发送用户消息（模拟用户在TUI中输入）"""
        if not self._ws or not self._session_id:
            logger.error("✗ 未连接或未创建会话")
            return

        logger.info("─" * 60)
        logger.info(f"👤 User: {content}")
        logger.info("─" * 60)

        await self._ws.send(json.dumps({
            "type": "user_input",
            "session_id": self._session_id,
            "payload": {
                "content": content,
                "attachments": [],
                "context_files": []
            },
            "timestamp": time.time()
        }))

    async def watch_responses(self, timeout: float = 30.0) -> None:
        """监听并显示所有响应（模拟TUI显示消息）"""
        start_time = time.time()
        turn_completed = False

        try:
            while time.time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(self._ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    payload = data.get("payload", {})

                    # 模拟TUI的显示逻辑
                    if msg_type == "agent_thinking":
                        description = payload.get("description", "")
                        logger.info(f"  💭 {description}")

                    elif msg_type == "tool_execution":
                        tool_name = payload.get("tool_name", "")
                        logger.info(f"  🔧 Tool: {tool_name} 执行中...")

                    elif msg_type == "tool_result":
                        tool_name = payload.get("tool_name", "")
                        logger.info(f"  ✓ Tool: {tool_name} 完成")

                    elif msg_type == "turn_completed":
                        response = payload.get("content", "") or payload.get("final_response", "")
                        logger.info("─" * 60)
                        logger.info(f"🤖 Assistant: {response}")
                        logger.info("─" * 60)
                        logger.info("")
                        turn_completed = True
                        break

                    elif msg_type == "error":
                        error_msg = payload.get("message", "Unknown error")
                        logger.error(f"  ❌ Error: {error_msg}")

                    elif msg_type == "title_updated":
                        # 静默处理title更新
                        pass

                    else:
                        # 其他消息类型
                        logger.debug(f"  📩 {msg_type}")

                except asyncio.TimeoutError:
                    if turn_completed:
                        break
                    continue

        except Exception as e:
            logger.error(f"✗ 监听响应异常: {e}")

    async def close(self) -> None:
        """关闭连接"""
        if self._ws:
            await self._ws.close()
            logger.info("=" * 60)
            logger.info("✓ 连接已关闭")
            logger.info("=" * 60)

    async def run_interactive_test(self) -> None:
        """运行交互式测试"""
        logger.info("\n")
        logger.info("╔" + "═" * 58 + "╗")
        logger.info("║" + " " * 15 + "AgentOS TUI 模拟测试" + " " * 23 + "║")
        logger.info("╚" + "═" * 58 + "╝")
        logger.info("")

        # 连接
        if not await self.connect():
            return

        # 创建会话
        if not await self.create_session():
            await self.close()
            return

        # 测试场景1: 工具调用
        logger.info("📝 测试场景1: 工具调用")
        await self.send_message("搜索苏超冠军是谁")
        await self.watch_responses(timeout=30.0)

        # 等待一下
        await asyncio.sleep(1)

        # 测试场景2: 多轮对话
        logger.info("📝 测试场景2: 多轮对话")
        await self.send_message("我第一个问题是什么")
        await self.watch_responses(timeout=20.0)

        # 等待一下
        await asyncio.sleep(1)

        # 测试场景3: 普通对话
        logger.info("📝 测试场景3: 普通对话")
        await self.send_message("你好")
        await self.watch_responses(timeout=15.0)

        # 关闭连接
        await self.close()

        logger.info("\n✅ 测试完成！")
        logger.info("\n如果你看到了上面的对话内容，说明TUI功能正常。")
        logger.info("现在可以运行真实的TUI: uv run python run_tui.py --port 8000")


async def main():
    ws_url = "ws://localhost:8000/ws"
    simulator = TUISimulator(ws_url)

    try:
        await simulator.run_interactive_test()
    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
