# 多 Agent 协作

AgentOS 支持在一个平台中定义和管理多个 Agent，每个 Agent 拥有独立的 LLM 配置、工具权限和系统提示。Agent 之间可以通过委托机制协作完成复杂任务。

## 核心概念

- **AgentConfig**：Agent 的完整配置数据类，定义一个行为剖面（system prompt + tools + skills + model + temperature）
- **AgentRegistry**：管理 Agent 配置的 CRUD、加载和发现
- **委托（Delegation）**：一个 Agent 将子任务交给另一个 Agent 处理

## AgentConfig 数据结构

位于 `agentos/capabilities/agents/config.py`：

```python
@dataclass
class AgentConfig:
    # 标识
    id: str                      # 唯一标识（slug 格式，如 "research-agent"）
    name: str                    # 人类可读名称
    description: str = ""        # 描述（LLM 用于判断委托目标）

    # LLM 配置
    provider: str = "openai"     # LLM 提供商："openai", "anthropic", "gemini", "mock"
    model: str = "gpt-4o-mini"   # 模型名称
    temperature: float = 0.2     # 温度参数
    max_tokens: int | None = None  # 最大 token 数

    # 行为配置
    system_prompt: str = ""      # 自定义系统提示词
    tools: list[str] = []        # 允许使用的工具列表（空 = 全部）
    skills: list[str] = []       # 允许使用的 Skills 列表（空 = 全部）

    # 委托配置
    can_delegate_to: list[str] = []  # 可委托的目标 Agent ID 列表（空 = 全部）
    max_delegation_depth: int = 3    # 最大委托深度

    # 元信息
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0
```

**序列化方法**：
- `to_dict()` → `dict`：序列化为字典（用于 JSON 持久化和 API 响应）
- `from_dict(data)` → `AgentConfig`：从字典反序列化
- `create(**kwargs)` → `AgentConfig`：便捷创建，自动填充时间戳

## AgentRegistry

位于 `agentos/capabilities/agents/registry.py`，管理所有 Agent 配置：

```python
class AgentRegistry:
    def __init__(self, config_dir: Path)
        """config_dir: Agent JSON 文件持久化目录"""

    # CRUD
    def register(agent: AgentConfig) -> None        # 注册或更新
    def get(agent_id: str) -> AgentConfig | None     # 获取配置
    def list_all() -> list[AgentConfig]              # 列出所有已启用 Agent
    def delete(agent_id: str) -> bool                # 删除（default 不可删）
    def update(agent_id: str, updates: dict) -> AgentConfig | None  # 部分更新

    # 委托发现
    def get_delegatable(from_agent_id: str) -> list[AgentConfig]
        """获取某个 Agent 可以委托的目标 Agent 列表"""

    # 加载
    def load_from_config(config_data: dict) -> None  # 从 config.yml 加载
    def load_from_dir() -> None                      # 从 JSON 文件加载

    # 持久化
    def save(agent: AgentConfig) -> None             # 保存到 JSON 文件
```

### 加载流程

AgentRegistry 从两个来源加载 Agent 配置：

**1. 从 config.yml 加载**

```yaml
# config.yml
agent:
  provider: openai
  default_model: gpt-4o-mini
  default_temperature: 0.2
  system_prompt: "你是一个有用的AI助手"

agents:
  research-agent:
    name: 研究助手
    description: 擅长信息检索和分析的 Agent
    system_prompt: "你是一个专业的研究助手..."
    tools: ["serper_search", "fetch_url", "read_file"]
    can_delegate_to: []

  code-reviewer:
    name: 代码审查员
    description: 擅长代码审查和优化建议的 Agent
    provider: anthropic
    model: claude-3-haiku
    tools: ["read_file", "bash_command"]
```

加载规则：
- `agent.*` 段始终创建 `id="default"` 的 AgentConfig（向后兼容）
- `agents.*` 段中的 Agent 未指定的 `provider`/`model`/`temperature` 继承 default Agent 的配置

**2. 从持久化目录加载**

```
workspace/agents/
  ├── research-agent.json
  └── code-reviewer.json
```

每个 JSON 文件包含完整的 AgentConfig 字段。通过 `create_agent` 工具创建的 Agent 会自动保存到此目录。

### 委托发现

`get_delegatable(from_agent_id)` 的逻辑：

```python
# 1. 查找来源 Agent 的配置
source = agents[from_agent_id]

# 2. 如果 can_delegate_to 为空列表 → 可委托给所有其他已启用 Agent
if not source.can_delegate_to:
    return [a for a in agents.values() if a.id != from_agent_id and a.enabled]

# 3. 否则只返回显式列出的目标
return [agents[aid] for aid in source.can_delegate_to if agents[aid].enabled]
```

