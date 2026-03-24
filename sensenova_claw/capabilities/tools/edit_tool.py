from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


def _resolve_edit_path(raw_path: str, agent_workdir: str | None) -> Path:
    """解析 edit 工具路径，保持与现有 workdir 语义一致。"""
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    if agent_workdir:
        return (Path(agent_workdir).expanduser() / path).resolve()
    return path.resolve()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _count_occurrences(content: str, needle: str) -> int:
    if needle == "":
        return 0
    return content.count(needle)


def _replace_once(content: str, old_text: str, new_text: str) -> str:
    return content.replace(old_text, new_text, 1)


def _generate_unified_diff(old_content: str, new_content: str, path_label: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=path_label,
            tofile=path_label,
            lineterm="",
        )
    )


def _first_changed_line(old_content: str, new_content: str) -> int | None:
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    max_len = max(len(old_lines), len(new_lines))
    for index in range(max_len):
        old_line = old_lines[index] if index < len(old_lines) else None
        new_line = new_lines[index] if index < len(new_lines) else None
        if old_line != new_line:
            return index + 1
    return None


class EditTool(Tool):
    name = "edit"
    description = "对文件执行精确文本替换，只允许 oldText 命中一次"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要编辑的文件路径"},
            "oldText": {"type": "string", "description": "被替换的旧文本"},
            "newText": {"type": "string", "description": "替换后的新文本"},
            "old_text": {"type": "string", "description": "oldText 的 snake_case 别名"},
            "new_text": {"type": "string", "description": "newText 的 snake_case 别名"},
            "old_string": {"type": "string", "description": "oldText 的兼容别名"},
            "new_string": {"type": "string", "description": "newText 的兼容别名"},
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        path_param = str(kwargs.get("path", "")).strip()
        old_text = self._pick_text(kwargs, primary="oldText", snake="old_text", compat="old_string")
        new_text = self._pick_text(kwargs, primary="newText", snake="new_text", compat="new_string")
        agent_workdir = kwargs.get("_agent_workdir")

        if not path_param:
            return {"success": False, "error": "path 不能为空"}
        if old_text is None:
            return {"success": False, "error": "oldText 不能为空"}
        if new_text is None:
            return {"success": False, "error": "newText 不能为空"}
        if old_text == "":
            return {"success": False, "error": "oldText 不能为空字符串"}

        try:
            return self._execute_once(path_param=path_param, old_text=old_text, new_text=new_text, agent_workdir=agent_workdir)
        except Exception as exc:
            recovered = self._recover_post_write_success(
                path_param=path_param,
                old_text=old_text,
                new_text=new_text,
                agent_workdir=agent_workdir,
            )
            if recovered is not None:
                return recovered
            raise exc

    @staticmethod
    def _pick_text(kwargs: dict[str, Any], *, primary: str, snake: str, compat: str) -> str | None:
        for key in (primary, snake, compat):
            value = kwargs.get(key)
            if value is not None:
                return str(value)
        return None

    def _execute_once(
        self,
        *,
        path_param: str,
        old_text: str,
        new_text: str,
        agent_workdir: str | None,
    ) -> dict[str, Any]:
        target = _resolve_edit_path(path_param, agent_workdir)
        if not target.exists():
            return {"success": False, "error": f"文件不存在: {path_param}"}
        if not target.is_file():
            return {"success": False, "error": f"目标不是普通文件: {path_param}"}

        old_content = _read_text(target)
        occurrences = _count_occurrences(old_content, old_text)
        if occurrences == 0:
            return {"success": False, "error": f"oldText 未命中: {path_param}"}
        if occurrences > 1:
            return {"success": False, "error": f"oldText 在文件中出现 multiple matches ({occurrences})，拒绝编辑: {path_param}"}

        new_content = _replace_once(old_content, old_text, new_text)
        target.write_text(new_content, encoding="utf-8")

        diff_text = _generate_unified_diff(old_content, new_content, path_param)
        return {
            "success": True,
            "message": f"Successfully replaced text in {path_param}.",
            "path": str(target),
            "diff": diff_text,
            "first_changed_line": _first_changed_line(old_content, new_content),
        }

    def _recover_post_write_success(
        self,
        *,
        path_param: str,
        old_text: str,
        new_text: str,
        agent_workdir: str | None,
    ) -> dict[str, Any] | None:
        try:
            target = _resolve_edit_path(path_param, agent_workdir)
            content = _read_text(target)
        except Exception:
            return None

        has_new = new_text in content
        still_has_old = bool(old_text) and old_text in content
        if has_new and not still_has_old:
            return {
                "success": True,
                "message": f"Successfully replaced text in {path_param}.",
                "path": str(target),
                "diff": "",
                "first_changed_line": None,
            }
        return None
