# 快速开始

本指南帮助你在本地环境快速搭建和运行 Sensenova-Claw。

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.12+ | 运行后端服务 |
| Node.js | 18+ | 运行前端应用 |
| uv | 最新版 | Python 包管理工具 |
| npm | 随 Node.js 安装 | Node.js 包管理工具 |

> **注意**: 当前环境中 `python` 命令可能不存在，请统一使用 `python3`。

## 安装步骤

### 1. 克隆项目

```bash
git clone <项目地址>
cd sensenova-claw
```

### 2. 安装后端依赖

```bash
# 安装 Python 依赖
uv sync

# 如需开发依赖（测试、lint 等）
uv sync --extra dev
```

> **提示**: 如果 `uv` 缓存目录无权限，可设置环境变量：
> ```bash
> export UV_CACHE_DIR=/tmp/uv_cache
> ```

### 3. 安装前端依赖

```bash
npm install
```

## 配置

在项目根目录创建 `config.yml` 配置文件：

```yaml
# LLM 提供商配置
OPENAI_BASE_URL: https://api.openai.com/v1
OPENAI_API_KEY: sk-your-api-key-here

# 网络搜索工具（可选）
SERPER_API_KEY: your-serper-api-key-here
BRAVE_SEARCH_API_KEY: your-brave-search-api-key-here
BAIDU_APPBUILDER_API_KEY: your-baidu-appbuilder-api-key-here
TAVILY_API_KEY: your-tavily-api-key-here

# Agent 配置
agent:
  provider: openai
  default_model: gpt-4o-mini
  system_prompt: "你是一个有用的AI助手"

# 工具配置
tools:
  serper_search:
    api_key: ${SERPER_API_KEY}
    timeout: 15
    max_results: 10
  brave_search:
    api_key: ${BRAVE_SEARCH_API_KEY}
    timeout: 15
    max_results: 10
  baidu_search:
    api_key: ${BAIDU_APPBUILDER_API_KEY}
    timeout: 15
    max_results: 10
  tavily_search:
    api_key: ${TAVILY_API_KEY}
    timeout: 15
    max_results: 5
```

**配置项说明：**

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `OPENAI_API_KEY` | 是 | OpenAI API 密钥（或兼容接口的密钥） |
| `OPENAI_BASE_URL` | 否 | API 基础地址，默认 `https://api.openai.com/v1` |
| `SERPER_API_KEY` | 否 | Serper 搜索 API 密钥，启用网络搜索工具需要 |
| `BRAVE_SEARCH_API_KEY` | 否 | Brave Search API 密钥，启用 `brave_search` 需要 |
| `BAIDU_APPBUILDER_API_KEY` | 否 | 百度 AppBuilder API 密钥，启用 `baidu_search` 需要 |
| `TAVILY_API_KEY` | 否 | Tavily API 密钥，启用 `tavily_search` 需要 |
| `agent.provider` | 否 | LLM 提供商，可选 `openai` / `anthropic` / `gemini` / `mock` |
| `agent.default_model` | 否 | 默认模型，如 `gpt-4o-mini`、`claude-3-sonnet` 等 |

> 配置加载优先级：**环境变量 > config.yml > 默认值**

### 获取搜索工具 API Key

如果你不想让 Agent 自己再去读外部文档解释，可以直接按下面的步骤手动拿到搜索工具 token：

#### Serper

1. 打开 `https://serper.dev/`，点击 `Sign up` 或 `Get started` 完成注册并登录。
2. 登录后进入 `Dashboard`，找到 `API Key` 区域。
3. 复制页面展示的 API Key。
4. 将该 key 填入 `SERPER_API_KEY` 或 `tools.serper_search.api_key`。

#### Brave Search

1. 打开 `https://api-dashboard.search.brave.com/app/documentation/web-search/get-started`，点击右上角 `Log in` 注册或登录。
2. 进入 dashboard 后，在 `Subscriptions` 中订阅一个 `Web Search` plan。
3. 打开订阅后的应用或凭据页，复制 `X-Subscription-Token`。
4. 将该 token 填入 `BRAVE_SEARCH_API_KEY` 或 `tools.brave_search.api_key`。

