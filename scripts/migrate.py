#!/usr/bin/env python3
"""代码重组迁移脚本：backend/app/ → agentos/ 新目录结构"""

import shutil
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ============================================================
# 1. 文件/目录映射：(源路径, 目标路径)  相对于 ROOT
# ============================================================
FILE_MOVES: list[tuple[str, str]] = [
    # --- kernel/events ---
    ("backend/app/events/bus.py",       "agentos/kernel/events/bus.py"),
    ("backend/app/events/envelope.py",  "agentos/kernel/events/envelope.py"),
    ("backend/app/events/persister.py", "agentos/kernel/events/persister.py"),
    ("backend/app/events/router.py",    "agentos/kernel/events/router.py"),
    ("backend/app/events/types.py",     "agentos/kernel/events/types.py"),

    # --- kernel/runtime ---
    ("backend/app/runtime/agent_runtime.py",       "agentos/kernel/runtime/agent_runtime.py"),
    ("backend/app/runtime/llm_runtime.py",         "agentos/kernel/runtime/llm_runtime.py"),
    ("backend/app/runtime/tool_runtime.py",        "agentos/kernel/runtime/tool_runtime.py"),
    ("backend/app/runtime/title_runtime.py",       "agentos/kernel/runtime/title_runtime.py"),
    ("backend/app/runtime/context_builder.py",     "agentos/kernel/runtime/context_builder.py"),
    ("backend/app/runtime/prompt_builder.py",      "agentos/kernel/runtime/prompt_builder.py"),
    ("backend/app/runtime/publisher.py",           "agentos/kernel/runtime/publisher.py"),
    ("backend/app/runtime/session_maintenance.py", "agentos/kernel/runtime/session_maintenance.py"),
    ("backend/app/runtime/state.py",               "agentos/kernel/runtime/state.py"),
    ("backend/app/runtime/ws_forwarder.py",        "agentos/kernel/runtime/ws_forwarder.py"),

    # --- kernel/runtime/workers ---
    ("backend/app/runtime/workers/base.py",         "agentos/kernel/runtime/workers/base.py"),
    ("backend/app/runtime/workers/agent_worker.py",  "agentos/kernel/runtime/workers/agent_worker.py"),
    ("backend/app/runtime/workers/llm_worker.py",    "agentos/kernel/runtime/workers/llm_worker.py"),
    ("backend/app/runtime/workers/tool_worker.py",   "agentos/kernel/runtime/workers/tool_worker.py"),

    # --- kernel/scheduler (原 cron) ---
    ("backend/app/cron/models.py",    "agentos/kernel/scheduler/models.py"),
    ("backend/app/cron/runtime.py",   "agentos/kernel/scheduler/runtime.py"),
    ("backend/app/cron/scheduler.py", "agentos/kernel/scheduler/scheduler.py"),
    ("backend/app/cron/tool.py",      "agentos/kernel/scheduler/tool.py"),

    # --- kernel/heartbeat ---
    ("backend/app/heartbeat/protocol.py", "agentos/kernel/heartbeat/protocol.py"),
    ("backend/app/heartbeat/runtime.py",  "agentos/kernel/heartbeat/runtime.py"),

    # --- capabilities/agents ---
    ("backend/app/agents/config.py",   "agentos/capabilities/agents/config.py"),
    ("backend/app/agents/registry.py", "agentos/capabilities/agents/registry.py"),

    # --- capabilities/tools ---
    ("backend/app/tools/base.py",           "agentos/capabilities/tools/base.py"),
    ("backend/app/tools/builtin.py",        "agentos/capabilities/tools/builtin.py"),
    ("backend/app/tools/registry.py",       "agentos/capabilities/tools/registry.py"),
    ("backend/app/tools/delegate_tool.py",  "agentos/capabilities/tools/delegate_tool.py"),
    ("backend/app/tools/workflow_tool.py",  "agentos/capabilities/tools/workflow_tool.py"),
    ("backend/app/tools/feishu_api_tool.py","agentos/capabilities/tools/feishu_api_tool.py"),
    ("backend/app/tools/message_tool.py",   "agentos/capabilities/tools/message_tool.py"),
    ("backend/app/tools/orchestration.py",  "agentos/capabilities/tools/orchestration.py"),

    # --- capabilities/workflows ---
    ("backend/app/workflows/models.py",   "agentos/capabilities/workflows/models.py"),
    ("backend/app/workflows/registry.py", "agentos/capabilities/workflows/registry.py"),
    ("backend/app/workflows/runtime.py",  "agentos/capabilities/workflows/runtime.py"),

    # --- capabilities/memory ---
    ("backend/app/memory/config.py",    "agentos/capabilities/memory/config.py"),
    ("backend/app/memory/embedding.py", "agentos/capabilities/memory/embedding.py"),
    ("backend/app/memory/index.py",     "agentos/capabilities/memory/index.py"),
    ("backend/app/memory/manager.py",   "agentos/capabilities/memory/manager.py"),
    ("backend/app/memory/chunker.py",   "agentos/capabilities/memory/chunker.py"),
    ("backend/app/memory/tools.py",     "agentos/capabilities/memory/tools.py"),

    # --- capabilities/skills (代码部分) ---
    ("backend/app/skills/registry.py",       "agentos/capabilities/skills/registry.py"),
    ("backend/app/skills/models.py",         "agentos/capabilities/skills/models.py"),
    ("backend/app/skills/market_service.py", "agentos/capabilities/skills/market_service.py"),
    ("backend/app/skills/arg_substitutor.py","agentos/capabilities/skills/arg_substitutor.py"),

    # --- adapters/llm ---
    ("backend/app/llm/base.py",                      "agentos/adapters/llm/base.py"),
    ("backend/app/llm/factory.py",                    "agentos/adapters/llm/factory.py"),
    ("backend/app/llm/providers/openai_provider.py",  "agentos/adapters/llm/providers/openai_provider.py"),
    ("backend/app/llm/providers/anthropic_provider.py","agentos/adapters/llm/providers/anthropic_provider.py"),
    ("backend/app/llm/providers/gemini_provider.py",  "agentos/adapters/llm/providers/gemini_provider.py"),
    ("backend/app/llm/providers/mock_provider.py",    "agentos/adapters/llm/providers/mock_provider.py"),

    # --- adapters/channels ---
    ("backend/app/gateway/base.py",                        "agentos/adapters/channels/base.py"),
    ("backend/app/gateway/channels/websocket_channel.py",  "agentos/adapters/channels/websocket_channel.py"),

    # --- adapters/channels/feishu (原 plugins/feishu) ---
    # 整个目录复制，见 DIR_COPIES

    # --- adapters/storage ---
    ("backend/app/db/repository.py", "agentos/adapters/storage/repository.py"),

    # --- adapters/skill_sources (原 skills/adapters) ---
    ("backend/app/skills/adapters/base.py",              "agentos/adapters/skill_sources/base.py"),
    ("backend/app/skills/adapters/clawhub.py",           "agentos/adapters/skill_sources/clawhub.py"),
    ("backend/app/skills/adapters/anthropic_market.py",  "agentos/adapters/skill_sources/anthropic_market.py"),
    ("backend/app/skills/adapters/git_adapter.py",       "agentos/adapters/skill_sources/git_adapter.py"),

    # --- adapters/plugins (插件框架) ---
    ("backend/app/plugins/base.py", "agentos/adapters/plugins/base.py"),

    # --- interfaces/http (原 api) ---
    ("backend/app/api/agents.py",     "agentos/interfaces/http/agents.py"),
    ("backend/app/api/config_api.py", "agentos/interfaces/http/config_api.py"),
    ("backend/app/api/gateway.py",    "agentos/interfaces/http/gateway.py"),
    ("backend/app/api/skills.py",     "agentos/interfaces/http/skills.py"),
    ("backend/app/api/tools.py",      "agentos/interfaces/http/tools.py"),
    ("backend/app/api/workflows.py",  "agentos/interfaces/http/workflows.py"),
    ("backend/app/api/workspace.py",  "agentos/interfaces/http/workspace.py"),

    # --- interfaces/ws ---
    ("backend/app/gateway/gateway.py", "agentos/interfaces/ws/gateway.py"),

    # --- platform/config ---
    ("backend/app/core/config.py",       "agentos/platform/config/config.py"),
    ("backend/app/workspace/manager.py", "agentos/platform/config/workspace.py"),

    # --- platform/logging ---
    ("backend/app/core/logging.py", "agentos/platform/logging/setup.py"),

    # --- platform/security ---
    ("backend/app/security/path_policy.py", "agentos/platform/security/path_policy.py"),
    ("backend/app/security/deny_list.py",   "agentos/platform/security/deny_list.py"),

    # --- app/gateway (入口) ---
    ("backend/app/main.py", "agentos/app/gateway/main.py"),

    # --- app/cli ---
    ("backend/cli/app.py",      "agentos/app/cli/app.py"),
    ("backend/cli/commands.py",  "agentos/app/cli/commands.py"),
    ("backend/cli/display.py",   "agentos/app/cli/display.py"),
    ("backend/cli_client.py",    "agentos/app/cli/cli_client.py"),
]

