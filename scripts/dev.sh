#!/usr/bin/env bash
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
