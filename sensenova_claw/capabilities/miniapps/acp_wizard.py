from __future__ import annotations

import asyncio
import logging
import os
import platform
import shlex
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

PlatformId = Literal["linux", "macos", "windows"]


def _quote_command(parts: list[str]) -> str:
    if not parts:
        return ""
    return shlex.join(parts)


def _platform_id() -> PlatformId:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def _platform_label(platform_id: PlatformId) -> str:
    return {
        "linux": "Linux",
        "macos": "macOS",
        "windows": "Windows",
    }[platform_id]


def _normalize_command_name(command: str) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    name = Path(text).name.lower()
    if name.endswith(".exe") or name.endswith(".cmd") or name.endswith(".bat"):
        return name.rsplit(".", 1)[0]
    return name


def _matches_configured_command(config: dict[str, Any], command: str, args: list[str]) -> bool:
    configured_command = _normalize_command_name(str(config.get("command") or ""))
    configured_args = [str(item) for item in list(config.get("args") or [])]
    return configured_command == _normalize_command_name(command) and configured_args == list(args)


@dataclass(frozen=True)
class CommandLocator:
    id: str
    label: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class InstallRecipe:
    id: str
    platforms: tuple[PlatformId, ...]
    command: tuple[str, ...]
    requires: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class InstallStep:
    id: str
    label: str
    target: CommandLocator
    recipes: tuple[InstallRecipe, ...]


@dataclass(frozen=True)
class EnvHint:
    key: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class ACPAgentSpec:
    id: str
    name: str
    summary: str
    homepage: str
    platforms: tuple[PlatformId, ...]
    mode: Literal["native", "adapter", "bridge"]
    runtime: CommandLocator
    default_args: tuple[str, ...]
    required_components: tuple[CommandLocator, ...]
    install_steps: tuple[InstallStep, ...]
    env_hints: tuple[EnvHint, ...] = ()
    notes: tuple[str, ...] = ()


class ACPWizardInstallError(RuntimeError):
    """ACP 向导安装失败。"""


