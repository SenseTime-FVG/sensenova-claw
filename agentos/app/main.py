#!/usr/bin/env python3
"""AgentOS 统一 CLI 入口

用法:
    agentos run [--port 8000] [--frontend-port 3000] [--no-frontend] [--dev]
    agentos cli [--host localhost] [--port 8000] [--agent default] [--session ID] [--debug] [-e MSG]
    agentos version
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from agentos.platform.config.config import Config, DEFAULT_CONFIG_PATH
from agentos.platform.secrets.migration import migrate_plaintext_secrets
from agentos.platform.secrets.store import KeyringSecretStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 前端目录解析：根据 project_root 定位
def _resolve_web_dir(project_root: Path) -> Path:
    web_dir = project_root / "agentos" / "app" / "web"
    if (web_dir / "node_modules").exists():
        return web_dir
    # 回退到 AGENTOS_HOME/app 下的前端（install.sh 安装场景）
    agentos_home = os.environ.get("AGENTOS_HOME", str(Path.home() / ".agentos"))
    installed_web = Path(agentos_home) / "app" / "agentos" / "app" / "web"
    if (installed_web / "node_modules").exists():
        return installed_web
    return web_dir


def _find_npm() -> str:
    """查找 npm 可执行文件路径"""
    import shutil
    npm = shutil.which("npm")
    if not npm:
        return ""
    return npm


def _spawn_managed_process(
    cmd: list[str],
    *,
    cwd: str,
    env: dict[str, str],
) -> subprocess.Popen:
    """启动受管进程，确保其位于独立进程组中。"""
    kwargs: dict[str, object] = {
        "cwd": cwd,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _terminate_managed_process(proc: subprocess.Popen, timeout: float = 5) -> None:
    """终止受管进程及其子进程。"""
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return

    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        return

    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=timeout)


# ── agentos run ──────────────────────────────────────

def _check_port(port: int) -> bool:
    """检查端口是否可用（尝试连接，连上说明被占用）"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return False  # 连上了，说明已被占用
        except (ConnectionRefusedError, OSError):
            return True  # 连不上，说明空闲


def cmd_run(args: argparse.Namespace) -> int:
    """启动后端服务 + 前端 dashboard"""
    backend_port = args.port
    frontend_port = args.frontend_port
    no_frontend = args.no_frontend
    dev_mode = args.dev

    # --dev 模式：使用当前工作目录的代码
    if dev_mode:
        project_root = Path.cwd().resolve()
        # 校验当前目录是否是 agentos 项目
        if not (project_root / "agentos" / "app" / "gateway" / "main.py").exists():
            print("错误: 当前目录不是 AgentOS 项目根目录", file=sys.stderr)
            return 1
        print(f"[dev] 使用本地代码: {project_root}")
    else:
        project_root = PROJECT_ROOT

    web_dir = _resolve_web_dir(project_root)

    # 端口检查
    if not _check_port(backend_port):
        print(f"错误: 端口 {backend_port} 已被占用", file=sys.stderr)
        return 1
    if not no_frontend and not _check_port(frontend_port):
        print(f"错误: 端口 {frontend_port} 已被占用", file=sys.stderr)
        return 1

    procs: list[subprocess.Popen] = []

    def cleanup(signum=None, frame=None):
        for p in procs:
            _terminate_managed_process(p, timeout=5)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 构建子进程环境变量
    env = os.environ.copy()
    if dev_mode:
        # 将本地项目根目录置于 PYTHONPATH 最前，确保子进程优先导入本地代码
        env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")

    # 启动后端
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "agentos.app.gateway.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", str(backend_port),
    ]
    print(f"启动后端服务: http://localhost:{backend_port}")
    backend_proc = _spawn_managed_process(backend_cmd, cwd=str(project_root), env=env)
    procs.append(backend_proc)

    # 等待后端启动
    time.sleep(2)
    if backend_proc.poll() is not None:
        print("错误: 后端启动失败", file=sys.stderr)
        return 1

    # 启动前端
    frontend_proc = None
    if not no_frontend:
        npm = _find_npm()
        if not npm:
            print("警告: 未找到 npm，跳过前端启动。安装 Node.js 后可使用前端 dashboard。", file=sys.stderr)
        elif not (web_dir / "node_modules").exists():
            print("警告: 前端依赖未安装，请先执行 'npm install'。跳过前端启动。", file=sys.stderr)
        else:
            print(f"启动前端 dashboard: http://localhost:{frontend_port}")
            frontend_env = env.copy()
            frontend_env["PORT"] = str(frontend_port)
            frontend_proc = _spawn_managed_process(
                [npm, "run", "dev"],
                cwd=str(web_dir),
                env=frontend_env,
            )
            procs.append(frontend_proc)

            time.sleep(2)
            if frontend_proc.poll() is not None:
                print("错误: 前端启动失败", file=sys.stderr)
                cleanup()
                return 1

    # 检测 LLM 配置状态
    try:
        from agentos.platform.config.config import Config, PROJECT_ROOT as _CFG_ROOT
        from agentos.platform.config.llm_presets import check_llm_configured
        _cfg = Config(project_root=_CFG_ROOT)
        _llm_ok, _ = check_llm_configured(_cfg.data, secret_store=getattr(_cfg, "_secret_store", None))
    except Exception:
        _llm_ok = True  # 检测失败时不误报警告

    # 读取后端生成的 token（通过环境变量传递，或从 stdout 解析）
    # 后端会在启动时打印 token URL，这里也提示用户
    print()
    print("=" * 50)
    print(f"  AgentOS 已启动" + (" (dev mode)" if dev_mode else ""))
    print(f"  后端 API:    http://localhost:{backend_port}")
    if dev_mode:
        print(f"  代码目录:    {project_root}")
    if frontend_proc:
        print(f"  Dashboard:   http://localhost:{frontend_port}")
    print(f"  CLI 连接:    agentos cli --port {backend_port}")
    print()
    print("  注意: 后端日志中包含带 token 的访问 URL")
    if not _llm_ok:
        print()
        print("  ⚠️  未检测到可用的 LLM API 配置，当前使用 Mock 模式")
        if frontend_proc:
            print(f"     → 访问 http://localhost:{frontend_port} 进行配置")
        print(f"     → 或使用 agentos cli --port {backend_port} 进行配置")
    print("=" * 50)
    print("按 Ctrl+C 停止所有服务\n")

    # 监控子进程
    try:
        while True:
            if backend_proc.poll() is not None:
                print("后端进程退出，正在停止所有服务。")
                cleanup()
                return 1
            if frontend_proc and frontend_proc.poll() is not None:
                print("前端进程退出，正在停止所有服务。")
                cleanup()
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
    return 0


