## 多agent和workflow模式

**目标**：
1. 用户可以：
 - 设置多个agent的config、system prompt、tools、skills等信息（可通过一个agent来配置）
 - 设置多个agent的workflow编排模式（以节点和边的形式）
2. 主agent可以：
 - 根据用户的需求，delegate task 给另一个agent
 - 并行或按一定的workflow（通常来自于用户安排）调用另一个agent

### 多agent模式

1. AgentRegistry
2. 多 Agent 配置
3. agent 间通过 Bus 和文件 通信

**验收**：主 Agent 能自动委托子 Agent，Bus 异步通知工作，Agent 崩溃自动恢复。

### Workflow模式

1. Workflow / WorkflowNode / Edge / WorkflowResult
2. 模板：plan-execute-review、fan-out-merge
