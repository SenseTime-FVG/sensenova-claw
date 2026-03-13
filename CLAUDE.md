# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AgentOS 是基于事件驱动架构的 AI Agent 平台，支持 Web、CLI、TUI 多种接入方式。

**技术栈**:
- 后端: FastAPI + Python 3.12 + asyncio + SQLite
- 前端: Next.js 14 + TypeScript + WebSocket
- 包管理: uv (Python), npm (Node.js)

## 常用命令

### 开发启动

```bash
# 一键启动前后端（推荐）
npm run dev

# 单独启动后端
npm run dev:server
# 或: python3 -m uvicorn agentos.app.gateway.main:app --reload --host 0.0.0.0 --port 8000

# 单独启动前端
npm run dev:web

# 启动 TUI 客户端（需后端已运行）
python3 -m agentos.app.cli.cli_client --port 8000
```

### 测试

```bash
# 后端 e2e 测试（需要真实 API key）
npm run test:e2e
# 或: python3 -m pytest tests/e2e -q

# 前端 e2e 测试
npm run test:web:e2e

# 后端单元测试
python3 -m pytest tests/unit/ -q

# 全部测试
python3 -m pytest tests/ -q
```

### Python 环境

```bash
# 安装依赖
uv sync

# 安装开发依赖
uv sync --extra dev

# 运行 Python 脚本
python3 xxx.py
```

## 核心架构

### 事件驱动架构

所有模块通过 **PublicEventBus** 解耦通信，事件封装为 `EventEnvelope`：

```python
class EventEnvelope:
    event_id: str      # UUID
    type: str          # 事件类型，如 "ui.user_input", "llm.call_completed"
    session_id: str    # 会话隔离
    turn_id: str       # 对话轮次
    trace_id: str      # 关联请求/响应（如 llm_call_id, tool_call_id）
    payload: dict      # 事件数据
    source: str        # 来源: ui/agent/llm/tool/system
```

**事件流**:
```
ui.user_input → agent.step_started → llm.call_requested → llm.call_completed
→ tool.call_requested → tool.call_completed → agent.step_completed
```

### Gateway 与 Channel

- **Gateway**: 管理多个 Channel，在 Channel 和 PublicEventBus 之间路由事件
- **Channel**: 用户接入抽象（WebSocketChannel、TUIChannel、CLIChannel）
- 每个 Channel 独立管理会话，通过 `session_id` 隔离

### 核心 Runtime 模块

所有 Runtime 订阅 PublicEventBus，通过 `session_id` 过滤事件：

- **AgentRuntime**: 对话流程编排，监听 `ui.user_input`，发布 `agent.step_*`
- **LLMRuntime**: LLM 调用管理，监听 `llm.call_requested`，发布 `llm.call_completed`
- **ToolRuntime**: 工具执行，监听 `tool.call_requested`，发布 `tool.call_completed`
- **TitleRuntime**: 自动生成会话标题

### 状态管理

- **SessionStateStore**: 内存状态管理（Turn、Message、工具调用状态）
- **SQLite**: 持久化存储（sessions、turns、messages、events 表）

### 工具系统

内置 5 个工具（`agentos/capabilities/tools/builtin.py`）：
- `bash_command`: 执行 shell 命令
- `serper_search`: 网络搜索（需 SERPER_API_KEY）
- `fetch_url`: 获取网页内容
- `read_file`: 读取文件
- `write_file`: 写入文件

工具注册在 `ToolRegistry`，通过 `@tool_registry.register()` 装饰器自动注册。

### Skills 系统

Skills 是声明式任务编排机制（`agentos/capabilities/skills/`），16 个内置 skills 包括：
- 文档处理: `pdf_to_markdown`, `docx_to_markdown`, `xlsx_to_markdown`
- 前端开发: `design_frontend`, `test_frontend`
- Skill 管理: `create_skill`

Skills 通过 YAML 配置定义，支持多步骤编排和条件分支。

## 配置文件

根目录 `config.yml`（不入库）：

```yaml
OPENAI_BASE_URL: https://api.openai.com/v1
OPENAI_API_KEY: sk-xxx
SERPER_API_KEY: xxx

agent:
  provider: openai
  default_model: gpt-4o-mini
  system_prompt: "你是一个有用的AI助手"

tools:
  serper_search:
    api_key: ${SERPER_API_KEY}
    timeout: 15
    max_results: 10
```

