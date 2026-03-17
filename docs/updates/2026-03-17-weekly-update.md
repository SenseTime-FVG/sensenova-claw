## 1. 代码架构重组 (v0.5)

将项目从 `backend/app/` 双层结构重组为 `agentos/` 六层架构：

```
agentos/
├── kernel/          # 事件系统、Runtime、调度
├── capabilities/    # Agent、工具、Skills、记忆
├── adapters/        # LLM 提供商、Channel、存储
├── interfaces/      # HTTP/WS 端点
├── platform/        # 配置、日志、安全
└── app/             # 入口（gateway、cli、web）
```

- 移除 Workflow 功能模块，简化系统复杂度
- 清理重构后残留的 `backend/frontend` 路径引用
- 重命名 npm scripts，统一使用 `dev:server` / `dev:web` 命名
- 统一依赖安装：`npm install` 一键完成前后端所有依赖（postinstall 脚本）

## 2. 多 Agent 系统

### 2.1 核心实现
- **AgentConfig / AgentRegistry**：支持多 Agent 配置管理（CRUD、持久化、Agent 发现）
- **send_message 工具**：Agent 间通过 `send_message` 工具异步发送任务
- **AgentMessageCoordinator**：异步消息协调器，管理子 Agent 会话生命周期、超时监控、重试
- **MessageRecord**：消息记录数据类，追踪 Agent 间通信状态
- 移除旧的 `delegate_tool`，统一为 `send_message` 语义

### 2.2 Per-Agent Workspace（未提交）
- 每个 Agent 拥有独立的存储目录 `workspace/agents/{agent_id}/`
  - `config.json` — Agent 配置持久化
  - `AGENTS.md` — Agent 行为指令
  - `USER.md` — 用户偏好配置
- 全局 `workspace/AGENTS.md` 和 `workspace/USER.md` 保留作为默认模板
- AgentRegistry 持久化改为目录结构，向后兼容旧扁平 JSON

### 2.3 Per-Agent Workdir（未提交）
- AgentConfig 新增 `workdir` 字段，默认 `workspace/workdir/{agent_id}`
- System prompt 向 LLM 注入 per-agent 工作目录（替代全局 workspace）
- `bash_command` 工具默认 cwd 改为 per-agent workdir
- 通过 TOOL_CALL_REQUESTED 事件传递 `_agent_workdir` 到工具层

### 2.4 设计文档
- 多 Agent Team 架构设计 spec
- 架构流程图（Coordinator 模型）
- 异步回传机制：改为 PrivateEventBus 轮间触发，移除 inbox 拉取

## 3. 消息增量持久化

- Agent Worker 改为逐条消息增量持久化（user → assistant → tool 各阶段立即写入 SQLite）
- 新增 Session JSONL 导出：按 `agent_id` 分目录写入 JSONL 文件，便于离线分析

## 4. 用户认证系统

- 后端：JWT Token 认证 + Argon2 密码哈希
  - `auth.py`：Token 签发/验证、密码哈希
  - `middleware.py`：请求认证中间件
  - `user_repository.py`：用户数据存储
  - `auth.py` (HTTP)：登录/注册/刷新 API 端点
- 前端：登录页面 + AuthContext + ProtectedRoute
  - `authFetch.ts`：带 Token 的请求封装
  - WebSocket 连接支持 Token 认证
- 默认关闭（`security.auth_enabled: false`），配置开启

## 5. 办公工具集

### 5.1 邮件工具（5 个工具）
- `send_email` — 发送邮件（支持 SMTP）
- `list_emails` — 列出邮件
- `read_email` — 读取邮件详情
- `download_attachment` — 下载附件
- `mark_email` / `search_emails` — 标记和搜索
- 支持 Gmail / Outlook / QQ 邮箱配置
- 邮件功能设计文档

### 5.2 图片搜索工具
- `serper_image_search` — 基于 Serper API 的图片搜索

### 5.3 PPT Skills 更新
- 新增/更新 6 个 PPT 相关 Skills：`pptx`、`ppt-html-gen`、`ppt-outline-gen`、`ppt-style-extract`、`ppt-image-selection`
- 新增 OCR 文档解析 Skill (`paddleocr-doc-parsing`)
- 新增语音转录 Skill (`openai-whisper-api`)

## 6. 安全加固

- 修复 dev 分支合并后的安全漏洞
- PathPolicy 不可 JSON 序列化问题修复
- 工具执行上下文注入隔离（`_path_policy` 等内部字段不泄露到事件持久化）

## 7. 测试覆盖

- 单元测试从 66% 覆盖率提升至 100%（补充 27 个模块）
- CLI 测试改为启动进程内 WebSocket 服务，消除 13 个 skip
- LLM 测试同时覆盖 mock_provider 和真实 Gemini API
- Agent 核心链路回归测试
- 删除重构前遗留的 `test/` 目录

## 8. 文档与工程

- README.md 重写，参考 nanobot 格式
- 添加 MIT License
- 框架文档采用 docsify 格式重新组织
- 修复 Config 多层配置发现、croniter 依赖
- 同步锁文件和修正 build-backend 配置
