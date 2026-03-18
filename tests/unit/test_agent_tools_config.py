"""Agent tools 配置契约测试"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_all_agents_include_ask_user() -> None:
    cfg_path = Path("config.yml")
    if not cfg_path.exists():
        pytest.skip("config.yml not found in current workspace")

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    agents = cfg.get("agents", {})

    for agent_id, agent_cfg in agents.items():
        tools = agent_cfg.get("tools", [])
        assert "ask_user" in tools, f"{agent_id} missing ask_user"
