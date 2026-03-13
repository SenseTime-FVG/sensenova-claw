# AgentOS Docs Workspace

本仓库用于维护 AgentOS 的代码与文档，包含前端、后端与架构文档。

## 目录说明

```text
.
├── backend/         # FastAPI 后端
├── frontend/        # Next.js 前端
├── docs/            # 模型生成文档（可修改）
├── docs_raw/        # 原始文档（不要修改）
├── scripts/         # 一键启动等脚本
└── config.yml       # 本地 API 配置（建议本地保存，不入库）
```

## 环境要求

- Node.js 18+
- Python 3.12+
- npm

## 快速开始

1. 安装依赖

```bash
npm install
cd frontend && npm install && cd ..
```

2. 配置 API Key（项目根目录 `config.yml`）

将项目根目录下的 `config_example.yml` 重命名为 `config.yml`，然后根据你的实际 API Key 进行填写：

```bash
cp config_example.yml config.yml
# 手动编辑 config.yml，填入各项 provider 与工具的 API Key
```

**注意：**  
- `config.yml` 仅用于本地开发环境，建议不要将包含私密信息的该文件提交到版本库。

3. 一键启动前后端

```bash
npm run dev
```

- 前端: http://localhost:3000
- 后端: http://localhost:8000

4. 启动 TUI（终端界面）

TUI 作为客户端连接到已运行的后端 Gateway。

首先确保后端已启动（步骤3），然后在新终端中运行：

```bash
cd backend
uv run python run_tui.py --port 8000
```

或使用模块方式：

```bash
cd backend
uv run python -m app.gateway.channels.tui_channel --port 8000
```

参数说明：
- `--port`: Gateway WebSocket 端口（默认: 8000）
- `--host`: Gateway 主机地址（默认: localhost）

TUI 提供了终端下的交互式界面，可以直接在命令行中与 Agent 对话。

## 测试

后端 e2e：

```bash
npm run test:backend:e2e
```

前端 Playwright e2e：

```bash
npm run test:frontend:e2e
```

## 文档入口

- 架构与设计文档: `docs/README.md`

## 说明

- `docs_raw/` 内容为用户原始文档，按约定不应修改。
- 后端默认输出 DEBUG 日志，便于排查 LLM 调用与工具链路问题。
