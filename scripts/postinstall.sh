#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MISSING=()

# 检查 uv
if ! command -v uv >/dev/null 2>&1; then
  MISSING+=("uv")
fi

# 检查 npm（子目录安装需要）
if ! command -v npm >/dev/null 2>&1; then
  MISSING+=("npm")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo -e "${RED}✗ 缺少必要的工具: ${MISSING[*]}${NC}"
  echo ""
  echo "请按以下指南安装："
  echo ""
  for tool in "${MISSING[@]}"; do
    case "$tool" in
      uv)
        echo -e "  ${YELLOW}uv${NC} (Python 包管理器):"
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "    详见: https://docs.astral.sh/uv/getting-started/installation/"
        echo ""
        ;;
      npm)
        echo -e "  ${YELLOW}npm${NC} (Node.js 包管理器):"
        echo "    安装 Node.js (>= 18): https://nodejs.org/"
        echo "    或使用 nvm: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash"
        echo ""
        ;;
    esac
  done
  echo -e "安装完成后重新运行 ${GREEN}npm install${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}▶ 安装 Python 依赖...${NC}"
cd "$ROOT_DIR"
uv sync

echo ""
echo -e "${GREEN}▶ 安装前端依赖...${NC}"
cd "$ROOT_DIR/agentos/app/web"
npm install

echo ""
echo -e "${GREEN}✔ 所有依赖安装完成${NC}"
