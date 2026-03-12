# AgentOS v1.7 — 编排中心 UI 整合 + 对话式创建工具

> 版本: v1.7
> 日期: 2026-03-12
> 前置: v1.0（多 Agent 与 Workflow）

---

## 1. 概述

本次更新包含三个紧密关联的改进：

1. **编排中心 UI**：将 Agents 和 Workflows 两个独立页面合并为统一的"编排中心"仪表盘
2. **会话目标选择器**：在 Sessions / Chat 页面增加 Agent 和 Workflow 选择能力
3. **对话式编排工具**：新增 `create_agent` 和 `create_workflow` 内置工具，使 LLM 能在对话中直接创建 Agent 和 Workflow

---

## 2. 编排中心 UI

### 2.1 设计思路

Agent（执行者）和 Workflow（编排方案）是同一层面的概念，都属于"编排"范畴。将它们放在同一页面，用户可以一屏总览所有可用的编排资源。

### 2.2 页面结构

```
/agents  (原 Agents 页面，改造为编排中心)
├── Header: "编排中心" + [New Agent] + [New Workflow]
├── 搜索栏: 同时搜索 Agents 和 Workflows
├── Agents 区块
│   ├── 区块标题: Bot 图标 + "Agents" + 数量徽章
│   └── 卡片网格: 每张卡片显示状态/名称/描述/provider·model/session·tool·skill 数
├── 分隔线
└── Workflows 区块
    ├── 区块标题: Network 图标 + "Workflows" + 数量徽章
    └── 卡片网格: 每张卡片显示启用状态/名称/描述/版本/节点·边数
```

### 2.3 导航变更

```python
# 变更前
navItems = [
    "/agents"    → Agents
    "/workflows" → Workflows
]

# 变更后
navItems = [
    "/agents"    → 编排中心 (同时高亮匹配 /workflows/* 路径)
]

# /workflows 列表页重定向到 /agents
# /workflows/{id} 详情页保持不变
```

### 2.4 涉及文件

| 文件 | 变更 |
|------|------|
| `frontend/app/agents/page.tsx` | 重写为编排中心，包含 Agent + Workflow 列表 + 两个创建弹窗 |
| `frontend/app/workflows/page.tsx` | 改为 redirect 到 `/agents` |
| `frontend/components/layout/DashboardNav.tsx` | 移除 Workflows 入口，Agents 改名为"编排中心" |

---

## 3. 会话目标选择器

### 3.1 设计思路

用户发起新会话时，应能指定使用哪个 Agent（不同模型/提示词/工具集）或哪个 Workflow（自动化多步执行）。

### 3.2 Sessions 页面 — New Chat 弹窗

点击 "New Chat" 弹出选择弹窗：

```
┌─────────────────────────────┐
│ 新建会话                  ✕ │
├─────────────────────────────┤
│ [选择 Agent] [选择 Workflow] │  ← Tab 切换
├─────────────────────────────┤
│ 🔍 搜索...                  │
├─────────────────────────────┤
│ ● Default Agent  (default)  │  ← 可点击，跳转 /chat?agent=xxx
│ ● Research Agent (research)  │
├─────────────────────────────┤
│ 或直接使用默认 Agent 开始 →  │
└─────────────────────────────┘
```

选择后导航到 `/chat?agent={id}` 或 `/chat?workflow={id}`。

### 3.3 Chat 页面 — Target Selector

输入框下方新增紧凑型下拉选择器：

```
┌─────────────────────────────────┐
│ [输入框...]              [发送] │
│ [🤖 Default Agent ▾] ● 已连接   │  ← 可切换
└─────────────────────────────────┘
```

点击展开弹出窗口，包含 Agents / Workflows 两个 Tab。

### 3.4 Agent 模式 vs Workflow 模式

```python
class ChatBehavior:
    """Chat 页面根据选择的目标切换行为"""

    def agent_mode(agent_id: str):
        # 1. 创建 session 时传递 agent_id
        ws.send({
            "type": "create_session",
            "payload": {"agent_id": agent_id, "meta": {...}}
        })
        # 2. 后端 AgentRuntime 根据 session meta 中的 agent_id
        #    查找对应 AgentConfig（provider/model/system_prompt/tools）
        # 3. 后续 user_input 走标准 WebSocket 对话流程

    def workflow_mode(workflow_id: str):
        # 1. 输入框 placeholder 变为"输入 Workflow 执行内容..."
        # 2. 发送时调用 REST API 而非 WebSocket
        response = POST(f"/api/workflows/{workflow_id}/run", {"input": content})
        # 3. 展示每个节点的执行结果（作为 tool 类型消息）
        # 4. 展示最终输出（作为 assistant 消息）
```

