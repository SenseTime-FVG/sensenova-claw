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
