"""AskUserTool — 向用户提问并等待回答

逻辑完全封装在 tool 内部：
1. 发布 USER_QUESTION_ASKED 事件通知前端/CLI
2. 通过 asyncio.Future 等待 USER_QUESTION_ANSWERED 事件
3. tool_worker 只需注入 _ask_user_handler 回调，不需要了解 ask_user 的业务逻辑
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from agentos.capabilities.tools.base import Tool

logger = logging.getLogger(__name__)


class AskUserTool(Tool):
    name = "ask_user"
    description = "向用户提问并等待回答。支持单选、多选和开放式问答。"
    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "问题文本"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选项列表（可选，不提供则为开放式问答）",
            },
            "multi_select": {
                "type": "boolean",
                "default": False,
                "description": "是否多选，默认 False",
            },
        },
        "required": ["question"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        question = kwargs.get("question")
        options = kwargs.get("options")
        multi_select = kwargs.get("multi_select", False)

        # 参数验证
        if multi_select and not options:
            return {"success": False, "error": "多选模式必须提供 options"}

        # 获取注入的回调（由 tool_worker 注入）
        ask_handler = kwargs.get("_ask_user_handler")
        if not ask_handler:
            # 没有 handler 时返回标记，向后兼容
            return {
                "_ask_user": True,
                "question": question,
                "options": options,
                "multi_select": multi_select,
            }

        # 通过 handler 发布问题并等待回答
        return await ask_handler(
            question=question,
            options=options,
            multi_select=multi_select,
            session_id=kwargs.get("_session_id", ""),
            turn_id=kwargs.get("_turn_id", ""),
            tool_call_id=kwargs.get("_tool_call_id", ""),
        )
