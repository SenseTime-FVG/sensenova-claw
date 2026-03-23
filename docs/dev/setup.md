# 开发环境搭建

本文档介绍如何搭建 Sensenova-Claw 的本地开发环境。

---

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.12+ | 后端运行时 |
| Node.js | 18+ | 前端构建和运行 |
| uv | 最新版 | Python 包管理工具 |
| npm | 随 Node.js 安装 | Node.js 包管理 |

> **注意**：当前环境中 `python` 命令可能不存在，请统一使用 `python3`。

---

## 安装步骤

### 1. 克隆仓库

```bash
git clone <repo-url>
cd sensenova-claw
```

### 2. 安装 Python 依赖

```bash
# 安装运行时依赖
uv sync

# 安装开发依赖（包含 pytest 等测试工具）
uv sync --extra dev
```

> 如果遇到 uv 缓存目录权限问题，可设置环境变量：
> ```bash
> export UV_CACHE_DIR=/tmp/uv_cache
> ```

### 3. 安装前端依赖

```bash
cd sensenova_claw/app/web
npm install
cd -
```

### 4. 配置文件

在项目根目录创建 `config.yml`：

```bash
cp config.example.yml config.yml
```

编辑 `config.yml`，填入必要的配置。敏感值推荐写成环境变量引用或 `${secret:...}` 引用：

```yaml
# LLM 提供商配置
OPENAI_BASE_URL: https://api.openai.com/v1
OPENAI_API_KEY: sk-your-api-key

# 搜索工具配置（可选）
SERPER_API_KEY: your-serper-api-key
BRAVE_SEARCH_API_KEY: your-brave-search-api-key
BAIDU_APPBUILDER_API_KEY: your-baidu-appbuilder-api-key
TAVILY_API_KEY: your-tavily-api-key

# Agent 配置
agent:
  provider: openai
  default_model: gpt-4o-mini
  system_prompt: "你是一个有用的AI助手"
  default_temperature: 0.2

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

也可以把敏感值放入系统 keyring，然后在 `config.yml` 中只保留引用：

```yaml
llm:
  providers:
    openai:
      api_key: ${secret:sensenova_claw/llm.providers.openai.api_key}
```

配置加载优先级：**环境变量覆盖值 > config.yml 中声明的来源 > 默认值**

如果你之前已经把 API Key 明文写进了 `config.yml`，可以在接入 keyring 后执行：

```bash
sensenova-claw migrate-secrets
```

它会把已登记的敏感字段迁移到系统 keyring，并把 `config.yml` 改写为 `${secret:...}` 引用。

---

## 启动开发服务

### 一键启动（推荐）

```bash
npm run dev
```

此命令会同时启动后端 API 服务和前端开发服务器。

### 单独启动后端

```bash
npm run dev:server
```

或直接使用 uvicorn：

```bash
python3 -m uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port 8000
```

后端启动后：
- REST API：`http://localhost:8000`
- WebSocket：`ws://localhost:8000/ws`
- API 文档（Swagger）：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### 单独启动前端

```bash
npm run dev:web
```

前端默认运行在 `http://localhost:3000`。

### TUI 客户端

TUI 客户端需要后端已运行：

```bash
python3 -m sensenova-claw.app.cli.cli_client --port 8000
```

---

## 项目结构

```
sensenova_claw/
  kernel/                        # 内核层
    events/                      #   事件系统
      bus.py                     #     PublicEventBus
      envelope.py                #     EventEnvelope 数据结构
      types.py                   #     事件类型常量
    runtime/                     #   Runtime 模块
      agent_runtime.py           #     Agent 对话编排
      llm_runtime.py             #     LLM 调用管理
      tool_runtime.py            #     工具执行
      publisher.py               #     事件发布器
    scheduler/                   #   Cron 定时任务调度
    heartbeat/                   #   心跳巡检
  capabilities/                  # 能力层
    agents/                      #   多 Agent 配置与注册
    tools/                       #   工具系统
      base.py                    #     工具基类
      builtin.py                 #     多个内置工具（bash/search/fetch/file）
      registry.py                #     工具注册表
    skills/                      #   Skills 声明式编排
    memory/                      #   记忆系统
  adapters/                      # 适配层
    llm/                         #   LLM 提供商适配（openai, anthropic, gemini, mock）
    channels/                    #   Channel 适配（websocket, feishu）
      websocket_channel.py       #     WebSocket Channel 实现
    storage/                     #   数据库仓储（SQLite）
    skill_sources/               #   Skill 市场适配器
    plugins/                     #   插件系统
  interfaces/                    # 接口层
    http/                        #   REST API 端点
      agents.py                  #     Agent CRUD
      tools.py                   #     工具管理
      skills.py                  #     Skills 管理
      gateway.py                 #     Gateway 状态
      workspace.py               #     工作区文件管理
      config_api.py              #     配置管理
    ws/                          #   WebSocket Gateway
      gateway.py                 #     Gateway 核心逻辑
  platform/                      # 平台层
    config/                      #   配置加载
    logging/                     #   日志
    security/                    #   路径策略、拒绝列表
  app/                           # 应用入口层
    gateway/                     #   后端入口
      main.py                    #     FastAPI 应用（含 WebSocket 端点）
    cli/                         #   CLI/TUI 客户端
    web/                         #   Next.js 前端

tests/                           # 测试
  unit/                          #   单元测试
  integration/                   #   集成测试
  e2e/                           #   端到端测试
  cross_feature/                 #   跨功能测试

workspace/                       # 运行时工作区（skills, workflows）
var/                             # 运行时数据（数据库等）
docs/                            # 技术文档（模型生成，可修改）
docs_raw/                        # 原始文档（不修改）
scripts/                         # 开发脚本
config.yml                       # 配置文件（不入库）
```

---

## 开发模式日志

开发模式下，后端会输出 DEBUG 级别日志，包括：

- 每次 LLM 调用的完整输入/输出
- 工具执行详情（参数、结果、耗时）
- 事件流转追踪（事件 ID、类型、会话 ID）

---

## 常见问题

### `python` 命令不存在

当前环境仅提供 `python3`，请在脚本和命令中统一使用 `python3`。

### uv 缓存目录权限问题

```bash
export UV_CACHE_DIR=/tmp/uv_cache
uv sync
```

### Playwright 系统库缺失

前端 e2e 测试依赖 Playwright，需要安装浏览器和系统库：

```bash
npx playwright install --with-deps
```

> 此命令可能需要 `sudo` 权限。如果无法安装，前端 e2e 测试将无法在本机执行。

### 端口占用

如果 8000 端口被占用，可以指定其他端口：

```bash
python3 -m uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port 8001
```

### Mock 模式

如果没有真实的 API Key，系统会自动使用 Mock Provider。要确保使用真实 LLM，请在 `config.yml` 中正确配置 `OPENAI_API_KEY` 和 `agent.provider`。
