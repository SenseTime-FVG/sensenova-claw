# Sensenova-Claw OpenShell 社区 Sandbox 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 sensenova-claw 打包为 OpenShell 社区 sandbox，用户通过 `openshell sandbox create --from sensenova-claw` 一条命令即可在隔离沙箱中启动完整的 AI Agent 平台（后端 + 前端）。

**Architecture:** 多阶段 Docker 构建 — Stage 1 用 Node.js 构建 Next.js standalone 前端，Stage 2 用 Python 3.12 运行时安装后端并复制前端产物。启动脚本同时拉起前后端服务。所有产物放入 OpenShell-Community 仓库的 `sandboxes/sensenova-claw/` 目录。

**Tech Stack:** Docker multi-stage build, Next.js 14 standalone output, Python 3.12, FastAPI, OpenShell sandbox policy YAML

**Git 分支:** 所有改动在 `feat/openshell-sandbox` 分支上进行，完成后通过 PR 合入 dev。

---

## Task 0: 创建 feature 分支

- [ ] **Step 1: 从 dev 创建并切换到 feature 分支**

```bash
git checkout -b feat/openshell-sandbox
```

---

## File Map

### sensenova-claw 仓库（本仓库）改动

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `sensenova_claw/app/web/next.config.mjs` | 添加 `output: 'standalone'` |

### OpenShell-Community 仓库新增

这些文件在 `~/gitRepos/OpenShell-Community/sandboxes/sensenova-claw/` 下创建（如果该仓库尚未 clone，先在本仓库 `sandboxes/sensenova-claw/` 下编写，后续再提交到社区仓库）。

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `sandboxes/sensenova-claw/Dockerfile` | 多阶段构建镜像 |
| Create | `sandboxes/sensenova-claw/policy.yaml` | 文件系统 + 网络策略 |
| Create | `sandboxes/sensenova-claw/sensenova-claw-start` | 启动脚本 |
| Create | `sandboxes/sensenova-claw/README.md` | 社区文档 |

---

### Task 1: 修改 Next.js 配置添加 standalone 输出

**Files:**
- Modify: `sensenova_claw/app/web/next.config.mjs`

- [ ] **Step 1: 读取当前 next.config.mjs 确认内容**

```bash
cat sensenova_claw/app/web/next.config.mjs
```

确认文件中 `nextConfig` 对象不包含 `output` 字段。

- [ ] **Step 2: 添加 `output: 'standalone'` 到 nextConfig**

在 `sensenova_claw/app/web/next.config.mjs` 中，将：

```javascript
const nextConfig = {
  reactStrictMode: true,
```

改为：

```javascript
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
```

- [ ] **Step 3: 验证前端仍可正常构建**

```bash
cd sensenova_claw/app/web && npm run build
```

Expected: 构建成功，且 `.next/standalone/` 目录存在，包含 `server.js`。

```bash
ls sensenova_claw/app/web/.next/standalone/server.js
```

Expected: 文件存在。

- [ ] **Step 4: 验证本地开发模式不受影响**

```bash
cd sensenova_claw/app/web && timeout 10 npm run dev || true
```

Expected: Next.js dev server 正常启动（超时退出即可，只要没有报错）。

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/app/web/next.config.mjs
git commit -m "feat(web): 添加 Next.js standalone 输出模式，支持 OpenShell 沙箱部署"
```

---

### Task 2: 创建 sandbox 目录结构

**Files:**
- Create: `sandboxes/sensenova-claw/` 目录

- [ ] **Step 1: 创建目录**

```bash
mkdir -p sandboxes/sensenova-claw
```

- [ ] **Step 2: Commit 空目录占位（通过后续文件一起提交）**

无需单独 commit，随 Task 3 一起提交。

---

### Task 3: 编写 Dockerfile

**Files:**
- Create: `sandboxes/sensenova-claw/Dockerfile`

- [ ] **Step 1: 创建 Dockerfile**

写入以下内容到 `sandboxes/sensenova-claw/Dockerfile`：

```dockerfile
# SPDX-FileCopyrightText: Copyright (c) 2026 SenseTime-FVG. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Sensenova-Claw: 事件驱动 AI Agent 平台
# 启动方式: openshell sandbox create --forward 8000 --forward 3000 --from sensenova-claw -- sensenova-claw-start

