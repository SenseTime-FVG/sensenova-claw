#!/usr/bin/env bash
# Sensenova-Claw 一键安装脚本（Linux/macOS）
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.sh | bash
#
# 或本地执行:
#   bash install/install.sh
#
# 开发模式（跳过克隆，使用当前目录代码）:
#   bash install/install.sh --dev
#
set -euo pipefail

# ── 配置 ──

SENSENOVA_CLAW_HOME="${SENSENOVA_CLAW_HOME:-$HOME/.sensenova-claw}"
APP_DIR="$SENSENOVA_CLAW_HOME/app"
REPO_URL="${SENSENOVA_CLAW_REPO_URL:-https://github.com/SenseTime-FVG/sensenova-claw.git}"
REPO_REF="${SENSENOVA_CLAW_REPO_REF:-${SENSENOVA_CLAW_REPO_BRANCH:-dev}}"
REQUIRED_PYTHON="3.12"
REQUIRED_NODE="18"
DEV_MODE=false

# 国内镜像
CN_NPM_REGISTRY="https://registry.npmmirror.com"
CN_PIP_INDEX="https://mirrors.aliyun.com/pypi/simple/"
CN_UV_INDEX="https://mirrors.aliyun.com/pypi/simple/"
CN_NVM_MIRROR="https://npmmirror.com/mirrors/node"

# ── 工具函数 ──

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }
info()  { echo -e "${BLUE}[i]${NC} $*"; }

