#!/usr/bin/env python
"""TUI 自动化测试脚本"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TUITester:
    """TUI 测试客户端"""

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._session_id: str | None = None
        self._messages = []
        self._test_results = []

    async def connect(self) -> bool:
        """连接到 Gateway"""
        try:
            self._ws = await websockets.connect(self._ws_url)
            logger.info(f"✓ 连接到 Gateway: {self._ws_url}")
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

            # 等待会话创建响应
            response = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get("type") == "session_created":
                self._session_id = data.get("session_id")
                logger.info(f"✓ 会话创建成功: {self._session_id}")
                return True
            else:
                logger.error(f"✗ 会话创建失败: {data}")
                return False
        except Exception as e:
            logger.error(f"✗ 会话创建异常: {e}")
            return False

    async def send_message(self, content: str) -> None:
        """发送用户消息"""
        if not self._ws or not self._session_id:
            logger.error("✗ 未连接或未创建会话")
            return

        logger.info(f"→ 发送消息: {content}")
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

    async def collect_responses(self, timeout: float = 30.0) -> list[dict]:
        """收集响应消息"""
        responses = []
        start_time = time.time()
        turn_completed = False

        try:
            while time.time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(self._ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    responses.append(data)

                    msg_type = data.get("type", "")

                    # 打印所有收到的消息用于调试
                    logger.debug(f"  📨 收到消息类型: {msg_type}")

                    # 记录关键事件
                    if msg_type == "tool_execution":
                        tool_name = data.get("payload", {}).get("tool_name", "")
                        status = data.get("payload", {}).get("status", "")
                        logger.info(f"  🔧 工具调用: {tool_name} - {status}")

                    elif msg_type == "tool_result":
                        tool_name = data.get("payload", {}).get("tool_name", "")
                        logger.info(f"  ✓ 工具完成: {tool_name}")

                    elif msg_type == "turn_completed":
                        content = data.get("payload", {}).get("content", "")
                        if content:
                            logger.info(f"  💬 Agent回复: {content[:100]}...")
                        turn_completed = True
                        break

                except asyncio.TimeoutError:
                    if turn_completed:
                        break
                    continue

        except Exception as e:
            logger.error(f"✗ 收集响应异常: {e}")

        logger.info(f"  📊 共收到 {len(responses)} 条消息")
        return responses

    async def test_tool_call(self) -> bool:
        """测试1: 工具调用"""
        logger.info("\n=== 测试1: 工具调用 ===")
        await self.send_message("搜索苏超冠军是谁")
        responses = await self.collect_responses(timeout=30.0)

        # 检查是否有工具调用
        tool_called = False
        tool_completed = False
        turn_completed = False

        for resp in responses:
            msg_type = resp.get("type", "")

            if msg_type == "tool_execution":
                tool_called = True
            elif msg_type == "tool_result":
                tool_completed = True
            elif msg_type == "turn_completed":
                turn_completed = True

        success = tool_called and tool_completed and turn_completed
        if success:
            logger.info("✓ 测试1通过: 工具调用正常")
        else:
            logger.error(f"✗ 测试1失败: tool_called={tool_called}, tool_completed={tool_completed}, turn_completed={turn_completed}")

        return success

    async def test_multi_turn(self) -> bool:
        """测试2: 多轮对话"""
        logger.info("\n=== 测试2: 多轮对话 ===")
        await self.send_message("我第一个问题是什么")
        responses = await self.collect_responses(timeout=20.0)

        # 检查是否有回复
        turn_completed = False
        reply_content = ""

        for resp in responses:
            msg_type = resp.get("type", "")

            if msg_type == "turn_completed":
                payload = resp.get("payload", {})
                reply_content = payload.get("content", "") or payload.get("final_response", "")
                turn_completed = True

        # 检查回复是否包含关键词或者至少有回复
        keywords = ["苏超", "冠军", "搜索", "问题"]
        contains_keyword = any(keyword in reply_content for keyword in keywords)
        has_reply = len(reply_content) > 0

        success = turn_completed and has_reply
        if success:
            if contains_keyword:
                logger.info(f"✓ 测试2通过: 多轮对话正常，回复包含上下文")
            else:
                logger.warning(f"⚠ 测试2部分通过: 有回复但未包含预期关键词")
            logger.info(f"  回复内容: {reply_content[:200]}...")
        else:
            logger.error(f"✗ 测试2失败: turn_completed={turn_completed}, has_reply={has_reply}")
            if reply_content:
                logger.error(f"  回复内容: {reply_content[:200]}")

        return success

    async def close(self) -> None:
        """关闭连接"""
        if self._ws:
            await self._ws.close()
            logger.info("✓ 连接已关闭")

    async def run_tests(self) -> bool:
        """运行所有测试"""
        logger.info("开始 TUI 自动化测试\n")

        # 连接
        if not await self.connect():
            return False

        # 创建会话
        if not await self.create_session():
            await self.close()
            return False

        # 测试1: 工具调用
        test1_passed = await self.test_tool_call()

        # 等待一下
        await asyncio.sleep(2)

        # 测试2: 多轮对话
        test2_passed = await self.test_multi_turn()

        # 关闭连接
        await self.close()

        # 总结
        logger.info("\n=== 测试总结 ===")
        logger.info(f"测试1 (工具调用): {'✓ 通过' if test1_passed else '✗ 失败'}")
        logger.info(f"测试2 (多轮对话): {'✓ 通过' if test2_passed else '✗ 失败'}")

        all_passed = test1_passed and test2_passed
        if all_passed:
            logger.info("\n🎉 所有测试通过!")
        else:
            logger.info("\n❌ 部分测试失败")

        return all_passed


async def main():
    ws_url = "ws://localhost:8000/ws"
    tester = TUITester(ws_url)

    try:
        success = await tester.run_tests()
        exit(0 if success else 1)
    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
