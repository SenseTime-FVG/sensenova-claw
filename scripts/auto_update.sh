#!/usr/bin/env bash
# Sensenova-Claw 自动更新脚本
# 定期检查 dev 分支是否有新 commit，有则 pull 并重启服务
#
# 用法:
#   ./scripts/auto_update.sh                  # 默认每 30 秒检查一次
#   ./scripts/auto_update.sh --interval 60    # 每 60 秒检查一次
#   BACKEND_PORT=9000 ./scripts/auto_update.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="dev"
CHECK_INTERVAL=30  # 秒
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

BACKEND_PID=""
FRONTEND_PID=""

# ── 参数解析 ──

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) CHECK_INTERVAL="$2"; shift 2 ;;
    --branch)   BRANCH="$2"; shift 2 ;;
    --port)     BACKEND_PORT="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# ── 工具函数 ──

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

kill_proc() {
  local pid="$1"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    # 等待最多 5 秒
    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || return 0
      sleep 0.5
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  log "正在停止服务..."
  kill_proc "$BACKEND_PID"
  kill_proc "$FRONTEND_PID"
  log "服务已停止"
  exit 0
}

trap cleanup EXIT INT TERM

# ── 启动服务 ──

start_services() {
  cd "$ROOT_DIR"

  # 启动后端
  log "启动后端 (port=$BACKEND_PORT)..."
  if command -v uv >/dev/null 2>&1; then
    uv run uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
  else
    python3 -m uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
  fi
  BACKEND_PID=$!
  sleep 2

  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "错误: 后端启动失败"
    return 1
  fi

  # 启动前端
  local web_dir="$ROOT_DIR/sensenova_claw/app/web"
  if [ -d "$web_dir/node_modules" ]; then
    log "启动前端 (port=$FRONTEND_PORT)..."
    cd "$web_dir"
    PORT="$FRONTEND_PORT" npm run dev &
    FRONTEND_PID=$!
    cd "$ROOT_DIR"
    sleep 2
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
      log "警告: 前端启动失败，仅运行后端"
      FRONTEND_PID=""
    fi
  else
    log "跳过前端（未安装依赖）"
  fi

  log "服务已启动"
  log "  后端: http://localhost:$BACKEND_PORT"
  [ -n "$FRONTEND_PID" ] && log "  前端: http://localhost:$FRONTEND_PORT"
}

stop_services() {
  log "停止服务..."
  kill_proc "$BACKEND_PID"
  kill_proc "$FRONTEND_PID"
  BACKEND_PID=""
  FRONTEND_PID=""
  sleep 1
}

# ── 检查更新 ──

check_and_update() {
  cd "$ROOT_DIR"

  # 获取远程最新状态
  git fetch origin "$BRANCH" --quiet 2>/dev/null || {
    log "警告: git fetch 失败，跳过本次检查"
    return 1
  }

  local local_hash remote_hash
  local_hash=$(git rev-parse "$BRANCH" 2>/dev/null)
  remote_hash=$(git rev-parse "origin/$BRANCH" 2>/dev/null)

  if [ "$local_hash" = "$remote_hash" ]; then
    return 1  # 无更新
  fi

  # 有更新
  local new_commits
  new_commits=$(git log --oneline "$BRANCH..origin/$BRANCH" 2>/dev/null)
  log "检测到新 commit:"
  echo "$new_commits" | while read -r line; do
    log "  $line"
  done

  # Pull
  log "正在拉取更新..."
  git pull origin "$BRANCH" --ff-only || {
    log "错误: git pull 失败（可能有本地冲突），跳过本次更新"
    return 1
  }

  # 检查是否需要重装依赖
  if git diff "$local_hash" "$remote_hash" --name-only | grep -q "pyproject.toml"; then
    log "检测到 pyproject.toml 变更，重新安装 Python 依赖..."
    if command -v uv >/dev/null 2>&1; then
      uv sync 2>/dev/null || true
    else
      pip install -e . 2>/dev/null || true
    fi
  fi

  if git diff "$local_hash" "$remote_hash" --name-only | grep -q "package.json\|package-lock.json"; then
    log "检测到 package.json 变更，重新安装 Node 依赖..."
    cd "$ROOT_DIR" && npm install 2>/dev/null || true
  fi

  return 0  # 有更新
}

# ── 主循环 ──

main() {
  cd "$ROOT_DIR"

  # 确保在目标分支上
  current_branch=$(git branch --show-current)
  if [ "$current_branch" != "$BRANCH" ]; then
    log "当前分支 $current_branch，切换到 $BRANCH..."
    git checkout "$BRANCH" || { log "错误: 无法切换到 $BRANCH"; exit 1; }
  fi

  log "Sensenova-Claw 自动更新服务启动"
  log "  分支: $BRANCH"
  log "  检查间隔: ${CHECK_INTERVAL}s"

  start_services || exit 1

  while true; do
    sleep "$CHECK_INTERVAL"

    # 检查服务是否存活
    if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      log "后端进程异常退出，正在重启..."
      stop_services
      start_services || exit 1
      continue
    fi

    # 检查更新
    if check_and_update; then
      log "更新完成，重启服务..."
      stop_services
      start_services || exit 1
      log "服务重启完成"
    fi
  done
}

main
