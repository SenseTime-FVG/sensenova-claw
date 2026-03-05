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

```yaml
OPENAI_BASE_URL: https://api.openai.com/v1
OPENAI_API_KEY: sk-xxx
SERPER_API_KEY: xxx
```

3. 一键启动前后端

```bash
npm run dev
```

- 前端: http://localhost:3000
- 后端: http://localhost:8000

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
