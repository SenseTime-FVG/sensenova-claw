# 安装后配置引导 + SystemAdmin Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户安装后未配置 LLM API 时，在终端、Web、CLI 三个入口提示配置，并提供 SystemAdmin 运维 Agent 辅助管理系统。

**Architecture:** 新增后端 LLM 状态检测 API，终端/CLI 通过读本地 config 判断，Web 通过 API 判断。CLI 提供交互式引导直接写 config.yml。Web 提供 `/setup` 引导页。SystemAdmin Agent 预注册并配备 system-admin-skill。

**Tech Stack:** Python/FastAPI (后端), Next.js/TypeScript (前端), Rich (CLI), YAML (配置)

---

## 共享数据：Provider 预设配置

CLI 和 Web 共用一套 provider/服务商/模型预设数据，定义如下（后续 Task 中会引用）：

```python
# sensenova_claw/platform/config/llm_presets.py
LLM_PROVIDER_CATEGORIES = [
    {
        "key": "openai_compatible",
        "label": "OpenAI 兼容",
        "providers": [
            {
                "key": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "models": [
                    {"key": "gpt-4o-mini", "model_id": "gpt-4o-mini"},
                    {"key": "gpt-4o", "model_id": "gpt-4o"},
                    {"key": "gpt-4.1", "model_id": "gpt-4.1"},
                ],
            },
            {
                "key": "qwen",
                "label": "通义千问 (Qwen)",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": [
                    {"key": "qwen-plus", "model_id": "qwen-plus"},
                    {"key": "qwen-turbo", "model_id": "qwen-turbo"},
                    {"key": "qwen-max", "model_id": "qwen-max"},
                ],
            },
            {
                "key": "zhipu",
                "label": "智谱 GLM (Zhipu)",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "models": [
                    {"key": "glm-4-plus", "model_id": "glm-4-plus"},
                    {"key": "glm-4-flash", "model_id": "glm-4-flash"},
                ],
            },
            {
                "key": "minimax",
                "label": "MiniMax",
                "base_url": "https://api.minimax.chat/v1",
                "models": [
                    {"key": "minimax-text-01", "model_id": "MiniMax-Text-01"},
                ],
            },
            {
                "key": "deepseek",
                "label": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "models": [
                    {"key": "deepseek-chat", "model_id": "deepseek-chat"},
                    {"key": "deepseek-reasoner", "model_id": "deepseek-reasoner"},
                ],
            },
            {
                "key": "yi",
                "label": "零一万物 (Yi)",
                "base_url": "https://api.lingyiwanwu.com/v1",
                "models": [
                    {"key": "yi-large", "model_id": "yi-large"},
                    {"key": "yi-medium", "model_id": "yi-medium"},
                ],
            },
        ],
    },
    {
        "key": "anthropic",
        "label": "Anthropic (Claude)",
        "providers": [
            {
                "key": "anthropic",
                "label": "Anthropic",
                "base_url": "https://api.anthropic.com",
                "models": [
                    {"key": "claude-sonnet", "model_id": "claude-sonnet-4-6"},
                    {"key": "claude-opus", "model_id": "claude-opus-4-6"},
                    {"key": "claude-haiku", "model_id": "claude-haiku-4-5-20251001"},
                ],
            },
        ],
    },
    {
        "key": "gemini",
        "label": "Google Gemini",
        "providers": [
            {
                "key": "gemini",
                "label": "Google Gemini",
                "base_url": "https://generativelanguage.googleapis.com",
                "models": [
                    {"key": "gemini-pro", "model_id": "gemini-2.5-pro"},
                    {"key": "gemini-flash", "model_id": "gemini-2.5-flash"},
                ],
            },
        ],
    },
]
```

---

### Task 1: 创建 LLM 预设配置模块

**Files:**
- Create: `sensenova_claw/platform/config/llm_presets.py`
- Test: `tests/unit/test_llm_presets.py`

- [ ] **Step 1: 创建预设模块**

创建 `sensenova_claw/platform/config/llm_presets.py`，包含上述 `LLM_PROVIDER_CATEGORIES` 数据和辅助函数：

```python
"""LLM 提供商预设配置，CLI 和 Web 共用"""
from __future__ import annotations
from typing import Any

LLM_PROVIDER_CATEGORIES: list[dict[str, Any]] = [
    # ... 上面的完整数据 ...
]


def get_all_providers() -> list[dict[str, Any]]:
    """返回所有服务商的扁平列表"""
    result = []
    for category in LLM_PROVIDER_CATEGORIES:
        for provider in category["providers"]:
            result.append({**provider, "category": category["key"]})
    return result


def get_provider(provider_key: str) -> dict[str, Any] | None:
    """根据 key 获取服务商信息"""
    for category in LLM_PROVIDER_CATEGORIES:
        for provider in category["providers"]:
            if provider["key"] == provider_key:
                return {**provider, "category": category["key"]}
    return None


def check_llm_configured(config_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """检查是否有可用的 LLM provider 已配置（api_key 非空且非 mock）。

    Returns:
        (configured: bool, configured_providers: list[str])
    """
    providers = config_data.get("llm", {}).get("providers", {})
    configured = []
    for name, cfg in providers.items():
        if name == "mock":
            continue
        api_key = cfg.get("api_key", "")
        if api_key and not api_key.startswith("${"):
            configured.append(name)
    return bool(configured), configured
```

