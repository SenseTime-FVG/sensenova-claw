"""飞书云空间工具。"""

from __future__ import annotations

from typing import Any

from sensenova_claw.adapters.plugins.feishu.tool_client import FeishuToolClient, FeishuToolError
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


class FeishuDriveTool(Tool):
    name = "feishu_drive"
    description = "飞书云空间操作。action: list/info/create_folder/move/delete。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "info", "create_folder", "move", "delete"],
            },
            "folder_token": {"type": "string"},
            "file_token": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["doc", "docx", "sheet", "bitable", "folder", "file", "mindnote", "shortcut", "slides"],
            },
            "name": {"type": "string"},
        },
        "required": ["action"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, feishu_channel: Any):
        self._client = FeishuToolClient(feishu_channel)

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action")
        try:
            if action == "list":
                response = await self._client.request_json(
                    "GET",
                    "/open-apis/drive/v1/files",
                    params={"folder_token": kwargs.get("folder_token")},
                )
                return {
                    "files": response.get("data", {}).get("files", []),
                    "next_page_token": response.get("data", {}).get("next_page_token"),
                }
            if action == "info":
                response = await self._client.request_json(
                    "GET",
                    "/open-apis/drive/v1/files",
                    params={"folder_token": kwargs.get("folder_token")},
                )
                files = response.get("data", {}).get("files", [])
                file_info = next(
                    (item for item in files if item.get("token") == kwargs["file_token"]),
                    None,
                )
                if not file_info:
                    raise FeishuToolError(f"File not found: {kwargs['file_token']}")
                return file_info
            if action == "create_folder":
                folder_token = kwargs.get("folder_token") or "0"
                response = await self._client.request_json(
                    "POST",
                    "/open-apis/drive/v1/files/create_folder",
                    body={"name": kwargs["name"], "folder_token": folder_token},
                )
                return {
                    "token": response.get("data", {}).get("token"),
                    "url": response.get("data", {}).get("url"),
                }
            if action == "move":
                response = await self._client.request_json(
                    "POST",
                    f"/open-apis/drive/v1/files/{kwargs['file_token']}/move",
                    body={"type": kwargs["type"], "folder_token": kwargs["folder_token"]},
                )
                return {"success": True, "task_id": response.get("data", {}).get("task_id")}
            if action == "delete":
                response = await self._client.request_json(
                    "DELETE",
                    f"/open-apis/drive/v1/files/{kwargs['file_token']}",
                    params={"type": kwargs["type"]},
                )
                return {"success": True, "task_id": response.get("data", {}).get("task_id")}
            return {"error": f"Unknown action: {action}"}
        except KeyError as exc:
            return {"error": f"Missing required parameter: {exc.args[0]}"}
        except FeishuToolError as exc:
            return {"error": str(exc)}
