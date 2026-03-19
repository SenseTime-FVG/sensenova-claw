#!/usr/bin/env python3
"""AgentOS 统一 CLI 入口

用法:
    agentos run [--port 8000] [--frontend-port 3000] [--no-frontend]
    agentos cli [--host localhost] [--port 8000] [--agent default] [--session ID] [--debug] [-e MSG]
    agentos version
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = Path(__file__).resolve().parent / "web"


def _find_npm() -> str:
    """查找 npm 可执行文件路径"""
    import shutil
    npm = shutil.which("npm")
    if not npm:
        return ""
    return npm


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
            try:
                p.terminate()
            except OSError:
                pass
        # 等待子进程退出
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 启动后端
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "agentos.app.gateway.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", str(backend_port),
    ]
    print(f"启动后端服务: http://localhost:{backend_port}")
    backend_proc = subprocess.Popen(backend_cmd, cwd=str(PROJECT_ROOT))
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
        elif not (WEB_DIR / "node_modules").exists():
            print("警告: 前端依赖未安装，请先执行 'npm install'。跳过前端启动。", file=sys.stderr)
        else:
            print(f"启动前端 dashboard: http://localhost:{frontend_port}")
            env = os.environ.copy()
            env["PORT"] = str(frontend_port)
            frontend_proc = subprocess.Popen(
                [npm, "run", "dev"],
                cwd=str(WEB_DIR),
                env=env,
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
        _llm_ok, _ = check_llm_configured(_cfg.data)
    except Exception:
        _llm_ok = True  # 检测失败时不误报警告

    # 读取后端生成的 token（通过环境变量传递，或从 stdout 解析）
    # 后端会在启动时打印 token URL，这里也提示用户
    print()
    print("=" * 50)
    print(f"  AgentOS 已启动")
    print(f"  后端 API:    http://localhost:{backend_port}")
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

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "cli":
        return cmd_cli(args)
    elif args.command == "version":
        return cmd_version(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