- [ ] **Step 2: 写测试**

```python
# tests/unit/test_llm_presets.py
from sensenova_claw.platform.config.llm_presets import (
    get_all_providers, get_provider, check_llm_configured,
    LLM_PROVIDER_CATEGORIES,
)

def test_get_all_providers_returns_flat_list():
    providers = get_all_providers()
    assert len(providers) > 5
    keys = [p["key"] for p in providers]
    assert "openai" in keys
    assert "qwen" in keys
    assert "anthropic" in keys

def test_get_provider_found():
    p = get_provider("deepseek")
    assert p is not None
    assert p["base_url"] == "https://api.deepseek.com/v1"
    assert p["category"] == "openai_compatible"

def test_get_provider_not_found():
    assert get_provider("nonexistent") is None

def test_check_llm_configured_no_key():
    data = {"llm": {"providers": {"mock": {"api_key": ""}, "openai": {"api_key": ""}}}}
    configured, providers = check_llm_configured(data)
    assert not configured
    assert providers == []

def test_check_llm_configured_with_env_var_unresolved():
    data = {"llm": {"providers": {"openai": {"api_key": "${OPENAI_API_KEY}"}}}}
    configured, providers = check_llm_configured(data)
    assert not configured

def test_check_llm_configured_with_real_key():
    data = {"llm": {"providers": {"openai": {"api_key": "sk-1234"}}}}
    configured, providers = check_llm_configured(data)
    assert configured
    assert providers == ["openai"]
```

- [ ] **Step 3: 运行测试**

Run: `python3 -m pytest tests/unit/test_llm_presets.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/platform/config/llm_presets.py tests/unit/test_llm_presets.py
git commit -m "feat: 添加 LLM 提供商预设配置模块"
```

---

### Task 2: 后端 LLM 状态检测 API

**Files:**
- Modify: `sensenova_claw/interfaces/http/config_api.py`
- Test: `tests/unit/test_llm_status_api.py`

- [ ] **Step 1: 添加 API 端点**

在 `config_api.py` 末尾添加：

```python
from sensenova_claw.platform.config.llm_presets import check_llm_configured, LLM_PROVIDER_CATEGORIES

@router.get("/llm-status")
async def get_llm_status(request: Request):
    """返回 LLM 配置状态：是否有可用 provider"""
    cfg = request.app.state.config
    configured, providers = check_llm_configured(cfg.data)
    return {"configured": configured, "providers": providers}

@router.get("/llm-presets")
async def get_llm_presets():
    """返回 LLM 提供商预设列表，供 Web 端配置页使用"""
    return {"categories": LLM_PROVIDER_CATEGORIES}
```

- [ ] **Step 2: 写测试**

```python
# tests/unit/test_llm_status_api.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sensenova_claw.interfaces.http.config_api import router

@pytest.fixture
def app_with_config():
    app = FastAPI()
    app.include_router(router)

    def _make(providers: dict):
        cfg = MagicMock()
        cfg.data = {"llm": {"providers": providers}}
        app.state.config = cfg
        return TestClient(app)

    return _make

def test_llm_status_not_configured(app_with_config):
    client = app_with_config({"mock": {"api_key": ""}})
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False

def test_llm_status_configured(app_with_config):
    client = app_with_config({"openai": {"api_key": "sk-test"}})
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert "openai" in data["providers"]

def test_llm_presets_returns_categories(app_with_config):
    client = app_with_config({})
    resp = client.get("/api/config/llm-presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert len(data["categories"]) >= 3
```

- [ ] **Step 3: 运行测试**

Run: `python3 -m pytest tests/unit/test_llm_status_api.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/interfaces/http/config_api.py tests/unit/test_llm_status_api.py
git commit -m "feat: 添加 LLM 配置状态检测和预设列表 API"
```

---

### Task 3: 终端启动提示

**Files:**
- Modify: `sensenova_claw/app/main.py:122-134`

- [ ] **Step 1: 修改 cmd_run 中的启动提示**

在 `main.py` 的 `cmd_run` 函数中，启动提示区块（第 122-134 行）之前，添加 LLM 配置检测：

```python
# 在 print("=" * 50) 之前，添加 LLM 配置检查
from sensenova_claw.platform.config.config import Config, PROJECT_ROOT
_cfg = Config(project_root=PROJECT_ROOT)

from sensenova_claw.platform.config.llm_presets import check_llm_configured
_llm_ok, _ = check_llm_configured(_cfg.data)
```

然后修改打印区块，在 `print("=" * 50)` 和 `print("按 Ctrl+C 停止所有服务\n")` 之间，加入：