fail() {
  error "$1"
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# 比较版本号: version_ge "3.12.1" "3.12" → 成功
version_ge() {
  local have="$1" need="$2"
  printf '%s\n%s' "$need" "$have" | sort -V | head -n1 | grep -qx "$need"
}

prompt_input() {
  local prompt="$1" default="${2:-}"
  if [ -n "$default" ]; then
    read -rp "$(echo -e "${BLUE}[?]${NC} ${prompt} [${default}]: ")" value
    echo "${value:-$default}"
  else
    read -rp "$(echo -e "${BLUE}[?]${NC} ${prompt}: ")" value
    echo "$value"
  fi
}

# ── 步骤 1: 地区检测 ──

detect_region() {
  info "检测网络环境..."
  IS_CN=false

  local resp
  resp=$(curl -s --connect-timeout 5 "https://api.iping.cc/v1/query" 2>/dev/null) || {
    warn "无法检测地区，使用默认源"
    return
  }

  local country_code
  # 尝试用 jq，没有则用 grep 提取
  if command_exists jq; then
    country_code=$(echo "$resp" | jq -r '.country_code // empty' 2>/dev/null)
  else
    country_code=$(echo "$resp" | grep -o '"country_code":"[^"]*"' | head -1 | cut -d'"' -f4)
  fi

  if [ "$country_code" = "CN" ]; then
    IS_CN=true
    log "检测到国内网络，将使用国内镜像加速"
  else
    log "检测到海外网络，使用默认源"
  fi
}

configure_cn_mirrors() {
  if [ "$IS_CN" != "true" ]; then
    return
  fi

  info "配置国内镜像源..."

  # npm 镜像
  if command_exists npm; then
    npm config set registry "$CN_NPM_REGISTRY" 2>/dev/null || true
    log "npm 镜像: $CN_NPM_REGISTRY"
  fi

  # pip/uv 镜像
  mkdir -p "$HOME/.config/uv"
  cat > "$HOME/.config/uv/uv.toml" <<EOF
[pip]
index-url = "$CN_UV_INDEX"

[[index]]
url = "$CN_UV_INDEX"
default = true
EOF
  log "uv/pip 镜像: $CN_UV_INDEX"

  # nvm Node 下载镜像
  export NVM_NODEJS_ORG_MIRROR="$CN_NVM_MIRROR"
}

# ── 步骤 1b: 安装 git ──

install_git() {
  if command_exists git; then
    log "git 已安装: $(git --version)"
    return
  fi

  info "安装 git..."

  if command_exists apt-get; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git
  elif command_exists yum; then
    sudo yum install -y -q git
  elif command_exists dnf; then
    sudo dnf install -y -q git
  elif command_exists pacman; then
    sudo pacman -S --noconfirm git
  elif command_exists brew; then
    brew install git
  elif command_exists apk; then
    sudo apk add --quiet git
  else
    fail "无法自动安装 git，请手动安装后重试: https://git-scm.com/downloads"
  fi

  if command_exists git; then
    log "git 安装成功: $(git --version)"
  else
    fail "git 安装失败，请手动安装: https://git-scm.com/downloads"
  fi
}

# ── 步骤 2: 安装 uv + Python ──

install_uv() {
  if command_exists uv; then
    log "uv 已安装: $(uv --version)"
    return
  fi

  info "安装 uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # 加载 uv 到当前 PATH
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

  if command_exists uv; then
    log "uv 安装成功: $(uv --version)"
  else
    fail "uv 安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
  fi
}

install_python() {
  # 检查是否已有合适版本
  if command_exists python3; then
    local py_ver
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if version_ge "$py_ver" "$REQUIRED_PYTHON"; then
      log "Python 已安装: $py_ver"
      return
    fi
    warn "Python 版本 $py_ver 低于要求的 $REQUIRED_PYTHON"
  fi

  info "通过 uv 安装 Python ${REQUIRED_PYTHON}..."
  uv python install "$REQUIRED_PYTHON"

  log "Python ${REQUIRED_PYTHON} 安装成功"
}

# ── 步骤 3: 安装 nvm + Node.js ──

install_nvm() {
  if command_exists nvm; then
    log "nvm 已安装"
    return
  fi

  # nvm 可能已安装但未加载
  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  if [ -s "$nvm_dir/nvm.sh" ]; then
    source "$nvm_dir/nvm.sh"
    if command_exists nvm; then
      log "nvm 已安装（已加载）"
      return
    fi
  fi

  info "安装 nvm..."
  local nvm_install_url="https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh"
  if [ "$IS_CN" = "true" ]; then
    # 国内可能需要通过 gitee 镜像
    nvm_install_url="https://gitee.com/mirrors/nvm/raw/v0.40.3/install.sh"
  fi

  curl -o- "$nvm_install_url" | bash 2>/dev/null || {
    # 降级方案
    warn "nvm 脚本安装失败，尝试 git 方式..."
    git clone https://github.com/nvm-sh/nvm.git "$nvm_dir" 2>/dev/null
    cd "$nvm_dir" && git checkout v0.40.3 2>/dev/null
    cd - >/dev/null
  }

  export NVM_DIR="$nvm_dir"
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

  if command_exists nvm; then
    log "nvm 安装成功"
  else
    fail "nvm 安装失败，请手动安装: https://github.com/nvm-sh/nvm#installing-and-updating"
  fi
}

install_node() {
  # 检查是否已有合适版本
  if command_exists node; then
    local node_ver
    node_ver=$(node -v | sed 's/^v//' | cut -d. -f1)
    if [ "$node_ver" -ge "$REQUIRED_NODE" ] 2>/dev/null; then
      log "Node.js 已安装: $(node -v)"
      return
    fi
    warn "Node.js 版本 $(node -v) 低于要求的 v${REQUIRED_NODE}"
  fi

  info "通过 nvm 安装 Node.js LTS..."

  # 国内镜像
  if [ "$IS_CN" = "true" ]; then
    export NVM_NODEJS_ORG_MIRROR="$CN_NVM_MIRROR"
  fi

  nvm install --lts
  nvm use --lts

  if command_exists node && command_exists npm; then
    log "Node.js 安装成功: $(node -v)"
    # 安装后配置 npm 镜像
    if [ "$IS_CN" = "true" ]; then
      npm config set registry "$CN_NPM_REGISTRY"
    fi
  else
    fail "Node.js 安装失败"
  fi
}

# ── 步骤 4: 克隆/更新仓库 ──

setup_repo() {
  if [ -d "$APP_DIR/.git" ]; then
    info "更新 Sensenova-Claw ($REPO_REF)..."
    cd "$APP_DIR"
    git fetch origin "$REPO_REF" --quiet || {
      warn "git fetch $REPO_REF 失败，跳过更新"
      cd - >/dev/null
      return
    }
    if git show-ref --verify --quiet "refs/remotes/origin/$REPO_REF"; then
      git checkout "$REPO_REF" --quiet 2>/dev/null || git checkout -B "$REPO_REF" "origin/$REPO_REF" --quiet
      git pull origin "$REPO_REF" --ff-only --quiet || {
        warn "git pull 失败，可能有本地修改，跳过更新"
      }
    else
      git checkout --detach FETCH_HEAD --quiet || {
        warn "git checkout $REPO_REF 失败，跳过更新"
        cd - >/dev/null
        return
      }
    fi
    cd - >/dev/null
    log "Sensenova-Claw 已更新"
  else
    info "克隆 Sensenova-Claw 仓库 ($REPO_REF)..."
    mkdir -p "$(dirname "$APP_DIR")"
    git clone --branch "$REPO_REF" --depth 1 "$REPO_URL" "$APP_DIR"
    log "Sensenova-Claw 克隆完成"
  fi
}

# ── 步骤 5: 安装项目依赖 ──

install_deps() {
  info "安装项目依赖..."
  cd "$APP_DIR"

  # 设置 uv 缓存目录（避免权限问题）
  export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv_cache}"

  # 1) Python 依赖
  info "安装 Python 依赖..."
  uv sync 2>&1 | tail -5
  log "Python 依赖安装完成"

  # 2) 根目录 npm 依赖（跳过 postinstall，避免重复）
  info "安装根目录 npm 依赖..."
  npm install --ignore-scripts 2>&1 | tail -5
  log "根目录 npm 依赖安装完成"

  # 3) 前端依赖
  info "安装前端依赖..."
  cd "$APP_DIR/sensenova_claw/app/web"
  npm install 2>&1 | tail -5
  cd "$APP_DIR"
  log "前端依赖安装完成"
}

