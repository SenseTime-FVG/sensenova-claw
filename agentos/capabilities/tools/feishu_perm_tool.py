"""飞书权限管理工具。"""

from __future__ import annotations

from typing import Any

from agentos.adapters.plugins.feishu.tool_client import FeishuToolClient, FeishuToolError
from agentos.capabilities.tools.base import Tool, ToolRiskLevel


class FeishuPermTool(Tool):
    name = "feishu_perm"
    description = "飞书权限管理。action: list/add/remove。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "add", "remove"]},
            "token": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["doc", "docx", "sheet", "bitable", "folder", "file", "wiki", "mindnote"],
            },
            "member_type": {
                "type": "string",
                "enum": ["email", "openid", "userid", "unionid", "openchat", "opendepartmentid"],
            },
            "member_id": {"type": "string"},
            "perm": {"type": "string", "enum": ["view", "edit", "full_access"]},
        },
        "required": ["action"],
    }
    risk_level = ToolRiskLevel.HIGH

    def __init__(self, feishu_channel: Any):
        self._client = FeishuToolClient(feishu_channel)

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action")
        try:
            if action == "list":
                response = await self._client.request_json(
                    "GET",
                    f"/open-apis/drive/v2/permissions/{kwargs['token']}/members",
                    params={"type": kwargs["type"]},
                )
                return {"members": response.get("data", {}).get("items", [])}
            if action == "add":
                response = await self._client.request_json(
                    "POST",
                    f"/open-apis/drive/v2/permissions/{kwargs['token']}/members",
                    params={"type": kwargs["type"], "need_notification": "false"},
                    body={
                        "member_type": kwargs["member_type"],
                        "member_id": kwargs["member_id"],
                        "perm": kwargs["perm"],
                    },
                )
                return {"success": True, "member": response.get("data", {}).get("member")}
            if action == "remove":
                await self._client.request_json(
                    "DELETE",
                    f"/open-apis/drive/v2/permissions/{kwargs['token']}/members/{kwargs['member_id']}",
                    params={"type": kwargs["type"], "member_type": kwargs["member_type"]},
                )
                return {"success": True}
            return {"error": f"Unknown action: {action}"}
        except KeyError as exc:
            return {"error": f"Missing required parameter: {exc.args[0]}"}
        except FeishuToolError as exc:
            return {"error": str(exc)}
