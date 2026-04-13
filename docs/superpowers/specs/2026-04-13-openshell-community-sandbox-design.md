# Sensenova-Claw OpenShell 社区 Sandbox 设计

## 概述

将 sensenova-claw 打包为 OpenShell 社区 sandbox，用户通过一条命令即可在隔离沙箱中启动完整的 AI Agent 平台（后端 + 前端 Dashboard），并在 Web 界面内完成所有配置。

## 用户体验

### 启动命令

```bash
openshell sandbox create \
  --forward 8000 --forward 3000 \
  --from sensenova-claw \
  -- sensenova-claw-start
```

### 使用流程

1. 执行上述命令，等待构建和启动（首次约数分钟，后续约 10 秒）
2. 浏览器访问 `http://127.0.0.1:3000`（Dashboard）
3. 在界面内配置 LLM provider 和 API key
4. 开始使用

### 工作区挂载

用户可将宿主机项目目录挂载到沙箱内供 Agent 操作：

```bash
openshell sandbox create \
  --forward 8000 --forward 3000 \
  --from sensenova-claw \
  --mount ~/my-project:/sandbox/workspace \
  -- sensenova-claw-start
```

## 文件结构

在 OpenShell-Community 仓库 `sandboxes/` 下新增：

```
sandboxes/sensenova-claw/
├── Dockerfile              # 多阶段构建
├── policy.yaml             # 网络与文件系统策略
├── sensenova-claw-start    # 启动脚本
└── README.md               # 社区文档
```

## Dockerfile：多阶段构建

### Stage 1：前端构建

- 基础镜像：`node:18-slim`
- 执行 `npm ci` + `npm run build`
- 产出 `.next/standalone/`（Next.js standalone 模式）和 `.next/static/`

### Stage 2：Python 运行时

- 基础镜像：`python:3.12-slim`
- 安装 OpenShell 必需系统包：`iproute2`、`iptables`、`curl`
- 安装 `nodejs`（apt，仅用于运行 Next.js standalone server）
- 创建 `sandbox` 用户（uid/gid 1000）
- `pip install .` 安装 sensenova-claw Python 包
- 从 Stage 1 复制前端构建产物到 `/opt/sensenova-claw/web/`
- 复制启动脚本到 `/usr/local/bin/`
- 预创建 `~/.sensenova-claw/data/` 数据目录

### 完整 Dockerfile

```dockerfile
# ── Stage 1: 构建前端 ──
FROM node:18-slim AS frontend-build
WORKDIR /build
COPY sensenova_claw/app/web/package*.json ./
RUN npm ci
COPY sensenova_claw/app/web/ ./
RUN npm run build

# ── Stage 2: Python 运行时 ──
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl iproute2 iptables nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 sandbox && \
    useradd -m -u 1000 -g sandbox sandbox

WORKDIR /opt/sensenova-claw
COPY pyproject.toml .
COPY sensenova_claw/ sensenova_claw/
RUN pip install --no-cache-dir .

COPY --from=frontend-build /build/.next/standalone /opt/sensenova-claw/web
COPY --from=frontend-build /build/.next/static /opt/sensenova-claw/web/.next/static
COPY --from=frontend-build /build/public /opt/sensenova-claw/web/public

COPY sandboxes/sensenova-claw/sensenova-claw-start /usr/local/bin/
RUN chmod +x /usr/local/bin/sensenova-claw-start

RUN mkdir -p /home/sandbox/.sensenova-claw/data && \
    chown -R sandbox:sandbox /home/sandbox/.sensenova-claw

WORKDIR /sandbox
EXPOSE 8000 3000
```

## 启动脚本 `sensenova-claw-start`

```bash
#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="$HOME/.sensenova-claw"
CONFIG_FILE="$CONFIG_DIR/config.yml"

# ── 1. 生成最小 config（如不存在）──
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<YAML
server:
  host: 0.0.0.0
  port: 8000
  cors_origins:
    - http://localhost:3000
    - http://127.0.0.1:3000

security:
  auth_enabled: false

delegation:
  enabled: true
YAML
    echo "[sensenova-claw] config.yml generated"
fi

# ── 2. 后台启动 Next.js frontend ──
cd /opt/sensenova-claw/web
PORT=3000 HOST=0.0.0.0 node server.js &
FRONTEND_PID=$!
echo "[sensenova-claw] frontend started (PID $FRONTEND_PID, port 3000)"

# ── 3. 前台启动 FastAPI backend ──
echo "[sensenova-claw] starting backend on port 8000..."
exec sensenova-claw run --no-frontend --port 8000
```

关键设计：
- 不预配置 LLM provider — 用户在 Web 界面内自行配置
- 不覆盖已有配置 — `if [ ! -f ]` 判断保护用户自定义
- backend 作为前台进程（`exec`）— OpenShell supervisor 可正确管理生命周期
- frontend 后台运行 — Next.js standalone server 轻量

## 网络策略 `policy.yaml`

```yaml
version: 1

filesystem_policy:
  include_workdir: true
  read_only: [/usr, /lib, /proc, /dev/urandom, /etc, /opt/sensenova-claw]
  read_write: [/sandbox, /tmp, /dev/null, /home/sandbox/.sensenova-claw]

landlock:
  compatibility: best_effort

process:
  run_as_user: sandbox
  run_as_group: sandbox

network_policies:
  general_outbound:
    name: permissive-outbound
    endpoints:
      - { host: "**", port: 443 }
      - { host: "**", port: 80 }
```

设计决策：
- **宽松出站** — 任意进程可访问任意 HTTP/HTTPS 目标，支持 LLM API、搜索工具、网页抓取等
- **文件系统隔离** — `/opt/sensenova-claw` 只读（程序不可篡改），`/sandbox` 读写（用户工作区）
- **无 binaries 限制** — 沙箱内所有进程均可联网
- 策略热可更新 — 用户可通过 `openshell policy set` 收紧

## 对 sensenova-claw 仓库的改动

唯一需要的代码改动：

**`sensenova_claw/app/web/next.config.js`** 添加 `output: 'standalone'`

此配置让 `npm run build` 额外产出 `.next/standalone/` 目录，包含独立的 `server.js` 和最小化 `node_modules`。

影响评估：
- 本地 `npm run dev` 开发不受影响
- `npm run build` 产物增加 standalone 目录，体积略增
- 无破坏性改动

## OpenShell Provider 集成

不需要。sensenova-claw 的所有配置（LLM provider、API key、搜索工具等）在启动后由用户通过 Web Dashboard 界面完成，OpenShell 侧零配置。

## 社区提交规范

按 OpenShell-Community 仓库要求：
- `Dockerfile` — 必需，定义容器镜像
- `README.md` — 必需，使用说明
- `policy.yaml` — 可选，默认安全策略
- 提交 PR 到 `sandboxes/sensenova-claw/` 目录