```python
    if not _llm_ok:
        print()
        print("  ⚠️  未检测到可用的 LLM API 配置，当前使用 Mock 模式")
        if frontend_proc:
            print(f"     → 访问 http://localhost:{frontend_port} 进行配置")
        print(f"     → 或使用 sensenova-claw cli --port {backend_port} 进行配置")
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/main.py
git commit -m "feat: sensenova-claw run 启动时检测 LLM 配置并提示"
```

---

### Task 4: CLI 交互式 LLM 配置引导

**Files:**
- Create: `sensenova_claw/app/cli/llm_setup.py`
- Modify: `sensenova_claw/app/cli/app.py:360-376` (在 `_run_interactive_mode` 中调用)
- Test: `tests/unit/test_cli_llm_setup.py`

- [ ] **Step 1: 创建 llm_setup.py**

```python
"""CLI 交互式 LLM 配置引导"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel

from sensenova_claw.platform.config.llm_presets import (
    LLM_PROVIDER_CATEGORIES,
    check_llm_configured,
)

console = Console()


def _prompt_choice(prompt: str, options: list[str], allow_skip: bool = False) -> int | None:
    """显示选项列表并获取用户选择，返回 0-based 索引，跳过返回 None"""
    console.print(f"\n[bold]{prompt}[/bold]")
    for i, opt in enumerate(options, 1):
        console.print(f"  {i}. {opt}")
    if allow_skip:
        console.print(f"  {len(options) + 1}. 跳过配置")

    while True:
        try:
            raw = input("> ").strip()
            if not raw:
                continue
            idx = int(raw)
            if allow_skip and idx == len(options) + 1:
                return None
            if 1 <= idx <= len(options):
                return idx - 1
            console.print("[red]无效选择，请重新输入[/red]")
        except (ValueError, EOFError):
            console.print("[red]请输入数字[/red]")


def _prompt_input(prompt: str, default: str = "") -> str:
    """获取用户输入，支持默认值"""
    suffix = f" (回车使用默认值 {default})" if default else ""
    console.print(f"[bold]{prompt}{suffix}:[/bold]")
    raw = input("> ").strip()
    return raw or default


async def run_llm_setup(config_path: Path) -> bool:
    """运行 LLM 配置引导。返回 True 表示配置成功，False 表示跳过。

    Args:
        config_path: config.yml 文件路径
    """
    console.print(Panel(
        "[yellow]⚠️  未检测到 LLM API 配置，请先完成初始设置[/yellow]",
        border_style="yellow",
    ))

    # Step 1: 选择 provider 大类
    category_labels = [c["label"] for c in LLM_PROVIDER_CATEGORIES]
    cat_idx = _prompt_choice("请选择 LLM 提供商:", category_labels, allow_skip=True)
    if cat_idx is None:
        console.print("[dim]已跳过 LLM 配置[/dim]")
        return False

    category = LLM_PROVIDER_CATEGORIES[cat_idx]
    providers = category["providers"]

    # Step 2: 如果大类下有多个服务商，让用户选择具体服务商
    if len(providers) == 1:
        provider = providers[0]
    else:
        provider_labels = [p["label"] for p in providers]
        provider_labels.append("其他 (手动输入 Base URL)")
        p_idx = _prompt_choice("请选择具体服务商:", provider_labels)
        if p_idx is None or p_idx >= len(providers):
            # "其他" 选项
            provider = {
                "key": category["key"],
                "label": "自定义",
                "base_url": "",
                "models": [],
            }
        else:
            provider = providers[p_idx]

    # Step 3: 输入 Base URL
    base_url = _prompt_input("请输入 Base URL", default=provider.get("base_url", ""))
    if not base_url:
        console.print("[red]Base URL 不能为空[/red]")
        return False

    # Step 4: 输入 API Key
    api_key = _prompt_input("请输入 API Key")
    if not api_key:
        console.print("[red]API Key 不能为空[/red]")
        return False

    # Step 5: 选择模型
    models = provider.get("models", [])
    if models:
        model_labels = [m["model_id"] for m in models]
        m_idx = _prompt_choice("请选择默认模型:", model_labels)
        if m_idx is None:
            m_idx = 0
        selected_model = models[m_idx]
    else:
        model_id = _prompt_input("请输入模型名称")
        selected_model = {"key": model_id, "model_id": model_id}

    # Step 6: 写入 config.yml
    _write_config(
        config_path=config_path,
        provider_key=provider["key"] if provider["key"] != category["key"] else category["key"],
        api_key=api_key,
        base_url=base_url,
        model_key=selected_model["key"],
        model_id=selected_model["model_id"],
        category_key=category["key"],
    )

    console.print("\n[green]✅ LLM 配置完成！已写入 config.yml[/green]")
    console.print("[cyan]💡 输入 /agent switch system-admin 可切换到运维助手，完成更多系统配置[/cyan]\n")
    return True


def _write_config(
    config_path: Path,
    provider_key: str,
    api_key: str,
    base_url: str,
    model_key: str,
    model_id: str,
    category_key: str,
) -> None:
    """将 LLM 配置写入 config.yml"""
    # 读取现有配置
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}

    # OpenAI 兼容类统一用 "openai" provider
    llm_provider = "openai" if category_key == "openai_compatible" else provider_key

    # 确保结构存在
    data.setdefault("llm", {})
    data["llm"].setdefault("providers", {})
    data["llm"].setdefault("models", {})

    # 写入 provider
    data["llm"]["providers"][llm_provider] = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": 60,
        "max_retries": 3,
    }

    # 写入 model
    data["llm"]["models"][model_key] = {
        "provider": llm_provider,
        "model_id": model_id,
    }

    # 设置默认模型
    data["llm"]["default_model"] = model_key

    # 更新 agent 默认模型
    data.setdefault("agent", {})
    data["agent"]["model"] = model_key

    # 写入文件
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

- [ ] **Step 2: 在 CLIApp._run_interactive_mode 中调用**

在 `app.py` 的 `_run_interactive_mode` 方法中，在 `self.display.show_welcome(...)` 之前添加 LLM 配置检测：

```python
    async def _run_interactive_mode(self) -> int:
        """交互模式：REPL 循环"""
        # 检测 LLM 配置状态，未配置时引导用户
        await self._check_and_setup_llm()

        # 获取 Agent 信息用于欢迎页
        agent_info = await self._fetch_agent_info(self.current_agent_id)
        # ... 后续不变
