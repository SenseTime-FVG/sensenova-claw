"""AgentRegistry — 管理 Agent 配置的注册表。

职责：
1. 管理 Agent 配置的 CRUD
2. 从 config.yml 和持久化 JSON 文件加载 Agent 配置
3. 提供 Agent 发现机制（供多 Agent 工具使用）

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

import yaml

from agentos.capabilities.agents.config import AgentConfig

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
        # 删除 agent 目录（新格式）
        agent_dir = self._config_dir / agent_id
        if agent_dir.is_dir():
            import shutil
            shutil.rmtree(agent_dir)
        # 兼容删除旧格式扁平文件
        fp = self._config_dir / f"{agent_id}.json"
        if fp.exists():
            fp.unlink()
        return True

    # ── Agent 发现 ───────────────────────────────────

    def get_sendable(self, from_agent_id: str) -> list[AgentConfig]:
        """获取某个 Agent 可以发送消息的目标 Agent 列表"""
        source = self._agents.get(from_agent_id)
        if not source:
            return []
        if not source.can_send_message_to:
            # 空列表 = 可以向所有其他已启用 Agent 发送消息
            return [a for a in self._agents.values()
                    if a.id != from_agent_id and a.enabled]
        return [self._agents[aid] for aid in source.can_send_message_to
                if aid in self._agents and self._agents[aid].enabled]

    def get_delegatable(self, from_agent_id: str) -> list[AgentConfig]:
        """兼容旧命名：内部复用 get_sendable。"""
        return self.get_sendable(from_agent_id)

    # ── 从 config.yml 加载 ────────────────────────────

    def load_from_config(self, config_data: dict[str, Any]) -> None:
        """从 config.yml 加载 Agent 配置

        新格式：agents 为 id 列表，每个 agent 的配置从 {config_dir}/{id}/config.yml 加载。
        兼容旧格式：agents 为 dict 时按旧逻辑处理。
        始终确保 default agent 存在。
        """
        agent_section = config_data.get("agent", {})
        agents_section = config_data.get("agents", ["default"])

        # 新格式：agents 为 id 列表
        if isinstance(agents_section, list):
            for agent_id in agents_section:
                if not isinstance(agent_id, str):
                    continue
                config_file = self._config_dir / agent_id / "config.yml"
                if config_file.exists():
                    try:
                        with config_file.open("r", encoding="utf-8") as f:
                            agent_dict = yaml.safe_load(f) or {}
                        agent = self._build_agent_from_dict(agent_id, agent_dict, agent_section)
                        self.register(agent)
                        logger.info("Loaded agent from config.yml: %s", agent_id)
                    except Exception:
                        logger.exception("Failed to load agent config: %s", config_file)
                else:
                    # 配置文件不存在时，使用 agent 段的默认值
                    agent = self._build_agent_from_dict(agent_id, {}, agent_section)
                    self.register(agent)
                    logger.info("Agent '%s' config.yml not found, using defaults", agent_id)

        # 兼容旧格式：agents 为 dict
        elif isinstance(agents_section, dict):
            for agent_id, agent_dict in agents_section.items():
                agent = self._build_agent_from_dict(agent_id, agent_dict, agent_section)
                self.register(agent)
                logger.info("Loaded agent from config (legacy): %s", agent_id)

        # 确保 default agent 始终存在
        if not self.get("default"):
            default = self._build_agent_from_dict("default", {}, agent_section)
            self.register(default)

    def _build_agent_from_dict(
        self, agent_id: str, agent_dict: dict[str, Any], fallback: dict[str, Any]
    ) -> AgentConfig:
        """从配置 dict 构建 AgentConfig，缺失字段从 fallback（agent 段）取默认值"""
        return AgentConfig(
            id=agent_id,
            name=agent_dict.get("name", agent_id.replace("-", " ").title() if agent_id != "default" else "Default Agent"),
            description=agent_dict.get("description", "默认 AI Agent" if agent_id == "default" else ""),
            provider="",  # provider 现在由 model key 通过 resolve_model 动态解析
            model=agent_dict.get("model", fallback.get("model", "mock")),
            temperature=agent_dict.get("temperature", fallback.get("temperature", 0.2)),
            max_tokens=agent_dict.get("max_tokens"),
            system_prompt=agent_dict.get("system_prompt", fallback.get("system_prompt", "")),
            tools=list(agent_dict.get("tools", [])),
            skills=list(agent_dict.get("skills", [])),
            workdir=agent_dict.get("workdir", ""),
            can_delegate_to=list(
                agent_dict.get("can_send_message_to", agent_dict.get("can_delegate_to", []))
            ),
            max_delegation_depth=agent_dict.get(
                "max_send_depth",
                agent_dict.get("max_delegation_depth", 3),
            ),
            max_pingpong_turns=agent_dict.get("max_pingpong_turns", 10),
            enabled=agent_dict.get("enabled", True),
        )

    # ── 从磁盘加载 / 持久化 ──────────────────────────

    def load_from_dir(self) -> None:
        """从持久化目录加载 Agent 配置。

        优先读取 agents/{id}/config.json（新格式），
        同时兼容旧的 agents/{id}.json 扁平文件。
        """
        if not self._config_dir.exists():
            return
        # 新格式：子目录下的 config.json
        for agent_dir in self._config_dir.iterdir():
            if agent_dir.is_dir():
                fp = agent_dir / "config.json"
                if fp.exists():
                    try:
                        data = json.loads(fp.read_text(encoding="utf-8"))
                        agent = AgentConfig.from_dict(data)
                        self.register(agent)
                        logger.info("Loaded agent from dir: %s", agent_dir.name)
                    except Exception:
                        logger.exception("Failed to load agent from %s", fp)
        # 向后兼容：扁平 JSON 文件
        for fp in self._config_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                agent_id = data.get("id", fp.stem)
                if agent_id not in self._agents:
                    agent = AgentConfig.from_dict(data)
                    self.register(agent)
                    logger.info("Loaded agent from legacy file: %s", fp.name)
            except Exception:
                logger.exception("Failed to load agent from %s", fp)

    def save(self, agent: AgentConfig) -> None:
        """持久化 Agent 配置到磁盘（agents/{id}/config.json）"""
        agent_dir = self._config_dir / agent.id
        agent_dir.mkdir(parents=True, exist_ok=True)
        fp = agent_dir / "config.json"
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
