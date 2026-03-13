# 内置工具

AgentOS 内置 8 个工具，覆盖命令执行、信息检索、文件操作、安全授权和多 Agent 协作场景。所有工具定义位于 `agentos/capabilities/tools/` 目录下。

## 工具总览

| 工具 | 描述 | 风险等级 | 来源文件 |
|------|------|---------|---------|
| `bash_command` | 执行 shell 命令 | HIGH | builtin.py |
| `serper_search` | Serper API 网络搜索 | LOW | builtin.py |
| `fetch_url` | HTTP 获取网页内容 | LOW | builtin.py |
| `read_file` | 读取文本文件 | LOW | builtin.py |
| `write_file` | 写入文本文件 | MEDIUM | builtin.py |
| `grant_path` | 授权目录访问权限 | HIGH | builtin.py |
| `create_agent` | 创建新 Agent 配置 | MEDIUM | orchestration.py |
| `delegate` | 委托任务给其他 Agent | MEDIUM | delegate_tool.py |

## bash_command

执行 shell 命令，支持指定工作目录。

**风险等级**：HIGH（默认需要用户确认）

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `command` | string | 是 | 要执行的 shell 命令 |
| `working_dir` | string | 否 | 工作目录，默认为 workspace |

**返回值**：

```json
{
  "return_code": 0,
  "stdout": "命令输出内容",
  "stderr": ""
}
```

**安全机制**：
- `working_dir` 受 PathPolicy 管控：DENY 的系统目录无法作为工作目录
- 未指定 `working_dir` 时默认在 `workspace` 目录执行
- 执行超时：300 秒（硬编码），可通过 `tools.bash_command.timeout` 配置 Worker 层超时
- 通过 `subprocess.run` 在线程池中执行，不阻塞事件循环

**使用示例**：

```json
{
  "command": "ls -la /tmp",
  "working_dir": "/home/user/project"
}
```

## serper_search

通过 Serper API 执行 Google 搜索，返回结构化搜索结果。

**风险等级**：LOW

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 搜索关键词 |
| `tbs` | string | 否 | 时间过滤：`h`(小时)、`d`(天)、`m`(月)、`y`(年) |
| `page` | integer | 否 | 页码，默认 1 |

**返回值**：

```json
{
  "query": "AgentOS 架构",
  "items": [
    {
      "title": "搜索结果标题",
      "link": "https://example.com",
      "snippet": "搜索结果摘要..."
    }
  ]
}
```

**配置**：
- `tools.serper_search.api_key`：Serper API 密钥（必须）
- `tools.serper_search.timeout`：请求超时，默认 15 秒
- `tools.serper_search.max_results`：最大返回结果数，默认 10

**注意**：未配置 `SERPER_API_KEY` 时返回空结果（不报错），附带提示信息。

## fetch_url

通过 HTTP GET 获取网页内容，支持重定向跟随。

**风险等级**：LOW

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 目标 URL |
| `method` | string | 否 | HTTP 方法，默认 GET |

**返回值**：

```json
{
  "url": "https://example.com/final-url",
  "status_code": 200,
  "content": "网页 HTML 内容..."
}
```

**保护机制**：
- 内存保护截断：响应体超过 `tools.fetch_url.max_response_mb`（默认 10 MB）时自动截断
- 返回原始内容，由 ToolRuntime 层做 token 级截断
- 支持重定向跟随（`follow_redirects=True`）
- 返回值中 `url` 为最终重定向后的地址

## read_file

读取文本文件内容，支持按行范围读取。

**风险等级**：LOW

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件路径 |
| `encoding` | string | 否 | 编码，默认 `utf-8` |
| `start_line` | integer | 否 | 起始行号（从 1 开始），默认 1 |
| `num_lines` | integer | 否 | 读取行数，省略时读取到末尾 |

**返回值**：

```json
{
  "file_path": "/absolute/path/to/file.txt",
  "content": "文件内容..."
}
```

**错误返回**：

```json
{
  "success": false,
  "error": "文件不存在: /path/to/file.txt"
}
```

**安全机制**：
- 路径通过 PathPolicy 检查读取权限
- DENY 的系统目录（如 `/etc`、`/sys`）无法读取
- NEED_GRANT 的目录需要用户先授权

