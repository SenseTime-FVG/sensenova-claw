"""个人待办事项 REST API。

数据以 JSON 文件存储在 ~/.sensenova-claw/todolist/todolist_YYYY-MM-DD.json，
方便 Agent 直接读写文件进行推送和标记。
写入操作完成后会通过 EventBus 广播 todolist.updated 事件，前端实时刷新。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from sensenova_claw.platform.config.workspace import default_sensenova_claw_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/todolist", tags=["todolist"])


async def _publish_todolist_event(request: Request, date_str: str, action: str) -> None:
    """通过 EventBus 广播 todolist 变更事件"""
    services = getattr(request.app.state, "services", None)
    if not services:
        return
    bus = getattr(services, "bus", None)
    if not bus:
        return
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    from sensenova_claw.kernel.events.types import TODOLIST_UPDATED, SYSTEM_SESSION_ID
    try:
        await bus.publish(EventEnvelope(
            type=TODOLIST_UPDATED,
            session_id=SYSTEM_SESSION_ID,
            source="api",
            payload={"date": date_str, "action": action},
        ))
    except Exception:
        logger.debug("Failed to publish todolist event", exc_info=True)


# ── Pydantic 模型 ──────────────────────────────────────────────


class TodoItemCreate(BaseModel):
    title: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"] = "medium"
    due_date: str | None = None  # YYYY-MM-DD


class TodoItemUpdate(BaseModel):
    title: str | None = None
    priority: Literal["high", "medium", "low"] | None = None
    due_date: str | None = None
    status: Literal["todo", "done"] | None = None
    order: int | None = None


class TodoReorderBody(BaseModel):
    item_ids: list[str]


# ── 辅助函数 ──────────────────────────────────────────────────


def _todolist_dir(request: Request) -> Path:
    """返回 todolist 目录，不存在则创建。"""
    home = getattr(request.app.state, "sensenova_claw_home", "") or str(default_sensenova_claw_home())
    d = Path(home) / "todolist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path(directory: Path, date_str: str) -> Path:
    return directory / f"todolist_{date_str}.json"


def _normalize_item(item: dict) -> dict:
    """规范化 Agent 手动写入的待办项（字段类型可能不一致）"""
    if "order" in item:
        try:
            item["order"] = int(item["order"])
        except (ValueError, TypeError):
            item["order"] = 0
    if item.get("completed_at") == "":
        item["completed_at"] = None
    return item


def _load_day(directory: Path, date_str: str) -> dict:
    fp = _file_path(directory, date_str)
    if fp.exists():
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("items", []):
            _normalize_item(item)
        return data
    return {"date": date_str, "items": []}


def _save_day(directory: Path, date_str: str, data: dict) -> None:
    fp = _file_path(directory, date_str)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _validate_date(date_str: str) -> None:
    """校验日期格式。"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"日期格式错误，需要 YYYY-MM-DD，收到: {date_str}")


# ── 端点 ──────────────────────────────────────────────────────


@router.get("/{date_str}")
async def get_day_todos(date_str: str, request: Request):
    """获取某天的所有待办。"""
    _validate_date(date_str)
    d = _todolist_dir(request)
    data = _load_day(d, date_str)
    # 按 order 排序
    data["items"].sort(key=lambda x: int(x.get("order", 0)))
    return data


@router.post("/{date_str}/items")
async def create_todo_item(date_str: str, body: TodoItemCreate, request: Request):
    """新增一条待办。"""
    _validate_date(date_str)
    d = _todolist_dir(request)
    data = _load_day(d, date_str)

    item = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "priority": body.priority,
        "due_date": body.due_date,
        "status": "todo",
        "order": len(data["items"]),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": None,
    }
    data["items"].append(item)
    _save_day(d, date_str, data)
    await _publish_todolist_event(request, date_str, "add")
    return item


@router.put("/{date_str}/items/{item_id}")
async def update_todo_item(
    date_str: str, item_id: str, body: TodoItemUpdate, request: Request
):
    """更新待办属性（含状态切换）。"""
    _validate_date(date_str)
    d = _todolist_dir(request)
    data = _load_day(d, date_str)

    for item in data["items"]:
        if item["id"] == item_id:
            if body.title is not None:
                item["title"] = body.title
            if body.priority is not None:
                item["priority"] = body.priority
            if body.due_date is not None:
                item["due_date"] = body.due_date
            if body.order is not None:
                item["order"] = body.order
            if body.status is not None:
                old_status = item["status"]
                item["status"] = body.status
                if body.status == "done" and old_status != "done":
                    item["completed_at"] = datetime.now().isoformat(
                        timespec="seconds"
                    )
                elif body.status == "todo":
                    item["completed_at"] = None
            _save_day(d, date_str, data)
            await _publish_todolist_event(request, date_str, "update")
            return item

    raise HTTPException(404, f"待办项 '{item_id}' 不存在")


@router.delete("/{date_str}/items/{item_id}")
async def delete_todo_item(date_str: str, item_id: str, request: Request):
    """删除一条待办。"""
    _validate_date(date_str)
    d = _todolist_dir(request)
    data = _load_day(d, date_str)

    original_len = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != item_id]
    if len(data["items"]) == original_len:
        raise HTTPException(404, f"待办项 '{item_id}' 不存在")

    # 重新编排 order
    for idx, item in enumerate(data["items"]):
        item["order"] = idx

    _save_day(d, date_str, data)
    await _publish_todolist_event(request, date_str, "delete")
    return {"status": "deleted"}


@router.put("/{date_str}/reorder")
async def reorder_todo_items(
    date_str: str, body: TodoReorderBody, request: Request
):
    """按提供的 id 列表重排待办顺序。"""
    _validate_date(date_str)
    d = _todolist_dir(request)
    data = _load_day(d, date_str)

    id_to_item = {item["id"]: item for item in data["items"]}
    reordered = []
    for idx, item_id in enumerate(body.item_ids):
        if item_id in id_to_item:
            item = id_to_item.pop(item_id)
            item["order"] = idx
            reordered.append(item)
    # 未出现在列表中的项追加到末尾
    for item in id_to_item.values():
        item["order"] = len(reordered)
        reordered.append(item)

    data["items"] = reordered
    _save_day(d, date_str, data)
    await _publish_todolist_event(request, date_str, "reorder")
    return data


@router.get("/range/query")
async def get_todos_range(
    request: Request,
    start: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """获取日期范围内的所有待办（用于检测过期项）。"""
    _validate_date(start)
    _validate_date(end)
    d = _todolist_dir(request)

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    result: list[dict] = []

    # 遍历目录中的文件
    if d.exists():
        for fp in sorted(d.glob("todolist_*.json")):
            try:
                ds = fp.stem.replace("todolist_", "")
                fd = date.fromisoformat(ds)
                if start_date <= fd <= end_date:
                    data = _load_day(d, ds)
                    for item in data["items"]:
                        item["_date"] = ds
                    result.extend(data["items"])
            except (ValueError, json.JSONDecodeError):
                continue

    return {"items": result}
