#!/usr/bin/env python3
"""Sensenova-Claw 统一 CLI 入口

用法:
    sensenova-claw run [--port 8000] [--frontend-port 3000] [--no-frontend] [--dev]
    sensenova-claw cli [--host localhost] [--port 8000] [--agent default] [--session ID] [--debug] [-e MSG]
    sensenova-claw version
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from sensenova_claw.platform.config.config import Config, get_default_config_path
from sensenova_claw.platform.config.workspace import default_sensenova_claw_home
from sensenova_claw.platform.secrets.migration import migrate_plaintext_secrets
from sensenova_claw.platform.secrets.store import build_default_secret_store

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 前端目录解析：根据 project_root 定位
def _resolve_web_dir(project_root: Path) -> Path:
    web_dir = project_root / "sensenova_claw" / "app" / "web"
    if (web_dir / "node_modules").exists():
        return web_dir
    # 回退到 SENSENOVA_CLAW_HOME/app 下的前端（install.sh 安装场景）
    installed_web = default_sensenova_claw_home() / "app" / "sensenova_claw" / "app" / "web"
    if (installed_web / "node_modules").exists():
        return installed_web
    return web_dir


def _find_npm() -> str:
    """查找 npm 可执行文件路径"""
    npm = shutil.which("npm")
    if not npm:
        return ""
    return npm

def _find_node() -> str:
    """查找 node 可执行文件路径。"""
    import shutil

    node = shutil.which("node")
    if not node:
        return ""
    return node


def _build_frontend_dev_cmd(web_dir: Path, frontend_port: int) -> list[str]:
    """优先直接启动 next dev，避免 Windows 下 npm 包装进程过早退出。"""
    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    node = _find_node()
    if node and next_cli.exists():
        return [node, str(next_cli), "dev", "-p", str(frontend_port)]

    npm = _find_npm()
    if npm:
        return [npm, "run", "dev", "--", "-p", str(frontend_port)]
    return []


def _build_frontend_prod_cmd(web_dir: Path, frontend_port: int) -> list[str]:
    """生产模式：使用 next start 启动预构建的前端。"""
    # 仅在存在有效生产构建标记时才允许 next start，避免把 dev/.next 缓存误判成可启动产物。
    build_id = web_dir / ".next" / "BUILD_ID"
    if not build_id.exists():
        return []
    if not build_id.read_text(encoding="utf-8").strip():
        return []

    next_cli = web_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    node = _find_node()
    if node and next_cli.exists():
        return [node, str(next_cli), "start", "-p", str(frontend_port)]

    npm = _find_npm()
    if npm:
        return [npm, "run", "start", "--", "-p", str(frontend_port)]
    return []


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
            ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
            if ctrl_break is not None:
                with contextlib.suppress(OSError, ValueError):
                    proc.send_signal(ctrl_break)
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
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        return

    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=timeout)


# ── sensenova_claw run ──────────────────────────────────────

def _check_port(port: int) -> bool:
    """检查端口是否可用（尝试连接，连上说明被占用）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return False  # 连上了，说明已被占用
        except (ConnectionRefusedError, OSError):
            return True  # 连不上，说明空闲