# ── Stage 1: 构建 Next.js 前端 ──
FROM node:18-slim AS frontend-build
WORKDIR /build
COPY sensenova_claw/app/web/package*.json ./
RUN npm ci
COPY sensenova_claw/app/web/ ./
RUN npm run build
# 产物: .next/standalone/ (含 server.js + 最小 node_modules)
#        .next/static/    (静态资源)

# ── Stage 2: Python 运行时 ──
FROM python:3.12-slim

# OpenShell 必需: iproute2 (网络命名空间), iptables (旁路检测)
# nodejs: 运行 Next.js standalone server
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl iproute2 iptables nodejs \
    && rm -rf /var/lib/apt/lists/*

# OpenShell 要求: sandbox 用户 (uid/gid 1000)
RUN groupadd -g 1000 sandbox && \
    useradd -m -u 1000 -g sandbox sandbox

# 安装 sensenova-claw Python 包
WORKDIR /opt/sensenova-claw
COPY pyproject.toml .
COPY sensenova_claw/ sensenova_claw/
RUN pip install --no-cache-dir .

# 复制前端构建产物
COPY --from=frontend-build /build/.next/standalone /opt/sensenova-claw/web
COPY --from=frontend-build /build/.next/static /opt/sensenova-claw/web/.next/static
COPY --from=frontend-build /build/public /opt/sensenova-claw/web/public

# 启动脚本
COPY sandboxes/sensenova-claw/sensenova-claw-start /usr/local/bin/
RUN chmod +x /usr/local/bin/sensenova-claw-start

# 数据目录
RUN mkdir -p /home/sandbox/.sensenova-claw/data && \
    chown -R sandbox:sandbox /home/sandbox/.sensenova-claw

WORKDIR /sandbox
EXPOSE 8000 3000
```

- [ ] **Step 2: 验证 Dockerfile 语法**

```bash
docker build --check -f sandboxes/sensenova-claw/Dockerfile . 2>&1 || echo "docker check not available, syntax review only"
```

如果 `docker` 不可用，手动检查：
- Stage 1 和 Stage 2 的 FROM 指令正确
- COPY 路径相对于构建上下文（仓库根目录）
- 所有 RUN 指令链式执行并清理缓存

- [ ] **Step 3: Commit**

```bash
git add sandboxes/sensenova-claw/Dockerfile
git commit -m "feat(sandbox): 添加 OpenShell 社区 sandbox Dockerfile（多阶段构建）"
```

---

### Task 4: 编写启动脚本

**Files:**
- Create: `sandboxes/sensenova-claw/sensenova-claw-start`

- [ ] **Step 1: 创建启动脚本**

写入以下内容到 `sandboxes/sensenova-claw/sensenova-claw-start`：

```bash
#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="$HOME/.sensenova-claw"
CONFIG_FILE="$CONFIG_DIR/config.yml"

# ── 1. 生成最小 config（如不存在）──
if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_FILE" <<'YAML'
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
    echo "[sensenova-claw] config.yml generated at $CONFIG_FILE"
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

- [ ] **Step 2: 设置可执行权限**

```bash
chmod +x sandboxes/sensenova-claw/sensenova-claw-start
```

- [ ] **Step 3: 验证脚本语法**

```bash
bash -n sandboxes/sensenova-claw/sensenova-claw-start
```

Expected: 无输出（语法正确）。

- [ ] **Step 4: Commit**

```bash
git add sandboxes/sensenova-claw/sensenova-claw-start
git commit -m "feat(sandbox): 添加 sensenova-claw-start 启动脚本"
```

---

### Task 5: 编写网络策略

**Files:**
- Create: `sandboxes/sensenova-claw/policy.yaml`

- [ ] **Step 1: 创建 policy.yaml**

写入以下内容到 `sandboxes/sensenova-claw/policy.yaml`：

```yaml
# SPDX-FileCopyrightText: Copyright (c) 2026 SenseTime-FVG. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Sensenova-Claw sandbox 策略
# 宽松网络出站 + 文件系统隔离

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

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('sandboxes/sensenova-claw/policy.yaml'))"
```

Expected: 无输出（解析成功）。

- [ ] **Step 3: Commit**

```bash
git add sandboxes/sensenova-claw/policy.yaml
git commit -m "feat(sandbox): 添加 OpenShell sandbox 网络与文件系统策略"
```

---

### Task 6: 编写 README

**Files:**
- Create: `sandboxes/sensenova-claw/README.md`

- [ ] **Step 1: 创建 README.md**

写入以下内容到 `sandboxes/sensenova-claw/README.md`：

```markdown
# Sensenova-Claw Sandbox

事件驱动 AI Agent 平台，支持多 LLM 提供商、工具调用、多 Agent 协作。在 OpenShell 沙箱中安全运行。

## Quick Start

```sh
openshell sandbox create \
  --forward 8000 --forward 3000 \
  --from sensenova-claw \
  -- sensenova-claw-start
```

启动完成后访问：

- **Dashboard:** http://127.0.0.1:3000
- **API:** http://127.0.0.1:8000
- **Health Check:** http://127.0.0.1:8000/health

首次启动后在 Dashboard 中配置 LLM provider 和 API key。

## 挂载工作区

将宿主机项目目录挂载到沙箱内供 Agent 操作：

```sh
openshell sandbox create \
  --forward 8000 --forward 3000 \
  --from sensenova-claw \
  --mount ~/my-project:/sandbox/workspace \
  -- sensenova-claw-start
```

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 3000 | Next.js Dashboard | Web 管理界面 |
| 8000 | FastAPI Backend | REST API + WebSocket |

## 功能

- 多 LLM 支持（OpenAI、Anthropic、Gemini、Qwen 等）
- 内置工具（bash 命令、文件读写、网页搜索、URL 抓取）
- 多 Agent 协作与委派
- 定时任务（Cron）
- Skills 编排系统
- 记忆系统

## 网络策略

默认使用宽松策略，允许所有 HTTP/HTTPS 出站。如需收紧：

```sh
openshell policy set <sandbox-name> --file my-strict-policy.yaml
```

## 相关链接

- [Sensenova-Claw 仓库](https://github.com/SenseTime-FVG/sensenova-claw)
- [OpenShell 文档](https://docs.openshell.dev)
```

- [ ] **Step 2: Commit**

```bash
git add sandboxes/sensenova-claw/README.md
git commit -m "feat(sandbox): 添加 OpenShell 社区 sandbox README 文档"
```

---

### Task 7: 本地构建验证

**Files:** 无新文件，验证性任务

- [ ] **Step 1: 验证 Docker 构建（如果 Docker 可用）**

```bash
cd /home/luojiapeng/projects/agentos/sensenova-claw
docker build -f sandboxes/sensenova-claw/Dockerfile -t sensenova-claw-sandbox .
```

Expected: 构建成功，无错误。

如果 Docker 不可用，跳过此步，记录需要在有 Docker 环境中验证。

- [ ] **Step 2: 验证镜像可启动（如果 Docker 可用）**

```bash
docker run --rm -p 8000:8000 -p 3000:3000 sensenova-claw-sandbox sensenova-claw-start &
sleep 15
curl -s http://localhost:8000/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
docker stop $(docker ps -q --filter ancestor=sensenova-claw-sandbox)
```

Expected:
- health 端点返回 200
- 前端返回 200

- [ ] **Step 3: 如果构建失败，根据错误修复 Dockerfile 并重新构建**

常见问题：
- `npm ci` 失败 → 检查 package-lock.json 是否在构建上下文中
- `pip install` 失败 → 检查 pyproject.toml 路径
- `COPY public` 失败 → 检查 public 目录是否存在于 standalone 构建产物外

- [ ] **Step 4: Commit 任何修复**

```bash
git add -A sandboxes/sensenova-claw/
git commit -m "fix(sandbox): 修复构建问题"
```

仅在有修复时执行。

---

### Task 8: OpenShell 端到端验证（需要 OpenShell 环境）

**Files:** 无新文件，验证性任务

- [ ] **Step 1: 使用本地 Dockerfile 创建沙箱**

```bash
openshell sandbox create \
  --forward 8000 --forward 3000 \
  --from /home/luojiapeng/projects/agentos/sensenova-claw/sandboxes/sensenova-claw \
  --policy /home/luojiapeng/projects/agentos/sensenova-claw/sandboxes/sensenova-claw/policy.yaml \
  -- sensenova-claw-start
```

Expected: 沙箱创建成功，端口转发生效。

- [ ] **Step 2: 验证服务可访问**

```bash
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000
```

Expected: 两个端点均返回 200。

- [ ] **Step 3: 在浏览器中打开 Dashboard 验证完整功能**

访问 `http://127.0.0.1:3000`，确认：
1. 页面正常加载
2. WebSocket 连接成功
3. 可以配置 LLM provider
4. 发送消息能得到响应

- [ ] **Step 4: 清理沙箱**

```bash
openshell sandbox delete <sandbox-name>
```
