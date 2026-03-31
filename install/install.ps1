# Sensenova-Claw 一键安装脚本（Windows PowerShell）
#
# 用法:
#   irm https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.ps1 | iex
#
# 或本地执行:
#   powershell -ExecutionPolicy Bypass -File install\install.ps1
#

$ErrorActionPreference = "Stop"

# ── 配置 ──

$SENSENOVA_CLAW_HOME = if ($env:SENSENOVA_CLAW_HOME) { $env:SENSENOVA_CLAW_HOME } else { "$env:USERPROFILE\.sensenova-claw" }
$APP_DIR = "$SENSENOVA_CLAW_HOME\app"
$REPO_URL = if ($env:SENSENOVA_CLAW_REPO_URL) { $env:SENSENOVA_CLAW_REPO_URL } else { "https://github.com/SenseTime-FVG/sensenova-claw.git" }
$REPO_REF = if ($env:SENSENOVA_CLAW_REPO_REF) { $env:SENSENOVA_CLAW_REPO_REF } elseif ($env:SENSENOVA_CLAW_REPO_BRANCH) { $env:SENSENOVA_CLAW_REPO_BRANCH } else { "dev" }
$REQUIRED_PYTHON = "3.12"
$REQUIRED_NODE = 18

# 国内镜像
$CN_NPM_REGISTRY = "https://registry.npmmirror.com"
$CN_PIP_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
$CN_FNM_MIRROR = "https://npmmirror.com/mirrors/node"

$IS_CN = $false

# ── 工具函数 ──