配置加载优先级: 环境变量 > config.yml > 默认值

## 开发规范

### 日志

开发模式下后端输出 DEBUG 日志，包括：
- 每次 LLM 调用的完整输入
- 工具执行详情
- 事件流转追踪

### 测试要求

- 新功能必须编写 e2e 测试
- 后端 e2e: 模拟用户输入，验证完整事件链路
- 前端 e2e: Playwright 无头浏览器测试
- e2e 测试使用真实 API key

### 文档规范

- `docs_raw/`: 用户原始文档，**不要修改**
- `docs/`: 模型生成文档，可修改
- 伪代码使用 Python 格式
- 注释和文档使用中文

### 代码规范

- 使用中文注释
- 先思考再行动
- 遇到外部资料先搜索/浏览
- 根据文档更新时需全面考虑代码/文档/测试

## 关键文件路径

```
agentos/
  kernel/
    events/            # 事件系统（bus.py, envelope.py, types.py）
    runtime/           # Runtime 模块（agent_runtime.py, llm_runtime.py, tool_runtime.py）
    scheduler/         # Cron 调度
    heartbeat/         # 心跳
  capabilities/
    agents/            # 多 Agent 配置
    tools/             # 工具系统（base.py, builtin.py, registry.py）
    skills/            # Skills 系统
    memory/            # 记忆系统
  adapters/
    llm/               # LLM 提供商（openai, anthropic, gemini, mock）
    channels/          # Channel（websocket, feishu）
    storage/           # 数据库仓储
    skill_sources/     # Skill 市场适配器
    plugins/           # 插件系统
  interfaces/
    http/              # REST API 端点
    ws/                # WebSocket Gateway
  platform/
    config/            # 配置加载
    logging/           # 日志
    security/          # 路径策略、拒绝列表
  app/
    gateway/           # 后端入口（main.py）
    cli/               # CLI/TUI 客户端
    web/               # Next.js 前端

tests/                 # 测试（unit/, integration/, e2e/, cross_feature/）
workspace/             # 运行时工作区（skills, workflows）
var/                   # 运行时数据（数据库等）
docs/                  # 技术文档
docs_raw/              # 原始文档（不修改）
scripts/               # 开发脚本
```

## 已知问题

- 当前环境 `python` 命令不存在，使用 `python3`
- Playwright 需要系统库，`npx playwright install --with-deps` 可能需要 sudo
- `uv` 缓存目录可能无权限，需设置 `UV_CACHE_DIR=/tmp/uv_cache`

## 版本信息

当前版本: v0.5

v0.5 新增:
- 代码架构重组（backend/app/ → agentos/ 六层架构）
- 移除 Workflow 功能模块
- 完整测试覆盖（734 tests）

v0.4 新增:
- Skills 系统（16 个内置 skills）
- Skills 配置管理

v0.2 新增:
- Gateway 架构
- CLI/TUI 客户端
- 自动标题生成
- 工具结果截断
- 消息归一化

暂不支持:
- 流式响应
- Token 管理
- 用户认证
- 沙箱执行

# 其他

使用中文写注释和文档

先思考再行动

遇到外部资料，先使用search/browse等工具获取相关信息再行动


如果用户需求是根据指定文档更新代码，你需要全面考虑需要更新哪些代码/文档/测试


# 自动生成的Notes

你可以修改这个这部分内容，但是不要更改上面的内容

每次你执行完成任务之后，需要总结成功和失败的经验，并选择会对后续任务有帮助的内容保存在这里

### 2026-03-05 任务复盘

成功经验：
- 后端事件驱动链路（`ui.user_input -> llm -> tool -> agent.step_completed`）可以通过集成测试稳定跑通，并且 DEBUG 日志中已包含 `LLM call input`，便于排查问题。
- 一键启动脚本 `scripts/dev.sh` 已支持端口检查、配置提示、进程联动退出；根目录 `npm run dev` 可以统一启动前后端。
- 在当前环境中，`sqlite3` 比 `aiosqlite` 更稳定；仓储层切换为 `sqlite3` 后，启动与测试阻塞问题消失。