```

新增方法 `_check_and_setup_llm`：

```python
    async def _check_and_setup_llm(self) -> None:
        """检测 LLM 配置，未配置时引导用户完成设置"""
        try:
            resp = await self._http_get("/api/config/llm-status")
            if resp.get("_error") or resp.get("configured"):
                return
        except Exception:
            return

        from sensenova_claw.app.cli.llm_setup import run_llm_setup
        from sensenova_claw.platform.config.config import PROJECT_ROOT
        config_path = PROJECT_ROOT / "config.yml"
        await asyncio.to_thread(
            lambda: asyncio.get_event_loop().run_until_complete(run_llm_setup(config_path))
        )
```

注意：`run_llm_setup` 内部使用 `input()` 阻塞调用，需要在线程中执行。由于函数本身是 async 但内部 I/O 用 `input()`，实际可以简化为同步调用套 `asyncio.to_thread`：

```python
    async def _check_and_setup_llm(self) -> None:
        """检测 LLM 配置，未配置时引导用户完成设置"""
        try:
            resp = await self._http_get("/api/config/llm-status")
            if resp.get("_error") or resp.get("configured"):
                return
        except Exception:
            return

        from sensenova_claw.app.cli.llm_setup import run_llm_setup_sync
        from sensenova_claw.platform.config.config import PROJECT_ROOT
        config_path = PROJECT_ROOT / "config.yml"
        await asyncio.to_thread(run_llm_setup_sync, config_path)
```

在 `llm_setup.py` 中将 `run_llm_setup` 改为同步函数 `run_llm_setup_sync`（去掉 async），因为内部全是同步 `input()` 调用。

- [ ] **Step 3: 写测试**

```python
# tests/unit/test_cli_llm_setup.py
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch
from sensenova_claw.app.cli.llm_setup import _write_config, run_llm_setup_sync

def test_write_config_creates_file(tmp_path):
    config_path = tmp_path / "config.yml"
    _write_config(
        config_path=config_path,
        provider_key="qwen",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_key="qwen-plus",
        model_id="qwen-plus",
        category_key="openai_compatible",
    )
    assert config_path.exists()
    data = yaml.safe_load(config_path.read_text())
    assert data["llm"]["providers"]["openai"]["api_key"] == "sk-test"
    assert data["llm"]["default_model"] == "qwen-plus"
    assert data["agent"]["model"] == "qwen-plus"

def test_write_config_preserves_existing(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({"tools": {"bash_command": {"enabled": True}}}))
    _write_config(
        config_path=config_path,
        provider_key="anthropic",
        api_key="sk-ant",
        base_url="https://api.anthropic.com",
        model_key="claude-sonnet",
        model_id="claude-sonnet-4-6",
        category_key="anthropic",
    )
    data = yaml.safe_load(config_path.read_text())
    # 保留原有配置
    assert data["tools"]["bash_command"]["enabled"] is True
    # 新配置已写入
    assert data["llm"]["providers"]["anthropic"]["api_key"] == "sk-ant"

def test_run_llm_setup_skip(tmp_path):
    """用户选择跳过时返回 False"""
    config_path = tmp_path / "config.yml"
    # 模拟用户输入：选择第 4 个选项（跳过）
    with patch("builtins.input", side_effect=["4"]):
        result = run_llm_setup_sync(config_path)
    assert result is False
