# SPDX-FileCopyrightText: Copyright (c) 2026 SenseTime-FVG. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Sensenova-Claw 镜像 —— 供 microsandbox (libkrun microVM) 启动使用。
#
# 已发布镜像: ghcr.io/tsunamiblue/sensenova-claw:msb (公共可拉，linux/arm64)
#
# 注意：microsandbox 仅从 OCI 注册表拉镜像（不读 docker daemon 本地镜像），
# 因此本地 build 之后必须 push 到一个 registry 才能在 msb 中使用。
#
# 重新构建 + 推送（在仓库根目录执行）:
#   docker build -f sandboxes/microsandbox/Dockerfile \
#                -t ghcr.io/tsunamiblue/sensenova-claw:msb .
#   docker push  ghcr.io/tsunamiblue/sensenova-claw:msb
#
# 在 microsandbox 中启动（CLI）:
#   msb run --image ghcr.io/tsunamiblue/sensenova-claw:msb \
#           -p 8000:8000 -p 3000:3000 \
#           -- sensenova-claw-start
#
# 通过 Python SDK 见 sandboxes/microsandbox/run.py。

# ── Stage 1: 构建 Next.js 前端 ──
FROM node:18-slim AS frontend-build
WORKDIR /build

# 使用国内 npm 镜像加速（默认 registry.npmjs.org 在国内常超时）。
# 想用官方 registry 时构建命令加 --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "$NPM_REGISTRY"

COPY sensenova_claw/app/web/package*.json ./
RUN npm ci
COPY sensenova_claw/app/web/ ./
ENV NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
RUN npm run build
# 产物: .next/standalone/ + .next/static/

# ── Stage 2: Python 运行时 ──
FROM python:3.12-slim

# microsandbox 不需要 iproute2/iptables/netns 工具 —— libkrun 自带网络栈，
# 出站策略由 host 侧的 SDK secrets/policy 配置实现。
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 从前端构建阶段直接拷出 node 二进制，省掉 ~37MB 的 libicu。
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node

# 使用国内 PyPI 镜像加速（同上理由）。
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=$PIP_INDEX_URL

# 安装 sensenova-claw（剥掉前端源码与 CLI 客户端，运行时不需要）
WORKDIR /opt/sensenova-claw
COPY pyproject.toml .
COPY sensenova_claw/ sensenova_claw/
RUN rm -rf sensenova_claw/app/web sensenova_claw/app/cli \
    && pip install --no-cache-dir . \
    && pip uninstall -y pip setuptools \
    && rm -rf /usr/local/lib/python3.12/site-packages/lark_oapi/api/*/v* \
    && find /usr/local/lib/python3.12/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# 前端构建产物
COPY --from=frontend-build /build/.next/standalone /opt/sensenova-claw/web
COPY --from=frontend-build /build/.next/static /opt/sensenova-claw/web/.next/static
COPY --from=frontend-build /build/public /opt/sensenova-claw/web/public

# 启动脚本 + 默认配置
COPY sandboxes/microsandbox/sensenova-claw-start /usr/local/bin/sensenova-claw-start
COPY sandboxes/sensenova-claw/default-config.yml /opt/sensenova-claw/default-config.yml
RUN chmod +x /usr/local/bin/sensenova-claw-start

# 内置 Agents 与 Skills 模板（启动脚本会按需复制到 $SENSENOVA_CLAW_HOME）
COPY .sensenova-claw/agents/ /etc/sensenova-claw/agents/
COPY .sensenova-claw/skills/ /etc/sensenova-claw/skills/

# Agent 持久化目录 —— 默认走 /root，外部如需跨 sandbox 持久化
# 通过 microsandbox 的 volume 把宿主目录挂到 /root/.sensenova-claw 即可。
ENV SENSENOVA_CLAW_HOME=/root/.sensenova-claw
RUN mkdir -p "$SENSENOVA_CLAW_HOME/data"

WORKDIR /root
EXPOSE 8000 3000

# microsandbox 启动 OCI 镜像后，agentd 作为 VM 内的 PID 1；
# 用户可通过 SDK 调用 `sb.shell("sensenova-claw-start")` 拉起服务，
# 或直接 `msb run -- sensenova-claw-start` 让 CMD 生效。
CMD ["sensenova-claw-start"]
