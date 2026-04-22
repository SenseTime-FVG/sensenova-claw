#!/usr/bin/env bash
# 停止并清理 sensenova-claw sandbox
# 用法:
#   ./sandbox-down.sh              # 删除所有 sandbox，保留 Colima/gateway
#   ./sandbox-down.sh <name>       # 只删除指定 sandbox
#   ./sandbox-down.sh --all        # 删除所有 sandbox 并停止 Colima
set -euo pipefail

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/docker.sock}"

say() { printf "\033[1;36m[sandbox-down]\033[0m %s\n" "$*"; }

STOP_COLIMA=0
TARGET=""
case "${1:-}" in
  --all) STOP_COLIMA=1 ;;
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

if [ "$STOP_COLIMA" = "1" ]; then
  say "停止 Colima"
  colima stop || true
fi

say "done"
