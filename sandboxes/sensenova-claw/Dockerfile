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
