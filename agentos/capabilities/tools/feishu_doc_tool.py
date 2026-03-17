"""飞书文档工具：兼容 feishu-doc skill 中约定的 action 调用方式。"""

from __future__ import annotations

from typing import Any

from agentos.adapters.channels.feishu.tool_client import FeishuToolClient, FeishuToolError
from agentos.capabilities.tools.base import Tool, ToolRiskLevel

BLOCK_TYPE_NAMES = {
    1: "Page",
    2: "Text",
    3: "Heading1",
    4: "Heading2",
    5: "Heading3",
    12: "Bullet",
    13: "Ordered",
    14: "Code",
    15: "Quote",
    17: "Todo",
    18: "Bitable",
    21: "Diagram",
    22: "Divider",
    23: "File",
    27: "Image",
    30: "Sheet",
    31: "Table",
    32: "TableCell",
}
STRUCTURED_BLOCK_TYPES = {14, 18, 21, 23, 27, 30, 31, 32}


class FeishuDocTool(Tool):
    name = "feishu_doc"
    description = (
        "飞书文档操作。"
        "action: read/write/append/create/list_blocks/get_block/update_block/delete_block/"
        "create_table/write_table_cells/create_table_with_values/upload_image/upload_file。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "read",
                    "write",
                    "append",
                    "create",
                    "list_blocks",
                    "get_block",
                    "update_block",
                    "delete_block",
                    "create_table",
                    "write_table_cells",
                    "create_table_with_values",
                    "upload_image",
                    "upload_file",
                ],
            },
            "doc_token": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "block_id": {"type": "string"},
            "folder_token": {"type": "string"},
            "owner_open_id": {"type": "string"},
            "parent_block_id": {"type": "string"},
            "table_block_id": {"type": "string"},
            "row_size": {"type": "integer", "minimum": 1},
            "column_size": {"type": "integer", "minimum": 1},
            "column_width": {"type": "array", "items": {"type": "number"}},
            "values": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "url": {"type": "string"},
            "file_path": {"type": "string"},
            "filename": {"type": "string"},
            "index": {"type": "integer", "minimum": 0},
        },
        "required": ["action"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, feishu_channel: Any):
        self._client = FeishuToolClient(feishu_channel)

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action")
        try:
            if action == "read":
                return await self._read_doc(kwargs["doc_token"])
            if action == "write":
                return await self._write_doc(kwargs["doc_token"], kwargs["content"])
            if action == "append":
                return await self._append_doc(kwargs["doc_token"], kwargs["content"])
            if action == "create":
                return await self._create_doc(
                    kwargs["title"],
                    folder_token=kwargs.get("folder_token"),
                    owner_open_id=kwargs.get("owner_open_id"),
                )
            if action == "list_blocks":
                return await self._list_blocks(kwargs["doc_token"])
            if action == "get_block":
                return await self._get_block(kwargs["doc_token"], kwargs["block_id"])
            if action == "update_block":
                return await self._update_block(
                    kwargs["doc_token"], kwargs["block_id"], kwargs["content"]
                )
            if action == "delete_block":
                return await self._delete_block(kwargs["doc_token"], kwargs["block_id"])
            if action == "create_table":
                return await self._create_table(
                    kwargs["doc_token"],
                    kwargs["row_size"],
                    kwargs["column_size"],
                    parent_block_id=kwargs.get("parent_block_id"),
                    column_width=kwargs.get("column_width"),
                )
            if action == "write_table_cells":
                return await self._write_table_cells(
                    kwargs["doc_token"], kwargs["table_block_id"], kwargs["values"]
                )
            if action == "create_table_with_values":
                created = await self._create_table(
                    kwargs["doc_token"],
                    kwargs["row_size"],
                    kwargs["column_size"],
                    parent_block_id=kwargs.get("parent_block_id"),
                    column_width=kwargs.get("column_width"),
                )
                written = await self._write_table_cells(
                    kwargs["doc_token"],
                    created["table_block_id"],
                    kwargs["values"],
                )
                return {**created, "cells_written": written["cells_written"]}
            if action == "upload_image":
                return await self._upload_image(
                    kwargs["doc_token"],
                    url=kwargs.get("url"),
                    file_path=kwargs.get("file_path"),
                    parent_block_id=kwargs.get("parent_block_id"),
                    filename=kwargs.get("filename"),
                    index=kwargs.get("index"),
                )
            if action == "upload_file":
                return await self._upload_file(
                    kwargs["doc_token"],
                    url=kwargs.get("url"),
                    file_path=kwargs.get("file_path"),
                    parent_block_id=kwargs.get("parent_block_id"),
                    filename=kwargs.get("filename"),
                )
            return {"error": f"Unknown action: {action}"}
        except KeyError as exc:
            return {"error": f"Missing required parameter: {exc.args[0]}"}
        except FeishuToolError as exc:
            return {"error": str(exc)}

    async def _read_doc(self, doc_token: str) -> dict[str, Any]:
        content_res, info_res, blocks_res = await self._multi_request(
            [
                self._client.request_json(
                    "GET",
                    f"/open-apis/docx/v1/documents/{doc_token}/raw_content",
                ),
                self._client.request_json(
                    "GET",
                    f"/open-apis/docx/v1/documents/{doc_token}",
                ),
                self._client.request_json(
                    "GET",
                    f"/open-apis/docx/v1/documents/{doc_token}/blocks",
                ),
            ]
        )
        blocks = blocks_res.get("data", {}).get("items", [])
        block_types: dict[str, int] = {}
        structured_types: list[str] = []
        for block in blocks:
            block_type = block.get("block_type", 0)
            name = BLOCK_TYPE_NAMES.get(block_type, f"type_{block_type}")
            block_types[name] = block_types.get(name, 0) + 1
            if block_type in STRUCTURED_BLOCK_TYPES and name not in structured_types:
                structured_types.append(name)
        result = {
            "title": info_res.get("data", {}).get("document", {}).get("title"),
            "content": content_res.get("data", {}).get("content", ""),
            "revision_id": info_res.get("data", {}).get("document", {}).get("revision_id"),
            "block_count": len(blocks),
            "block_types": block_types,
        }
        if structured_types:
            result["hint"] = (
                f'This document contains {", ".join(structured_types)} '
                'which are NOT included in the plain text above. '
                'Use feishu_doc with action: "list_blocks" to get full content.'
            )
        return result

    async def _write_doc(self, doc_token: str, content: str) -> dict[str, Any]:
        deleted = await self._clear_document(doc_token)
        blocks, first_level_ids = await self._convert_markdown(content)
        if not blocks:
            return {"success": True, "blocks_deleted": deleted, "blocks_added": 0}
        inserted = await self._insert_descendants(
            doc_token=doc_token,
            parent_block_id=doc_token,
            blocks=blocks,
            children_ids=first_level_ids,
        )
        return {
            "success": True,
            "blocks_deleted": deleted,
            "blocks_added": len(blocks),
            "block_ids": [item.get("block_id") for item in inserted if item.get("block_id")],
        }

    async def _append_doc(self, doc_token: str, content: str) -> dict[str, Any]:
        blocks, first_level_ids = await self._convert_markdown(content)
        if not blocks:
            raise FeishuToolError("Content is empty")
        inserted = await self._insert_descendants(
            doc_token=doc_token,
            parent_block_id=doc_token,
            blocks=blocks,
            children_ids=first_level_ids,
        )
        return {
            "success": True,
            "blocks_added": len(blocks),
            "block_ids": [item.get("block_id") for item in inserted if item.get("block_id")],
        }

    async def _create_doc(
        self,
        title: str,
        *,
        folder_token: str | None = None,
        owner_open_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        response = await self._client.request_json(
            "POST",
            "/open-apis/docx/v1/documents",
            body=body,
        )
        document = response.get("data", {}).get("document", {})
        doc_token = document.get("document_id")
        result = {
            "document_id": doc_token,
            "title": document.get("title", title),
            "url": f"https://feishu.cn/docx/{doc_token}" if doc_token else None,
        }
        if owner_open_id and doc_token:
            try:
                await self._client.request_json(
                    "POST",
                    f"/open-apis/drive/v2/permissions/{doc_token}/members",
                    params={"type": "docx", "need_notification": "false"},
                    body={
                        "member_type": "openid",
                        "member_id": owner_open_id,
                        "perm": "edit",
                    },
                )
                result["requester_permission_added"] = True
                result["requester_open_id"] = owner_open_id
            except FeishuToolError as exc:
                result["requester_permission_added"] = False
                result["requester_permission_error"] = str(exc)
        return result

    async def _list_blocks(self, doc_token: str) -> dict[str, Any]:
        response = await self._client.request_json(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks",
        )
        return {"blocks": response.get("data", {}).get("items", [])}

    async def _get_block(self, doc_token: str, block_id: str) -> dict[str, Any]:
        response = await self._client.request_json(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{block_id}",
        )
        return {"block": response.get("data", {}).get("block")}

    async def _update_block(self, doc_token: str, block_id: str, content: str) -> dict[str, Any]:
        await self._client.request_json(
            "PATCH",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{block_id}",
            body={
                "update_text_elements": {
                    "elements": [{"text_run": {"content": content}}],
                }
            },
        )
        return {"success": True, "block_id": block_id}

    async def _delete_block(self, doc_token: str, block_id: str) -> dict[str, Any]:
        block = await self._get_block(doc_token, block_id)
        parent_id = block.get("block", {}).get("parent_id") or doc_token
        children = await self._client.request_json(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{parent_id}/children",
        )
        items = children.get("data", {}).get("items", [])
        idx = next((i for i, item in enumerate(items) if item.get("block_id") == block_id), -1)
        if idx < 0:
            raise FeishuToolError("Block not found")
        await self._client.request_json(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{parent_id}/children/batch_delete",
            body={"start_index": idx, "end_index": idx + 1},
        )
        return {"success": True, "deleted_block_id": block_id}

    async def _create_table(
        self,
        doc_token: str,
        row_size: int,
        column_size: int,
        *,
        parent_block_id: str | None = None,
        column_width: list[int] | None = None,
    ) -> dict[str, Any]:
        if column_width and len(column_width) != column_size:
            raise FeishuToolError("column_width length must equal column_size")
        block_id = parent_block_id or doc_token
        body: dict[str, Any] = {
            "children": [
                {
                    "block_type": 31,
                    "table": {
                        "property": {
                            "row_size": row_size,
                            "column_size": column_size,
                        }
                    },
                }
            ]
        }
        if column_width:
            body["children"][0]["table"]["property"]["column_width"] = column_width
        response = await self._client.request_json(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{block_id}/children",
            body=body,
        )
        children = response.get("data", {}).get("children", [])
        table_block = next(
            (item for item in children if item.get("block_type") == 31),
            None,
        )
        return {
            "success": True,
            "table_block_id": table_block.get("block_id") if table_block else None,
            "row_size": row_size,
            "column_size": column_size,
        }

    async def _write_table_cells(
        self,
        doc_token: str,
        table_block_id: str,
        values: list[list[str]],
    ) -> dict[str, Any]:
        table_res = await self._client.request_json(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{table_block_id}",
        )
        table = table_res.get("data", {}).get("block", {}).get("table", {})
        rows = table.get("property", {}).get("row_size")
        cols = table.get("property", {}).get("column_size")
        cell_ids = table.get("cells", [])
        if not rows or not cols or not cell_ids:
            raise FeishuToolError("Table cell IDs unavailable from table block")
        written = 0
        for row_idx, row_values in enumerate(values[:rows]):
            for col_idx, cell_value in enumerate(row_values[:cols]):
                cell_id = cell_ids[row_idx * cols + col_idx]
                await self._replace_cell_content(doc_token, cell_id, cell_value)
                written += 1
        return {
            "success": True,
            "table_block_id": table_block_id,
            "cells_written": written,
            "table_size": {"rows": rows, "cols": cols},
        }

    async def _upload_image(
        self,
        doc_token: str,
        *,
        url: str | None,
        file_path: str | None,
        parent_block_id: str | None,
        filename: str | None,
        index: int | None,
    ) -> dict[str, Any]:
        block_id = parent_block_id or doc_token
        created = await self._client.request_json(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{block_id}/children",
            body={
                "children": [{"block_type": 27, "image": {}}],
                "index": index if index is not None else -1,
            },
        )
        image_block = next(
            (item for item in created.get("data", {}).get("children", []) if item.get("block_type") == 27),
            None,
        )
        if not image_block:
            raise FeishuToolError("Failed to create image block")
        file_bytes, resolved_name = await self._resolve_upload_input(url, file_path, filename)
        uploaded = await self._client.request_multipart(
            "/open-apis/drive/v1/medias/upload_all",
            data={
                "file_name": resolved_name,
                "parent_type": "docx_image",
                "parent_node": image_block["block_id"],
                "size": len(file_bytes),
                "extra": {"drive_route_token": doc_token},
            },
            file_bytes=file_bytes,
            file_name=resolved_name,
        )
        file_token = uploaded.get("file_token") or uploaded.get("data", {}).get("file_token")
        await self._client.request_json(
            "PATCH",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{image_block['block_id']}",
            body={"replace_image": {"token": file_token}},
        )
        return {
            "success": True,
            "block_id": image_block["block_id"],
            "file_token": file_token,
            "file_name": resolved_name,
            "size": len(file_bytes),
        }

    async def _upload_file(
        self,
        doc_token: str,
        *,
        url: str | None,
        file_path: str | None,
        parent_block_id: str | None,
        filename: str | None,
    ) -> dict[str, Any]:
        _ = parent_block_id
        file_bytes, resolved_name = await self._resolve_upload_input(url, file_path, filename)
        uploaded = await self._client.request_multipart(
            "/open-apis/drive/v1/medias/upload_all",
            data={
                "file_name": resolved_name,
                "parent_type": "docx_file",
                "parent_node": doc_token,
                "size": len(file_bytes),
            },
            file_bytes=file_bytes,
            file_name=resolved_name,
        )
        file_token = uploaded.get("file_token") or uploaded.get("data", {}).get("file_token")
        return {
            "success": True,
            "file_token": file_token,
            "file_name": resolved_name,
            "size": len(file_bytes),
            "note": "File uploaded to drive. Direct file block creation is not supported by the Feishu API.",
        }

    async def _convert_markdown(self, content: str) -> tuple[list[dict[str, Any]], list[str]]:
        response = await self._client.request_json(
            "POST",
            "/open-apis/docx/v1/documents/convert",
            body={"content_type": "markdown", "content": content},
        )
        data = response.get("data", {})
        return data.get("blocks", []), data.get("first_level_block_ids", [])

    async def _clear_document(self, doc_token: str) -> int:
        blocks = await self._list_blocks(doc_token)
        items = blocks.get("blocks", [])
        top_level = [
            item for item in items
            if item.get("parent_id") == doc_token and item.get("block_type") != 1
        ]
        if top_level:
            await self._client.request_json(
                "POST",
                f"/open-apis/docx/v1/documents/{doc_token}/blocks/{doc_token}/children/batch_delete",
                body={"start_index": 0, "end_index": len(top_level)},
            )
        return len(top_level)

    async def _insert_descendants(
        self,
        *,
        doc_token: str,
        parent_block_id: str,
        blocks: list[dict[str, Any]],
        children_ids: list[str],
        index: int = -1,
    ) -> list[dict[str, Any]]:
        response = await self._client.request_json(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{parent_block_id}/descendant",
            body={
                "children_id": children_ids,
                "descendants": blocks,
                "index": index,
            },
        )
        return response.get("data", {}).get("children", [])

    async def _replace_cell_content(self, doc_token: str, cell_id: str, content: str) -> None:
        children_res = await self._client.request_json(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{cell_id}/children",
        )
        items = children_res.get("data", {}).get("items", [])
        if items:
            await self._client.request_json(
                "POST",
                f"/open-apis/docx/v1/documents/{doc_token}/blocks/{cell_id}/children/batch_delete",
                body={"start_index": 0, "end_index": len(items)},
            )
        blocks, first_level_ids = await self._convert_markdown(content)
        if blocks:
            await self._insert_descendants(
                doc_token=doc_token,
                parent_block_id=cell_id,
                blocks=blocks,
                children_ids=first_level_ids,
            )

    async def _resolve_upload_input(
        self,
        url: str | None,
        file_path: str | None,
        filename: str | None,
    ) -> tuple[bytes, str]:
        if bool(url) == bool(file_path):
            raise FeishuToolError("Provide exactly one of url or file_path")
        if url:
            content, guessed_name = await self._client.download(url)
            return content, filename or guessed_name
        content, local_name = self._client.read_local_file(file_path or "")
        return content, filename or local_name

    @staticmethod
    async def _multi_request(tasks: list[Any]) -> list[Any]:
        import asyncio

        return list(await asyncio.gather(*tasks))