## 委托流程

### 整体流程

```
Agent A（调用方）
  │
  ├─ LLM 决定需要委托任务
  ├─ 调用 delegate 工具
  │    target_agent: "research-agent"
  │    task: "搜索 AgentOS 的最新文档"
  │
  ├─ DelegateTool 执行：
  │    ├─ 1. 验证 target 存在
  │    ├─ 2. 检查委托深度 < max_delegation_depth
  │    ├─ 3. 创建子 session（delegate_{random_id}）
  │    │      meta.agent_id = "research-agent"
  │    │      meta.parent_session_id = 当前 session
  │    │      meta.delegation_depth = current + 1
  │    ├─ 4. 订阅子 session 的完成事件
  │    ├─ 5. 向子 session 发布 ui.user_input
  │    └─ 6. 等待 agent.step_completed（超时 300s）
  │
Agent B（研究助手）
  │
  ├─ AgentRuntime 监听到 ui.user_input
  ├─ 使用 research-agent 的配置（provider, model, tools...）
  ├─ 执行搜索和分析
  └─ 发布 agent.step_completed
        │
        └─ DelegateTool 收到结果，返回给 Agent A
```

### 委托深度控制

防止 Agent 间无限递归委托：

```python
# AgentConfig 默认
max_delegation_depth: int = 3

# DelegateTool 检查
current_depth = session_meta.get("delegation_depth", 0)
if current_depth >= target_config.max_delegation_depth:
    return {"error": "Maximum delegation depth exceeded"}

# 子 session 的深度 = 当前深度 + 1
new_depth = current_depth + 1
```

### 上下文传递

如果委托时提供了 `context` 参数，会与 `task` 合并为用户输入：

```python
# 有上下文时
user_input = f"上下文信息：\n{context}\n\n任务：\n{task}"

# 无上下文时
user_input = task
```

## Agent 在会话中的使用

### 创建会话时指定 Agent

会话创建时可指定 `agent_id`，存入 session meta：

```json
{
  "session_id": "abc123",
  "meta": {
    "agent_id": "research-agent",
    "title": "研究任务"
  }
}
```

### AgentRuntime 的配置解析

AgentRuntime 处理用户输入时：

1. 从 session meta 获取 `agent_id`
2. 查询 AgentRegistry 获取 `AgentConfig`
3. 使用 Agent 配置覆盖全局默认值：
   - `provider` 和 `model` → LLM 调用配置
   - `system_prompt` → 系统提示词
   - `tools` → 过滤可用工具列表
   - `skills` → 过滤可用 Skill 列表

### 动态创建 Agent

除了配置文件定义，还可以在对话中通过 `create_agent` 工具动态创建：

```
用户: 帮我创建一个专门翻译英文文档的 Agent

Agent 调用 create_agent:
  id: "translator"
  name: "翻译助手"
  description: "专门将英文文档翻译为中文"
  system_prompt: "你是一个专业的英中翻译..."
  tools: ["read_file", "write_file"]
```

创建后：
- 立即注册到 AgentRegistry 内存
- 持久化到 `workspace/agents/translator.json`
- 可在后续会话或委托中使用

## 配置参考

### config.yml 完整示例

```yaml
agent:
  provider: openai
  default_model: gpt-4o-mini
  default_temperature: 0.2
  system_prompt: "你是一个有用的AI助手"

agents:
  research-agent:
    name: 研究助手
    description: 擅长信息检索和数据分析
    system_prompt: |
      你是一个专业的研究助手，擅长：
      - 使用搜索工具查找最新信息
      - 分析和总结搜索结果
      - 提供有据可依的回答
    tools: ["serper_search", "fetch_url", "read_file"]
    can_delegate_to: []
    max_delegation_depth: 2

  code-reviewer:
    name: 代码审查员
    description: 擅长代码审查和优化建议
    provider: anthropic
    model: claude-3-haiku
    temperature: 0.1
    tools: ["read_file", "bash_command"]
    can_delegate_to: ["research-agent"]
    max_delegation_depth: 1
    enabled: true
```

### Agent JSON 文件示例

```json
{
  "id": "translator",
  "name": "翻译助手",
  "description": "专门将英文文档翻译为中文",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.2,
  "max_tokens": null,
  "system_prompt": "你是一个专业的英中翻译...",
  "tools": ["read_file", "write_file"],
  "skills": [],
  "can_delegate_to": [],
  "max_delegation_depth": 3,
  "enabled": true,
  "created_at": 1709625600.0,
  "updated_at": 1709625600.0
}
```
