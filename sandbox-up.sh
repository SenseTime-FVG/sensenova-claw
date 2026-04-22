#!/usr/bin/env bash
# 一键启动 sensenova-claw OpenShell sandbox（前端 + 后端）
# 用法: ./sandbox-up.sh [sandbox-name]
#   不传 name 时复用已有 sandbox（若存在），否则新建随机名
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
POLICY_FILE="${POLICY_FILE:-$REPO_DIR/sandboxes/sensenova-claw/policy.yaml}"
BACKEND_PORT=8000
FRONTEND_PORT=3000
SANDBOX_NAME="${1:-}"

# 让 brew 和 docker 在非交互 shell 下可用
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/docker.sock}"

say() { printf "\033[1;36m[sandbox-up]\033[0m %s\n" "$*"; }
die() { printf "\033[1;31m[sandbox-up]\033[0m %s\n" "$*" >&2; exit 1; }

# 1. Colima
if ! colima status >/dev/null 2>&1; then
  say "Colima 未运行，启动中..."
  colima start
else
  say "Colima 已在运行"
fi

# 2. Gateway
if ! openshell status >/dev/null 2>&1; then
  say "OpenShell gateway 未运行，启动中..."
  openshell gateway start
else
  say "OpenShell gateway 已连接"
fi

# 3. 策略文件
[ -f "$POLICY_FILE" ] || die "策略文件不存在: $POLICY_FILE"

# 4. Dockerfile 软链（构建上下文需要在仓库根）
[ -d "$REPO_DIR" ] || die "仓库目录不存在: $REPO_DIR"
cd "$REPO_DIR"
if [ ! -e Dockerfile ]; then
  say "链接 Dockerfile 到仓库根"
  ln -s sandboxes/sensenova-claw/Dockerfile Dockerfile
fi

# 5. 释放本地 3000 端口（避免 Next.js dev server 冲突）
pid_3000="$(lsof -ti :$FRONTEND_PORT -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$pid_3000" ]; then
  # 仅在确认是本机其他 node 进程时才 kill；openshell forward 也可能占用
  if ! openshell forward list 2>/dev/null | awk '{print $4,$5}' | grep -q "^$FRONTEND_PORT "; then
    say "本地 $FRONTEND_PORT 被 PID $pid_3000 占用，kill 释放"
    kill "$pid_3000" || true
    sleep 1
  fi
fi

# 6. 选/建 sandbox
existing="$(openshell sandbox list 2>/dev/null | awk 'NR>1 {print $1}' | head -n1 || true)"
if [ -z "$SANDBOX_NAME" ] && [ -n "$existing" ]; then
  SANDBOX_NAME="$existing"
  say "复用已有 sandbox: $SANDBOX_NAME"
else
  if [ -n "$SANDBOX_NAME" ]; then
    if openshell sandbox list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$SANDBOX_NAME"; then
      say "复用已有 sandbox: $SANDBOX_NAME"
    else
      say "创建 sandbox: $SANDBOX_NAME"
      openshell sandbox create \
        --name "$SANDBOX_NAME" \
        --forward "$BACKEND_PORT" \
        --from . \
        --policy "$POLICY_FILE" \
        -- sensenova-claw-start &
      CREATE_PID=$!
    fi
  else
    say "创建新 sandbox（随机名）"
    openshell sandbox create \
      --forward "$BACKEND_PORT" \
      --from . \
      --policy "$POLICY_FILE" \
      -- sensenova-claw-start &
    CREATE_PID=$!
  fi
fi

# 7. 等 sandbox Ready（create 在后台，前台等待）
say "等待 sandbox 就绪..."
for i in $(seq 1 60); do
  line="$(openshell sandbox list 2>/dev/null | awk 'NR>1' | head -n1 || true)"
  phase="$(echo "$line" | awk '{print $4}')"
  name="$(echo "$line" | awk '{print $1}')"
  [ -z "$SANDBOX_NAME" ] && SANDBOX_NAME="$name"
  if [ "$phase" = "Ready" ]; then
    say "sandbox $SANDBOX_NAME 就绪"
    break
  fi
  sleep 2
done

# 8. 确保 8000 / 3000 forward 都在跑
strip_ansi() { sed 's/\x1b\[[0-9;]*[a-zA-Z]//g'; }
ensure_forward() {
  local port="$1"
  local status
  status="$(openshell forward list 2>/dev/null | strip_ansi | awk -v p="$port" '$3==p {print $5}' | head -n1)"
  if [ "$status" = "running" ]; then
    say "端口 $port 已转发"
    return
  fi
  if [ -n "$status" ]; then
    say "端口 $port 转发状态异常($status)，重启"
    openshell forward stop "$port" >/dev/null 2>&1 || true
  fi
  say "启动端口 $port 转发"
  openshell forward start -d "$port" "$SANDBOX_NAME" >/dev/null
}
ensure_forward "$BACKEND_PORT"
ensure_forward "$FRONTEND_PORT"

# 9. 健康检查
sleep 2
if curl -sS --max-time 5 -o /dev/null -w "" "http://localhost:$BACKEND_PORT/api/health"; then
  say "后端健康: http://localhost:$BACKEND_PORT"
else
  say "后端暂未响应，稍等几秒再访问"
fi

# 10. 打印 token（从 PVC 持久化路径读取）
token="$(openshell sandbox exec -n "$SANDBOX_NAME" -- sh -c 'cat /sandbox/.sensenova-claw/token 2>/dev/null || cat /home/sandbox/.sensenova-claw/token 2>/dev/null' 2>&1 | grep -v '\.profile' | grep -vE '^$' | tail -n1 || true)"
echo
echo "========================================"
echo "  sandbox:  $SANDBOX_NAME"
echo "  frontend: http://localhost:$FRONTEND_PORT/?token=$token"
echo "  backend:  http://localhost:$BACKEND_PORT"
echo "  token:    $token"
echo "========================================"
