# 核心模块设计

## AgentRuntime 模块

AgentRuntime 是系统的核心执行引擎，负责协调整个对话流程。

### 设计原则

**事件驱动而非循环驱动**

传统的 Agent 实现通常使用循环：
```python
# 传统方式 (不采用)
while not done:
    response = llm.call(messages)
    if response.tool_calls:
        results = execute_tools(response.tool_calls)
        messages.append(results)
    else:
        done = True
```

AgentOS 采用事件驱动方式，通过监听和发布事件来推进流程，实现更好的解耦和可观测性。

### 核心职责

1. **会话管理**: 创建和维护 session_id、turn_id
2. **流程编排**: 根据事件决定下一步动作
3. **上下文构建**: 调用 ContextBuilder 准备 LLM 输入
4. **事件发布**: 发布各阶段的状态事件

### 状态机设计

```
IDLE → PROCESSING_INPUT → WAITING_LLM → WAITING_TOOL → COMPLETED
  ↑                                          ↓
  └──────────────────────────────────────────┘
```

### 事件处理逻辑

#### 接收 user.input 事件
```python
1. 生成 session_id (如果是新会话)
2. 生成 turn_id
3. 初始化会话状态
4. 发布 agent.step_started
5. 调用 ContextBuilder.build_messages()
6. 发布 llm.call_requested
7. 状态转换: IDLE → WAITING_LLM
```

#### 接收 llm.call_completed 事件
```python
1. 检查 finish_reason
2. 如果是 "tool_calls":
   - 解析工具调用列表
   - 为每个工具调用发布 tool.call_requested
   - 状态转换: WAITING_LLM → WAITING_TOOL
3. 如果是 "stop":
   - 发布 agent.step_completed
   - 状态转换: WAITING_LLM → COMPLETED
```

#### 接收 tool.call_completed 事件
```python
1. 收集所有工具调用结果
2. 如果所有工具都已完成:
   - 调用 ContextBuilder 添加工具结果
   - 发布新的 llm.call_requested
   - 状态转换: WAITING_TOOL → WAITING_LLM
```

### 并发工具调用

当 LLM 返回多个工具调用时，AgentRuntime 会并发执行所有工具，提升效率。

```python
# 伪代码
tool_calls = response.tool_calls
pending_tools = set(tool_call.id for tool_call in tool_calls)

for tool_call in tool_calls:
    publish_event("tool.call_requested", tool_call)

# 等待所有工具完成
while pending_tools:
    event = await private_bus.get()
    if event.type == "tool.call_completed":
        pending_tools.remove(event.payload["tool_call_id"])
```

## LLM 模块

LLM 模块提供统一的大语言模型调用接口，屏蔽不同提供商的差异。

### 支持的提供商

- **OpenAI**: GPT-4, GPT-3.5 等
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus 等

### 接口设计

```python
class LLMProvider:
    async def call(
        self,
        model: str,
        messages: list,
        tools: list = None,
        temperature: float = 0.7,
        max_tokens: int = None
    ) -> dict:
        """调用 LLM API"""
        pass
```

### 事件处理

#### 接收 llm.call_requested 事件
```python
1. 提取 payload 中的参数
2. 发布 llm.call_started
3. 根据 model 选择对应的 Provider
4. 调用 Provider.call()
5. 发布 llm.call_completed (包含响应和 usage)
```

### 错误处理

- API 调用失败: 发布 error.raised 事件
- 重试策略: 指数退避，最多重试 3 次
- 超时处理: 默认 60 秒超时

### 响应格式标准化

不同提供商的响应格式会被标准化为统一结构：

```python
{
    "content": str,              # 文本内容
    "tool_calls": [              # 工具调用列表
        {
            "id": str,
            "name": str,
            "arguments": dict
        }
    ],
    "finish_reason": str         # stop/tool_calls/length
}
```

## ToolRuntime 模块

ToolRuntime 负责工具的注册、管理和执行。

### 工具注册机制

```python
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema

    async def execute(self, **kwargs) -> any:
        """执行工具逻辑"""
        pass
```

### 内置工具列表

#### 1. bash_command
执行 Bash/Shell 命令。

**参数**:
- `command`: str - 要执行的命令
- `working_dir`: str - 工作目录 (可选)

**返回**: 命令输出或错误信息

**超时**: 15 秒

#### 2. serper_search
使用 Serper.dev API 进行网络搜索。