### 3.5 空状态差异化

| 模式 | 图标 | 提示文字 | 标签 |
|------|------|----------|------|
| Agent 模式 | 🤖 Bot | "开始一段新对话" | `Agent: {agent_id}` (蓝色) |
| Workflow 模式 | 🔗 Network | "开始一段新对话" | `Workflow: {workflow_id}` (绿色) |
| 默认 | 🤖 Bot | "开始一段新对话" / "在下方输入你的问题" | 无 |

### 3.6 Sessions 列表 — Target 列

Sessions 表格新增 "Target" 列，从 session meta 中读取 `agent_id` 或 `workflow_id`，显示为彩色标签：

- Agent 标签: 蓝色背景，Bot 图标
- Workflow 标签: 绿色背景，Network 图标
- 默认: 灰色文字 "default"

### 3.7 涉及文件

| 文件 | 变更 |
|------|------|
| `frontend/app/sessions/page.tsx` | New Chat 弹窗 + Target 列 |
| `frontend/app/chat/page.tsx` | TargetSelector 组件 + URL 参数读取 + Workflow 运行逻辑 |

---

## 4. 对话式编排工具

### 4.1 设计思路

用户在对话中说"帮我创建一个专门做代码审查的 Agent"，LLM 应该能直接调用工具完成创建，而不需要用户手动到管理界面操作。

### 4.2 工具定义

#### create_agent

```python
class CreateAgentTool(Tool):
    name = "create_agent"
    description = "创建一个新的 AI Agent"
    risk_level = ToolRiskLevel.MEDIUM   # 有副作用但可控

    parameters = {
        "id": str,          # 必填，slug 格式
        "name": str,        # 必填，人类可读名称
        "description": str, # Agent 描述
        "system_prompt": str,   # 系统提示词
        "provider": str,    # LLM 提供商（留空继承 default）
        "model": str,       # 模型名称（留空继承 default）
        "temperature": float,   # 温度参数（留空默认 0.2）
        "tools": list[str], # 允许的工具列表（空 = 全部）
        "can_delegate_to": list[str],  # 可委托目标（空 = 全部）
    }

    async def execute(self, **kwargs):
        # 1. 从 kwargs 提取注入的 _agent_registry
        # 2. 校验 id 不重复
        # 3. 从 default Agent 继承未指定的配置
        # 4. 创建 AgentConfig，注册到 registry，持久化到磁盘
        # 5. 返回创建结果
```

#### create_workflow

```python
class CreateWorkflowTool(Tool):
    name = "create_workflow"
    description = "创建一个多步骤工作流（DAG）"
    risk_level = ToolRiskLevel.MEDIUM

    parameters = {
        "id": str,          # 必填，slug 格式
        "name": str,        # 必填
        "description": str,
        "nodes": list[{     # 必填，至少一个节点
            "id": str,          # 节点 ID
            "agent_id": str,    # 执行节点的 Agent（默认 default）
            "description": str,
            "input_template": str,  # 支持 {workflow.input}, {node_id.output}
            "timeout": float,
            "retry": int,
        }],
        "edges": list[{     # 节点间执行路径
            "from_node": str,
            "to_node": str,
            "condition": str,   # 条件表达式
            "label": str,
        }],
        "entry_node": str,
        "exit_nodes": list[str],
        "max_iterations": int,
        "timeout": float,
    }

    async def execute(self, **kwargs):
        # 1. 从 kwargs 提取注入的 _workflow_registry
        # 2. 校验 id 不重复
        # 3. 构建 WorkflowNode / WorkflowEdge / Workflow 对象
        # 4. 注册到 registry，持久化到磁盘（YAML 格式）
        # 5. 返回创建结果
```

### 4.3 上下文注入机制

工具执行时需要访问 `AgentRegistry` 和 `WorkflowRegistry`，通过已有的 kwargs 注入机制传递：

```python
# ToolRuntime 持有 registry 引用
class ToolRuntime:
    def __init__(self, ..., agent_registry=None, workflow_registry=None):
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry

# ToolSessionWorker 在执行工具时注入
class ToolSessionWorker:
    async def _handle_tool_requested(self, event):
        arguments = event.payload.get("arguments", {})
        # 注入上下文对象（与 _path_policy 同一机制）
        if self.rt.agent_registry:
            arguments["_agent_registry"] = self.rt.agent_registry
        if self.rt.workflow_registry:
            arguments["_workflow_registry"] = self.rt.workflow_registry
        result = await tool.execute(**arguments, _session_id=session_id)

# 工具内部通过 kwargs.pop 提取并使用
class CreateAgentTool(Tool):
    async def execute(self, **kwargs):
        registry = kwargs.pop("_agent_registry", None)
        ...
```

