"""CLI 交互式 LLM 配置引导模块（同步）

引导用户选择 LLM 提供商、输入 API Key，并写入 config.yml。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel

from agentos.platform.config.llm_presets import LLM_PROVIDER_CATEGORIES

console = Console()


# ── 辅助函数 ──────────────────────────────────────────────


def _prompt_choice(prompt: str, options: list[str], allow_skip: bool = False) -> int | None:
    """显示编号选项，返回 0-based 索引；允许跳过时返回 None。

    :param prompt: 提示文字
    :param options: 选项列表
    :param allow_skip: 是否允许跳过（输入 0 或空回车）
    :return: 0-based 索引，跳过时返回 None
    """
    console.print(f"\n[bold]{prompt}[/bold]")
    for i, opt in enumerate(options, 1):
        console.print(f"  {i}. {opt}")
    if allow_skip:
        console.print("  0. 跳过")

    while True:
        raw = input("> ").strip()
        if allow_skip and (raw == "0" or raw == ""):
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        console.print(f"[yellow]请输入 1-{len(options)} 之间的数字[/yellow]")


def _prompt_input(prompt: str, default: str = "") -> str:
    """获取用户输入，支持默认值。

    :param prompt: 提示文字
    :param default: 默认值（显示在括号中）
    :return: 用户输入的字符串（若为空则返回 default）
    """
    if default:
        console.print(f"\n[bold]{prompt}[/bold] [dim](默认: {default})[/dim]")
    else:
        console.print(f"\n[bold]{prompt}[/bold]")
    raw = input("> ").strip()
    return raw if raw else default


# ── 写配置 ────────────────────────────────────────────────


def _write_config(
    *,
    config_path: Path,
    provider_key: str,
    api_key: str,
    base_url: str,
    model_key: str,
    model_id: str,
    category_key: str,
) -> None:
    """将 LLM 配置写入 config.yml（深度合并，保留已有配置）。

    OpenAI 兼容提供商统一使用 "openai" 作为 provider 存储键。

    :param config_path: config.yml 路径
    :param provider_key: 提供商 key（如 "qwen"、"openai"、"anthropic"）
    :param api_key: API Key
    :param base_url: Base URL
    :param model_key: 模型 key（用于 llm.models 和 agent.model）
    :param model_id: 实际模型 ID（传给 LLM 的 model 参数）
    :param category_key: 分类 key（"openai_compatible"/"anthropic"/"gemini"）
    """
    # 读取已有配置
    existing: dict = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            existing = raw

    # OpenAI 兼容提供商统一用 "openai" 作为 provider 存储键
    storage_provider_key = "openai" if category_key == "openai_compatible" else provider_key

    # 构造新配置片段
    patch: dict = {
        "llm": {
            "providers": {
                storage_provider_key: {
                    "api_key": api_key,
                    "base_url": base_url,
                },
            },
            "models": {
                model_key: {
                    "provider": storage_provider_key,
                    "model_id": model_id,
                },
            },
            "default_model": model_key,
        },
        "agent": {
            "model": model_key,
        },
    }

    # 深度合并：existing 为基础，patch 覆盖
    merged = _deep_merge(existing, patch)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _deep_merge(base: dict, override: dict) -> dict:
    """递归深度合并两个 dict，override 中的值覆盖 base。"""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


# ── 主流程 ────────────────────────────────────────────────


def run_llm_setup_sync(config_path: Path) -> bool:
    """交互式 LLM 配置引导（同步）。

    引导用户完成 LLM 提供商选择、API Key 输入，并写入 config.yml。

    :param config_path: 目标 config.yml 路径
    :return: True 表示完成配置，False 表示用户跳过
    """
    console.print(
        Panel(
            "[bold yellow]⚠️  未检测到 LLM API 配置，请先完成初始设置[/bold yellow]\n\n"
            "AgentOS 需要至少一个 LLM 提供商的 API Key 才能正常工作。\n"
            "以下引导将帮助您完成基础配置。",
            title="LLM 配置向导",
            border_style="yellow",
        )
    )

    # 步骤 1：选择提供商分类
    category_labels = [c["label"] for c in LLM_PROVIDER_CATEGORIES] + ["跳过配置"]
    cat_idx = _prompt_choice("请选择 LLM 提供商类别", category_labels)

    # 用户选择了最后一项（跳过配置）
    if cat_idx is None or cat_idx == len(LLM_PROVIDER_CATEGORIES):
        console.print("[dim]已跳过 LLM 配置，您可以稍后手动编辑 config.yml。[/dim]")
        return False

    selected_category = LLM_PROVIDER_CATEGORIES[cat_idx]
    category_key: str = selected_category["key"]
    providers: list[dict] = selected_category["providers"]

    # 步骤 2：选择具体提供商（若该分类只有一个提供商则自动选择）
    if len(providers) == 1:
        selected_provider = providers[0]
    else:
        provider_labels = [p["label"] for p in providers]
        prov_idx = _prompt_choice("请选择具体提供商", provider_labels)
        if prov_idx is None:
            console.print("[dim]已跳过 LLM 配置。[/dim]")
            return False
        selected_provider = providers[prov_idx]

    provider_key: str = selected_provider["key"]
    default_base_url: str = selected_provider.get("base_url", "")
    preset_models: list[dict] = selected_provider.get("models", [])

    # 步骤 3：输入 Base URL
    base_url = _prompt_input("请输入 Base URL", default=default_base_url)
    if not base_url:
        base_url = default_base_url

    # 步骤 4：输入 API Key
    console.print("\n[bold]请输入 API Key[/bold]")
    api_key = input("> ").strip()
    if not api_key:
        console.print("[yellow]API Key 不能为空，已跳过配置。[/yellow]")
        return False

    # 步骤 5：选择模型
    model_key: str
    model_id: str

    if preset_models:
        model_options = [f"{m['model_id']}  [dim]({m['key']})[/dim]" for m in preset_models]
        model_options_plain = [m["model_id"] for m in preset_models]
        model_options.append("手动输入模型名称")

        console.print(f"\n[bold]请选择模型[/bold]")
        for i, opt in enumerate(model_options, 1):
            console.print(f"  {i}. {opt}")

        while True:
            raw = input("> ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if idx == len(preset_models):
                    # 手动输入
                    model_id = _prompt_input("请输入模型名称（model_id）")
                    if not model_id:
                        console.print("[yellow]模型名称不能为空，使用第一个预设模型。[/yellow]")
                        model_id = preset_models[0]["model_id"]
                        model_key = preset_models[0]["key"]
                    else:
                        # 生成 key：将 model_id 中的 `-` 和 `.` 替换为 `_`
                        model_key = model_id.replace("-", "_").replace(".", "_")
                    break
                if 0 <= idx < len(preset_models):
                    model_key = preset_models[idx]["key"]
                    model_id = preset_models[idx]["model_id"]
                    break
            console.print(f"[yellow]请输入 1-{len(model_options)} 之间的数字[/yellow]")
    else:
        # 无预设，直接手动输入
        model_id = _prompt_input("请输入模型名称（model_id）")
        if not model_id:
            console.print("[yellow]模型名称不能为空，已跳过配置。[/yellow]")
            return False
        model_key = model_id.replace("-", "_").replace(".", "_")

    # 步骤 6：写入配置文件
    _write_config(
        config_path=config_path,
        provider_key=provider_key,
        api_key=api_key,
        base_url=base_url,
        model_key=model_key,
        model_id=model_id,
        category_key=category_key,
    )

    console.print(
        Panel(
            f"[bold green]✅ 配置已保存到 {config_path}[/bold green]\n\n"
            f"  提供商: [cyan]{selected_provider['label']}[/cyan]\n"
            f"  模型: [cyan]{model_id}[/cyan]\n\n"
            "提示: 如需切换 Agent 使用的模型，可使用命令:\n"
            "[dim]/agent switch system-admin[/dim]",
            title="配置完成",
            border_style="green",
        )
    )
    console.print("[dim]请重启 AgentOS 以使配置生效。[/dim]")

    return True
