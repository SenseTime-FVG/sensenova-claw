#!/usr/bin/env bash
# 兼容入口：执行当前 tests/ 目录下的后端测试，并生成结果矩阵
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

mkdir -p "$RESULTS_DIR"

if [ "${USE_UV:-0}" = "1" ] && command -v uv >/dev/null 2>&1; then
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv_cache}"
    PYTEST_RUNNER=(uv run python -m pytest)
    PYTHON_RUNNER=(uv run python)
else
    PYTEST_RUNNER=(python3 -m pytest)
    PYTHON_RUNNER=(python3)
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
FAIL=0

run_suite() {
    local label="$1" xml="$2"
    shift 2
    echo -e "\n${CYAN}=== $label ===${NC}"
    if "${PYTEST_RUNNER[@]}" "$@" --junitxml="$xml" -q; then
        echo -e "${GREEN}  ✓ $label 通过${NC}"
    else
        echo -e "${RED}  ✗ $label 存在失败${NC}"
        FAIL=1
    fi
}

run_suite "L1 单元测试"  "$RESULTS_DIR/unit.xml"        "$ROOT_DIR/tests/unit"
run_suite "L2 集成测试"  "$RESULTS_DIR/integration.xml" "$ROOT_DIR/tests/integration"
run_suite "L3 API 测试"  "$RESULTS_DIR/api.xml"         \
    "$ROOT_DIR/tests/unit/test_agents_api.py"          \
    "$ROOT_DIR/tests/unit/test_config_api.py"          \
    "$ROOT_DIR/tests/unit/test_gateway_api.py"         \
    "$ROOT_DIR/tests/unit/test_skill_api.py"           \
    "$ROOT_DIR/tests/unit/test_tools_api.py"           \
    "$ROOT_DIR/tests/unit/test_workspace_api.py"
run_suite "跨功能测试"   "$RESULTS_DIR/cross.xml"       "$ROOT_DIR/tests/cross_feature"
run_suite "E2E 后端测试" "$RESULTS_DIR/e2e_backend.xml" "$ROOT_DIR/tests/e2e"

echo -e "\n${CYAN}=== 生成功能验证矩阵 ===${NC}"
"${PYTHON_RUNNER[@]}" "$SCRIPT_DIR/generate_matrix.py"

echo ""
cat "$RESULTS_DIR/feature_matrix.md" | head -3
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}全部通过 → $RESULTS_DIR${NC}"
    echo -e "${CYAN}真实 API 回归可额外执行: uv run python tests/e2e/run_e2e.py --provider openai${NC}"
else
    echo -e "${RED}存在失败，请查看上方输出 → $RESULTS_DIR${NC}"
    exit 1
fi