# ── 步骤 5b: 构建 SENSENOVA_CLAW_HOME 目录结构 ──

setup_home_dir() {
  info "初始化 SENSENOVA_CLAW_HOME 目录结构..."

  # 创建核心子目录
  for subdir in agents/default data skills workdir/default db; do
    mkdir -p "$SENSENOVA_CLAW_HOME/$subdir"
  done

  local builtin_dir="$APP_DIR/.sensenova-claw"

  # 复制预置 agents（不覆盖已有文件）
  if [ -d "$builtin_dir/agents" ]; then
    find "$builtin_dir/agents" -mindepth 1 -maxdepth 1 -type d | while read -r agent_dir; do
      local agent_name
      agent_name=$(basename "$agent_dir")
      local target_dir="$SENSENOVA_CLAW_HOME/agents/$agent_name"
      mkdir -p "$target_dir"
      find "$agent_dir" -maxdepth 1 -type f | while read -r f; do
        local target_file="$target_dir/$(basename "$f")"
        if [ ! -f "$target_file" ]; then
          cp "$f" "$target_file"
        fi
      done
    done
    log "预置 Agents 已复制"
  fi

  # 复制预置 skills（不覆盖已有目录）
  if [ -d "$builtin_dir/skills" ]; then
    find "$builtin_dir/skills" -mindepth 1 -maxdepth 1 -type d | while read -r skill_dir; do
      local skill_name
      skill_name=$(basename "$skill_dir")
      local target_dir="$SENSENOVA_CLAW_HOME/skills/$skill_name"
      if [ ! -d "$target_dir" ]; then
        cp -r "$skill_dir" "$target_dir"
      fi
    done
    log "预置 Skills 已复制"
  fi

  log "SENSENOVA_CLAW_HOME 初始化完成: $SENSENOVA_CLAW_HOME"
}

# ── 步骤 6: 初始化配置文件 ──

setup_config() {
  # 配置文件放在 SENSENOVA_CLAW_HOME 根目录，与代码 DEFAULT_CONFIG_PATH 一致
  local config_file="$SENSENOVA_CLAW_HOME/config.yml"
  local example_file="$APP_DIR/config_example.yml"

  if [ -f "$config_file" ]; then
    info "检测到已有配置文件，跳过"
    log "保留现有配置: $config_file"
    return
  fi

  if [ -f "$example_file" ]; then
    cp "$example_file" "$config_file"
    log "已从 config_example.yml 生成配置文件: $config_file"
    info "请编辑 $config_file 填入 LLM API Key 等配置"
  else
    warn "未找到 config_example.yml，请手动创建 $config_file"
  fi
}