```

- [ ] **Step 4: 运行测试**

Run: `python3 -m pytest tests/unit/test_cli_llm_setup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/app/cli/llm_setup.py sensenova_claw/app/cli/app.py tests/unit/test_cli_llm_setup.py
git commit -m "feat: CLI 交互式 LLM 配置引导"
```

---

### Task 5: SystemAdmin Agent 注册

**Files:**
- Modify: `sensenova_claw/capabilities/agents/registry.py:82-106`
- Create: `sensenova_claw/capabilities/skills/builtin/system-admin-skill/SKILL.md`

- [ ] **Step 1: 在 AgentRegistry.load_from_config 中注册 system-admin Agent**

修改 `registry.py` 的 `load_from_config` 方法，在确保 default agent 之后，确保 system-admin agent 也始终存在：

```python
    def load_from_config(self, config_data: dict[str, Any]) -> None:
        # ... 原有代码不变 ...

        # 确保 default agent 始终存在
        if not self.get("default"):
            default = self._build_agent_from_dict("default", {}, agent_section)
            self.register(default)

        # 确保 system-admin agent 始终存在
        if not self.get("system-admin"):
            system_admin_dict = {
                "name": "SystemAdmin",
                "description": "系统运维管理员，负责 Sensenova-Claw 平台的配置管理、Agent 管理、工具管理、Skill/Plugin 安装等运维操作",
                "system_prompt": (
                    "你是 Sensenova-Claw 的系统管理员（SystemAdmin）。你的职责是帮助用户管理和配置 Sensenova-Claw 平台。\n\n"
                    "你可以通过读写配置文件和执行系统命令来完成管理任务。操作前请先告知用户你将要执行的操作，等用户确认后再执行。\n\n"
                    "修改配置文件后，请提醒用户某些配置可能需要重启服务才能生效。"
                ),
                "tools": ["read_file", "write_file", "bash_command"],
                "skills": ["system-admin-skill"],
            }
            sa = self._build_agent_from_dict("system-admin", system_admin_dict, agent_section)
            self.register(sa)
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/capabilities/agents/registry.py
git commit -m "feat: 预注册 SystemAdmin Agent"
```

---

### Task 6: system-admin-skill 编写

**Files:**
- Create: `sensenova_claw/capabilities/skills/builtin/system-admin-skill/SKILL.md`

- [ ] **Step 1: 创建 SKILL.md**

```markdown
---
name: system-admin-skill
description: Sensenova-Claw 系统运维管理技能，涵盖 LLM 配置、Agent 管理、工具配置、Skill/Plugin 安装、Cron 管理和系统状态查看
---

# Sensenova-Claw 系统管理员技能

你是 Sensenova-Claw 的系统管理员。通过 `read_file`、`write_file`、`bash_command` 三个工具完成所有管理操作。

## 环境感知

在执行任何操作前，必须先确定配置目录：

1. 执行 `bash_command`: `echo $SENSENOVA_CLAW_HOME` 获取环境变量
2. 如果为空，读取 config.yml 中 `system.sensenova_claw_home` 字段
3. 如果仍为空，默认使用 `~/.sensenova-claw/`
4. 记住这个路径作为 `{SENSENOVA_CLAW_HOME}`，后续所有操作使用它

项目根目录的 config.yml 是主配置文件，通过 `bash_command` 执行 `pwd` 确定项目根目录。

## 目录结构

```
{SENSENOVA_CLAW_HOME}/
├── agents/
│   ├── default/          # 默认 Agent
│   │   ├── config.json
│   │   ├── AGENTS.md     # Agent 指令
│   │   └── USER.md       # 用户档案
│   └── {agent_id}/       # 自定义 Agent
├── workdir/
│   └── {agent_id}/       # Agent 工作目录（bash_command 的 cwd）
├── skills/               # 用户安装的 Skill
│   └── {skill_name}/
│       └── SKILL.md
├── data/
│   ├── sensenova-claw.db        # 主数据库
│   └── memory_index.db   # 记忆索引
├── .agent_preferences.json  # 工具/Skill 启用偏好
├── skills_state.json     # Skill 启用/禁用状态
└── token                 # 认证 Token
```

## 1. LLM 配置管理

### 查看当前配置
```
读取项目根目录 config.yml，解析 llm.providers 和 llm.models 段落
```

### 添加/修改 Provider
编辑 config.yml 中的 `llm.providers` 部分：
```yaml
llm:
  providers:
    openai:                    # provider 名称
      api_key: "sk-xxx"       # API Key
      base_url: "https://api.openai.com/v1"  # Base URL
      timeout: 60
      max_retries: 3
```

OpenAI 兼容的服务商（通义千问、智谱GLM、DeepSeek 等）统一使用 `openai` 作为 provider 名称，通过 `base_url` 区分。

### 添加/修改模型
编辑 config.yml 中的 `llm.models` 部分：
```yaml
llm:
  models:
    qwen-plus:                 # 模型 key（自定义名称）
      provider: openai         # 引用 providers 中的 key
      model_id: qwen-plus      # 实际模型 ID
      timeout: 60
      max_output_tokens: 8192
```

