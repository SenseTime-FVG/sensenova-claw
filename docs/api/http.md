# HTTP REST API

AgentOS 后端基于 FastAPI 构建，提供以下 REST API 端点。默认监听地址为 `http://localhost:8000`。

---

## 健康检查

### `GET /health`

检查服务是否正常运行。

**响应示例**：

```json
{
  "status": "healthy",
  "timestamp": 1710400000.0,
  "version": "0.1.0"
}
```

---

## Agent 管理

前缀：`/api/agents`

### `GET /api/agents`

获取所有 Agent 列表，包含每个 Agent 的配置详情、工具/技能数量、会话统计等。

**响应示例**：

```json
[
  {
    "id": "default",
    "name": "默认助手",
    "status": "active",
    "description": "通用 AI 助手",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "systemPrompt": "你是一个有用的AI助手",
    "temperature": 0.2,
    "maxTokens": null,
    "toolCount": 8,
    "skillCount": 16,
    "tools": ["bash_command", "serper_search", "brave_search", "baidu_search", "tavily_search", "fetch_url", "read_file", "write_file"],
    "skills": ["pdf_to_markdown", "design_frontend"],
    "toolsDetail": [
      {"name": "bash_command", "description": "执行 shell 命令", "enabled": true}
    ],
    "skillsDetail": [
      {"name": "pdf_to_markdown", "description": "PDF 转 Markdown", "enabled": true, "category": "builtin"}
    ],
    "canDelegateTo": [],
    "maxDelegationDepth": 3,
    "sessionCount": 5,
    "lastActive": "3 minutes ago",
    "createdAt": 1710400000.0,
    "updatedAt": 1710400000.0
  }
]
```

### `GET /api/agents/{agent_id}`

获取指定 Agent 的详细信息，包含最近 20 条会话记录。

**路径参数**：
- `agent_id` (string) - Agent 唯一标识

**响应示例**：

```json
{
  "id": "default",
  "name": "默认助手",
  "status": "active",
  "sessionCount": 5,
  "sessions": [
    {
      "id": "sess_abc123",
      "status": "active",
      "channel": "websocket",
      "messageCount": 12,
      "startedAt": 1710400000.0,
      "lastActive": 1710401000.0
    }
  ]
}
```

**错误响应**：
- `404` - Agent 不存在

### `POST /api/agents`

创建新的 Agent。未指定的配置项会从 default Agent 继承。

**请求体**：

