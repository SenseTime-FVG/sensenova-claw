# AgentOS 安装指南

## 一键安装

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/SenseTime-FVG/agentos/dev/install/install.sh | bash
```

### Windows（PowerShell）

```powershell
irm https://raw.githubusercontent.com/SenseTime-FVG/agentos/dev/install/install.ps1 | iex
```

> 如果 PowerShell 提示执行策略限制，先运行: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`

## 安装脚本做了什么

脚本会自动完成以下步骤：

| 步骤 | 说明 |
|------|------|
| 1. 地区检测 | 通过 iping.cc API 判断国内/海外，国内自动配置 npm 和 pip 镜像 |
| 2. 安装 Python | 通过 [uv](https://docs.astral.sh/uv/) 安装 Python 3.12+（已有则跳过） |
| 3. 安装 Node.js | 通过 [nvm](https://github.com/nvm-sh/nvm)（Linux/macOS）或 [fnm](https://github.com/Schniz/fnm)（Windows）安装 Node.js 18+（已有则跳过） |
| 4. 克隆仓库 | 将 AgentOS 克隆到 `~/.agentos/app/`（已存在则更新） |
| 5. 安装依赖 | `npm install` 自动安装 Node.js 和 Python 依赖 |
| 6. 交互配置 | 引导选择 LLM 提供商、输入 API Key，生成 `config.yml` |
| 7. 注册命令 | 注册全局 `agentos` 命令 |

## 安装完成后

```bash
# 启动服务（后端 + 前端 Dashboard）
agentos run

# 仅启动后端
agentos run --no-frontend

# 启动 CLI 客户端（需先启动服务）
agentos cli
```

首次启动时，终端会打印带 token 的访问 URL，复制到浏览器即可访问 Dashboard。

## 目录结构

```
~/.agentos/
├── app/             # AgentOS 程序代码
│   ├── config.yml   # 配置文件
│   └── ...
├── data/            # 数据库
├── workspace/       # 工作区
├── agents/          # Agent 配置
└── skills/          # 已安装的 Skills
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
git clone https://github.com/SenseTime-FVG/agentos.git ~/.agentos/app
cd ~/.agentos/app
npm install
```

### 3. 配置

复制示例配置并编辑：

```bash
cp config_example.yml config.yml
# 编辑 config.yml，填入 LLM API Key
```

### 4. 启动

```bash
npm run dev
# 或
python3 -m agentos.app.main run
```

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux / macOS / Windows 10+ |
| Python | >= 3.12 |
| Node.js | >= 18 |
| 磁盘空间 | >= 500MB |
| 网络 | 需要访问 GitHub 和 LLM API |

## 常见问题

### Q: 安装后 `agentos` 命令找不到

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

### Q: 如何卸载

```bash
# 删除安装目录
rm -rf ~/.agentos

# 移除全局命令
uv tool uninstall agentos

# 可选：移除镜像配置
rm -f ~/.config/uv/uv.toml
npm config delete registry
```