### 切换默认模型
修改 config.yml 中：
```yaml
llm:
  default_model: "qwen-plus"   # 引用 models 中的 key
agent:
  model: "qwen-plus"           # 同步修改
```

## 2. Agent 管理

### 查看 Agent 列表
```bash
ls {SENSENOVA_CLAW_HOME}/agents/
```

### 创建 Agent
1. 创建目录：`mkdir -p {SENSENOVA_CLAW_HOME}/agents/{agent_id}`
2. 创建 `config.json`：
```json
{
  "id": "agent_id",
  "name": "Agent 名称",
  "description": "Agent 描述",
  "provider": "",
  "model": "qwen-plus",
  "temperature": 0.2,
  "max_tokens": null,
  "system_prompt": "系统提示词",
  "tools": [],
  "skills": [],
  "workdir": "",
  "can_send_message_to": [],
  "max_send_depth": 3,
  "max_pingpong_turns": 10,
  "enabled": true,
  "created_at": 1234567890.0,
  "updated_at": 1234567890.0
}
```
3. 可选创建 `AGENTS.md`（Agent 指令）和 `USER.md`（用户档案）

### 修改 Agent
读取 → 修改 → 写回 `{SENSENOVA_CLAW_HOME}/agents/{agent_id}/config.json`

### 删除 Agent
```bash
rm -rf {SENSENOVA_CLAW_HOME}/agents/{agent_id}
rm -rf {SENSENOVA_CLAW_HOME}/workdir/{agent_id}
```
**注意：不能删除 default Agent。**

## 3. 工具配置

### 搜索工具配置
编辑 config.yml 中的 `tools` 部分：
```yaml
tools:
  serper_search:
    api_key: "your-serper-key"
    timeout: 15
    max_results: 10
  brave_search:
    api_key: "your-brave-key"
  tavily_search:
    api_key: "your-tavily-key"
```

### 邮件工具配置
```yaml
tools:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    imap_host: imap.gmail.com
    imap_port: 993
    username: "user@gmail.com"
    password: "app-specific-password"
```

### 启用/禁用工具
编辑 `{SENSENOVA_CLAW_HOME}/.agent_preferences.json`：
```json
{
  "tools": {
    "bash_command": true,
    "serper_search": false
  }
}
```

## 4. Skill 管理

### 查看已安装 Skill
```bash
# 内置 Skill
ls sensenova_claw/capabilities/skills/builtin/
# 用户安装的 Skill
ls {SENSENOVA_CLAW_HOME}/skills/
```

### 安装 Skill（从本地路径）
```bash
cp -r /path/to/skill_dir {SENSENOVA_CLAW_HOME}/skills/{skill_name}
```
确保目标目录中包含 `SKILL.md` 文件。

### 卸载 Skill
```bash
rm -rf {SENSENOVA_CLAW_HOME}/skills/{skill_name}
```

### 启用/禁用 Skill
编辑 `{SENSENOVA_CLAW_HOME}/skills_state.json`：
```json
{
  "skill_name": true,
  "another_skill": false
}
```

## 5. Plugin 管理

### 查看 Plugin 配置
读取 config.yml 中的 `plugins` 部分。

### 启用/配置 Plugin
编辑 config.yml 中的 `plugins` 部分：
```yaml
plugins:
  feishu:
    enabled: true
    app_id: "your-app-id"
    app_secret: "your-app-secret"
  wecom:
    enabled: true
    bot_id: "your-bot-id"
    secret: "your-secret"
```

## 6. Cron 管理

### 查看 Cron 配置
读取 config.yml 中的 `cron` 部分。

### 修改 Cron 配置
```yaml
cron:
  enabled: true
  max_concurrent_runs: 1
  retry:
    max_attempts: 3
    backoff_ms: [60000, 120000, 300000]
```

## 7. 系统状态

### 查看配置概览
读取 config.yml 并输出关键配置项摘要。

### 查看目录结构
```bash
ls -la {SENSENOVA_CLAW_HOME}/
ls -la {SENSENOVA_CLAW_HOME}/agents/
ls -la {SENSENOVA_CLAW_HOME}/skills/
```

### 查看数据库大小
```bash
ls -lh {SENSENOVA_CLAW_HOME}/data/
```

### 查看日志
```bash
# 查看最近的日志输出
tail -50 /path/to/log
```

## 安全规范