#### 百度千帆 / AppBuilder AI Search

1. 打开 `https://cloud.baidu.com/doc/qianfan-docs/s/qm8qxemze`，按文档入口进入百度智能云控制台的 `安全认证 -> API Key` 页面。
2. 点击 `创建 API Key`，并在 `添加权限` 中勾选千帆 / AppBuilder / AI 搜索相关能力。
3. 创建完成后复制 API Key。
4. 将该 key 填入 `BAIDU_APPBUILDER_API_KEY` 或 `tools.baidu_search.api_key`；请求时会按 `Bearer <api_key>` 方式使用。

#### Tavily

1. 打开 `https://tavily.com/` 并登录。
2. 进入 `Dashboard` 或 `API Keys` 区域。
3. 复制系统生成的 Tavily API Key。
4. 将该 key 填入 `TAVILY_API_KEY` 或 `tools.tavily_search.api_key`；请求时会按 `Authorization: Bearer <api_key>` 使用。

详细配置说明请参考 [配置指南](configuration.md)。

## 启动服务

### 一键启动（推荐）

```bash
npm run dev
```

该命令会同时启动后端（端口 8000）和前端（端口 3000）。

### 单独启动后端

```bash
npm run dev:server
```

或者直接使用 uvicorn：

```bash
python3 -m uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port 8000
```

### 单独启动前端

```bash
npm run dev:web
```

### 启动 TUI 客户端

TUI 客户端提供终端交互界面，需要后端已运行：

```bash
python3 -m sensenova-claw.app.cli.cli_client --port 8000
```

## 访问服务

启动成功后，可通过以下地址访问：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | http://localhost:3000 | Next.js Web 应用 |
| 后端 API | http://localhost:8000 | FastAPI 服务 |
| API 文档 | http://localhost:8000/docs | Swagger 自动生成的 API 文档 |

## 验证安装

### 1. 验证后端

打开浏览器访问 http://localhost:8000/docs ，如果能看到 Swagger API 文档页面，说明后端已成功启动。

### 2. 验证前端

打开浏览器访问 http://localhost:3000 ，页面应显示 Sensenova-Claw 的对话界面。

### 3. 发送测试消息

在前端对话界面中输入一条测试消息（如"你好"），如果能收到 AI 回复，说明整个链路已正常运行：

```
用户输入 → WebSocket → Gateway → AgentRuntime → LLMRuntime → 返回响应
```

### 4. 测试工具调用

输入一条需要工具调用的消息（如"请帮我执行 ls 命令"），验证工具系统是否正常工作：

```
用户输入 → LLM 返回 tool_calls → ToolRuntime 执行 → 结果返回
```

## 运行测试

```bash
# 后端单元测试
python3 -m pytest tests/unit/ -q

# 后端端到端测试（需要真实 API key）
npm run test:e2e

# 前端端到端测试
npm run test:web:e2e

# 运行全部测试
python3 -m pytest tests/ -q
```

## 常见问题

### `python` 命令不存在

当前环境仅提供 `python3`，请确保所有命令使用 `python3` 而非 `python`。

### uv 缓存目录无权限

设置环境变量指定临时缓存目录：

```bash
export UV_CACHE_DIR=/tmp/uv_cache
uv sync
```

### Playwright 缺少系统库

前端 e2e 测试需要 Playwright 浏览器，安装时可能需要系统权限：

```bash
npx playwright install --with-deps
```

> 该命令可能需要 `sudo` 权限来安装系统级依赖。

### 端口被占用

如果 8000 或 3000 端口已被占用，请先释放端口后再启动服务。

## 下一步

- 了解完整的 [配置选项](configuration.md)
- 阅读 [架构设计](../architecture/) 理解系统原理
- 查看 [API 参考](../api/) 了解接口详情