失败/风险经验：
- 当前环境缺少 `uv`，且 `python` 命令不存在（仅有 `python3`），脚本必须显式使用 `python3`。
- 当前环境运行 Playwright Chromium 缺少系统库（如 `libatk-1.0.so.0`），`npx playwright install --with-deps` 需要 sudo 密码，无法自动完成，导致前端 e2e 无法在本机执行。
- 当前环境对 `localhost` 访问存在限制，基于真实端口的后端 e2e不稳定；优先使用进程内事件流集成测试验证后端逻辑。

### 2026-03-05 真实API回归补充

成功经验：
- 在越权网络环境下，`api.uniapi.io` 和 `google.serper.dev` 都可连通，真实调用可以跑到“LLM首轮 + 多个 Serper 工具并发执行”。  

失败/风险经验：
- 当前后端在第二次 `chat.completions` 请求中，会把上一轮 assistant 的 `tool_calls` 以 `{id,name,arguments}` 回传，但缺少 `tool_calls[*].type=\"function\"`，导致 OpenAI 兼容网关返回 `400 invalid_value`。  
- v0.5 重构后，后端已从项目根目录启动，自动读取根目录 `config.yml`。

### 2026-03-05 Bug修复补充

成功经验：
- 对 OpenAI provider 增加消息归一化后，真实链路可通过：首轮 LLM -> 工具并发 -> 二轮 LLM -> `agent.step_completed`。  
- `tool` 消息携带 `tool_call_id` 后，上下文关联更稳定，兼容网关不会因字段缺失拒绝请求。  

风险提醒：
- 真实链路下模型输出不稳定，前端 e2e 断言不应依赖固定文案；建议断言事件类型或结构化字段。

### 2026-03-05 配置与前端回归补充

成功经验：
- 仅在仓库根目录 `config.yml` 配置 `OPENAI_API_KEY`/`SERPER_API_KEY` 时，配置加载应自动将 `agent.provider` 切到 `openai`，否则前端 e2e 会误跑 `mock` provider。  
- 当 `agent.default_model` 未显式配置时，按当前 provider 自动回填默认模型（如 `openai -> gpt-4o-mini`）可避免 provider 与 model 不匹配。  
- Playwright 断言改为“WebSocket 已连接 + 用户消息已回显 + 出现非用户响应气泡”后，对真实 API 返回波动更稳健。  

失败/风险经验：
- `npm run test:e2e` 已使用 `python3 -m pytest`，无需单独的 `pytest` 命令。

### 2026-03-07 CLI 交互修复补充

成功经验：
- `asyncio` 场景下仅在 `Prompt.ask` 外层捕获 `KeyboardInterrupt` 不够，需额外注册 `SIGINT` 处理器并在主循环兜底捕获，才能避免连续 `Ctrl+C` 直接退出。
- 将命令输入统一做 `strip()` 后再分派，可稳定识别 ` / ` 与 `/quit`，避免因为前后空白导致命令失效。
- 将输入分派提炼为纯函数（`parse_user_input`）后，可用轻量单测快速覆盖 `/` 菜单、`/quit` 退出和未知命令行为。

失败/风险经验：
- 当前环境运行 `uv` 默认缓存目录 `~/.cache/uv` 可能无权限，需要显式设置 `UV_CACHE_DIR=/tmp/uv_cache`。
- 若本地未同步 dev 依赖，`uv run python -m pytest` 会报 `No module named pytest`，需先执行 `uv sync --extra dev`。

### 2026-03-07 CLI 即时命令菜单补充

成功经验：
- 终端若使用按行读取（如 `Prompt.ask`），`/` 命令天然需要回车；要实现“按下 `/` 立即弹菜单”，需要切到逐字符读取（raw mode）。
- 通过 `termios + tty.setraw` 在“输入缓冲为空且按下 `/`”时直接返回命令动作，可实现无需回车的命令菜单触发。
- 将“是否触发即时菜单”抽成纯函数（`should_trigger_menu_on_keypress`）后，能用单测稳定覆盖该交互规则。

失败/风险经验：
- `termios` 仅适用于类 Unix 终端；非 TTY/不支持环境需保留按行读取降级路径，避免脚本不可用。