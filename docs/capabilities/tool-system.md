# 工具系统

工具系统是 Sensenova-Claw 的核心能力层之一，为 Agent 提供与外部世界交互的能力。工具系统采用注册表模式管理工具，通过事件驱动实现异步执行，并内置权限控制和结果截断机制。

## 架构概览

```
ToolRegistry（工具注册表）
    ├── Tool 基类（定义工具接口）
    ├── 内置工具（BashCommand, SerperSearch, BraveSearch, BaiduSearch, TavilySearch, FetchUrl, ReadFile, WriteFile）
    ├── 动态 MCP 工具（从外部 MCP server 拉取）
    ├── 编排工具（CreateAgent）
    └── 多 Agent 通信工具（SendMessage，Gateway 启动时注册）

ToolRuntime（工具运行时）
    └── ToolSessionWorker（会话级 Worker，每个 session 一个实例）
         ├── 权限确认（confirmation）
         ├── 工具执行（execute）
         └── 结果截断（truncate）
```

## Tool 基类

所有工具必须继承 `Tool` 基类，位于 `sensenova_claw/capabilities/tools/base.py`：

```python
class ToolRiskLevel(Enum):
    LOW = "low"           # 只读操作，无副作用
    MEDIUM = "medium"     # 有副作用但可控
    HIGH = "high"         # 高风险操作，需用户确认

class Tool:
    name: str = ""                              # 工具名称（唯一标识）
    description: str = ""                       # 描述（传递给 LLM，用于 function calling）
    parameters: dict[str, Any] = {}             # JSON Schema 参数定义
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW  # 风险等级

    async def execute(self, **kwargs: Any) -> Any:
        """执行工具逻辑，子类必须实现"""
        raise NotImplementedError
```

**关键设计**：
- `parameters` 使用 JSON Schema 格式，直接传递给 LLM 的 function calling 接口
- `risk_level` 用于权限控制，决定工具执行前是否需要用户确认
- `execute` 方法是异步的，通过 `asyncio.to_thread` 支持阻塞操作（如 shell 命令执行）

## ToolRegistry

`ToolRegistry` 是工具的注册表，位于 `sensenova_claw/capabilities/tools/registry.py`：

```python
class ToolRegistry:
    _tools: dict[str, Tool]           # 名称 → 工具实例
    _mcp_manager: McpSessionManager   # session → MCP catalog/runtime

    def register(tool: Tool) -> None
        """注册工具到内存字典"""

    def get(name: str, session_id: str | None = None) -> Tool | None
        """按名称获取工具实例，必要时返回动态 MCP 工具适配器"""

    async def ensure_mcp_session(session_id: str) -> None
        """预热该 session 的 MCP catalog"""

    def as_llm_tools(session_id: str | None = None) -> list[dict]
        """转换为 LLM function calling 格式，含动态 MCP 工具"""
```

**初始化流程**：
1. `ToolRegistry.__init__()` 时自动调用 `_register_builtin()`
2. 内置注册 9 个工具：`BashCommandTool`、`SerperSearchTool`、`BraveSearchTool`、`BaiduSearchTool`、`TavilySearchTool`、`FetchUrlTool`、`ReadFileTool`、`WriteFileTool`、`CreateAgentTool`
3. `SendMessageTool` 因依赖注入需要，在 Gateway 启动时单独注册
4. 搜索工具（serper/brave/baidu/tavily）在未配置对应 API key 时不暴露给 LLM
5. MCP 工具按 session 懒加载：首轮对话前连接配置的 MCP server，执行 `listTools`，再物化进工具列表

**`as_llm_tools()` 输出格式**：

```json
[
  {
    "name": "bash_command",
    "description": "执行 shell 命令",
    "parameters": {
      "type": "object",
      "properties": { ... },
      "required": ["command"]
    }
  }
]
```

## 工具执行流程（ToolSessionWorker）

`ToolSessionWorker` 是每个会话的工具执行器，位于 `sensenova_claw/kernel/runtime/workers/tool_worker.py`。完整执行流程如下：

### 1. 接收工具调用请求

Worker 监听 `tool.call_requested` 事件，每个工具调用创建独立的 `asyncio.Task`，支持并发执行多个工具。

```
事件: tool.call_requested
payload: {
    tool_call_id: str,    # 工具调用唯一标识
    tool_name: str,       # 工具名称
    arguments: dict       # 调用参数
}
```

### 2. 发布执行开始信号

发布 `tool.call_started` 事件，通知前端显示加载状态。

### 3. 查找工具实例

从 `ToolRegistry` 按 `tool_name` 获取工具实例。若工具不存在，发布错误结果并返回。

对于 MCP 工具，`ToolRegistry` 会返回一个轻量适配器；它仍通过统一的 `Tool.execute()` 入口执行，但内部会转发到 `McpSessionManager.call_tool(...)`。

### 4. 权限确认检查

```python
def _needs_confirmation(self, tool: Tool) -> bool:
    # 仅当 tools.permission.enabled = true 时启用
    # 检查工具的 risk_level 是否在 auto_approve_levels 中
    # 默认 auto_approve_levels = ["low"]
```