# 目录级复制
DIR_COPIES: list[tuple[str, str]] = [
    # feishu 插件 → channels/feishu
    ("backend/app/plugins/feishu", "agentos/adapters/channels/feishu"),

    # workflow 模板 → workspace/workflows
    ("backend/app/workflows/templates", "workspace/workflows"),
]

# Skill 实例目录（YAML/Markdown 定义）→ workspace/skills/
SKILL_INSTANCE_DIRS = [
    "algorithmic-art", "brand-guidelines", "canvas-design", "doc-coauthoring",
    "docx", "feishu", "frontend-design", "internal-comms", "mcp-builder",
    "pdf", "pptx", "skill-creator", "slack-gif-creator", "theme-factory",
    "webapp-testing", "web-artifacts-builder", "xlsx",
]

# ============================================================
# 2. Import 映射：(旧前缀, 新前缀)  按具体度从高到低排列
# ============================================================
IMPORT_MAPPINGS: list[tuple[str, str]] = [
    # kernel
    ("app.events",                "agentos.kernel.events"),
    ("app.runtime.workers",       "agentos.kernel.runtime.workers"),
    ("app.runtime",               "agentos.kernel.runtime"),
    ("app.cron",                  "agentos.kernel.scheduler"),
    ("app.heartbeat",             "agentos.kernel.heartbeat"),

    # capabilities
    ("app.agents",                "agentos.capabilities.agents"),
    ("app.tools",                 "agentos.capabilities.tools"),
    ("app.workflows",             "agentos.capabilities.workflows"),
    ("app.memory",                "agentos.capabilities.memory"),
    ("app.skills.adapters",       "agentos.adapters.skill_sources"),
    ("app.skills",                "agentos.capabilities.skills"),

    # adapters
    ("app.llm",                   "agentos.adapters.llm"),
    ("app.gateway.channels",      "agentos.adapters.channels"),
    ("app.gateway.base",          "agentos.adapters.channels.base"),
    ("app.gateway.gateway",       "agentos.interfaces.ws.gateway"),
    ("app.gateway",               "agentos.interfaces.ws"),
    ("app.plugins.feishu",        "agentos.adapters.channels.feishu"),
    ("app.plugins.base",          "agentos.adapters.plugins.base"),
    ("app.plugins",               "agentos.adapters.plugins"),
    ("app.db",                    "agentos.adapters.storage"),

    # interfaces
    ("app.api",                   "agentos.interfaces.http"),

    # platform
    ("app.core.config",           "agentos.platform.config.config"),
    ("app.core.logging",          "agentos.platform.logging.setup"),
    ("app.core",                  "agentos.platform.config"),
    ("app.security",              "agentos.platform.security"),
    ("app.workspace.manager",     "agentos.platform.config.workspace"),
    ("app.workspace",             "agentos.platform.config"),

    # app entry
    ("app.main",                  "agentos.app.gateway.main"),

    # CLI
    ("cli.app",                   "agentos.app.cli.app"),
    ("cli.commands",              "agentos.app.cli.commands"),
    ("cli.display",               "agentos.app.cli.display"),
    ("cli.",                      "agentos.app.cli."),
]

