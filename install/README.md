# Sensenova-Claw 安装指南

## 一键安装

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.sh | bash
```

### Windows（PowerShell）

```powershell
irm https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.ps1 | iex
```

> 如果 PowerShell 提示执行策略限制，先运行: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 指定安装版本

安装脚本默认拉取 `dev` 分支，也支持通过环境变量显式指定分支或 tag，便于发布验证与回滚。

Linux / macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.sh | SENSENOVA_CLAW_REPO_REF=v0.5.0 bash
```

Windows（PowerShell）:

```powershell
$env:SENSENOVA_CLAW_REPO_REF="v0.5.0"
irm https://raw.githubusercontent.com/SenseTime-FVG/sensenova_claw/dev/install/install.ps1 | iex
```

## 安装脚本做了什么

脚本会自动完成以下步骤：

| 步骤 | 说明 |
|------|------|
| 1. 选择安装路径 | 默认 `~/.sensenova-claw`，可自定义 |
| 2. 地区检测 | 通过 iping.cc API 判断国内/海外，国内自动配置 npm 和 pip 镜像 |
| 3. 安装 Python | 通过 [uv](https://docs.astral.sh/uv/) 安装 Python 3.12+（已有则跳过） |
| 4. 安装 Node.js | 通过 [nvm](https://github.com/nvm-sh/nvm)（Linux/macOS）或 [fnm](https://github.com/Schniz/fnm)（Windows）安装 Node.js 18+（已有则跳过） |
| 5. 克隆仓库 | 将 Sensenova-Claw 克隆到 `{安装路径}/app/`（已存在则更新） |
| 6. 安装依赖 | `npm install` 自动安装 Node.js 和 Python 依赖 |
| 7. 初始化目录 | 创建 SENSENOVA_CLAW_HOME 目录结构，复制预置 agents 和 skills |
| 8. 初始化配置 | 从 `config_example.yml` 生成 `config.yml`（已有则跳过） |
| 9. 注册命令 | 以 editable 模式注册全局 `sensenova-claw` 命令，避免 CLI 与安装目录代码漂移 |

## 安装完成后

**1. 启动服务**

```bash
sensenova-claw run
```

**2. 配置 LLM 等设置**

启动后，打开 Web 界面进行配置：

- Web Dashboard: http://localhost:3000

或使用 CLI 客户端（需先启动服务）：

```bash
sensenova-claw cli
```

首次启动时，终端会打印带 token 的访问 URL，复制到浏览器即可访问 Dashboard。

## 目录结构

安装完成后的目录结构：

```
~/.sensenova-claw/                # SENSENOVA_CLAW_HOME（可自定义）
├── app/                   # Sensenova-Claw 程序代码（git 仓库）
│   ├── config.yml         # 配置文件（安装时自动生成）
│   ├── config_example.yml # 配置示例
│   └── ...
├── agents/                # Agent 配置（预置 + 用户自建）
│   └── default/           # 默认 Agent
│       ├── AGENTS.md
│       └── USER.md
├── skills/                # Skills（预置 + 用户安装）
│   ├── pptx/
│   ├── paddleocr-doc-parsing/
│   └── ...
├── data/                  # 数据库
├── db/                    # SQLite 数据库
└── workdir/               # Agent 工作目录
    └── default/
```

## 国内镜像说明

安装脚本会自动检测是否在国内网络，如果是，将配置以下镜像：

| 工具 | 镜像地址 |
|------|----------|
| npm | `https://registry.npmmirror.com` |
| pip/uv | `https://mirrors.aliyun.com/pypi/simple/` |
| Node.js 下载 | `https://npmmirror.com/mirrors/node` |

如需手动配置或取消镜像：

```bash
# npm
npm config set registry https://registry.npmmirror.com   # 设置
npm config delete registry                                 # 取消

# uv/pip（编辑 ~/.config/uv/uv.toml）
# 删除该文件即可恢复默认源
```

## 手动安装

如果一键安装脚本不适用，可以手动安装：

### 1. 安装前置依赖

- **Python 3.12+**: https://www.python.org/downloads/ 或通过 uv: `curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.12`
- **Node.js 18+**: https://nodejs.org/ 或通过 nvm: `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash && nvm install --lts`
- **Git**: https://git-scm.com/downloads

### 2. 克隆并安装

```bash
git clone https://github.com/SenseTime-FVG/sensenova-claw.git ~/.sensenova-claw/app
cd ~/.sensenova-claw/app
npm install
```

### 3. 初始化目录

```bash
# 复制预置 agents 和 skills
cp -rn .sensenova-claw/agents/* ~/.sensenova-claw/agents/
cp -rn .sensenova-claw/skills/* ~/.sensenova-claw/skills/

# 创建数据目录
mkdir -p ~/.sensenova-claw/{data,db,workdir/default}
```

### 4. 配置

```bash
cp config_example.yml config.yml
# 编辑 config.yml，填入 LLM provider 和 API Key
```

### 5. 启动

```bash
sensenova-claw run
# 或
python3 -m sensenova_claw.app.main run
```

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux / macOS / Windows 10+ |
| Python | >= 3.12（脚本自动安装） |
| Node.js | >= 18（脚本自动安装） |
| Git | 任意版本 |
| 磁盘空间 | >= 500MB |
| 网络 | 需要访问 GitHub 和 LLM API |

## 常见问题

### Q: 安装后 `sensenova-claw` 命令找不到

重新打开终端，或手动将 `~/.local/bin` 添加到 PATH：

```bash
# Linux/macOS（添加到 ~/.bashrc 或 ~/.zshrc）
export PATH="$HOME/.local/bin:$PATH"
```

### Q: npm install 失败

检查网络连接，如果在国内，确认镜像是否配置：

```bash
npm config get registry
# 应该显示 https://registry.npmmirror.com
```

### Q: Python 版本不对

安装脚本使用 uv 管理 Python 版本，不影响系统自带的 Python：

```bash
uv python list    # 查看已安装的 Python 版本
uv python install 3.12  # 手动安装
```

### Q: Windows 上 PowerShell 无法执行脚本

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q: 如何更新 Sensenova-Claw

```bash
cd ~/.sensenova-claw/app
git pull origin dev
npm install
```

### Q: 如何重新配置 LLM

直接编辑配置文件：

```bash
vim ~/.sensenova-claw/app/config.yml
```

或重新运行安装脚本（会询问是否覆盖现有配置）。

### Q: 如何卸载

```bash
# 删除安装目录
rm -rf ~/.sensenova-claw

# 移除全局命令
uv tool uninstall sensenova-claw

# 可选：移除镜像配置
rm -f ~/.config/uv/uv.toml
npm config delete registry
```