如果工具需要确认：
1. 发布 `tool.confirmation_requested` 事件（包含工具名称、参数、风险等级）
2. 创建 `asyncio.Event` 挂起等待
3. 前端展示确认对话框，用户操作后发布 `tool.confirmation_response`
4. 超时时间由 `tools.permission.confirmation_timeout` 控制，默认 60 秒
5. 超时行为由 `tools.permission.timeout_action` 控制：`reject`（默认，自动拒绝）、`approve`（自动批准）、`block`（无限等待）

### 5. 执行工具

```python
# 注入内部上下文对象
exec_kwargs = dict(arguments)
exec_kwargs["_path_policy"] = self.rt.path_policy        # 路径安全策略
exec_kwargs["_agent_registry"] = self.rt.agent_registry   # Agent 注册表

result = await asyncio.wait_for(
    tool.execute(**exec_kwargs, _session_id=session_id),
    timeout=timeout,  # 默认 15s，可按工具配置
)
```

### 6. 结果截断

```python
def _truncate_result(self, result, tool_call_id) -> Any:
    max_tokens = config.get("tools.result_truncation.max_tokens", 8000)
    max_chars = max_tokens * 3  # 粗略估算：1 token 约 3 字符

    if len(result_str) <= max_chars:
        return result  # 不截断

    # 超出限制：保存完整结果到文件
    # 路径: workspace/{session_id}/tool_result_{tool_call_id[:8]}_{random}.txt
    file_path = session_dir / file_name
    file_path.write_text(result_str)

    # 返回截断文本 + 文件路径引用
    return truncated + f"\n\n[内容已截断] 完整结果已保存到: {file_path}"
```

### 7. 发布结果事件

按顺序发布两个事件：

```
事件 1: tool.call_result（携带执行结果）
payload: {
    tool_call_id, tool_name,
    result: Any,       # 执行结果（可能已截断）
    success: bool,
    error: str
}

事件 2: tool.call_completed（终止信号，不携带 result）
payload: {
    tool_call_id, tool_name,
    success: bool
}
```

### 8. 异常处理

执行异常时额外发布 `error.raised` 事件：

```
事件: error.raised
payload: {
    error_type: str,      # 异常类名
    error_message: str,   # 异常消息
    context: {
        tool_name: str,
        arguments: dict
    }
}
```

## 完整事件流

```
tool.call_requested
  → tool.call_started
  → [tool.confirmation_requested → tool.confirmation_response]  (可选)
  → tool.call_result
  → tool.call_completed
  → [error.raised]  (异常时)
```

## MCP 工具物化流程

1. `AgentSessionWorker` 在处理用户输入前调用 `ToolRegistry.ensure_mcp_session(session_id)`
2. `McpSessionManager` 读取 `mcp.servers`
3. 对每个 server 执行 `listTools`
4. 将结果归一化为 provider-safe 名称：`mcp__<server>__<tool>`
5. `ToolRegistry.as_llm_tools(session_id=...)` 将这些动态工具和内置工具一起暴露给 LLM
6. 当 LLM 调用动态 MCP 工具时，`ToolSessionWorker` 仍沿用统一的 `tool.call_requested -> tool.call_result` 事件链

## 路径安全（PathPolicy）

`read_file`、`write_file`、`bash_command` 工具在执行前通过 `PathPolicy` 检查路径权限：

- **PathVerdict.ALLOW**：允许访问
- **PathVerdict.DENY**：系统目录，绝对禁止
- **PathVerdict.NEED_GRANT**：未授权目录，需要用户许可

`bash_command` 的 `working_dir` 也受 PathPolicy 管控，未指定时默认在 `workspace` 目录执行。

## 配置参考

```yaml
tools:
  permission:
    enabled: false                    # 是否启用权限确认
    auto_approve_levels: ["low"]      # 自动批准的风险等级
    confirmation_timeout: 60          # 确认超时（秒）
    timeout_action: reject            # 超时策略：reject | approve | block

  result_truncation:
    max_tokens: 8000                  # 结果最大 token 数
    save_dir: workspace               # 截断后完整结果保存目录

  bash_command:
    timeout: 15                       # 执行超时（秒）

  serper_search:
    api_key: ${SERPER_API_KEY}
    timeout: 15
    max_results: 10

  fetch_url:
    timeout: 15
    max_response_mb: 10               # HTTP 响应体最大 MB
```

## 扩展工具

新增工具只需三步：

1. **定义工具类**：继承 `Tool`，实现 `execute` 方法
2. **注册工具**：在 `ToolRegistry._register_builtin()` 中添加实例，或通过 `registry.register()` 动态注册
3. **配置超时**：在 `config.yml` 的 `tools.{tool_name}.timeout` 中设置

```python
class MyTool(Tool):
    name = "my_tool"
    description = "自定义工具描述"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"},
        },
        "required": ["param1"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        param1 = kwargs.get("param1", "")
        # 实现工具逻辑
        return {"result": "..."}
```