function Log { param($msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Err { param($msg) Write-Host "[x] $msg" -ForegroundColor Red }
function Info { param($msg) Write-Host "[i] $msg" -ForegroundColor Cyan }

function Fail {
    param($msg)
    Err $msg
    exit 1
}

function Command-Exists {
    param($cmd)
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Prompt-Input {
    param($prompt, $default = "")
    if ($default) {
        $value = Read-Host "[?] $prompt [$default]"
        if (-not $value) { return $default }
        return $value
    }
    return Read-Host "[?] $prompt"
}

# ── 步骤 1: 地区检测 ──

function Detect-Region {
    Info "检测网络环境..."
    try {
        $resp = Invoke-RestMethod -Uri "https://api.iping.cc/v1/query" -TimeoutSec 5 -ErrorAction Stop
        if ($resp.country_code -eq "CN") {
            $script:IS_CN = $true
            Log "检测到国内网络，将使用国内镜像加速"
        } else {
            Log "检测到海外网络，使用默认源"
        }
    } catch {
        Warn "无法检测地区，使用默认源"
    }
}

function Configure-CN-Mirrors {
    if (-not $IS_CN) { return }

    Info "配置国内镜像源..."

    # npm 镜像
    if (Command-Exists npm) {
        npm config set registry $CN_NPM_REGISTRY 2>$null
        Log "npm 镜像: $CN_NPM_REGISTRY"
    }

    # uv/pip 镜像
    $uvConfigDir = "$env:USERPROFILE\.config\uv"
    New-Item -ItemType Directory -Force -Path $uvConfigDir | Out-Null
    @"
[pip]
index-url = "$CN_PIP_INDEX"

[[index]]
url = "$CN_PIP_INDEX"
default = true
"@ | Set-Content "$uvConfigDir\uv.toml" -Encoding UTF8

    Log "uv/pip 镜像: $CN_PIP_INDEX"
}

# ── 步骤 2: 安装 uv + Python ──

function Install-Uv {
    if (Command-Exists uv) {
        Log "uv 已安装: $(uv --version)"
        return
    }

    Info "安装 uv..."
    irm https://astral.sh/uv/install.ps1 | iex

    # 刷新 PATH
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:PATH"

    if (Command-Exists uv) {
        Log "uv 安装成功: $(uv --version)"
    } else {
        Fail "uv 安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
    }
}

function Install-Python {
    if (Command-Exists python) {
        $pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($pyVer -and [version]$pyVer -ge [version]$REQUIRED_PYTHON) {
            Log "Python 已安装: $pyVer"
            return
        }
        Warn "Python 版本 $pyVer 低于要求的 $REQUIRED_PYTHON"
    }

    Info "通过 uv 安装 Python $REQUIRED_PYTHON..."
    uv python install $REQUIRED_PYTHON

    Log "Python $REQUIRED_PYTHON 安装成功"
}

# ── 步骤 3: 安装 fnm + Node.js ──

function Install-Fnm {
    if (Command-Exists fnm) {
        Log "fnm 已安装"
        return
    }

    Info "安装 fnm (Node.js 版本管理器)..."

    # 尝试 winget
    if (Command-Exists winget) {
        winget install Schniz.fnm --accept-package-agreements --accept-source-agreements 2>$null
    } else {
        # 降级：PowerShell 安装
        irm https://fnm.vercel.app/install.ps1 | iex
    }

    # 刷新 PATH
    $env:PATH = "$env:APPDATA\fnm;$env:LOCALAPPDATA\fnm;$env:PATH"

    if (Command-Exists fnm) {
        Log "fnm 安装成功"
        # 初始化 fnm 环境
        fnm env --use-on-cd | Out-String | Invoke-Expression
    } else {
        Fail "fnm 安装失败，请手动安装: https://github.com/Schniz/fnm#installation"
    }
}

function Install-Node {
    if (Command-Exists node) {
        $nodeVer = (node -v) -replace '^v', '' -replace '\..*', ''
        if ([int]$nodeVer -ge $REQUIRED_NODE) {
            Log "Node.js 已安装: $(node -v)"
            return
        }
        Warn "Node.js 版本 $(node -v) 低于要求的 v$REQUIRED_NODE"
    }

    Info "通过 fnm 安装 Node.js LTS..."

    if ($IS_CN) {
        $env:FNM_NODE_DIST_MIRROR = $CN_FNM_MIRROR
    }

    fnm install --lts
    fnm use --lts
    fnm env --use-on-cd | Out-String | Invoke-Expression

    if ((Command-Exists node) -and (Command-Exists npm)) {
        Log "Node.js 安装成功: $(node -v)"
        if ($IS_CN) {
            npm config set registry $CN_NPM_REGISTRY
        }
    } else {
        Fail "Node.js 安装失败"
    }
}

# ── 步骤 4: 克隆/更新仓库 ──

function Setup-Repo {
    if (Test-Path "$APP_DIR\.git") {
        Info "更新 Sensenova-Claw ($REPO_REF)..."
        Push-Location $APP_DIR
        try {
            git fetch origin $REPO_REF --quiet 2>$null
            $remoteBranchRef = "refs/remotes/origin/$REPO_REF"
            git show-ref --verify --quiet $remoteBranchRef 2>$null
            if ($LASTEXITCODE -eq 0) {
                git checkout $REPO_REF --quiet 2>$null
                if ($LASTEXITCODE -ne 0) {
                    git checkout -B $REPO_REF "origin/$REPO_REF" --quiet 2>$null
                }
                git pull origin $REPO_REF --ff-only --quiet 2>$null
            } else {
                git checkout --detach FETCH_HEAD --quiet 2>$null
            }
        } catch {
            Warn "git 更新 $REPO_REF 失败，跳过更新"
        }
        Pop-Location
        Log "Sensenova-Claw 已更新"
    } else {
        Info "克隆 Sensenova-Claw 仓库 ($REPO_REF)..."
        $parent = Split-Path $APP_DIR -Parent
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        git clone --branch $REPO_REF --depth 1 $REPO_URL $APP_DIR
        Log "Sensenova-Claw 克隆完成"
    }
}

# ── 步骤 5: 安装项目依赖 ──

function Install-Deps {
    Info "安装项目依赖..."
    Push-Location $APP_DIR
    npm install
    Pop-Location
    Log "项目依赖安装完成"
}

# ── 步骤 5b: 构建 SENSENOVA_CLAW_HOME 目录结构 ──

function Setup-HomeDir {
    Info "初始化 SENSENOVA_CLAW_HOME 目录结构..."

    # 创建核心子目录
    foreach ($subdir in @("agents\default", "data", "skills", "workdir\default", "db")) {
        New-Item -ItemType Directory -Force -Path "$SENSENOVA_CLAW_HOME\$subdir" | Out-Null
    }

    $builtinDir = "$APP_DIR\.sensenova-claw"

    # 复制预置 agents（不覆盖已有文件）
    $builtinAgents = "$builtinDir\agents"
    if (Test-Path $builtinAgents) {
        Get-ChildItem $builtinAgents -Directory | ForEach-Object {
            $targetDir = "$SENSENOVA_CLAW_HOME\agents\$($_.Name)"
            New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
            Get-ChildItem $_.FullName -File | ForEach-Object {
                $targetFile = "$targetDir\$($_.Name)"
                if (-not (Test-Path $targetFile)) {
                    Copy-Item $_.FullName $targetFile
                }
            }
        }
        Log "预置 Agents 已复制"
    }

    # 复制预置 skills（不覆盖已有目录）
    $builtinSkills = "$builtinDir\skills"
    if (Test-Path $builtinSkills) {
        Get-ChildItem $builtinSkills -Directory | ForEach-Object {
            $targetDir = "$SENSENOVA_CLAW_HOME\skills\$($_.Name)"
            if (-not (Test-Path $targetDir)) {
                Copy-Item $_.FullName $targetDir -Recurse
            }
        }
        Log "预置 Skills 已复制"
    }

    Log "SENSENOVA_CLAW_HOME 初始化完成: $SENSENOVA_CLAW_HOME"
}

# ── 步骤 6: 初始化配置文件 ──

function Setup-Config {
    $configFile = "$SENSENOVA_CLAW_HOME\config.yml"
    $exampleFile = "$APP_DIR\config_example.yml"

    if (Test-Path $configFile) {
        Info "检测到已有配置文件，跳过"
        Log "保留现有配置: $configFile"
        return
    }

    if (Test-Path $exampleFile) {
        Copy-Item $exampleFile $configFile
        Log "已从 config_example.yml 生成配置文件"
        Info "请编辑 $configFile 填入 LLM API Key 等配置"
    } else {
        Warn "未找到 config_example.yml，请手动创建 config.yml"
    }
}

# ── 步骤 7: 注册全局命令 ──

function Register-Command {
    Info "注册 sensenova-claw 命令..."
    Push-Location $APP_DIR

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    uv tool install --editable --from . --force sensenova-claw 2>$null
    if ($LASTEXITCODE -ne 0) {
        Warn "uv tool install 失败，尝试 uv pip install..."
        uv pip install -e . 2>$null
        if ($LASTEXITCODE -ne 0) {
            Warn "uv pip install 失败，尝试 pip install..."
            pip install -e . 2>$null
        }
    }

    $ErrorActionPreference = $prevEAP

    Pop-Location

    # 刷新 PATH
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

    if (Command-Exists sensenova-claw) {
        Log "sensenova-claw 命令已注册"
    } else {
        Warn "sensenova-claw 命令未在 PATH 中找到，你可能需要重新打开终端"
    }
}

# ── 步骤 8: 完成 ──

function Print-Success {
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host "  Sensenova-Claw 安装完成!" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  安装目录: $APP_DIR"
    Write-Host "  数据目录: $SENSENOVA_CLAW_HOME"
    Write-Host "  安装来源: $REPO_URL@$REPO_REF"
    Write-Host ""
    if ($IS_CN) {
        Write-Host "  已配置国内镜像: npm($CN_NPM_REGISTRY) pip($CN_PIP_INDEX)"
        Write-Host ""
    }
    Write-Host "  下一步:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    1. 启动服务:"
    Write-Host "       sensenova-claw run" -ForegroundColor White
    Write-Host ""
    Write-Host "    2. 打开 Web 界面进行 LLM 等配置:"
    Write-Host "       http://localhost:3000" -ForegroundColor White
    Write-Host ""
    Write-Host "    或使用 CLI 客户端（需先启动服务）:"
    Write-Host "       sensenova-claw cli" -ForegroundColor White
    Write-Host ""
    Write-Host "  文档: https://github.com/SenseTime-FVG/sensenova-claw"
    Write-Host ""
}

# ── 主流程 ──

function Main {
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "         Sensenova-Claw 一键安装脚本 (Windows)        " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""

    # 选择安装路径
    $script:SENSENOVA_CLAW_HOME = Prompt-Input "安装路径" $SENSENOVA_CLAW_HOME
    $script:APP_DIR = "$SENSENOVA_CLAW_HOME\app"
    Log "安装到: $SENSENOVA_CLAW_HOME"
    Write-Host ""

    Detect-Region
    Configure-CN-Mirrors
    Install-Uv
    Install-Python
    Install-Fnm
    Install-Node
    Setup-Repo
    Install-Deps
    Setup-HomeDir
    Setup-Config
    Register-Command
    Print-Success
}

Main
