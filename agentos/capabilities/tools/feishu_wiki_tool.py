"""飞书知识库工具。"""

from __future__ import annotations

from typing import Any

from agentos.adapters.channels.feishu.tool_client import FeishuToolClient, FeishuToolError
from agentos.capabilities.tools.base import Tool, ToolRiskLevel


class FeishuWikiTool(Tool):
    name = "feishu_wiki"
    description = "飞书知识库操作。action: spaces/nodes/get/create/move/rename。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["spaces", "nodes", "get", "create", "move", "rename"],
            },
            "space_id": {"type": "string"},
            "parent_node_token": {"type": "string"},
            "token": {"type": "string"},
            "title": {"type": "string"},
            "obj_type": {
                "type": "string",
                "enum": ["doc", "docx", "sheet", "bitable", "mindnote", "file", "slides"],
            },
            "node_token": {"type": "string"},
            "target_space_id": {"type": "string"},
            "target_parent_token": {"type": "string"},
        },
        "required": ["action"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, feishu_channel: Any):
        self._client = FeishuToolClient(feishu_channel)

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action")
        try:
            if action == "spaces":
                response = await self._client.request_json("GET", "/open-apis/wiki/v2/spaces")
                spaces = response.get("data", {}).get("items", [])
                result = {
                    "spaces": [
                        {
                            "space_id": item.get("space_id"),
                            "name": item.get("name"),
                            "description": item.get("description"),
                            "visibility": item.get("visibility"),
                        }
                        for item in spaces
                    ]
                }
                if not spaces:
                    result["hint"] = (
                        "To grant wiki access: Open wiki space -> Settings -> Members -> Add the bot."
                    )
                return result
            if action == "nodes":
                response = await self._client.request_json(
                    "GET",
                    f"/open-apis/wiki/v2/spaces/{kwargs['space_id']}/nodes",
                    params={"parent_node_token": kwargs.get("parent_node_token")},
                )
                return {"nodes": response.get("data", {}).get("items", [])}
            if action == "get":
                response = await self._client.request_json(
                    "GET",
                    "/open-apis/wiki/v2/spaces/get_node",
                    params={"token": kwargs["token"]},
                )
                return response.get("data", {})
            if action == "create":
                response = await self._client.request_json(
                    "POST",
                    f"/open-apis/wiki/v2/spaces/{kwargs['space_id']}/nodes",
                    body={
                        "obj_type": kwargs.get("obj_type", "docx"),
                        "node_type": "origin",
                        "title": kwargs["title"],
                        "parent_node_token": kwargs.get("parent_node_token"),
                    },
                )
                return response.get("data", {}).get("node", {})
            if action == "move":
                response = await self._client.request_json(
                    "POST",
                    f"/open-apis/wiki/v2/spaces/{kwargs['space_id']}/nodes/{kwargs['node_token']}/move",
                    body={
                        "target_space_id": kwargs.get("target_space_id") or kwargs["space_id"],
                        "target_parent_token": kwargs.get("target_parent_token"),
                    },
                )
                return {
                    "success": True,
                    "node_token": response.get("data", {}).get("node", {}).get("node_token", kwargs["node_token"]),
                }
            if action == "rename":
                await self._client.request_json(
                    "POST",
                    f"/open-apis/wiki/v2/spaces/{kwargs['space_id']}/nodes/{kwargs['node_token']}/update_title",
                    body={"title": kwargs["title"]},
                )
                return {
                    "success": True,
                    "node_token": kwargs["node_token"],
                    "title": kwargs["title"],
                }
            return {"error": f"Unknown action: {action}"}
        except KeyError as exc:
            return {"error": f"Missing required parameter: {exc.args[0]}"}
        except FeishuToolError as exc:
            return {"error": str(exc)}
