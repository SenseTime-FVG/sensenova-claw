# agentos 软件架构设计 v0.1

当前版本只实现最基本功能开发
1. 支持前端对话和消息显示
2. 基础agent tool call

## 技术栈

Next.js构建前端

FastAPI作为网关

前端和后端使用websocket作为通信协议

后端存储使用sqlite


## 后端架构和模块

后端使用事件总线模式
各个模块通过事件总线来和其他模块交互

有一条public bus，然后每个agent会有自己的private bus
agent之外的模块会往public bus中发送消息
bus_router模块根据session_id把每个event复制到每个agent的private bus

配置文件使用YAML格式， API_KEY都统一写在YAML配置文件中


### EventEnvelope类型
class EventEnvelope:
    event_id（全局唯一）
    type（如 llm.call_completed）
    ts
    session_id
    agent_id（如果一个 session 多 agent）
    turn_id
    step_id（可选，但强烈建议：一步一 ID）
    trace_id / correlation_id（把 request 和 completed 串起来，非常关键）
    例如：llm_call_id、tool_call_id
    payload（事件内容）
    source（ui / agent / llm / tool / system）

### 事件最小集合
1. UI 事件：
   1. `ui.user_input`
   4. `ui.turn_cancel_requested`
2. Agent 事件：
   1. `agent.step_started`
   2. `agent.step_completed`
   3. `user.input`
3. LLM 事件：
   1. `llm.call_requested`
   1. `llm.call_started`
   2. `llm.call_completed`
4. Tool 事件：
   1. `tool.call_requested`
   2. `tool.call_started`
   3. `tool.call_completed`
   4. `tool.execution_start`
   6. `tool.execution_end`
5. 错误事件：
   1. `error.raised`


### AgentRuntime 模块

最核心模块，提供agent的底层运行逻辑
执行逻辑是 input -> init prompt -> llm api call -> llm response -> tool call -> tool response -> llm api call但是不用

执行逻辑不直接用循环实现，而是从event_bus中获取事件，分析处理事件，发布结果

一个agent的session从获取 user.input 事件开始
1. 创建session_id, turn_id等准备工作
2. 发布事件agent.step_started
3. 使用 ContextBuilder 模块构建需要输入给LLM的messages
4. 发布事件llm.call_requested

从总线接收到llm.call_completed之后
1. 判断是否需要toolcall
2. 如果需要toolcall, 发布tool.call_requested
3. 如果不需要开始结束流程，发布对应的agent.step_completed

### LLM 模块

提供不同模型的

### ToolRuntime 模块

提供工具注册和工具标准化接口
目前需要的工具类型
1. 命令行工具 执行 bash, cmd, powershell的能力
2. serper搜索工具，使用serper.dev搜索
3. fetch_url工具
4. 读写文件工具
5. skill工具，提供加载agent skill的能力


### ContextBuilder 模块

根据当前的messages，和接收到的event内容，拼接成新的messages，作为下一轮输入传给LLM


## 数据库 sqlite

sessions表字段：session_id、created_at、last_active、meta

turns表字段：turn_id、session_id、status、started_at、ended_at

events表字段：event_id、session_id、turn_id、payload_json




## 前端功能
总是使用类似vscode界面
最上方是菜单栏
左侧sidebar是
页面中间是对话区域

具体设计见 docs/ui 中的文件

