# Sensenova-Claw 一键安装脚本（Windows PowerShell）
#
# 用法:
#   远程执行（普通用户）:
#     irm https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.ps1 | iex
#
#   本地执行（普通用户）:
#     powershell -ExecutionPolicy Bypass -File install\install.ps1
#
#   开发者模式（跳过前端 build/精简，APP_DIR 是完整源码目录，editable 安装，改代码即时生效）:
#     本地执行（已有源码）:
#       powershell -ExecutionPolicy Bypass -File install\install.ps1 -Dev
#       powershell -ExecutionPolicy Bypass -File install\install.ps1 -Dev -DevSource d:\code\sensenova-claw
#
#     远程执行（irm | iex，脚本会 clone 源码到 $SENSENOVA_CLAW_HOME\src）:
#       $env:SENSENOVA_CLAW_DEV = "1"
#       irm https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.ps1 | iex
#
#   参数:
#     -Dev              启用开发者模式（等价环境变量 SENSENOVA_CLAW_DEV=1）
#     -DevSource <path> 源码路径；省略时依次回退到 SENSENOVA_CLAW_DEV_SOURCE、脚本所在仓库、自动 clone
#     -InstallHome <p>  自定义 SENSENOVA_CLAW_HOME（配置/数据目录），默认 $env:USERPROFILE\.sensenova-claw
#     -Ref <branch>     clone 的分支/tag（正常模式和开发模式远程 clone 都生效），默认 dev
#

param(
    [switch]$Dev,
    [string]$DevSource,
    [Alias("Home")][string]$InstallHome,
    [string]$Ref
)

$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

# ── 配置 ──（CLI 参数优先，环境变量次之，默认值兜底）

$SENSENOVA_CLAW_HOME = if ($InstallHome) { $InstallHome } elseif ($env:SENSENOVA_CLAW_HOME) { $env:SENSENOVA_CLAW_HOME } else { "$env:USERPROFILE\.sensenova-claw" }
$APP_DIR = "$SENSENOVA_CLAW_HOME\app"
$REPO_URL = if ($env:SENSENOVA_CLAW_REPO_URL) { $env:SENSENOVA_CLAW_REPO_URL } else { "https://github.com/SenseTime-FVG/sensenova-claw.git" }
$REPO_REF = if ($Ref) { $Ref } elseif ($env:SENSENOVA_CLAW_APP_BRANCH) { $env:SENSENOVA_CLAW_APP_BRANCH } elseif ($env:SENSENOVA_CLAW_REPO_REF) { $env:SENSENOVA_CLAW_REPO_REF } elseif ($env:SENSENOVA_CLAW_REPO_BRANCH) { $env:SENSENOVA_CLAW_REPO_BRANCH } else { "dev" }
$REQUIRED_PYTHON = "3.12"
$REQUIRED_NODE = 18