## write_file

写入文本文件，支持全量覆盖、追加和按行插入/替换三种模式。

**风险等级**：MEDIUM

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件路径 |
| `content` | string | 是 | 要写入的内容 |
| `mode` | string | 否 | 写入模式：`write`(覆盖，默认)、`append`(追加)、`insert`(插入/替换) |
| `start_line` | integer | 否 | 起始行号（仅 `insert` 模式），从 1 开始 |
| `end_line` | integer | 否 | 结束行号（仅 `insert` 模式），省略时为纯插入，指定时替换该范围 |

**写入模式说明**：

| 模式 | 行为 |
|------|------|
| `write` | 全量覆盖文件内容 |
| `append` | 追加到文件末尾 |
| `insert`（无 end_line） | 在 `start_line` 之前插入新内容，原内容下移 |
| `insert`（有 end_line） | 替换 `start_line` 到 `end_line` 范围的内容 |

**返回值**：

```json
{
  "success": true,
  "file_path": "/absolute/path/to/file.txt",
  "size": 1024,
  "mode": "write"
}
```

**安全机制**：
- 路径通过 PathPolicy 检查写入权限
- 自动创建父目录（`mkdir -p` 语义）
- 优先写入 workspace 目录

## grant_path

授权 Agent 访问指定目录。因为风险等级为 HIGH，执行前自动触发用户确认流程。

**风险等级**：HIGH

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 要授权的目录路径 |

**返回值**：

```json
{
  "success": true,
  "granted": "/resolved/absolute/path"
}
```

**使用场景**：当 `read_file` 或 `write_file` 返回 `NEED_GRANT` 错误时，Agent 可调用此工具请求用户授权，授权后重试文件操作。

## create_agent

在对话中动态创建新的 Agent 配置。创建后 Agent 立即可用，可在后续对话中通过委托机制调用。

**风险等级**：MEDIUM

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | Agent 唯一标识，slug 格式（如 `research-agent`） |
| `name` | string | 是 | Agent 名称，人类可读 |
| `description` | string | 否 | Agent 描述，说明用途和能力 |
| `system_prompt` | string | 否 | 系统提示词，定义角色和行为 |
| `provider` | string | 否 | LLM 提供商（如 `openai`、`anthropic`），留空继承默认 |
| `model` | string | 否 | 模型名称（如 `gpt-4o-mini`），留空继承默认 |
| `temperature` | number | 否 | 温度参数（0-2），默认 0.2 |
| `tools` | array[string] | 否 | 允许使用的工具列表，空数组 = 全部 |
| `can_delegate_to` | array[string] | 否 | 可委托的目标 Agent ID 列表，空数组 = 全部 |

**返回值**：

```json
{
  "success": true,
  "agent_id": "research-agent",
  "name": "研究助手",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "message": "Agent '研究助手' (id=research-agent) 已创建成功，可在委托或新会话中使用"
}
```

**行为**：
- 未指定的 `provider`/`model`/`temperature` 从 default Agent 继承
- 创建后同时持久化到 `workspace/agents/{id}.json`
- 若 `id` 已存在，返回错误

## delegate

将子任务委托给另一个 Agent 处理。对调用方（LLM）表现为同步工具调用，内部通过事件系统异步执行。

**风险等级**：MEDIUM

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target_agent` | string | 是 | 目标 Agent 的 ID |
| `task` | string | 是 | 要委托的任务描述 |
| `context` | string | 否 | 传递给目标 Agent 的上下文信息 |

**返回值**：

```json
{
  "success": true,
  "result": "目标 Agent 的最终响应内容"
}
```

**内部机制**：
1. 验证目标 Agent 存在且可委托
2. 检查委托深度（防止无限递归，默认最大 3 层）
3. 创建子 session（`delegate_{random_id}`），绑定目标 Agent 配置
4. 向子 session 发布 `ui.user_input` 事件
5. 监听子 session 的 `agent.step_completed` 事件
6. 返回子 Agent 的最终响应
7. 超时：默认 300 秒

**错误情况**：
- 目标 Agent 不存在：`Agent '{id}' not found`
- 超过最大委托深度：`Maximum delegation depth exceeded`
- 子 Agent 执行超时：`Delegation timed out after 300s`