# ── 步骤 7: 注册全局命令 ──

register_command() {
  info "注册 sensenova-claw 命令..."
  cd "$APP_DIR"

  # 使用 editable 安装，避免 uv tool 环境里残留一份过期代码副本。
  uv tool install --editable --from . --force sensenova-claw 2>/dev/null || {
    # 降级：用 pip install -e
    warn "uv tool install 失败，尝试 pip install..."
    uv pip install -e . 2>/dev/null || pip install -e . 2>/dev/null || {
      warn "全局命令注册失败，你可以手动运行: cd $APP_DIR && python3 -m sensenova_claw.app.main run"
      return
    }
  }

  # 确保 PATH 包含 uv tool 目录
  local uv_bin="$HOME/.local/bin"
  if [[ ":$PATH:" != *":$uv_bin:"* ]]; then
    export PATH="$uv_bin:$PATH"
  fi

  if command_exists sensenova-claw; then
    log "sensenova-claw 命令已注册"
  else
    warn "sensenova-claw 命令未在 PATH 中找到，你可能需要重新打开终端"
    info "或手动添加到 PATH: export PATH=\"$uv_bin:\$PATH\""
  fi
}

# ── 步骤 8: 完成 ──

print_success() {
  echo ""
  echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  Sensenova-Claw 安装完成!${NC}"
  echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
  echo ""
  if [ "$DEV_MODE" = "true" ]; then
    echo "  模式:     开发模式"
    echo "  代码目录: $APP_DIR"
  else
    echo "  安装目录: $APP_DIR"
    echo "  安装来源: $REPO_URL@$REPO_REF"
  fi
  echo "  数据目录: $SENSENOVA_CLAW_HOME"
  echo ""
  if [ "$IS_CN" = "true" ]; then
    echo "  已配置国内镜像: npm($CN_NPM_REGISTRY) pip($CN_UV_INDEX)"
    echo ""
  fi
  echo -e "  ${YELLOW}下一步:${NC}"
  echo ""
  echo "    1. 启动服务:"
  echo "       sensenova-claw run"
  echo ""
  echo "    2. 打开 Web 界面进行 LLM 等配置:"
  echo "       http://localhost:3000"
  echo ""
  echo "    或使用 CLI 客户端（需先启动服务）:"
  echo "       sensenova-claw cli"
  echo ""
  echo "  文档: https://github.com/SenseTime-FVG/sensenova-claw"
  echo ""
}

# ── 主流程 ──

main() {
  # 解析参数
  for arg in "$@"; do
    case "$arg" in
      --dev) DEV_MODE=true ;;
    esac
  done

  echo ""
  echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BLUE}║         Sensenova-Claw 一键安装脚本          ║${NC}"
  echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
  echo ""

  if [ "$DEV_MODE" = "true" ]; then
    # 开发模式：使用当前目录的代码，跳过克隆
    # 找到 install.sh 所在的仓库根目录
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    APP_DIR="$(cd "$script_dir/.." && pwd)"

    # 校验是否是 sensenova-claw 项目
    if [ ! -f "$APP_DIR/sensenova_claw/app/gateway/main.py" ]; then
      fail "当前仓库不是 Sensenova-Claw 项目，无法使用 --dev 模式"
    fi

    log "开发模式: 使用本地代码 $APP_DIR"
    echo ""

    detect_region
    configure_cn_mirrors
    install_uv
    install_python
    install_nvm
    install_node
    # 跳过 setup_repo（不克隆）
    install_deps
    setup_home_dir
    setup_config
    register_command
    print_success
  else
    # 正常安装模式
    local default_dir="$SENSENOVA_CLAW_HOME"
    SENSENOVA_CLAW_HOME=$(prompt_input "安装路径" "$default_dir")
    APP_DIR="$SENSENOVA_CLAW_HOME/app"
    log "安装到: $SENSENOVA_CLAW_HOME"
    echo ""

    detect_region
    configure_cn_mirrors
    install_git
    install_uv
    install_python
    install_nvm
    install_node
    setup_repo
    install_deps
    setup_home_dir
    setup_config
    register_command
    print_success
  fi
}

main "$@"