# ============================================================
# 3. 需要创建的 __init__.py
# ============================================================
INIT_DIRS = [
    "agentos",
    "agentos/kernel",
    "agentos/kernel/events",
    "agentos/kernel/runtime",
    "agentos/kernel/runtime/workers",
    "agentos/kernel/scheduler",
    "agentos/kernel/heartbeat",
    "agentos/capabilities",
    "agentos/capabilities/agents",
    "agentos/capabilities/tools",
    "agentos/capabilities/workflows",
    "agentos/capabilities/memory",
    "agentos/capabilities/skills",
    "agentos/adapters",
    "agentos/adapters/llm",
    "agentos/adapters/llm/providers",
    "agentos/adapters/channels",
    "agentos/adapters/channels/feishu",
    "agentos/adapters/storage",
    "agentos/adapters/skill_sources",
    "agentos/adapters/plugins",
    "agentos/interfaces",
    "agentos/interfaces/http",
    "agentos/interfaces/ws",
    "agentos/interfaces/dto",
    "agentos/platform",
    "agentos/platform/config",
    "agentos/platform/logging",
    "agentos/platform/security",
    "agentos/app",
    "agentos/app/gateway",
    "agentos/app/cli",
    "agentos/app/web",
]


def create_directories():
    """创建所有目标目录"""
    print("=== 创建目录结构 ===")
    for d in INIT_DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # workspace 目录
    for d in ["workspace/agents", "workspace/skills", "workspace/workflows", "workspace/memory"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # var 目录
    for d in ["var/data", "var/logs", "var/cache", "var/sessions", "var/tmp"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # tests 目录
    for d in ["tests/unit", "tests/integration", "tests/e2e", "tests/fixtures", "tests/helpers"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # scripts 子目录
    for d in ["scripts/dev", "scripts/test", "scripts/release"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # docs 子目录
    for d in ["docs/architecture", "docs/api"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    print("  目录结构创建完成")


def copy_files():
    """复制文件到新位置"""
    print("\n=== 复制文件 ===")
    for src_rel, dst_rel in FILE_MOVES:
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            print(f"  [跳过] {src_rel} (不存在)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  {src_rel} → {dst_rel}")

    # 目录级复制
    for src_rel, dst_rel in DIR_COPIES:
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            print(f"  [跳过目录] {src_rel} (不存在)")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"  [目录] {src_rel} → {dst_rel}")

    # Skill 实例移入 workspace/skills/
    print("\n=== 复制 Skill 实例到 workspace/skills/ ===")
    for skill_name in SKILL_INSTANCE_DIRS:
        src = ROOT / "backend" / "app" / "skills" / skill_name
        dst = ROOT / "workspace" / "skills" / skill_name
        if not src.exists():
            print(f"  [跳过] {skill_name} (不存在)")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"  skills/{skill_name} → workspace/skills/{skill_name}")

    print("  文件复制完成")


def create_init_files():
    """创建 __init__.py 文件"""
    print("\n=== 创建 __init__.py 文件 ===")
    for d in INIT_DIRS:
        init_file = ROOT / d / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

    # tests 目录也需要
    for d in ["tests", "tests/unit", "tests/integration", "tests/e2e", "tests/fixtures", "tests/helpers"]:
        init_file = ROOT / d / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

    print("  __init__.py 文件创建完成")


def update_imports_in_file(filepath: Path):
    """更新单个文件中的 import 语句"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False

    original = content

    for old_prefix, new_prefix in IMPORT_MAPPINGS:
        # 匹配 from xxx import ... 和 import xxx
        # Pattern 1: from app.xxx.yyy import ...
        content = re.sub(
            rf'\bfrom\s+{re.escape(old_prefix)}(\S*)\s+import\b',
            f'from {new_prefix}\\1 import',
            content
        )
        # Pattern 2: import app.xxx.yyy
        content = re.sub(
            rf'\bimport\s+{re.escape(old_prefix)}(\S*)\b',
            f'import {new_prefix}\\1',
            content
        )

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        return True
    return False


def update_all_imports():
    """更新所有 Python 文件中的 import"""
    print("\n=== 更新 import 语句 ===")
    count = 0

    # 更新 agentos/ 下所有 Python 文件
    for py_file in (ROOT / "agentos").rglob("*.py"):
        if update_imports_in_file(py_file):
            print(f"  更新: {py_file.relative_to(ROOT)}")
            count += 1

    # 更新 tests/ 下所有 Python 文件
    for py_file in (ROOT / "tests").rglob("*.py"):
        if update_imports_in_file(py_file):
            print(f"  更新: {py_file.relative_to(ROOT)}")
            count += 1

    # 更新 test/ 下所有 Python 文件（旧测试目录，以防）
    test_dir = ROOT / "test"
    if test_dir.exists():
        for py_file in test_dir.rglob("*.py"):
            if update_imports_in_file(py_file):
                print(f"  更新: {py_file.relative_to(ROOT)}")
                count += 1

    print(f"  共更新 {count} 个文件")


def copy_tests():
    """复制测试文件到新位置"""
    print("\n=== 复制测试文件 ===")

    # backend/tests/ 下的测试文件
    backend_tests = ROOT / "backend" / "tests"
    if backend_tests.exists():
        # e2e 测试
        e2e_src = backend_tests / "e2e"
        if e2e_src.exists():
            for f in e2e_src.iterdir():
                if f.is_file() and f.suffix == ".py":
                    dst = ROOT / "tests" / "e2e" / f.name
                    shutil.copy2(f, dst)
                    print(f"  tests/e2e/{f.name}")

        # 单元测试
        for f in backend_tests.iterdir():
            if f.is_file() and f.suffix == ".py" and f.name.startswith("test_"):
                dst = ROOT / "tests" / "unit" / f.name
                shutil.copy2(f, dst)
                print(f"  tests/unit/{f.name}")

    # test/ 目录下的测试（根目录旧结构）
    old_test = ROOT / "test"
    if old_test.exists():
        for f in old_test.iterdir():
            if f.is_file() and f.suffix == ".py" and f.name.startswith("test_"):
                dst = ROOT / "tests" / "unit" / f.name
                if not dst.exists():
                    shutil.copy2(f, dst)
                    print(f"  tests/unit/{f.name} (from test/)")
        # conftest.py
        conftest = old_test / "conftest.py"
        if conftest.exists():
            shutil.copy2(conftest, ROOT / "tests" / "conftest.py")
            print(f"  tests/conftest.py")
        # e2e 子目录
        old_e2e = old_test / "e2e"
        if old_e2e.exists():
            for f in old_e2e.iterdir():
                if f.is_file() and f.suffix == ".py":
                    dst = ROOT / "tests" / "e2e" / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
                        print(f"  tests/e2e/{f.name} (from test/e2e/)")
        # unit 子目录
        old_unit = old_test / "unit"
        if old_unit.exists():
            for f in old_unit.iterdir():
                if f.is_file() and f.suffix == ".py":
                    dst = ROOT / "tests" / "unit" / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
                        print(f"  tests/unit/{f.name} (from test/unit/)")

    print("  测试文件复制完成")


def copy_frontend():
    """复制前端到 agentos/app/web/"""
    print("\n=== 复制前端代码 ===")
    src = ROOT / "frontend"
    dst = ROOT / "agentos" / "app" / "web"
    if not src.exists():
        print("  [跳过] frontend/ 不存在")
        return

    # 复制前端文件，排除 node_modules 和 .next
    for item in src.iterdir():
        if item.name in ("node_modules", ".next", ".cache"):
            continue
        dst_item = dst / item.name
        if item.is_dir():
            if dst_item.exists():
                shutil.rmtree(dst_item)
            shutil.copytree(item, dst_item, ignore=shutil.ignore_patterns(
                "node_modules", ".next", ".cache", "__pycache__"
            ))
        else:
            shutil.copy2(item, dst_item)
    print("  前端代码复制到 agentos/app/web/")


def update_conftest():
    """更新 tests/conftest.py"""
    print("\n=== 更新 conftest.py ===")
    conftest = ROOT / "tests" / "conftest.py"
    if not conftest.exists():
        print("  [跳过] tests/conftest.py 不存在")
        return

    content = conftest.read_text(encoding="utf-8")

    # 更新 sys.path 插入
    content = content.replace(
        'sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))',
        'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))'
    )

    # 更新 builtin_skills_dir 路径
    content = content.replace(
        'Path(__file__).resolve().parent.parent / "backend" / "app" / "skills"',
        'Path(__file__).resolve().parent.parent / "workspace" / "skills"'
    )

    # 更新 import 路径
    for old_prefix, new_prefix in IMPORT_MAPPINGS:
        content = re.sub(
            rf'\bfrom\s+{re.escape(old_prefix)}(\S*)\s+import\b',
            f'from {new_prefix}\\1 import',
            content
        )
        content = re.sub(
            rf'\bimport\s+{re.escape(old_prefix)}(\S*)\b',
            f'import {new_prefix}\\1',
            content
        )

    conftest.write_text(content, encoding="utf-8")
    print("  conftest.py 更新完成")


def create_pyproject_toml():
    """在根目录创建新的 pyproject.toml"""
    print("\n=== 创建根目录 pyproject.toml ===")
    content = '''[project]
name = "agentos"
version = "0.5.0"
description = "AgentOS - 基于事件驱动架构的 AI Agent 平台"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "pydantic>=2.9.0",
  "pyyaml>=6.0.2",
  "aiosqlite>=0.20.0",
  "httpx>=0.27.0",
  "openai>=1.55.0",
  "anthropic>=0.40.0",
  "textual>=0.47.0",
  "lark-oapi>=1.5.3",
  "croniter>=2.0.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.24.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"
'''
    (ROOT / "pyproject.toml").write_text(content, encoding="utf-8")
    print("  pyproject.toml 创建完成")


def update_package_json():
    """更新根目录 package.json"""
    print("\n=== 更新 package.json ===")
    content = '''{
  "name": "agentos",
  "private": true,
  "version": "0.5.0",
  "scripts": {
    "dev": "bash ./scripts/dev.sh",
    "dev:backend": "python3 -m uvicorn agentos.app.gateway.main:app --reload --host 0.0.0.0 --port 8000",
    "dev:frontend": "cd agentos/app/web && npm run dev",
    "test:backend": "python3 -m pytest tests/ -q",
    "test:backend:unit": "python3 -m pytest tests/unit/ -q",
    "test:backend:e2e": "python3 -m pytest tests/e2e/ -q",
    "test:frontend:e2e": "cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.58.2"
  }
}
'''
    (ROOT / "package.json").write_text(content, encoding="utf-8")
    print("  package.json 更新完成")


def update_dev_script():
    """更新 scripts/dev.sh"""
    print("\n=== 更新 scripts/dev.sh ===")
    content = '''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

check_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "端口 $port 已被占用，请先释放后再启动。"
      return 1
    fi
  elif command -v ss >/dev/null 2>&1; then
    if ss -ltn | awk '{print $4}' | grep -q ":$port$"; then
      echo "端口 $port 已被占用，请先释放后再启动。"
      return 1
    fi
  fi
  return 0
}

start_backend() {
  cd "$ROOT_DIR"
  if command -v uv >/dev/null 2>&1; then
    uv run uvicorn agentos.app.gateway.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
  else
    python3 -m uvicorn agentos.app.gateway.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
  fi
  BACKEND_PID=$!
  sleep 2
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "后端启动失败"
    return 1
  fi
}

start_frontend() {
  cd "$ROOT_DIR/agentos/app/web"
  npm run dev &
  FRONTEND_PID=$!
  sleep 2
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "前端启动失败"
    return 1
  fi
}

cleanup() {
  set +e
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

main() {
  check_port "$BACKEND_PORT"
  check_port "$FRONTEND_PORT"

  trap cleanup EXIT INT TERM

  start_backend || exit 1
  start_frontend || exit 1

  echo "前后端已启动"
  echo "后端: http://localhost:${BACKEND_PORT}"
  echo "前端: http://localhost:${FRONTEND_PORT}"

  while true; do
    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      echo "后端进程退出，正在停止前端。"
      exit 1
    fi
    if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
      echo "前端进程退出，正在停止后端。"
      exit 1
    fi
    sleep 1
  done
}

main
'''
    dev_sh = ROOT / "scripts" / "dev.sh"
    dev_sh.write_text(content, encoding="utf-8")
    dev_sh.chmod(0o755)
    print("  scripts/dev.sh 更新完成")


def create_cli_entry():
    """创建根目录 CLI 入口脚本"""
    print("\n=== 创建 CLI 入口 ===")
    content = '''#!/usr/bin/env python3
"""AgentOS CLI 入口"""
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentos.app.cli.cli_client import main

if __name__ == "__main__":
    main()
'''
    cli_entry = ROOT / "cli.py"
    cli_entry.write_text(content, encoding="utf-8")
    print("  cli.py 创建完成")


def create_var_gitignore():
    """为 var/ 创建 .gitignore"""
    print("\n=== 创建 var/.gitignore ===")
    content = "# 运行时数据，不入库\n*\n!.gitignore\n"
    (ROOT / "var" / ".gitignore").write_text(content, encoding="utf-8")
    print("  var/.gitignore 创建完成")


def main():
    print(f"项目根目录: {ROOT}\n")

    create_directories()
    copy_files()
    copy_tests()
    copy_frontend()
    create_init_files()
    update_all_imports()
    update_conftest()
    create_pyproject_toml()
    update_package_json()
    update_dev_script()
    create_cli_entry()
    create_var_gitignore()

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)
    print("\n后续步骤:")
    print("  1. 运行测试: python3 -m pytest tests/ -q")
    print("  2. 验证通过后删除旧目录: backend/, frontend/, test/")
    print("  3. 更新 .gitignore")


if __name__ == "__main__":
    main()