```json
{
  "id": "code-assistant",
  "name": "代码助手",
  "description": "专注于编程辅助的 Agent",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.2,
  "max_tokens": 4096,
  "system_prompt": "你是一个专业的编程助手",
  "tools": ["bash_command", "read_file", "write_file"],
  "skills": [],
  "can_delegate_to": [],
  "max_delegation_depth": 3
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | Agent 唯一标识 |
| `name` | string | 是 | Agent 显示名称 |
| `description` | string | 否 | 描述，默认为空 |
| `provider` | string | 否 | LLM 提供商，默认继承自 default Agent |
| `model` | string | 否 | 模型名称，默认继承自 default Agent |
| `temperature` | float | 否 | 温度参数，默认继承自 default Agent |
| `max_tokens` | int | 否 | 最大 token 数 |
| `system_prompt` | string | 否 | 系统提示词 |
| `tools` | string[] | 否 | 可用工具名列表 |
| `skills` | string[] | 否 | 可用技能名列表 |
| `can_delegate_to` | string[] | 否 | 可委托的 Agent ID 列表 |
| `max_delegation_depth` | int | 否 | 最大委托深度，默认 3 |

**错误响应**：
- `409` - Agent ID 已存在

### `PUT /api/agents/{agent_id}/config`

更新 Agent 配置。所有字段均为可选，仅更新提供的字段。

> **注意**：更新 default Agent 的 `provider`、`model`、`temperature`、`system_prompt` 时，会同步更新全局配置。

**请求体**：

```json
{
  "name": "新名称",
  "provider": "anthropic",
  "model": "claude-3-sonnet",
  "temperature": 0.5,
  "systemPrompt": "更新后的系统提示词"
}
```

**错误响应**：
- `404` - Agent 不存在

### `DELETE /api/agents/{agent_id}`

删除指定 Agent。不允许删除 default Agent。

**响应示例**：

```json
{
  "status": "deleted",
  "agent_id": "code-assistant"
}
```

**错误响应**：
- `400` - 不允许删除 default Agent
- `404` - Agent 不存在

### `PUT /api/agents/{agent_id}/preferences`

批量更新 Agent 的工具/技能启用偏好。

**请求体**：

```json
{
  "tools": {
    "bash_command": true,
    "serper_search": false
  },
  "skills": {
    "pdf_to_markdown": true,
    "design_frontend": false
  }
}
```

**响应示例**：

```json
{
  "status": "saved"
}
```

---

## 工具管理

前缀：`/api/tools`

### `GET /api/tools`

获取所有已注册的工具列表。

**响应示例**：

```json
[
  {
    "id": "tool-bash_command",
    "name": "bash_command",
    "description": "执行 shell 命令",
    "category": "builtin",
    "version": "1.0.0",
    "enabled": true,
    "riskLevel": "high",
    "parameters": {
      "type": "object",
      "properties": {
        "command": {"type": "string", "description": "要执行的命令"}
      }
    }
  }
]
```

### `PUT /api/tools/{tool_name}/enabled`

启用或禁用指定工具。

**请求体**：

```json
{
  "enabled": false
}
```

**响应示例**：

```json
{
  "name": "bash_command",
  "enabled": false
}
```

**错误响应**：
- `404` - 工具不存在

---

## 会话管理

### `GET /api/sessions`

获取会话列表（最多 50 条）。

**响应示例**：

```json
{
  "sessions": [
    {
      "session_id": "sess_abc123",
      "status": "active",
      "channel": "websocket",
      "agent_id": "default",
      "created_at": 1710400000.0,
      "last_active": 1710401000.0,
      "message_count": 12
    }
  ]
}
```

### `GET /api/sessions/{session_id}/turns`

获取指定会话的所有对话轮次。

**响应示例**：

```json
{
  "turns": [
    {
      "turn_id": "turn_001",
      "session_id": "sess_abc123",
      "user_input": "你好",
      "assistant_response": "你好！有什么我可以帮你的吗？",
      "created_at": 1710400000.0
    }
  ]
}
```

### `GET /api/sessions/{session_id}/events`

获取指定会话的所有事件（用于调试和回放）。

**响应示例**：

```json
{
  "events": [
    {
      "event_id": "evt_abc123",
      "type": "user.input",
      "session_id": "sess_abc123",
      "turn_id": "turn_001",
      "payload": {"content": "你好"},
      "source": "ui",
      "ts": 1710400000.0
    }
  ]
}
```

### `GET /api/sessions/{session_id}/messages`

获取指定会话的所有消息（用于聊天历史展示）。

**响应示例**：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "你好",
      "timestamp": 1710400000.0
    },
    {
      "role": "assistant",
      "content": "你好！有什么我可以帮你的吗？",
      "timestamp": 1710400001.0
    }
  ]
}
```

---

## Gateway 状态

前缀：`/api/gateway`

### `GET /api/gateway/stats`

获取 Gateway 统计信息。

**响应示例**：

```json
{
  "totalChannels": 1,
  "activeChannels": 1,
  "totalConnections": 3,
  "totalSessions": 15
}
```

### `GET /api/gateway/channels`

获取所有已注册的 Channel 列表。

**响应示例**：

```json
[
  {
    "id": "websocket",
    "name": "websocket",
    "type": "websocket",
    "status": "connected",
    "config": {}
  }
]
```

---

## Skills 管理

前缀：`/api/skills`

### `GET /api/skills`

获取所有已加载的 Skills，包含分类和依赖状态。

**响应示例**：

```json
[
  {
    "id": "skill-pdf_to_markdown",
    "name": "pdf_to_markdown",
    "description": "将 PDF 文件转换为 Markdown 格式",
    "category": "builtin",
    "enabled": true,
    "path": "/path/to/skills/pdf_to_markdown",
    "source": "builtin",
    "version": "1.0.0",
    "has_update": false,
    "update_version": null,
    "dependencies": {"pdftotext": true},
    "all_deps_met": true
  }
]
```

Skills 的 `category` 有三种分类：
- `builtin` - 内置技能
- `workspace` - 工作区自定义技能
- `installed` - 从市场安装的技能

### `GET /api/skills/search`

统一搜索本地和远程市场的 Skills。

**查询参数**：
- `q` (string, 必填) - 搜索关键词
- `sources` (string, 可选) - 搜索源，逗号分隔，支持 `local`、`clawhub`、`anthropic`，默认 `all`

**响应示例**：

```json
{
  "local_results": [
    {
      "id": "local:pdf_to_markdown",
      "name": "pdf_to_markdown",
      "description": "PDF 转 Markdown",
      "category": "builtin",
      "installed": true
    }
  ],
  "remote_results": [
    {
      "id": "clawhub:pdf-parser",
      "name": "pdf-parser",
      "description": "高级 PDF 解析",
      "category": "clawhub",
      "installed": false
    }
  ],
  "total_local": 1,
  "total_remote": 1
}
```

### `GET /api/skills/market/browse`

浏览市场 Skills 列表（推荐/热门）。

**查询参数**：
- `source` (string, 必填) - 市场来源（如 `clawhub`、`anthropic`）
- `page` (int, 可选) - 页码，默认 1
- `page_size` (int, 可选) - 每页数量，默认 20