1. **备份优先**：修改 config.yml 前先执行 `cp config.yml config.yml.bak`
2. **确认操作**：执行删除或覆盖操作前，告知用户将要做什么并等待确认
3. **不碰数据库**：不直接读写 .db 文件
4. **敏感信息**：写入 API Key 后提醒用户不要分享 config.yml
5. **重启提醒**：修改配置后提醒用户部分配置需要重启服务才能生效
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/capabilities/skills/builtin/system-admin-skill/SKILL.md
git commit -m "feat: 添加 system-admin-skill 运维技能"
```

---

### Task 7: Web 端 LLM 配置引导页

**Files:**
- Create: `sensenova_claw/app/web/app/setup/page.tsx`
- Modify: `sensenova_claw/app/web/components/ProtectedRoute.tsx`

- [ ] **Step 1: 创建 /setup 页面**

创建 `sensenova_claw/app/web/app/setup/page.tsx`，风格仿照 `/login` 页面：

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { authGet, authPost, authFetch, API_BASE } from "@/lib/authFetch";

interface ProviderOption {
  key: string;
  label: string;
  base_url: string;
  models: { key: string; model_id: string }[];
}

interface CategoryOption {
  key: string;
  label: string;
  providers: ProviderOption[];
}

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<"category" | "provider" | "config" | "model">("category");
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<CategoryOption | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<ProviderOption | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [customModelId, setCustomModelId] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    authGet<{ categories: CategoryOption[] }>(`${API_BASE}/api/config/llm-presets`)
      .then((data) => setCategories(data.categories))
      .catch(() => {});
  }, []);

  const handleCategorySelect = (cat: CategoryOption) => {
    setSelectedCategory(cat);
    if (cat.providers.length === 1) {
      setSelectedProvider(cat.providers[0]);
      setBaseUrl(cat.providers[0].base_url);
      setStep("config");
    } else {
      setStep("provider");
    }
  };

  const handleProviderSelect = (prov: ProviderOption | null) => {
    if (prov) {
      setSelectedProvider(prov);
      setBaseUrl(prov.base_url);
    } else {
      // "其他" 选项
      setSelectedProvider({ key: selectedCategory!.key, label: "自定义", base_url: "", models: [] });
      setBaseUrl("");
    }
    setStep("config");
  };

  const handleConfigNext = () => {
    if (!baseUrl.trim()) { setError("请输入 Base URL"); return; }
    if (!apiKey.trim()) { setError("请输入 API Key"); return; }
    setError("");
    if (selectedProvider?.models.length) {
      setStep("model");
    } else {
      // 无预设模型，直接输入
      setStep("model");
    }
  };

  const handleSubmit = async () => {
    setIsLoading(true);
    setError("");
    try {
      const categoryKey = selectedCategory!.key;
      const llmProvider = categoryKey === "openai_compatible" ? "openai" : selectedProvider!.key;
      const modelKey = selectedModel || customModelId;
      const modelId = selectedProvider?.models.find(m => m.key === selectedModel)?.model_id || customModelId;

      if (!modelKey) { setError("请选择或输入模型"); setIsLoading(false); return; }

      await authFetch(`${API_BASE}/api/config/sections`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm: {
            providers: {
              [llmProvider]: {
                api_key: apiKey,
                base_url: baseUrl,
                timeout: 60,
                max_retries: 3,
              },
            },
            models: {
              [modelKey]: {
                provider: llmProvider,
                model_id: modelId,
              },
            },
            default_model: modelKey,
          },
          agent: { model: modelKey },
        }),
      });

      router.push("/chat?agent=system-admin");
    } catch (e: any) {
      setError(e.message || "配置保存失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkip = () => router.push("/chat");

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-6 p-8 bg-white rounded-lg shadow-md">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-gray-900">Sensenova-Claw</h2>
          <p className="mt-2 text-center text-sm text-gray-600">配置 LLM 服务</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>
        )}

        {/* Step: 选择大类 */}
        {step === "category" && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700">选择 LLM 提供商</p>
            {categories.map((cat) => (
              <button
                key={cat.key}
                onClick={() => handleCategorySelect(cat)}
                className="w-full text-left px-4 py-3 border border-gray-300 rounded-md hover:border-blue-500 hover:bg-blue-50 transition-colors"
              >
                <span className="font-medium">{cat.label}</span>
              </button>
            ))}
          </div>
        )}

        {/* Step: 选择具体服务商 */}
        {step === "provider" && selectedCategory && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700">选择具体服务商</p>
            {selectedCategory.providers.map((prov) => (
              <button
                key={prov.key}
                onClick={() => handleProviderSelect(prov)}
                className="w-full text-left px-4 py-3 border border-gray-300 rounded-md hover:border-blue-500 hover:bg-blue-50 transition-colors"
              >
                <span className="font-medium">{prov.label}</span>
              </button>
            ))}
            <button
              onClick={() => handleProviderSelect(null)}
              className="w-full text-left px-4 py-3 border border-gray-300 rounded-md hover:border-blue-500 hover:bg-blue-50 transition-colors"
            >
              <span className="font-medium">其他 (手动输入 Base URL)</span>
            </button>
            <button
              onClick={() => setStep("category")}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← 返回
            </button>
          </div>
        )}

        {/* Step: 输入 Base URL 和 API Key */}
        {step === "config" && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Base URL</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                placeholder="https://api.openai.com/v1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                placeholder="sk-..."
              />
            </div>
            <button
              onClick={handleConfigNext}
              className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              下一步
            </button>
            <button
              onClick={() => selectedCategory!.providers.length > 1 ? setStep("provider") : setStep("category")}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← 返回
            </button>
          </div>
        )}

        {/* Step: 选择模型 */}
        {step === "model" && (
          <div className="space-y-4">
            <p className="text-sm font-medium text-gray-700">选择默认模型</p>
            {selectedProvider?.models.length ? (
              <div className="space-y-2">
                {selectedProvider.models.map((m) => (
                  <label key={m.key} className="flex items-center space-x-3 px-4 py-2 border rounded-md cursor-pointer hover:bg-blue-50">
                    <input
                      type="radio"
                      name="model"
                      value={m.key}
                      checked={selectedModel === m.key}
                      onChange={() => { setSelectedModel(m.key); setCustomModelId(""); }}
                      className="text-blue-600"
                    />
                    <span className="text-sm">{m.model_id}</span>
                  </label>
                ))}
                <div className="pt-2 border-t">
                  <label className="block text-sm text-gray-500 mb-1">或手动输入模型名称</label>
                  <input
                    type="text"
                    value={customModelId}
                    onChange={(e) => { setCustomModelId(e.target.value); setSelectedModel(""); }}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    placeholder="模型名称..."
                  />
                </div>
              </div>
            ) : (
              <div>
                <input
                  type="text"
                  value={customModelId}
                  onChange={(e) => setCustomModelId(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  placeholder="输入模型名称..."
                />
              </div>
            )}
            <button
              onClick={handleSubmit}
              disabled={isLoading}
              className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400"
            >
              {isLoading ? "保存中..." : "完成配置"}
            </button>
            <button
              onClick={() => setStep("config")}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← 返回
            </button>
          </div>
        )}

        {/* Skip 按钮始终显示 */}
        <div className="text-center pt-2 border-t border-gray-200">
          <button
            onClick={handleSkip}
            className="text-sm text-gray-400 hover:text-gray-600"
          >
            跳过，稍后配置
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 修改 ProtectedRoute 添加 LLM 状态检测**

修改 `ProtectedRoute.tsx`，在认证通过后检测 LLM 配置状态：

```tsx
"use client";

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { authGet, API_BASE } from '@/lib/authFetch';

