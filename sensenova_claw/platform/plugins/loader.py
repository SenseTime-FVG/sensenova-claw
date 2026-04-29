"""PluginLoader — 扫描所有 source、按 identity 过滤、把 contribution 注入 Registry。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.3。

P1 范围：
  - load_all：识别 identity 参数但**不实施过滤**（P5 接入）
  - install_into_registries：把 contributes 解析成 RegistryEntry 注入对应 Registry
  - 不实例化 impl（P2 会在 install 时反射 Python 类）

不在 P1 范围：
  - visibility/identity 过滤算法（P5）
  - mcp_servers / hooks 的实际执行（P6）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sensenova_claw.platform.plugins.manifest import PluginManifest
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry
from sensenova_claw.platform.plugins.sources import PluginSource

if TYPE_CHECKING:
    from sensenova_claw.adapters.channels.channel_registry import ChannelRegistry
    from sensenova_claw.adapters.llm.factory import LLMFactory
    from sensenova_claw.capabilities.agents.registry import AgentRegistry
    from sensenova_claw.capabilities.commands.registry import CommandRegistry
    from sensenova_claw.capabilities.hooks.registry import HookRegistry
    from sensenova_claw.capabilities.skills.registry import SkillRegistry
    from sensenova_claw.capabilities.tools.registry import ToolRegistry
    from sensenova_claw.platform.identity.identity import Identity  # P5 占位

logger = logging.getLogger(__name__)


@dataclass
class InstallFailure:
    """单条 contribution 注入失败的诊断信息。"""

    plugin_id: str
    contribution_kind: str         # llm_providers / tools / ...
    contribution_id: str | None    # 短 id；解析失败时可能为 None
    reason: str


@dataclass
class InstallReport:
    """install_into_registries 的结果汇总。

    永远不抛异常——失败的条目记在这里，方便诊断 / 上报事件。
    """

    installed: int = 0
    failures: list[InstallFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class PluginLoader:
    """plugin 加载与注入入口。"""

    def __init__(self, sources: list[PluginSource]) -> None:
        self._sources = sources

    # ── 扫描 ───────────────────────────────────────────────────

    def load_all(self, identity: "Identity | None" = None) -> list[PluginManifest]:
        """扫描所有 source，返回（按 identity 过滤后的）可见 plugin manifest。

        P1 实现：忽略 identity（参数保留兼容签名）。P5 接入真实过滤。
        """
        if identity is not None:
            logger.debug(
                "PluginLoader.load_all: identity=%r 已收到，但 P1 阶段不做过滤"
                "（P5 会接入 visibility 过滤）",
                identity,
            )
        manifests: list[PluginManifest] = []
        for source in self._sources:
            manifests.extend(source.list())
        return manifests

    # ── 注入 Registry ─────────────────────────────────────────

    def install_into_registries(
        self,
        manifests: list[PluginManifest],
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        llm_registry: "LLMFactory",
        channel_registry: "ChannelRegistry",
        agent_registry: "AgentRegistry",
        hook_registry: "HookRegistry",
        command_registry: "CommandRegistry",
    ) -> InstallReport:
        """把每个 manifest 的 contributes 解析成 RegistryEntry 注入到对应 Registry。

        失败的 contribution 进入 InstallReport.failures，永不抛异常。
        ``mcp_servers`` 段在 P1 阶段不由本方法路由（P6 由 McpSessionManager 自取
        manifest.contributes['mcp_servers']）。
        """
        report = InstallReport()

        # contribution kind -> (target registry, has-id?)
        # has-id=True：contribution 必须自带 ``id`` 字段；False：用 event+idx 生成
        routes: dict[str, tuple[Any, bool]] = {
            "llm_providers": (llm_registry, True),
            "tools": (tool_registry, True),
            "channels": (channel_registry, True),
            "skills": (skill_registry, True),
            "agents": (agent_registry, True),
            "commands": (command_registry, True),
            "hooks": (hook_registry, False),
        }
        # P1 阶段 mcp_servers 由 P6 自己消费；这里识别但不路由也不报错
        ignored_kinds = {"mcp_servers"}

        for manifest in manifests:
            for kind, items in manifest.contributes.items():
                if kind in ignored_kinds:
                    continue
                if kind not in routes:
                    report.failures.append(
                        InstallFailure(
                            plugin_id=manifest.id,
                            contribution_kind=kind,
                            contribution_id=None,
                            reason=f"unknown contribution kind: {kind!r}",
                        )
                    )
                    continue
                if not isinstance(items, list):
                    report.failures.append(
                        InstallFailure(
                            plugin_id=manifest.id,
                            contribution_kind=kind,
                            contribution_id=None,
                            reason=f"{kind} must be a list, got {type(items).__name__}",
                        )
                    )
                    continue

                target_registry, requires_id = routes[kind]
                for idx, raw in enumerate(items):
                    self._install_one(
                        manifest=manifest,
                        kind=kind,
                        index=idx,
                        raw=raw,
                        target_registry=target_registry,
                        requires_id=requires_id,
                        report=report,
                    )

        return report

    # ── 内部：注入一条 contribution ──────────────────────────

    def _install_one(
        self,
        *,
        manifest: PluginManifest,
        kind: str,
        index: int,
        raw: Any,
        target_registry: Any,
        requires_id: bool,
        report: InstallReport,
    ) -> None:
        if not isinstance(raw, dict):
            report.failures.append(
                InstallFailure(
                    plugin_id=manifest.id,
                    contribution_kind=kind,
                    contribution_id=None,
                    reason=f"contribution must be a mapping, got {type(raw).__name__}",
                )
            )
            return

        # 计算 short_id
        if requires_id:
            short_id = raw.get("id")
            if not isinstance(short_id, str) or not short_id:
                report.failures.append(
                    InstallFailure(
                        plugin_id=manifest.id,
                        contribution_kind=kind,
                        contribution_id=None,
                        reason=f"{kind}[{index}] missing required 'id'",
                    )
                )
                return
        else:
            # hooks 没有 id 字段 — 用 event 名 + 索引生成
            event = raw.get("event", "Unknown")
            short_id = f"{event}_{index}"

        entry = RegistryEntry(
            id=f"{manifest.id}::{short_id}",
            short_id=short_id,
            owner_plugin=manifest.id,
            owner_team=manifest.owner,
            visibility=manifest.visibility,
            impl=None,                       # P1 不实例化
            metadata=dict(raw),              # 原样透传给 P2/P6
        )

        try:
            target_registry.register_from_plugin(entry)
        except Exception as e:  # 防御：register_from_plugin 不应抛，但兜底
            report.failures.append(
                InstallFailure(
                    plugin_id=manifest.id,
                    contribution_kind=kind,
                    contribution_id=short_id,
                    reason=f"register_from_plugin failed: {e}",
                )
            )
            return

        report.installed += 1
