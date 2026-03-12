#!/usr/bin/env bash
# 一键执行全部测试 + 生成功能验证矩阵
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
RESULTS_DIR="$SCRIPT_DIR/results"

mkdir -p "$RESULTS_DIR"
cd "$BACKEND_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
FAIL=0

run_suite() {
    local label="$1" xml="$2"
    shift 2
    echo -e "\n${CYAN}=== $label ===${NC}"
    if uv run python -m pytest "$@" --junitxml="$xml" -q; then
        echo -e "${GREEN}  ✓ $label 通过${NC}"
    else
        echo -e "${RED}  ✗ $label 存在失败${NC}"
        FAIL=1
    fi
}

run_suite "L1 单元测试"  "$RESULTS_DIR/unit.xml"        "$SCRIPT_DIR/unit"
run_suite "L2 集成测试"  "$RESULTS_DIR/integration.xml" "$SCRIPT_DIR/integration"
run_suite "L3 API 测试"  "$RESULTS_DIR/api.xml"         "$SCRIPT_DIR/api"
run_suite "跨功能测试"   "$RESULTS_DIR/cross.xml"       "$SCRIPT_DIR/cross_feature"
run_suite "E2E 后端/CLI" "$RESULTS_DIR/e2e_backend.xml" "$SCRIPT_DIR/e2e/backend" "$SCRIPT_DIR/e2e/cli"

echo -e "\n${CYAN}=== 生成功能验证矩阵 ===${NC}"
uv run python "$SCRIPT_DIR/generate_matrix.py"

echo ""
cat "$RESULTS_DIR/feature_matrix.md" | head -3
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}全部通过 → $RESULTS_DIR${NC}"
else
    echo -e "${RED}存在失败，请查看上方输出 → $RESULTS_DIR${NC}"
    exit 1
fi
