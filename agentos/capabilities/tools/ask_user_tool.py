from __future__ import annotations

from typing import Any

from agentos.capabilities.tools.base import Tool


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

        # 返回特殊标记，让 ToolRuntime 识别并处理
        return {
            "_ask_user": True,
            "question": question,
            "options": options,
            "multi_select": multi_select,
        }
