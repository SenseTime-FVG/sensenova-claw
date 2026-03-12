"""AgentRegistry — 管理 Agent 配置的注册表。

职责：
1. 管理 Agent 配置的 CRUD
2. 从 config.yml 和持久化 JSON 文件加载 Agent 配置
3. 提供 Agent 发现机制（供 DelegateTool 使用）

不做：
- 不管理 Agent 实例的生命周期（那是 AgentRuntime 的事）
- 不执行 Agent 逻辑（那是 AgentSessionWorker 的事）
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.agents.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentRegistry:

    def __init__(self, config_dir: Path):
        self._agents: dict[str, AgentConfig] = {}
        self._config_dir = config_dir

    # ── CRUD ──────────────────────────────────────────

    def register(self, agent: AgentConfig) -> None:
        """注册或更新一个 Agent 配置"""
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> AgentConfig | None:
        """获取 Agent 配置"""
        return self._agents.get(agent_id)

    def list_all(self) -> list[AgentConfig]:
        """列出所有已注册且启用的 Agent"""
        return [a for a in self._agents.values() if a.enabled]

    def delete(self, agent_id: str) -> bool:
        """删除 Agent（不能删除 default）。返回是否成功。"""
        if agent_id == "default":
            return False
        agent = self._agents.pop(agent_id, None)
        if agent is None:
            return False
        # 删除持久化文件
        fp = self._config_dir / f"{agent_id}.json"
        if fp.exists():
            fp.unlink()
        return True

    # ── 委托发现 ──────────────────────────────────────

    def get_delegatable(self, from_agent_id: str) -> list[AgentConfig]:
        """获取某个 Agent 可以委托的目标 Agent 列表"""
        source = self._agents.get(from_agent_id)
        if not source:
            return []
        if not source.can_delegate_to:
            # 空列表 = 可以委托给所有其他已启用 Agent
            return [a for a in self._agents.values()
                    if a.id != from_agent_id and a.enabled]
        return [self._agents[aid] for aid in source.can_delegate_to
                if aid in self._agents and self._agents[aid].enabled]

    # ── 从 config.yml 加载 ────────────────────────────

    def load_from_config(self, config_data: dict[str, Any]) -> None:
        """从 config.yml 加载 Agent 配置

        1. 始终从 agent.* 创建 id="default" 的 AgentConfig（向后兼容）
        2. 加载 agents.* 配置中的额外 Agent
        """
        agent_section = config_data.get("agent", {})
        default = AgentConfig(
            id="default",
            name="Default Agent",
            description="默认 AI Agent",
            provider=agent_section.get("provider", "openai"),
            model=agent_section.get("default_model", "gpt-4o-mini"),
            temperature=agent_section.get("default_temperature", 0.2),
            system_prompt=agent_section.get("system_prompt", ""),
        )
        self.register(default)

        agents_section = config_data.get("agents", {})
        for agent_id, agent_dict in agents_section.items():
            agent = AgentConfig(
                id=agent_id,
                name=agent_dict.get("name", agent_id),
                description=agent_dict.get("description", ""),
                provider=agent_dict.get("provider", default.provider),
                model=agent_dict.get("model", default.model),
                temperature=agent_dict.get("temperature", default.temperature),
                max_tokens=agent_dict.get("max_tokens"),
                system_prompt=agent_dict.get("system_prompt", ""),
                tools=list(agent_dict.get("tools", [])),
                skills=list(agent_dict.get("skills", [])),
                can_delegate_to=list(agent_dict.get("can_delegate_to", [])),
                max_delegation_depth=agent_dict.get("max_delegation_depth", 3),
                enabled=agent_dict.get("enabled", True),
            )
            self.register(agent)
            logger.info("Loaded agent from config: %s", agent_id)

    # ── 从磁盘加载 / 持久化 ──────────────────────────

    def load_from_dir(self) -> None:
        """从持久化目录加载 Agent 配置（JSON 文件）"""
        if not self._config_dir.exists():
            return
        for fp in self._config_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                agent = AgentConfig.from_dict(data)
                self.register(agent)
                logger.info("Loaded agent from file: %s", fp.name)
            except Exception:
                logger.exception("Failed to load agent from %s", fp)

    def save(self, agent: AgentConfig) -> None:
        """持久化 Agent 配置到磁盘"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        fp = self._config_dir / f"{agent.id}.json"
        fp.write_text(
            json.dumps(agent.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def update(self, agent_id: str, updates: dict[str, Any]) -> AgentConfig | None:
        """部分更新 Agent 配置"""
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        for key, value in updates.items():
            if hasattr(agent, key) and key not in ("id", "created_at"):
                setattr(agent, key, value)
        agent.updated_at = time.time()
        # 非 default Agent 持久化到磁盘
        if agent_id != "default":
            self.save(agent)
        return agent