# 开发者模式触发：-Dev 开关 / SENSENOVA_CLAW_DEV=1 / SENSENOVA_CLAW_DEV_SOURCE 非空（任一即可）
# 源码路径优先级：-DevSource > SENSENOVA_CLAW_DEV_SOURCE > 脚本所在仓库 > 自动 clone 到 $SENSENOVA_CLAW_HOME\src
$DEV_MODE = [bool]($Dev -or $env:SENSENOVA_CLAW_DEV -or $env:SENSENOVA_CLAW_DEV_SOURCE)
$DEV_SOURCE = $null
$DEV_NEEDS_CLONE = $false
if ($DEV_MODE) {
    $rawSource = if ($DevSource) { $DevSource } `
                 elseif ($env:SENSENOVA_CLAW_DEV_SOURCE) { $env:SENSENOVA_CLAW_DEV_SOURCE } `
                 elseif ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } `
                 else { $null }
    if ($rawSource) {
        $resolved = Resolve-Path $rawSource -ErrorAction SilentlyContinue
        # 需同时满足 pyproject.toml 和 gateway/main.py，避免 $PSScriptRoot 落在无关仓库时误判
        if ($resolved -and `
            (Test-Path "$($resolved.Path)\pyproject.toml") -and `
            (Test-Path "$($resolved.Path)\sensenova_claw\app\gateway\main.py")) {
            $DEV_SOURCE = $resolved.Path
        }
    }
    if (-not $DEV_SOURCE) {
        # 远程 irm|iex 场景：无 $PSScriptRoot、用户未传 -DevSource → 自动 clone 源码
        $DEV_NEEDS_CLONE = $true
    }
}

# 国内镜像
$CN_NPM_REGISTRY = "https://registry.npmmirror.com"
$CN_PIP_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
$CN_NODE_MIRROR = "https://npmmirror.com/mirrors/node"

$IS_CN = $false

# ── 工具函数 ──

function Log { param($msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Err { param($msg) Write-Host "[x] $msg" -ForegroundColor Red }
function Info { param($msg) Write-Host "[i] $msg" -ForegroundColor Cyan }

function Fail {
    param($msg)
    Err $msg
    Write-Host ""
    Write-Host "安装中断，请根据以上错误信息排查后重试。" -ForegroundColor Yellow
    throw $msg
}

# 安全执行远程安装脚本：下载内容后替换 exit 为 return，防止终止宿主进程
function Invoke-RemoteInstall {
    param($url)
    $scriptContent = Invoke-RestMethod $url
    $safeScript = $scriptContent -replace '\bexit\b', 'return'
    Invoke-Expression $safeScript
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

# ── 步骤 1b: 安装 git ──

function Install-Git {
    if (Command-Exists git) {
        Log "git 已安装: $(git --version)"
        return
    }

    Info "安装 git..."

    # 方式 1: 尝试 winget
    if (Command-Exists winget) {
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements 2>$null
        # 刷新 PATH（winget 装在 Program Files）
        $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Command-Exists git) {
            Log "git 安装成功: $(git --version)"
            return
        }
        Warn "winget 安装 git 失败"
    }

    # 方式 2: 提示手动安装（Git 没有可靠的便携 zip 发行）
    Fail "无法自动安装 git，请手动安装后重试: https://git-scm.com/download/win"
}

# ── 步骤 2: 安装 uv + Python ──

function Install-Uv {
    if (Command-Exists uv) {
        Log "uv 已安装: $(uv --version)"
        return
    }

    Info "安装 uv..."
    Invoke-RemoteInstall "https://astral.sh/uv/install.ps1"

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

# ── 步骤 3: 安装 Node.js ──

function Install-Node {
    if (Command-Exists node) {
        $nodeVer = (node -v) -replace '^v', '' -replace '\..*', ''
        if ([int]$nodeVer -ge $REQUIRED_NODE) {
            Log "Node.js 已安装: $(node -v)"
            return
        }
        Warn "Node.js 版本 $(node -v) 低于要求的 v$REQUIRED_NODE"
    }

    # 方式 1: 尝试 winget
    if (Command-Exists winget) {
        Info "通过 winget 安装 Node.js LTS..."
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements 2>$null
        # winget 安装后刷新 PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Command-Exists node) {
            Log "Node.js 安装成功: $(node -v)"
            return
        }
        Warn "winget 安装 Node.js 失败，尝试直接下载"
    }

    # 方式 2: 直接从 nodejs.org 下载 zip 到用户目录
    Info "从 nodejs.org 下载 Node.js..."
    $nodeDir = "$SENSENOVA_CLAW_HOME\node"

    # 获取最新 LTS 版本号
    $nodeVersions = Invoke-RestMethod "https://nodejs.org/dist/index.json"
    $ltsVersion = ($nodeVersions | Where-Object { $_.lts } | Select-Object -First 1).version
    if (-not $ltsVersion) {
        Fail "无法获取 Node.js LTS 版本信息"
    }
    Info "最新 LTS 版本: $ltsVersion"

    $nodeZip = "$env:TEMP\node-$ltsVersion-win-x64.zip"
    $nodeMirror = if ($IS_CN) { $CN_NODE_MIRROR } else { "https://nodejs.org/dist" }
    $prevProgressPref = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri "$nodeMirror/$ltsVersion/node-$ltsVersion-win-x64.zip" -OutFile $nodeZip -UseBasicParsing
    $ProgressPreference = $prevProgressPref

    # 解压到用户目录
    New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
    Expand-Archive -Path $nodeZip -DestinationPath $nodeDir -Force
    Remove-Item $nodeZip -ErrorAction SilentlyContinue

    # 添加到 PATH
    $env:PATH = "$nodeDir\node-$ltsVersion-win-x64;$env:PATH"

    if ((Command-Exists node) -and (Command-Exists npm)) {
        Log "Node.js 安装成功: $(node -v)"
        if ($IS_CN) {
            npm config set registry $CN_NPM_REGISTRY
        }
    } else {
        Fail "Node.js 安装失败"
    }
}

# ── 步骤 3.5: 安装 Git ──

function Install-Git {
    if (Command-Exists git) {
        Log "Git 已安装: $(git --version)"
        return
    }

    # 方式 1: 尝试 winget
    if (Command-Exists winget) {
        Info "通过 winget 安装 Git..."
        winget install Git.Git --accept-package-agreements --accept-source-agreements 2>$null
        # 刷新 PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Command-Exists git) {
            Log "Git 安装成功: $(git --version)"
            return
        }
        Warn "winget 安装 Git 失败，尝试下载 MinGit"
    }

    # 方式 2: 下载 MinGit 到用户目录（便携版 Git，标准 zip，约 45MB）
    Info "从 GitHub 获取 MinGit 最新版本..."
    try {
        $release = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest" -Headers @{ "User-Agent" = "sensenova-claw-installer" } -TimeoutSec 15
        $asset = $release.assets | Where-Object { $_.name -match "^MinGit-.*-64-bit\.zip$" } | Select-Object -First 1
        if (-not $asset) {
            Fail "未找到 MinGit 下载地址，请手动安装 Git: https://git-scm.com/download/win"
        }
        $tag = $release.tag_name
        $assetName = $asset.name
        $githubUrl = $asset.browser_download_url
        $primaryUrl = if ($IS_CN) {
            "https://registry.npmmirror.com/-/binary/git-for-windows/$tag/$assetName"
        } else {
            $githubUrl
        }
    } catch {
        Fail "获取 Git 下载地址失败: $_。请手动安装 Git: https://git-scm.com/download/win"
    }

    $gitDir = "$SENSENOVA_CLAW_HOME\git"
    $gitZip = "$env:TEMP\$assetName"
    $prevProgressPref = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"

    Info "下载 MinGit: $primaryUrl"
    $downloaded = $false
    try {
        Invoke-WebRequest -Uri $primaryUrl -OutFile $gitZip -UseBasicParsing
        $downloaded = $true
    } catch {
        Warn "下载失败: $_"
    }
    if ((-not $downloaded) -and $IS_CN -and ($primaryUrl -ne $githubUrl)) {
        Warn "国内镜像不可用，回退到 GitHub 直链..."
        try {
            Invoke-WebRequest -Uri $githubUrl -OutFile $gitZip -UseBasicParsing
            $downloaded = $true
        } catch {
            Warn "GitHub 下载也失败: $_"
        }
    }
    $ProgressPreference = $prevProgressPref

    if (-not $downloaded) {
        Fail "MinGit 下载失败，请手动安装 Git: https://git-scm.com/download/win"
    }

    New-Item -ItemType Directory -Force -Path $gitDir | Out-Null
    Expand-Archive -Path $gitZip -DestinationPath $gitDir -Force
    Remove-Item $gitZip -ErrorAction SilentlyContinue

    # 添加到 PATH（当前进程）
    $env:PATH = "$gitDir\cmd;$env:PATH"

    if (Command-Exists git) {
        Log "Git (MinGit) 安装成功: $(git --version)"
    } else {
        Fail "Git 安装失败，请手动安装: https://git-scm.com/download/win"
    }
}

# ── 步骤 4: 克隆/更新仓库 ──

# 返回用于 clone/fetch 的 URL 列表：原始 URL 优先，失败后用 GitHub 代理镜像兜底
function Resolve-RepoUrls {
    $urls = @($REPO_URL)
    # 仅 github.com 的 URL 才能套公共代理
    if ($REPO_URL -match '^https?://github\.com/') {
        foreach ($proxy in @("https://gh-proxy.com/", "https://ghfast.top/", "https://mirror.ghproxy.com/")) {
            $urls += "$proxy$REPO_URL"
        }
    }
    return $urls
}

function Setup-Repo {
    # 开发者模式：$APP_DIR 必须指向完整源码目录（本地已有 或 远程 clone 出来）
    # 这样后续 Install-Deps / Setup-HomeDir / Register-Command 都在源码目录上操作，
    # editable 安装 + 源码目录本身 = 改源码立即生效。
    if ($DEV_MODE) {
        if (-not $DEV_NEEDS_CLONE) {
            Info "开发者模式：使用本地源码，跳过 clone"
            Log "源码目录: $DEV_SOURCE"
            return
        }

        # 远程模式：clone 到 $SENSENOVA_CLAW_HOME\src（和 \app 区分，语义更清晰）
        $srcDir = "$SENSENOVA_CLAW_HOME\src"
        Info "开发者模式（远程）：未检测到本地源码，将 clone 到 $srcDir"

        $urls = Resolve-RepoUrls
        if (Test-Path "$srcDir\.git") {
            Info "更新 Sensenova-Claw 源码 ($REPO_REF)..."
            Push-Location $srcDir
            try {
                $fetched = $false
                foreach ($url in $urls) {
                    git remote set-url origin $url 2>$null
                    git fetch origin $REPO_REF --quiet 2>$null
                    if ($LASTEXITCODE -eq 0) { $fetched = $true; break }
                }
                git remote set-url origin $REPO_URL 2>$null
                if ($fetched) {
                    git checkout $REPO_REF --quiet 2>$null
                    if ($LASTEXITCODE -ne 0) {
                        git checkout -B $REPO_REF "origin/$REPO_REF" --quiet 2>$null
                    }
                    git reset --hard "origin/$REPO_REF" --quiet 2>$null
                    Log "源码已更新到 $REPO_REF"
                } else {
                    Warn "无法拉取更新，使用当前本地副本"
                }
            } catch {
                Warn "git 更新失败: $_"
            }
            Pop-Location
        } else {
            $parent = Split-Path $srcDir -Parent
            New-Item -ItemType Directory -Force -Path $parent | Out-Null

            $cloned = $false
            foreach ($url in $urls) {
                if ($url -eq $REPO_URL) {
                    Info "使用源: $url"
                } else {
                    Warn "直连失败，尝试代理: $url"
                }
                # 注意：开发模式下 clone 完整历史（不加 --depth 1），方便切分支/改提交
                git clone --branch $REPO_REF $url $srcDir
                if ($LASTEXITCODE -eq 0) { $cloned = $true; break }
                if (Test-Path $srcDir) {
                    Remove-Item $srcDir -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
            if (-not $cloned) {
                Fail "无法克隆仓库，请检查网络或设置 SENSENOVA_CLAW_REPO_URL"
            }
            # 若通过代理完成克隆，恢复 origin 为原始 URL
            Push-Location $srcDir
            git remote set-url origin $REPO_URL 2>$null
            Pop-Location
            Log "源码克隆完成: $srcDir"
        }

        # 把 APP_DIR 切到 clone 出来的源码目录
        $script:DEV_SOURCE = (Resolve-Path $srcDir).Path
        $script:APP_DIR = $script:DEV_SOURCE
        return
    }

    $urls = Resolve-RepoUrls

    if (Test-Path "$APP_DIR\.git") {
        Info "更新 Sensenova-Claw ($REPO_REF)..."
        Push-Location $APP_DIR
        try {
            $fetched = $false
            foreach ($url in $urls) {
                if ($url -ne $REPO_URL) {
                    Warn "直连 GitHub 失败，尝试代理: $url"
                }
                # 临时将 origin 切到当前候选源后拉取
                git remote set-url origin $url 2>$null
                # 强制刷新 tags 和分支，确保 force-push 的 tag 也能更新
                git fetch origin --tags --force --depth 1 --quiet 2>$null
                if ($LASTEXITCODE -eq 0) {
                    git fetch origin $REPO_REF --depth 1 --quiet 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        $fetched = $true
                        break
                    }
                }
            }
            # 无论成败都恢复 origin 为原始 URL，避免污染用户本地 remote
            git remote set-url origin $REPO_URL 2>$null

            if (-not $fetched) {
                Warn "所有源均无法拉取更新，跳过更新"
            } else {
                $remoteBranchRef = "refs/remotes/origin/$REPO_REF"
                git show-ref --verify --quiet $remoteBranchRef 2>$null
                if ($LASTEXITCODE -eq 0) {
                    git checkout $REPO_REF --quiet 2>$null
                    if ($LASTEXITCODE -ne 0) {
                        git checkout -B $REPO_REF "origin/$REPO_REF" --quiet 2>$null
                    }
                    git reset --hard "origin/$REPO_REF" --quiet 2>$null
                } else {
                    # tag 或 detached ref
                    git checkout --detach FETCH_HEAD --quiet 2>$null
                }
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

        $cloned = $false
        $usedUrl = $null
        foreach ($url in $urls) {
            if ($url -eq $REPO_URL) {
                Info "使用源: $url"
            } else {
                Warn "直连 GitHub 失败，尝试代理: $url"
            }
            git clone --branch $REPO_REF --depth 1 $url $APP_DIR
            if ($LASTEXITCODE -eq 0) {
                $cloned = $true
                $usedUrl = $url
                break
            }
            # 清理 clone 失败可能残留的部分文件
            if (Test-Path $APP_DIR) {
                Remove-Item $APP_DIR -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        if (-not $cloned) {
            Fail "无法克隆仓库，请检查网络，或设置 SENSENOVA_CLAW_REPO_URL 指向可访问的镜像"
        }
        # 若通过代理完成克隆，恢复 origin 为原始 URL 便于后续手动操作
        if ($usedUrl -ne $REPO_URL) {
            Push-Location $APP_DIR
            git remote set-url origin $REPO_URL 2>$null
            Pop-Location
        }
        Log "Sensenova-Claw 克隆完成"
    }
}

# ── 步骤 5: 安装项目依赖 ──

function Install-Deps {
    Info "安装项目依赖..."
    Push-Location $APP_DIR
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $hasNativePref = $null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)
    if ($hasNativePref) {
        $prevNativeEAP = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    # 1) Python 依赖
    Info "安装 Python 依赖..."
    # 用 cmd /c 包裹避免 PowerShell 将 stderr 进度信息误报为错误
    cmd /c "uv sync 2>&1" | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) { Fail "Python 依赖安装失败（uv sync）" }
    Log "Python 依赖安装完成"

    # 2) 根目录 npm 依赖（跳过 postinstall，避免重复）
    Info "安装根目录 npm 依赖..."
    cmd /c "npm install --ignore-scripts 2>&1" | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) { Fail "根目录 npm 依赖安装失败" }
    Log "根目录 npm 依赖安装完成"

    # 3) 前端依赖
    Info "安装前端依赖..."
    Push-Location "$APP_DIR\sensenova_claw\app\web"
    cmd /c "npm install 2>&1" | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) { Fail "前端 npm 依赖安装失败" }
    Log "前端依赖安装完成"

    # 4) 确保 next.config.mjs 启用 standalone 输出
    $nextConfig = "$APP_DIR\sensenova_claw\app\web\next.config.mjs"
    if (Test-Path $nextConfig) {
        $content = Get-Content $nextConfig -Raw
        if ($content -notmatch "output:\s*['""]standalone['""]") {
            Info "为 next.config.mjs 注入 output: 'standalone'..."
            $content = $content -replace "(const nextConfig\s*=\s*\{)", "`$1`n  output: 'standalone',"
            Set-Content $nextConfig $content -Encoding UTF8
        }
    }

    # 5) 构建前端生产版本（standalone 模式）——开发者模式跳过
    if ($DEV_MODE) {
        Info "开发者模式：跳过 npm run build 与前端产物精简，保留 node_modules 以便 npm run dev:web"
        Pop-Location
        Pop-Location
        Log "项目依赖安装完成（开发者模式）"
        if ($hasNativePref) {
            $PSNativeCommandUseErrorActionPreference = $prevNativeEAP
        }
        $ErrorActionPreference = $prevEAP
        return
    }

    Info "构建前端生产版本（standalone 模式）..."
    cmd /c "npm run build 2>&1"
    if ($LASTEXITCODE -ne 0) { Fail "前端生产构建失败（npm run build）" }
    Log "前端生产构建完成"

    # 6) 精简前端产物
    $webDir = "$APP_DIR\sensenova_claw\app\web"
    $standaloneDir = "$webDir\.next\standalone"
    if (Test-Path $standaloneDir) {
        Info "精简前端产物，移除开发依赖..."

        # 将 public/ 和 .next/static/ 复制到 standalone 目录
        if (Test-Path "$webDir\public") {
            Copy-Item "$webDir\public" "$standaloneDir\public" -Recurse -ErrorAction SilentlyContinue
        }
        New-Item -ItemType Directory -Force -Path "$standaloneDir\.next" | Out-Null
        Copy-Item "$webDir\.next\static" "$standaloneDir\.next\static" -Recurse

        # 删除 .next/ 下非 standalone 的构建产物（cache/server/trace 等，~400 MB）
        Get-ChildItem "$webDir\.next" -Directory | Where-Object { $_.Name -ne "standalone" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem "$webDir\.next" -File | Where-Object { $_.Name -ne "BUILD_ID" } | Remove-Item -Force -ErrorAction SilentlyContinue

        # 删除前端 node_modules（~600 MB）
        Remove-Item "$webDir\node_modules" -Recurse -Force -ErrorAction SilentlyContinue
        Log "前端产物已精简（仅保留 standalone + BUILD_ID）"
    } else {
        Warn "未生成 standalone 产物，保留 node_modules"
    }

    Pop-Location

    # 6) 清理插件 node_modules
    $whatsappModules = "$APP_DIR\sensenova_claw\adapters\plugins\whatsapp\bridge\node_modules"
    if (Test-Path $whatsappModules) {
        Remove-Item $whatsappModules -Recurse -Force -ErrorAction SilentlyContinue
        Log "WhatsApp bridge node_modules 已清理"
    }

    if ($hasNativePref) {
        $PSNativeCommandUseErrorActionPreference = $prevNativeEAP
    }
    $ErrorActionPreference = $prevEAP

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
    if ($DEV_MODE) {
        Write-Host "  模式:     开发模式"
        Write-Host "  代码目录: $APP_DIR"
    } else {
        Write-Host "  模式:     生产模式（前端已预构建）"
        Write-Host "  安装目录: $APP_DIR"
        Write-Host "  安装来源: $REPO_URL@$REPO_REF"
    }
    Write-Host "  数据目录: $SENSENOVA_CLAW_HOME"
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

    if ($DEV_MODE) {
        Write-Host "  [开发者模式] 跳过 npm run build / 前端精简，editable 安装，改代码即时生效" -ForegroundColor Magenta
        if ($DEV_NEEDS_CLONE) {
            Write-Host "  [开发者模式] 远程模式：将 clone 源码到 $SENSENOVA_CLAW_HOME\src" -ForegroundColor Magenta
        } else {
            Write-Host "  [开发者模式] 源码: $DEV_SOURCE" -ForegroundColor Magenta
        }
        Write-Host ""

        # 本地源码已就绪时，APP_DIR 直接指向源码；远程 clone 情况由 Setup-Repo 回填
        if (-not $DEV_NEEDS_CLONE) {
            $script:APP_DIR = $DEV_SOURCE
        }
        Log "数据目录: $SENSENOVA_CLAW_HOME"
        Write-Host ""

        Detect-Region
        Configure-CN-Mirrors
        Install-Git      # 远程模式要 clone；本地模式这步会秒过
        Install-Uv
        Install-Python
        Install-Node
        Setup-Repo       # 本地：立即返回；远程：clone 并回填 $APP_DIR
        Install-Deps
        Setup-HomeDir
        Setup-Config
        Register-Command
        Print-Success
        return
    }

    # 选择安装路径（仅正常模式）
    $script:SENSENOVA_CLAW_HOME = Prompt-Input "安装路径" $SENSENOVA_CLAW_HOME
    $script:APP_DIR = "$SENSENOVA_CLAW_HOME\app"
    Log "安装到: $SENSENOVA_CLAW_HOME"
    Write-Host ""

    Detect-Region
    Configure-CN-Mirrors
    Install-Git
    Install-Uv
    Install-Python
    Install-Node
    Setup-Repo
    Install-Deps
    Setup-HomeDir
    Setup-Config
    Register-Command
    Print-Success
}

Main
