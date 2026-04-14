# SPDX-FileCopyrightText: Copyright (c) 2026 SenseTime-FVG. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Sensenova-Claw: 事件驱动 AI Agent 平台
# 启动方式: openshell sandbox create --forward 8000 --from ghcr.io/luojiapeng14/sensenova-claw-sandbox:v0.6 -- sensenova-claw-start

# ── Stage 1: 构建 Next.js 前端 ──
FROM node:18-slim AS frontend-build
WORKDIR /build
COPY sensenova_claw/app/web/package*.json ./
RUN npm ci
COPY sensenova_claw/app/web/ ./
ENV NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
RUN npm run build
# 产物: .next/standalone/ (含 server.js + 最小 node_modules)
#        .next/static/    (静态资源)

# ── Stage 2: Python 运行时 ──
FROM python:3.12-slim

# OpenShell 必需: iproute2 (网络命名空间), iptables (旁路检测)
# 从 Stage 1 复制 node binary（避免 apt install nodejs 引入 libicu ~37MB）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl iproute2 iptables \
    && rm -rf /var/lib/apt/lists/*
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node

# OpenShell 要求: sandbox 用户 (uid/gid 1000)
RUN groupadd -g 1000 sandbox && \
    useradd -m -u 1000 -g sandbox sandbox

# 安装 sensenova-claw Python 包（排除前端目录和不需要的插件）
WORKDIR /opt/sensenova-claw
COPY pyproject.toml .
COPY sensenova_claw/ sensenova_claw/
RUN rm -rf sensenova_claw/app/web \
           sensenova_claw/app/cli \
    && pip install --no-cache-dir . \
    && pip uninstall -y pip setuptools \
    && rm -rf /usr/local/lib/python3.12/site-packages/lark_oapi/api/*/v* \
    && find /usr/local/lib/python3.12/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# 复制前端构建产物
COPY --from=frontend-build /build/.next/standalone /opt/sensenova-claw/web
COPY --from=frontend-build /build/.next/static /opt/sensenova-claw/web/.next/static
COPY --from=frontend-build /build/public /opt/sensenova-claw/web/public

# 启动脚本
COPY sandboxes/sensenova-claw/sensenova-claw-start /usr/local/bin/
RUN chmod +x /usr/local/bin/sensenova-claw-start

# 内置 Agent 配置 + 数据目录
COPY .sensenova-claw/agents/ /home/sandbox/.sensenova-claw/agents/
RUN mkdir -p /home/sandbox/.sensenova-claw/data && \
    chown -R sandbox:sandbox /home/sandbox/.sensenova-claw

WORKDIR /sandbox
EXPOSE 8000 3000