// 不做拦截的页面
const BYPASS_PATHS = ['/login', '/setup'];

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [llmChecked, setLlmChecked] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(true); // 默认 true 避免闪烁

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !BYPASS_PATHS.includes(pathname)) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  // 认证通过后检测 LLM 配置状态
  useEffect(() => {
    if (isAuthenticated && !BYPASS_PATHS.includes(pathname)) {
      authGet<{ configured: boolean }>(`${API_BASE}/api/config/llm-status`)
        .then((data) => {
          setLlmConfigured(data.configured);
          setLlmChecked(true);
          if (!data.configured) {
            router.push('/setup');
          }
        })
        .catch(() => {
          setLlmChecked(true); // 出错时不拦截
        });
    } else {
      setLlmChecked(true);
    }
  }, [isAuthenticated, pathname, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">验证中...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated && !BYPASS_PATHS.includes(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">跳转中...</p>
        </div>
      </div>
    );
  }

  if (!llmChecked && !BYPASS_PATHS.includes(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">检查配置...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
```

- [ ] **Step 3: Commit**

```bash
git add sensenova_claw/app/web/app/setup/page.tsx sensenova_claw/app/web/components/ProtectedRoute.tsx
git commit -m "feat: Web 端 LLM 配置引导页 + 路由拦截"
```

---

### Task 8: 集成验证

- [ ] **Step 1: 运行全部单元测试**

Run: `python3 -m pytest tests/unit/ -q`
Expected: All PASS，无新增失败

- [ ] **Step 2: 验证 SystemAdmin Agent 注册**

```python
# 快速验证脚本
python3 -c "
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from pathlib import Path
import tempfile, json

with tempfile.TemporaryDirectory() as td:
    reg = AgentRegistry(Path(td))
    reg.load_from_config({})
    sa = reg.get('system-admin')
    assert sa is not None, 'system-admin agent not found'
    assert sa.name == 'SystemAdmin'
    assert 'read_file' in sa.tools
    assert 'system-admin-skill' in sa.skills
    print('✅ SystemAdmin Agent 注册验证通过')
"
```

- [ ] **Step 3: 验证 LLM 状态检测**

```python
python3 -c "
from sensenova_claw.platform.config.llm_presets import check_llm_configured
ok, provs = check_llm_configured({'llm': {'providers': {'mock': {'api_key': ''}, 'openai': {'api_key': ''}}}})
assert not ok
ok2, provs2 = check_llm_configured({'llm': {'providers': {'openai': {'api_key': 'sk-test'}}}})
assert ok2
print('✅ LLM 状态检测验证通过')
"
```

- [ ] **Step 4: Commit 最终状态**

```bash
git add -A
git commit -m "feat: 安装后配置引导完整实现 — LLM 检测 + 终端提示 + CLI 引导 + Web 引导页 + SystemAdmin Agent"
```