### `GET /api/skills/market/search`

搜索市场 Skills。

**查询参数**：
- `source` (string, 必填) - 市场来源
- `q` (string, 必填) - 搜索关键词
- `page` (int, 可选) - 页码，默认 1
- `page_size` (int, 可选) - 每页数量，默认 20

### `GET /api/skills/market/detail`

获取市场 Skill 的详细信息。

**查询参数**：
- `source` (string, 必填) - 市场来源
- `id` (string, 必填) - Skill ID

### `POST /api/skills/install`

从市场安装 Skill。

**请求体**：

```json
{
  "source": "clawhub",
  "id": "skill-id-123",
  "repo_url": "https://github.com/user/skill-repo"
}
```

**响应示例**：

```json
{
  "ok": true,
  "skill_name": "pdf_parser",
  "dependencies": {"pdftotext": true},
  "all_deps_met": true
}
```

**错误响应**：
- `409` - 名称冲突
- `400` - 安装失败

### `POST /api/skills/check-updates`

检查所有已安装 Skill 的更新。

**响应示例**：

```json
{
  "updates": [
    {
      "name": "pdf_parser",
      "current_version": "1.0.0",
      "latest_version": "1.1.0"
    }
  ]
}
```

### `PATCH /api/skills/{skill_name}`

启用或禁用指定 Skill。

**请求体**：

```json
{
  "enabled": false
}
```

### `DELETE /api/skills/{skill_name}`

卸载已安装的 Skill。内置技能和核心技能不允许卸载。

**错误响应**：
- `403` - 权限不足（不允许卸载）
- `404` - Skill 不存在

### `POST /api/skills/{skill_name}/update`

更新已安装的 Skill 到最新版本。

### `POST /api/sessions/{session_id}/skill-invoke`

通过斜杠命令调用 Skill（发布 `user.input` 事件触发执行）。

**请求体**：

```json
{
  "skill_name": "pdf_to_markdown",
  "arguments": "input.pdf"
}
```

**响应示例**：

```json
{
  "ok": true,
  "session_id": "sess_abc123",
  "skill_name": "pdf_to_markdown"
}
```

---

## 工作区管理

前缀：`/api/workspace`

工作区目录存放 Agent 运行时使用的 Markdown 文件（如 `AGENTS.md`、`USER.md`、`MEMORY.md` 等）。

### `GET /api/workspace/files`

列出工作区目录下所有 `.md` 文件。

**响应示例**：

```json
[
  {
    "name": "AGENTS.md",
    "size": 1024,
    "editable": true
  },
  {
    "name": "USER.md",
    "size": 512,
    "editable": true
  }
]
```

### `GET /api/workspace/files/{filename}`

读取指定工作区文件内容。仅支持 `.md` 文件。

**响应示例**：

```json
{
  "name": "USER.md",
  "content": "# 用户偏好\n\n- 语言: 中文\n"
}
```

**错误响应**：
- `400` - 仅支持 `.md` 文件
- `404` - 文件不存在

### `PUT /api/workspace/files/{filename}`

创建或更新工作区文件。

**请求体**：

```json
{
  "content": "# 用户偏好\n\n- 语言: 中文\n- 风格: 简洁\n"
}
```

**响应示例**：

```json
{
  "name": "USER.md",
  "size": 48,
  "status": "saved"
}
```

### `DELETE /api/workspace/files/{filename}`

删除工作区文件。核心文件（`AGENTS.md`、`USER.md`）不允许删除。

**错误响应**：
- `403` - 核心文件不允许删除
- `404` - 文件不存在

---

## 配置管理

前缀：`/api/config`

支持读写 `config.yml` 中的三个可编辑 section：`llm_providers`、`agent`、`plugins`。

### `GET /api/config/sections`

获取当前配置的三个 section。

**响应示例**：

```json
{
  "llm_providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-***"
    }
  },
  "agent": {
    "provider": "openai",
    "default_model": "gpt-4o-mini",
    "system_prompt": "你是一个有用的AI助手",
    "default_temperature": 0.2
  },
  "plugins": {}
}
```

### `PUT /api/config/sections`

更新配置并持久化到 `config.yml`，同时热更新运行时配置。

**请求体**（所有字段可选，仅更新提供的 section）：

```json
{
  "agent": {
    "provider": "anthropic",
    "default_model": "claude-3-sonnet"
  }
}
```

**响应示例**：

```json
{
  "status": "saved",
  "sections": {
    "llm_providers": {},
    "agent": {
      "provider": "anthropic",
      "default_model": "claude-3-sonnet"
    },
    "plugins": {}
  }
}
```

**错误响应**：
- `400` - 未提供任何更新内容
- `500` - 写入配置文件失败