# ── agentos cli ──────────────────────────────────────

def cmd_cli(args: argparse.Namespace) -> int:
    """启动 CLI 客户端"""
    from agentos.app.cli.app import CLIApp

    app = CLIApp(
        host=args.host,
        port=args.port,
        agent_id=args.agent,
        session_id=args.session,
        debug=args.debug,
        execute=args.execute,
    )
    return asyncio.run(app.run())


# ── agentos version ─────────────────────────────────

def cmd_version(args: argparse.Namespace) -> int:
    print("AgentOS v0.5.0")
    return 0


def cmd_migrate_secrets(args: argparse.Namespace) -> int:
    """迁移当前 config.yml 中的明文敏感字段到 keyring。"""
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else _default_config_path()
    cfg = Config(config_path=config_path, secret_store=KeyringSecretStore())
    report = migrate_plaintext_secrets(cfg, secret_store=cfg._secret_store)
    print(f"migrated={report['migrated']}")
    for path in report["migrated_paths"]:
        print(path)
    return 0


def _default_config_path() -> Path:
    local = Path.cwd() / "config.yml"
    if local.exists():
        return local
    return DEFAULT_CONFIG_PATH


# ── 主入口 ───────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agentos",
        description="AgentOS - 基于事件驱动架构的 AI Agent 平台",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # agentos run
    run_parser = subparsers.add_parser("run", help="启动后端服务和前端 dashboard")
    run_parser.add_argument("--port", type=int, default=8000, help="后端端口 (默认 8000)")
    run_parser.add_argument("--frontend-port", type=int, default=3000, help="前端端口 (默认 3000)")
    run_parser.add_argument("--no-frontend", action="store_true", help="仅启动后端，不启动前端")
    run_parser.add_argument("--dev", action="store_true", help="开发模式：使用当前目录的代码而非安装目录")

    # agentos cli
    cli_parser = subparsers.add_parser("cli", help="启动 CLI 交互客户端")
    cli_parser.add_argument("--host", default="localhost", help="后端地址 (默认 localhost)")
    cli_parser.add_argument("--port", type=int, default=8000, help="后端端口 (默认 8000)")
    cli_parser.add_argument("--agent", default=None, help="Agent ID")
    cli_parser.add_argument("--session", default=None, help="恢复指定 session")
    cli_parser.add_argument("--debug", action="store_true", help="调试模式")
    cli_parser.add_argument("-e", "--execute", default=None, help="执行单条消息后退出")

    # agentos version
    subparsers.add_parser("version", help="显示版本号")
    migrate_parser = subparsers.add_parser("migrate-secrets", help="迁移 config.yml 中的明文 secret 到 keyring")
    migrate_parser.add_argument("--config", default=None, help="指定 config.yml 路径")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "cli":
        return cmd_cli(args)
    elif args.command == "version":
        return cmd_version(args)
    elif args.command == "migrate-secrets":
        return cmd_migrate_secrets(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
