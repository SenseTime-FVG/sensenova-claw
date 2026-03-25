"""Agent 工具偏好读取与写入。

当前约定：
- 顶层 `tools`：全局工具开关（Tools 页面使用）
- 顶层 `agent_tools`：按 agent 覆盖的工具开关（Agent 设置页使用）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PREFERENCES_FILENAME = ".agent_preferences.json"
AGENT_TOOLS_KEY = "agent_tools"


def preferences_path(sensenova_claw_home: str | Path | None) -> Path:
    """返回偏好文件路径。"""
    base = Path(sensenova_claw_home or Path.home() / ".sensenova-claw")
    return base / PREFERENCES_FILENAME


def load_preferences(sensenova_claw_home: str | Path | None) -> dict[str, Any]:
    """读取偏好文件；不存在或损坏时回退为空配置。"""
    path = preferences_path(sensenova_claw_home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load agent preferences from %s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def save_preferences(sensenova_claw_home: str | Path | None, prefs: dict[str, Any]) -> None:
    """写回偏好文件。"""
    path = preferences_path(sensenova_claw_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def _coerce_bool_map(raw: Any) -> dict[str, bool]:
    """只保留合法的 bool 开关映射。"""
    if not isinstance(raw, dict):
        return {}
    result: dict[str, bool] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, bool):
            result[key] = value
    return result


def _agent_tool_map(prefs: dict[str, Any], agent_id: str) -> dict[str, bool]:
    raw_agents = prefs.get(AGENT_TOOLS_KEY, {})
    if not isinstance(raw_agents, dict):
        return {}
    return _coerce_bool_map(raw_agents.get(agent_id, {}))


def resolve_tool_enabled_from_prefs(
    prefs: dict[str, Any],
    agent_id: str,
    tool_name: str,
    default: bool = True,
) -> bool:
    """解析工具是否启用：全局禁用优先，其次 agent 级覆盖。"""
    global_tools = _coerce_bool_map(prefs.get("tools", {}))
    if tool_name in global_tools:
        global_enabled = global_tools[tool_name]
        if not global_enabled:
            return False
    else:
        global_enabled = default

    agent_tools = _agent_tool_map(prefs, agent_id)
    if tool_name in agent_tools:
        return agent_tools[tool_name]

    return global_enabled


def save_agent_tool_preferences(
    sensenova_claw_home: str | Path | None,
    agent_id: str,
    tool_updates: dict[str, bool],
) -> dict[str, Any]:
    """按 agent 写入工具开关覆盖。"""
    prefs = load_preferences(sensenova_claw_home)
    agent_tools = prefs.get(AGENT_TOOLS_KEY, {})
    if not isinstance(agent_tools, dict):
        agent_tools = {}

    merged = _coerce_bool_map(agent_tools.get(agent_id, {}))
    merged.update(_coerce_bool_map(tool_updates))
    agent_tools[agent_id] = merged
    prefs[AGENT_TOOLS_KEY] = agent_tools
    save_preferences(sensenova_claw_home, prefs)
    return prefs
