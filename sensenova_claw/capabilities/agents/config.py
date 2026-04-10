"""AgentConfig — Agent 的完整配置数据类。

Agent 是一个配置边界，定义了一个行为剖面
（system prompt + tools + skills + model + temperature）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def _parse_delegate_list(data: dict[str, Any]) -> list[str] | None:
    """解析委托白名单：None = 禁止发消息，[] = 全部允许，[...] = 仅限指定。"""
    raw = data.get("can_send_message_to", data.get("can_delegate_to", []))
    if raw is None:
        return None
    return list(raw)


@dataclass
class AgentConfig:
    """一个 Agent 的完整配置。"""

    id: str                                           # 唯一标识（slug 格式，如 "research-agent"）
    name: str                                         # 人类可读名称
    description: str = ""                             # 描述（用于 LLM 选择委托目标）

    # LLM 配置
    model: str = "gpt-4o-mini"                        # 模型名称（引用 llm.models 中的 key，provider 由 resolve_model 动态解析）
    temperature: float = 1.0                          # 温度参数
    max_tokens: int | None = None                     # 最大 token 数
    extra_body: dict[str, Any] = field(default_factory=dict)  # 透传给 LLM API 的额外参数

    # 行为配置
    system_prompt: str = ""                           # 系统提示词
    tools: list[str] = field(default_factory=list)    # 允许使用的工具列表（空 = 全部）
    skills: list[str] = field(default_factory=list)   # 允许使用的 Skills 列表（空 = 全部）
    mcp_servers: list[str] = field(default_factory=list)  # 启用的 MCP server（空 = 全部启用）
    mcp_tools: list[str] = field(default_factory=list)    # 启用的 MCP tool 选择器（空 = 全部启用）
    workdir: str = ""                                 # 工作目录（空=运行时解析为 workspace/workdir/{id}）

    # 委托配置
    can_delegate_to: list[str] | None = field(default_factory=list)   # 可委托的 Agent ID 列表（空 = 全部，None = 禁止）
    max_delegation_depth: int = 3                               # 最大委托深度
    max_pingpong_turns: int = 10                                # 单个子会话最大往返轮数

    # 元信息
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（用于 JSON 持久化和 API 响应）"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "extra_body": dict(self.extra_body),
            "system_prompt": self.system_prompt,
            "tools": list(self.tools),
            "skills": list(self.skills),
            "mcp_servers": list(self.mcp_servers),
            "mcp_tools": list(self.mcp_tools),
            "workdir": self.workdir,
            "can_delegate_to": list(self.can_delegate_to) if self.can_delegate_to is not None else None,
            "max_delegation_depth": self.max_delegation_depth,
            "max_pingpong_turns": self.max_pingpong_turns,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """从 dict 反序列化"""
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            model=data.get("model", "gpt-4o-mini"),
            temperature=data.get("temperature", 1.0),
            max_tokens=data.get("max_tokens"),
            extra_body=dict(data.get("extra_body", {})),
            system_prompt=data.get("system_prompt", ""),
            tools=list(data.get("tools", [])),
            skills=list(data.get("skills", [])),
            mcp_servers=list(data.get("mcp_servers", data.get("mcp_servers_allow", []))),
            mcp_tools=list(data.get("mcp_tools", data.get("mcp_tools_allow", []))),
            workdir=data.get("workdir", ""),
            can_delegate_to=_parse_delegate_list(data),
            max_delegation_depth=data.get(
                "max_send_depth",
                data.get("max_delegation_depth", 3),
            ),
            max_pingpong_turns=data.get("max_pingpong_turns", 10),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )

    @classmethod
    def create(cls, **kwargs: Any) -> AgentConfig:
        """便捷创建方法，自动填充时间戳"""
        if "can_send_message_to" in kwargs and "can_delegate_to" not in kwargs:
            kwargs["can_delegate_to"] = kwargs.pop("can_send_message_to")
        if "max_send_depth" in kwargs and "max_delegation_depth" not in kwargs:
            kwargs["max_delegation_depth"] = kwargs.pop("max_send_depth")
        now = time.time()
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        return cls(**kwargs)

    @property
    def can_send_message_to(self) -> list[str] | None:
        """`send_message` 语义下的白名单别名。"""
        return self.can_delegate_to

    @can_send_message_to.setter
    def can_send_message_to(self, value: list[str] | None) -> None:
        self.can_delegate_to = list(value) if value is not None else None

    @property
    def max_send_depth(self) -> int:
        """`send_message` 语义下的深度别名。"""
        return self.max_delegation_depth

    @max_send_depth.setter
    def max_send_depth(self, value: int) -> None:
        self.max_delegation_depth = value