**LLM 需提供的参数**:
- `q`: str - 搜索关键词
- `tbs`: str (可选) - 时间范围过滤，不传表示任意时间；`h`=最近1小时，`d`=最近1天，`m`=最近1个月，`y`=最近1年
- `page`: int (可选) - 页码，默认 1

**固定参数**（由系统注入，LLM 无需关心）:
- `gl`: `"cn"` - 地区
- `hl`: `"zh-cn"` - 语言

**示例调用**:
```python
import requests

url = "https://google.serper.dev/search"
payload = {
    "q": "apple inc",
    "gl": "cn",
    "hl": "zh-cn",
    "tbs": "qdr:h",  # 不传该参数表示任意时间，h/d/m/y 分别表示最近小时/日/月/年
    "page": 1,
}
headers = {
    "X-API-KEY": "<SERPER_API_KEY>",
    "Content-Type": "application/json",
}
response = requests.post(url, headers=headers, json=payload)
print(response.text)
```

**返回**: 搜索结果列表

**超时**: 15 秒

#### 3. fetch_url
获取指定 URL 的内容。

**参数**:
- `url`: str - 目标 URL
- `method`: str - HTTP 方法 (默认 GET)

**返回**: 网页内容

**超时**: 15 秒

#### 4. read_file
读取文件内容。

**参数**:
- `file_path`: str - 文件路径（绝对或相对）
- `encoding`: str - 编码格式（默认 utf-8）
- `start_line`: int (可选) - 起始行号，从 1 开始，默认从第 1 行开始
- `num_lines`: int (可选) - 读取的行数，不传则读取到文件末尾

**返回**: 文件内容

**限制**: 仅支持文本文件

#### 5. write_file
写入文件内容。

**参数**:
- `file_path`: str - 文件路径
- `content`: str - 要写入的内容
- `mode`: str - 写入模式 (write/append)
- `start_line`: int (可选) - 写入起始行号，从 1 开始，仅在 `mode=insert` 时生效

**返回**: 成功或失败信息

#### 6. search_skill
搜索可用的 Agent Skill 列表。

**参数**:
- `keyword`: str (可选) - 按关键词过滤 Skill 名称或描述，不传则返回全部

**返回**: 匹配的 Skill 列表，每项包含 `skill_name`、`description` 等字段

---

#### 7. load_skill
加载并执行 Agent Skill。

**参数**:
- `skill_name`: str - Skill 名称
- `skill_args`: dict - Skill 参数

**返回**: Skill 执行结果

### 事件处理

#### 接收 tool.call_requested 事件
```python
1. 提取 tool_name 和 arguments
2. 发布 tool.call_started
3. 查找对应的 Tool 实例
4. 发布 tool.execution_start
5. 执行 Tool.execute() (带超时控制)
6. 发布 tool.execution_end
7. 发布 tool.call_completed (包含结果或错误)
```

### 超时控制

所有工具执行都使用 asyncio.wait_for() 进行超时控制：

```python
try:
    result = await asyncio.wait_for(
        tool.execute(**arguments),
        timeout=15.0
    )
except asyncio.TimeoutError:
    result = {"error": "Tool execution timeout"}
```

### 安全考虑

v0.1 版本暂不实现安全限制，但预留扩展点：
- 命令白名单/黑名单
- 文件访问权限检查
- 资源使用限制

## ContextBuilder 模块

ContextBuilder 负责构建发送给 LLM 的消息列表。

### 核心功能

1. **初始化系统提示**: 加载 Agent 的系统提示词
2. **添加历史消息**: 从数据库加载历史对话
3. **添加工具结果**: 将工具执行结果格式化为消息
4. **上下文压缩**: 当消息过长时进行智能压缩 (v0.1 暂不实现)

### 消息格式

遵循 OpenAI 的消息格式标准：

```python
[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."}
]
```

### 构建流程

```python
def build_messages(session_id: str, turn_id: str) -> list:
    messages = []

    # 1. 添加系统提示
    messages.append(get_system_prompt())

    # 2. 加载历史消息
    history = load_history_from_db(session_id)
    messages.extend(history)

    # 3. 添加当前用户输入
    current_input = get_current_input(turn_id)
    messages.append(current_input)

    return messages
```

### 工具结果处理

当接收到工具执行结果时，需要将其转换为 LLM 可理解的格式：

```python
def add_tool_results(messages: list, tool_results: list) -> list:
    for result in tool_results:
        messages.append({
            "role": "tool",
            "tool_call_id": result["tool_call_id"],
            "content": json.dumps(result["result"])
        })
    return messages
```
