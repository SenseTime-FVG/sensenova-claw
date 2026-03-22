"""AgentRegistry — 管理 Agent 配置的注册表。

职责：
1. 管理 Agent 配置的 CRUD
2. 从 config.yml 加载 Agent 配置（system_prompt 从文件读取）
3. 提供 Agent 发现机制（供多 Agent 工具使用）

不做：
- 不管理 Agent 实例的生命周期（那是 AgentRuntime 的事）
- 不执行 Agent 逻辑（那是 AgentSessionWorker 的事）
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentos.capabilities.agents.config import AgentConfig

if TYPE_CHECKING:
    from agentos.kernel.events.bus import PublicEventBus
    from agentos.platform.config.config import Config

logger = logging.getLogger(__name__)

# system prompt 文件名
SYSTEM_PROMPT_FILENAME = "SYSTEM_PROMPT.md"


class AgentRegistry:

    def __init__(self, agentos_home: str | Path | None = None):
        self._agents: dict[str, AgentConfig] = {}
        self._agentos_home = Path(agentos_home) if agentos_home else None

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
        return self._agents.pop(agent_id, None) is not None

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
        """从 config.yml 的 agents 段加载 Agent 配置

        agents 为 dict 格式，每个 key 是 agent id，value 是配置。
        始终确保 default agent 存在。
        """
        agent_section = config_data.get("agent", {})
        agents_section = config_data.get("agents", {})

        if not isinstance(agents_section, dict):
            agents_section = {}

        for agent_id, agent_dict in agents_section.items():
            if not isinstance(agent_dict, dict):
                continue
            agent = self._build_agent_from_dict(agent_id, agent_dict, agent_section)
            self.register(agent)
            logger.info("Loaded agent from config: %s", agent_id)

        # 确保 default agent 始终存在
        if not self.get("default"):
            default = self._build_agent_from_dict("default", {}, agent_section)
            self.register(default)

    def _build_agent_from_dict(
        self, agent_id: str, agent_dict: dict[str, Any], fallback: dict[str, Any]
    ) -> AgentConfig:
        """从配置 dict 构建 AgentConfig，缺失字段从 fallback（agent 段）取默认值。

        system_prompt 不允许在 config.yml 中配置，必须放在
        {agentos_home}/agents/{agent_id}/SYSTEM_PROMPT.md 文件中。
        """
        if "system_prompt" in agent_dict:
            raise ValueError(
                f"Agent '{agent_id}' 的 system_prompt 不应写在 config.yml 中，"
                f"请移到 agents/{agent_id}/{SYSTEM_PROMPT_FILENAME}"
            )

        # 从文件读取 system_prompt
        system_prompt = self._load_system_prompt(agent_id)
        if not system_prompt:
            # 回退到 agent 段的全局默认 system_prompt
            system_prompt = fallback.get("system_prompt", "")

        return AgentConfig(
            id=agent_id,
            name=agent_dict.get("name", agent_id.replace("-", " ").title() if agent_id != "default" else "Default Agent"),
            description=agent_dict.get("description", "默认 AI Agent" if agent_id == "default" else ""),
            model=agent_dict.get("model", ""),
            temperature=agent_dict.get("temperature", fallback.get("temperature", 0.2)),
            max_tokens=agent_dict.get("max_tokens"),
            system_prompt=system_prompt,
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

    def _load_system_prompt(self, agent_id: str) -> str:
        """从 {agentos_home}/agents/{agent_id}/SYSTEM_PROMPT.md 读取 system prompt"""
        if not self._agentos_home:
            return ""
        prompt_file = self._agentos_home / "agents" / agent_id / SYSTEM_PROMPT_FILENAME
        if prompt_file.exists():
            try:
                content = prompt_file.read_text(encoding="utf-8").strip()
                if content:
                    logger.info("Loaded system prompt from %s", prompt_file)
                    return content
            except Exception:
                logger.warning("Failed to read system prompt: %s", prompt_file, exc_info=True)
        return ""

    # ── 运行时更新 ──────────────────────────────────

    async def start_config_listener(self, bus: PublicEventBus, config: Config) -> None:
        """订阅 config.updated 事件，agents section 变更时重载"""
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "agents":
                self._agents.clear()
                self.load_from_config(config.data)
                logger.info("AgentRegistry: agents reloaded due to config change")

    def update(self, agent_id: str, updates: dict[str, Any]) -> AgentConfig | None:
        """部分更新 Agent 配置（仅内存，不持久化）"""
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        for key, value in updates.items():
            if hasattr(agent, key) and key not in ("id", "created_at"):
                setattr(agent, key, value)
        agent.updated_at = time.time()
        return agent