class ACPWizardService:
    """ACP agent 检测、安装与推荐配置生成。"""

    INSTALL_TIMEOUT_SECONDS = 15 * 60

    def __init__(self, *, project_root: str | Path | None = None) -> None:
        self._project_root = Path(project_root or Path.cwd()).resolve()
        self._platform = _platform_id()
        self._installers = {
            "npm": CommandLocator("npm", "npm", ("npm",)),
            "uv": CommandLocator("uv", "uv", ("uv",)),
            "brew": CommandLocator("brew", "Homebrew", ("brew",)),
            "bash": CommandLocator("bash", "bash", ("bash",)),
            "curl": CommandLocator("curl", "curl", ("curl",)),
            "powershell": CommandLocator("powershell", "PowerShell", ("pwsh", "powershell")),
        }
        self._specs = self._build_specs()

    def inspect(self, *, current_config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = dict(current_config or {})
        installers = self._detect_installers()
        agents = [self._inspect_agent(spec, config, installers) for spec in self._specs]
        return {
            "platform": {
                "id": self._platform,
                "label": _platform_label(self._platform),
                "python": sys.executable,
            },
            "installers": installers,
            "agents": agents,
            "current_config": {
                "enabled": bool(config.get("enabled")),
                "command": str(config.get("command") or ""),
                "args": [str(item) for item in list(config.get("args") or [])],
                "env": {str(key): str(value) for key, value in dict(config.get("env") or {}).items()},
                "startup_timeout_seconds": int(config.get("startup_timeout_seconds") or 20),
                "request_timeout_seconds": int(config.get("request_timeout_seconds") or 180),
            },
        }

    async def install(
        self,
        agent_id: str,
        *,
        step_ids: list[str] | None = None,
        current_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = self._get_spec(agent_id)
        installers = self._detect_installers()
        selected_step_ids = {item for item in (step_ids or []) if item}
        executed_steps: list[dict[str, Any]] = []

        for step in spec.install_steps:
            resolved_target = self._resolve_locator(step.target)
            if resolved_target["found"]:
                continue
            if selected_step_ids and step.id not in selected_step_ids:
                continue

            recipe = self._select_recipe(step, installers)
            if recipe is None:
                raise ACPWizardInstallError(f"{step.label} 当前平台缺少可用安装方式")
            command = self._materialize_recipe_command(recipe, installers)

            logger.info(
                "ACP wizard install step: agent=%s step=%s command=%s",
                spec.id,
                step.id,
                _quote_command(command),
            )
            stdout, stderr, return_code = await self._run_command(command)
            executed_steps.append(
                {
                    "id": step.id,
                    "label": step.label,
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "return_code": return_code,
                }
            )
            if return_code != 0:
                tail = "\n".join((stdout + stderr).splitlines()[-40:])
                raise ACPWizardInstallError(
                    f"{step.label} 安装失败，退出码 {return_code}\n{tail}".strip()
                )

        return {
            "ok": True,
            "agent_id": spec.id,
            "executed_steps": executed_steps,
            "wizard": self.inspect(current_config=current_config),
        }

    def _build_specs(self) -> list[ACPAgentSpec]:
        codex_cli = CommandLocator("codex", "Codex CLI", ("codex",))
        codex_adapter = CommandLocator("codex-acp", "codex-acp adapter", ("codex-acp",))
        claude_adapter = CommandLocator("claude-agent-acp", "claude-agent-acp adapter", ("claude-agent-acp",))
        gemini_cli = CommandLocator("gemini", "Gemini CLI", ("gemini",))
        kimi_cli = CommandLocator("kimi", "Kimi CLI", ("kimi",))
        opencode_cli = CommandLocator("opencode", "opencode", ("opencode",))
        python_locator = CommandLocator("python", "Python", (sys.executable, "python3", "python"))

        return [
            ACPAgentSpec(
                id="codex",
                name="Codex CLI",
                summary="通过 Zed 官方 codex-acp adapter 将 Codex CLI 接入 ACP。",
                homepage="https://github.com/zed-industries/codex-acp",
                platforms=("linux", "macos", "windows"),
                mode="adapter",
                runtime=codex_adapter,
                default_args=(),
                required_components=(codex_cli, codex_adapter),
                install_steps=(
                    InstallStep(
                        id="agent",
                        label="安装 Codex CLI",
                        target=codex_cli,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "@openai/codex"),
                                requires=("npm",),
                                note="官方 npm 包",
                            ),
                        ),
                    ),
                    InstallStep(
                        id="adapter",
                        label="安装 codex-acp adapter",
                        target=codex_adapter,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "@zed-industries/codex-acp"),
                                requires=("npm",),
                                note="Zed 官方 adapter",
                            ),
                        ),
                    ),
                ),
                env_hints=(
                    EnvHint("OPENAI_API_KEY", "Codex CLI 常见鉴权方式"),
                    EnvHint("CODEX_API_KEY", "如果使用 Codex 专用 key，可在 ACP env 中注入"),
                ),
                notes=(
                    "如果当前环境里已经完成 Codex 登录，通常不需要额外 env。",
                ),
            ),
            ACPAgentSpec(
                id="claude",
                name="Claude Agent / Claude Code",
                summary="通过 Zed 官方 claude-agent-acp adapter 接入 Claude Agent SDK。",
                homepage="https://github.com/zed-industries/claude-agent-acp",
                platforms=("linux", "macos", "windows"),
                mode="adapter",
                runtime=claude_adapter,
                default_args=(),
                required_components=(claude_adapter,),
                install_steps=(
                    InstallStep(
                        id="adapter",
                        label="安装 claude-agent-acp adapter",
                        target=claude_adapter,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "@zed-industries/claude-agent-acp"),
                                requires=("npm",),
                                note="Zed 官方 adapter",
                            ),
                        ),
                    ),
                ),
                env_hints=(
                    EnvHint("ANTHROPIC_API_KEY", "未走交互式登录时可直接注入"),
                ),
                notes=(
                    "官方 ACP adapter 当前基于 Claude Agent SDK；如果你习惯称它为 Claude Code，可以直接按这个预设配置。",
                ),
            ),
            ACPAgentSpec(
                id="gemini",
                name="Gemini CLI",
                summary="Gemini CLI 原生支持 ACP，需带上 --experimental-acp。",
                homepage="https://github.com/google-gemini/gemini-cli",
                platforms=("linux", "macos", "windows"),
                mode="native",
                runtime=gemini_cli,
                default_args=("--experimental-acp",),
                required_components=(gemini_cli,),
                install_steps=(
                    InstallStep(
                        id="agent",
                        label="安装 Gemini CLI",
                        target=gemini_cli,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "@google/gemini-cli"),
                                requires=("npm",),
                                note="官方 npm 包",
                            ),
                            InstallRecipe(
                                id="brew",
                                platforms=("linux", "macos"),
                                command=("brew", "install", "gemini-cli"),
                                requires=("brew",),
                                note="Homebrew",
                            ),
                        ),
                    ),
                ),
                env_hints=(
                    EnvHint("GEMINI_API_KEY", "如果不使用交互登录，可在 env 中提供"),
                ),
                notes=(
                    "Gemini CLI 的 ACP 仍是 experimental 模式，推荐保留默认参数 --experimental-acp。",
                ),
            ),
            ACPAgentSpec(
                id="kimi",
                name="Kimi CLI",
                summary="Kimi CLI 原生提供 kimi acp，可直接接入 ACP client。",
                homepage="https://moonshotai.github.io/kimi-cli/en/guides/getting-started.html",
                platforms=("linux", "macos", "windows"),
                mode="native",
                runtime=kimi_cli,
                default_args=("acp",),
                required_components=(kimi_cli,),
                install_steps=(
                    InstallStep(
                        id="agent",
                        label="安装 Kimi CLI",
                        target=kimi_cli,
                        recipes=(
                            InstallRecipe(
                                id="uv",
                                platforms=("linux", "macos", "windows"),
                                command=("uv", "tool", "install", "--python", "3.13", "kimi-cli"),
                                requires=("uv",),
                                note="官方推荐的 uv 安装方式",
                            ),
                            InstallRecipe(
                                id="script",
                                platforms=("linux", "macos"),
                                command=("bash", "-lc", "curl -LsSf https://code.kimi.com/install.sh | bash"),
                                requires=("bash", "curl"),
                                note="官方安装脚本",
                            ),
                            InstallRecipe(
                                id="powershell",
                                platforms=("windows",),
                                command=(
                                    "powershell",
                                    "-NoProfile",
                                    "-ExecutionPolicy",
                                    "Bypass",
                                    "-Command",
                                    "Invoke-RestMethod https://code.kimi.com/install.ps1 | Invoke-Expression",
                                ),
                                requires=("powershell",),
                                note="官方 PowerShell 安装脚本",
                            ),
                        ),
                    ),
                ),
                notes=(
                    "首次使用前请先在终端运行 kimi，并执行 /login 完成登录。",
                ),
            ),
            ACPAgentSpec(
                id="opencode",
                name="OpenCode",
                summary="OpenCode 原生支持 opencode acp，可直接用于 mini-app ACP 构建。",
                homepage="https://opencode.ai/docs/cli/",
                platforms=("linux", "macos", "windows"),
                mode="native",
                runtime=opencode_cli,
                default_args=("acp",),
                required_components=(opencode_cli,),
                install_steps=(
                    InstallStep(
                        id="agent",
                        label="安装 OpenCode",
                        target=opencode_cli,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "opencode-ai"),
                                requires=("npm",),
                                note="npm 包名为 opencode-ai，安装后命令为 opencode",
                            ),
                            InstallRecipe(
                                id="script",
                                platforms=("linux", "macos"),
                                command=("bash", "-lc", "curl -fsSL https://opencode.ai/install | bash"),
                                requires=("bash", "curl"),
                                note="官方安装脚本",
                            ),
                        ),
                    ),
                ),
                notes=(
                    "OpenCode 默认就支持 ACP，不需要额外 adapter。",
                ),
            ),
            ACPAgentSpec(
                id="codex-bridge",
                name="内置 Codex ACP Bridge",
                summary="使用仓库内 Python bridge 将 codex exec 暴露为 ACP，适合作为无 adapter 环境的兜底方案。",
                homepage="https://github.com/openai/codex",
                platforms=("linux", "macos", "windows"),
                mode="bridge",
                runtime=python_locator,
                default_args=("-m", "sensenova_claw.capabilities.miniapps.codex_acp_bridge"),
                required_components=(python_locator, codex_cli),
                install_steps=(
                    InstallStep(
                        id="agent",
                        label="安装 Codex CLI",
                        target=codex_cli,
                        recipes=(
                            InstallRecipe(
                                id="npm",
                                platforms=("linux", "macos", "windows"),
                                command=("npm", "install", "-g", "@openai/codex"),
                                requires=("npm",),
                                note="官方 npm 包",
                            ),
                        ),
                    ),
                ),
                notes=(
                    "这个预设不依赖额外 ACP adapter，但仍需要本机可用的 codex 命令。",
                ),
            ),
        ]

    def _inspect_agent(
        self,
        spec: ACPAgentSpec,
        current_config: dict[str, Any],
        installers: dict[str, Any],
    ) -> dict[str, Any]:
        components = [self._resolve_locator(locator) for locator in spec.required_components]
        runtime = self._resolve_locator(spec.runtime)
        ready = all(component["found"] for component in components)
        recommended_command = runtime["path"] or spec.runtime.candidates[0]
        recommended_args = list(spec.default_args)
        recommended_config = {
            "enabled": True,
            "command": recommended_command,
            "args": recommended_args,
            "env": dict(current_config.get("env") or {}),
            "startup_timeout_seconds": int(current_config.get("startup_timeout_seconds") or 20),
            "request_timeout_seconds": int(current_config.get("request_timeout_seconds") or 180),
            "default_builder": "acp",
        }
        install_steps: list[dict[str, Any]] = []
        for step in spec.install_steps:
            step_target = self._resolve_locator(step.target)
            recipe = self._select_recipe(step, installers)
            command_preview = ""
            if recipe is not None:
                command_preview = _quote_command(self._materialize_recipe_command(recipe, installers))
            install_steps.append(
                {
                    "id": step.id,
                    "label": step.label,
                    "installed": step_target["found"],
                    "available": recipe is not None,
                    "selected_recipe_id": recipe.id if recipe else "",
                    "command_preview": command_preview,
                    "note": recipe.note if recipe else "",
                }
            )

        missing = [component["label"] for component in components if not component["found"]]
        configured = _matches_configured_command(current_config, recommended_command, recommended_args)
        return {
            "id": spec.id,
            "name": spec.name,
            "summary": spec.summary,
            "homepage": spec.homepage,
            "platforms": list(spec.platforms),
            "supported_on_current_platform": self._platform in spec.platforms,
            "mode": spec.mode,
            "ready": ready,
            "configured": configured,
            "components": components,
            "runtime": runtime,
            "missing_components": missing,
            "recommended_config": recommended_config,
            "install_steps": install_steps,
            "env_hints": [
                {
                    "key": item.key,
                    "description": item.description,
                    "required": item.required,
                }
                for item in spec.env_hints
            ],
            "notes": list(spec.notes),
        }

    def _detect_installers(self) -> dict[str, Any]:
        return {
            key: self._resolve_locator(locator)
            for key, locator in self._installers.items()
        }

    def _resolve_locator(self, locator: CommandLocator) -> dict[str, Any]:
        for candidate in locator.candidates:
            path = self._which(candidate)
            if path:
                return {
                    "id": locator.id,
                    "label": locator.label,
                    "found": True,
                    "path": path,
                    "candidate": candidate,
                }
        return {
            "id": locator.id,
            "label": locator.label,
            "found": False,
            "path": "",
            "candidate": locator.candidates[0] if locator.candidates else "",
        }

    def _select_recipe(self, step: InstallStep, installers: dict[str, Any]) -> InstallRecipe | None:
        for recipe in step.recipes:
            if self._platform not in recipe.platforms:
                continue
            if all(bool((installers.get(requirement) or {}).get("found")) for requirement in recipe.requires):
                return recipe
        return None

    def _materialize_recipe_command(
        self,
        recipe: InstallRecipe,
        installers: dict[str, Any],
    ) -> list[str]:
        command = list(recipe.command)
        if not command:
            return command
        first = command[0]
        installer = installers.get(first) or {}
        path = str(installer.get("path") or "").strip()
        if path:
            command[0] = path
        return command

    def _get_spec(self, agent_id: str) -> ACPAgentSpec:
        for spec in self._specs:
            if spec.id == agent_id:
                return spec
        raise ACPWizardInstallError(f"未知 ACP agent: {agent_id}")

    def _which(self, command: str) -> str:
        text = str(command or "").strip()
        if not text:
            return ""
        if os.path.isabs(text) and os.path.exists(text):
            return text
        resolved = shutil.which(text)
        return resolved or ""

    async def _run_command(self, argv: list[str]) -> tuple[str, str, int]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self._project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        started_at = time.time()
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=self.INSTALL_TIMEOUT_SECONDS,
        )
        logger.info(
            "ACP wizard install command completed: command=%s return_code=%s duration_ms=%s",
            _quote_command(argv),
            proc.returncode,
            int((time.time() - started_at) * 1000),
        )
        return (
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            int(proc.returncode or 0),
        )