### 4.4 main.py 初始化

```python
# agent_registry 在 ToolRuntime 构造时传入
tool_runtime = ToolRuntime(
    bus_router=bus_router,
    registry=tool_registry,
    path_policy=path_policy,
    agent_registry=agent_registry,    # 直接传入
)

# workflow_registry 在后续条件块中延迟设置
if config.get("workflow.enabled", True):
    workflow_registry = WorkflowRegistry(...)
    tool_runtime.workflow_registry = workflow_registry   # 延迟注入
```

### 4.5 涉及文件

| 文件 | 变更 |
|------|------|
| `backend/app/tools/orchestration.py` | **新增** CreateAgentTool + CreateWorkflowTool |
| `backend/app/tools/registry.py` | 注册两个新工具 |
| `backend/app/runtime/tool_runtime.py` | 新增 agent_registry / workflow_registry 属性 |
| `backend/app/runtime/workers/tool_worker.py` | 注入 _agent_registry / _workflow_registry |
| `backend/app/main.py` | 传递 registry 给 ToolRuntime |

---

## 5. 完整工具列表（更新后）

| # | 工具名 | 描述 | 风险等级 | 来源 |
|---|--------|------|----------|------|
| 1 | `bash_command` | 执行 shell 命令 | HIGH | builtin |
| 2 | `serper_search` | 网络搜索 | LOW | builtin |
| 3 | `fetch_url` | 获取网页内容 | LOW | builtin |
| 4 | `read_file` | 读取文本文件 | LOW | builtin |
| 5 | `write_file` | 写入文本文件 | MEDIUM | builtin |
| 6 | `grant_path` | 授权目录访问 | HIGH | builtin |
| 7 | **`create_agent`** | **创建新 Agent** | **MEDIUM** | **orchestration** |
| 8 | **`create_workflow`** | **创建新 Workflow** | **MEDIUM** | **orchestration** |
| 9 | `delegate` | 委托子任务给其他 Agent | MEDIUM | delegation |
| 10 | `run_workflow` | 运行预定义 Workflow | MEDIUM | workflow |
| 11 | `message` | 主动发送消息到渠道 | MEDIUM | plugin(feishu) |
| 12 | `cron_manage` | 管理定时任务 | MEDIUM | plugin(cron) |

---

## 6. 用户交互示例

### 示例 1：对话中创建 Agent

```
用户: 帮我创建一个专门做代码审查的 Agent，要求严格检查代码规范

助手: 好的，我来创建一个代码审查 Agent。
      [调用 create_agent 工具]
      参数: {
        "id": "code-reviewer",
        "name": "代码审查专家",
        "description": "专注于代码规范检查和最佳实践审查",
        "system_prompt": "你是一位严格的代码审查专家...",
        "tools": ["read_file", "bash_command"]
      }

      ✅ Agent "代码审查专家" (id=code-reviewer) 已创建成功！
      你可以在新会话中选择该 Agent，或通过委托机制让当前 Agent 将代码审查任务交给它。
```

### 示例 2：对话中创建 Workflow

```
用户: 帮我创建一个先搜索资料再写报告的工作流

助手: 好的，我来创建一个"搜索-撰写"工作流。
      [调用 create_workflow 工具]
      参数: {
        "id": "search-and-report",
        "name": "搜索撰写工作流",
        "nodes": [
          {"id": "search", "agent_id": "default", "input_template": "搜索以下主题的资料: {workflow.input}"},
          {"id": "write", "agent_id": "default", "input_template": "根据以下搜索结果撰写报告:\n{search.output}"}
        ],
        "edges": [{"from_node": "search", "to_node": "write"}]
      }

      ✅ Workflow "搜索撰写工作流" 已创建，包含 2 个节点和 1 条边。
      你可以在 Chat 页面选择此 Workflow 来运行。
```

### 示例 3：从 Sessions 页面选择 Workflow 开始新会话

```
1. Sessions 页面 → 点击 [New Chat]
2. 弹窗中切换到 "选择 Workflow" Tab
3. 点击 "搜索撰写工作流"
4. 跳转到 /chat?workflow=search-and-report
5. 输入框 placeholder: "输入 Workflow 执行内容..."
6. 输入 "量子计算的最新进展" → 自动运行 Workflow
7. 依次展示 search 节点结果 → write 节点结果 → 最终报告
```