def _wait_for_port_listen(port: int, *, timeout: float, proc: subprocess.Popen | None = None) -> bool:
    """等待端口开始监听；若进程提前退出则立即失败。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _check_port(port):
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.2)
    return False


def cmd_run(args: argparse.Namespace) -> int:
    """启动后端服务 + 前端 dashboard"""
    backend_port = args.port
    frontend_port = args.frontend_port
    no_frontend = args.no_frontend
    dev_mode = args.dev

    # --dev 模式：使用当前工作目录的代码
    if dev_mode:
        project_root = Path.cwd().resolve()
        # 校验当前目录是否是 sensenova_claw 项目
        if not (project_root / "sensenova_claw" / "app" / "gateway" / "main.py").exists():
            print("错误: 当前目录不是 Sensenova-Claw 项目根目录", file=sys.stderr)
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
    shutdown_requested = False

    def cleanup():
        for p in procs:
            _terminate_managed_process(p, timeout=5)

    def handle_signal(signum=None, frame=None):
        nonlocal shutdown_requested
        shutdown_requested = True
        cleanup()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 构建子进程环境变量
    env = os.environ.copy()
    if dev_mode:
        # 将本地项目根目录置于 PYTHONPATH 最前，确保子进程优先导入本地代码
        env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")

    # 启动后端：仅在前端存在有效生产构建时才视为生产模式。
    is_production = bool(_build_frontend_prod_cmd(web_dir, frontend_port))
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "sensenova_claw.app.gateway.main:app",
        "--host", "0.0.0.0",
        "--port", str(backend_port),
    ]
    if not is_production:
        backend_cmd.insert(4, "--reload")
    print(f"启动后端服务: http://localhost:{backend_port}")
    backend_proc = _spawn_managed_process(backend_cmd, cwd=str(project_root), env=env)
    procs.append(backend_proc)

    # 等待后端启动，避免仅依赖包装进程 pid
    if not _wait_for_port_listen(backend_port, timeout=15, proc=backend_proc):
        print("错误: 后端启动失败", file=sys.stderr)
        cleanup()
        return 1

    # 启动前端：检测到 .next/ 目录（已 build）自动用 next start，否则回退 next dev
    frontend_proc = None
    if not no_frontend:
        frontend_cmd = _build_frontend_prod_cmd(web_dir, frontend_port)
        if frontend_cmd:
            print("检测到前端预构建产物，使用 next start（生产模式）")
        else:
            print("未检测到前端预构建产物，使用 next dev（开发模式）")
            frontend_cmd = _build_frontend_dev_cmd(web_dir, frontend_port)
        if not frontend_cmd:
            print("警告: 未找到可用的 Node.js/npm，跳过前端启动。安装 Node.js 后可使用前端 dashboard。", file=sys.stderr)
        elif not (web_dir / "node_modules").exists():
            print("警告: 前端依赖未安装，请先执行 'npm install'。跳过前端启动。", file=sys.stderr)
        else:
            print(f"启动前端 dashboard: http://localhost:{frontend_port}")
            frontend_env = env.copy()
            frontend_env["PORT"] = str(frontend_port)
            frontend_proc = _spawn_managed_process(
                frontend_cmd,
                cwd=str(web_dir),
                env=frontend_env,
            )
            procs.append(frontend_proc)

            if not _wait_for_port_listen(frontend_port, timeout=20, proc=frontend_proc):
                print("错误: 前端启动失败", file=sys.stderr)
                cleanup()
                return 1

    # 检测 LLM 配置状态
    try:
        from sensenova_claw.platform.config.config import Config, PROJECT_ROOT as _CFG_ROOT
        from sensenova_claw.platform.config.llm_presets import check_llm_configured
        _cfg = Config(project_root=_CFG_ROOT)
        _llm_ok, _ = check_llm_configured(_cfg.data, secret_store=getattr(_cfg, "_secret_store", None))
    except Exception:
        _llm_ok = True  # 检测失败时不误报警告

    # 读取后端生成的 token（通过环境变量传递，或从 stdout 解析）
    # 后端会在启动时打印 token URL，这里也提示用户
    print()
    print("=" * 50)
    mode_label = " (dev mode)" if dev_mode else " (production)" if is_production else ""
    print(f"  Sensenova-Claw 已启动{mode_label}")
    print(f"  后端 API:    http://localhost:{backend_port}")
    if dev_mode:
        print(f"  代码目录:    {project_root}")
    if frontend_proc:
        print(f"  Dashboard:   http://localhost:{frontend_port}")
    print(f"  CLI 连接:    sensenova-claw cli --port {backend_port}")
    print()
    print("  注意: 后端日志中包含带 token 的访问 URL")
    if not _llm_ok:
        print()
        print("  ⚠️  未检测到可用的 LLM API 配置，当前使用 Mock 模式")
        if frontend_proc:
            print(f"     → 访问 http://localhost:{frontend_port} 进行配置")
        print(f"     → 或使用 sensenova-claw cli --port {backend_port} 进行配置")
    print("=" * 50)
    print("按 Ctrl+C 停止所有服务\n")

    # 监控子进程
    try:
        while True:
            if shutdown_requested:
                return 0
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
        shutdown_requested = True
    finally:
        cleanup()
    return 0 if shutdown_requested else 1


# ── sensenova_claw cli ──────────────────────────────────────

def cmd_cli(args: argparse.Namespace) -> int:
    """启动 CLI 客户端"""
    from sensenova_claw.app.cli.app import CLIApp

    app = CLIApp(
        host=args.host,
        port=args.port,
        agent_id=args.agent,
        session_id=args.session,
        debug=args.debug,
        execute=args.execute,
    )
    return asyncio.run(app.run())


# ── sensenova_claw version ─────────────────────────────────

def cmd_version(args: argparse.Namespace) -> int:
    print("Sensenova-Claw v0.5.0")
    return 0


def cmd_migrate_secrets(args: argparse.Namespace) -> int:
    """迁移当前 config.yml 中的明文敏感字段到 keyring。"""
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else _default_config_path()
    cfg = Config(config_path=config_path, secret_store=build_default_secret_store())
    report = migrate_plaintext_secrets(cfg, secret_store=cfg._secret_store)
    print(f"migrated={report['migrated']}")
    for path in report["migrated_paths"]:
        print(path)
    return 0


def _default_config_path() -> Path:
    local = Path.cwd() / "config.yml"
    if local.exists():
        return local
    return get_default_config_path()


# ── 主入口 ───────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sensenova-claw",
        description="Sensenova-Claw - 基于事件驱动架构的 AI Agent 平台",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # sensenova_claw run
    run_parser = subparsers.add_parser("run", help="启动后端服务和前端 dashboard")
    run_parser.add_argument("--port", type=int, default=8000, help="后端端口 (默认 8000)")
    run_parser.add_argument("--frontend-port", type=int, default=3000, help="前端端口 (默认 3000)")
    run_parser.add_argument("--no-frontend", action="store_true", help="仅启动后端，不启动前端")
    run_parser.add_argument("--dev", action="store_true", help="开发模式：使用当前目录的代码而非安装目录")

    # sensenova_claw cli
    cli_parser = subparsers.add_parser("cli", help="启动 CLI 交互客户端")
    cli_parser.add_argument("--host", default="localhost", help="后端地址 (默认 localhost)")
    cli_parser.add_argument("--port", type=int, default=8000, help="后端端口 (默认 8000)")
    cli_parser.add_argument("--agent", default=None, help="Agent ID")
    cli_parser.add_argument("--session", default=None, help="恢复指定 session")
    cli_parser.add_argument("--debug", action="store_true", help="调试模式")
    cli_parser.add_argument("-e", "--execute", default=None, help="执行单条消息后退出")

    # sensenova_claw version
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
