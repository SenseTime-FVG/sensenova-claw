#!/usr/bin/env bash
# 停止并清理 sensenova-claw sandbox
# 用法:
#   ./sandbox-down.sh              # 删除所有 sandbox，保留 Docker 后端/gateway
#   ./sandbox-down.sh <name>       # 只删除指定 sandbox
#   ./sandbox-down.sh --all        # 删除所有 sandbox 并停止 Docker 后端（仅对 Colima 生效）
set -euo pipefail

# ── Homebrew shell env（macOS 两种架构都试；Linux 下安静跳过）──
for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
  if [ -x "$brew_bin" ]; then
    eval "$("$brew_bin" shellenv)"
    break
  fi
done

say() { printf "\033[1;36m[sandbox-down]\033[0m %s\n" "$*"; }

# ── Docker 后端探测（仅为了决定 --all 时是否 colima stop）──
# 删除 sandbox 本身只依赖 openshell，不需要动 Docker 后端。
DETECTED_BACKEND=""
docker_ping() {
  DOCKER_HOST="$1" docker info >/dev/null 2>&1
}
detect_docker_backend() {
  if [ -n "${DOCKER_HOST:-}" ] && docker_ping "$DOCKER_HOST"; then
    DETECTED_BACKEND="env"; return 0
  fi
  local candidates=(
    "docker-desktop|unix://$HOME/.docker/run/docker.sock"
    "colima|unix://$HOME/.colima/docker.sock"
    "rancher|unix://$HOME/.rd/docker.sock"
    "podman|unix://${XDG_RUNTIME_DIR:-/run/user/$(id -u 2>/dev/null || echo 0)}/podman/podman.sock"
    "native|unix:///var/run/docker.sock"
  )
  for pair in "${candidates[@]}"; do
    local name="${pair%%|*}"
    local sock="${pair#*|}"
    local path="${sock#unix://}"
    [ -S "$path" ] || continue
    if docker_ping "$sock"; then
      DETECTED_BACKEND="$name"; export DOCKER_HOST="$sock"; return 0
    fi
  done
  return 1
}
# 探测失败不致命：可能后端已经停了，仍然允许删除 sandbox
command -v docker >/dev/null 2>&1 && detect_docker_backend || true

STOP_BACKEND=0
TARGET=""
case "${1:-}" in
  --all) STOP_BACKEND=1 ;;
  "") ;;
  *) TARGET="$1" ;;
esac

if [ -n "$TARGET" ]; then
  openshell sandbox delete "$TARGET" || true
else
  openshell sandbox list 2>/dev/null | awk 'NR>1 {print $1}' | while read -r s; do
    [ -n "$s" ] && openshell sandbox delete "$s" || true
  done
fi

if [ "$STOP_BACKEND" = "1" ]; then
  # 只有 Colima 适合在脚本里 stop；Docker Desktop/Rancher 由用户 GUI 管理，
  # 原生 Docker Engine 不应随手关闭。
  if [ "$DETECTED_BACKEND" = "colima" ] && command -v colima >/dev/null 2>&1; then
    say "停止 Colima"
    colima stop || true
  else
    say "--all 对 $DETECTED_BACKEND 后端无效果（只对 Colima 自动停止）"
  fi
fi

say "done"
