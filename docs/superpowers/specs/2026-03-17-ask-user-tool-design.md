# AskUserQuestion 工具设计文档

**日期**: 2026-03-17
**版本**: v1.1

## 概述

实现 `AskUserQuestion` 工具，允许 Agent 在执行任务时向用户提问并等待回答。支持单选、多选和开放式问答三种模式。

## 使用场景

1. **确认操作** - "是否删除该文件？"
2. **选择方案** - "选择部署环境：dev / staging / prod"
3. **收集信息** - "请输入数据库连接字符串"
4. **多选配置** - "启用哪些功能：[日志, 监控, 缓存]"

## 架构设计

### 核心组件

1. **AskUserTool** - 新增工具类，发布问题事件并等待响应
2. **ToolRuntime 扩展** - 管理问答 Future 映射和超时
3. **新增事件类型** - `user.question_asked` 和 `user.question_answered`
4. **Channel 适配** - Web/CLI/TUI 各自处理问题渲染

### 事件流

```
Agent 调用 ask_user 工具
  ↓
ToolRuntime 识别为特殊工具，生成 question_id
  ↓
ToolRuntime 创建 Future，发布 user.question_asked 到 PrivateEventBus
  ↓
PrivateEventBus → Gateway 路由到对应 Channel
  ↓
Channel 渲染问题 UI（Web 显示对话框，CLI 显示菜单）
  ↓
用户回答，Channel 发布 user.question_answered 到 PrivateEventBus
  ↓
ToolRuntime 监听事件，完成 Future
  ↓
工具返回答案给 Agent
```

**事件总线路由：**
- `user.question_asked` 和 `user.question_answered` 都通过 **PrivateEventBus** 传递
- 使用 `trace_id` 字段关联问答对，便于调试和追踪

## 数据结构

### AskUserTool 参数（模型可见）

```python
{
    "question": str,              # 问题文本
    "options": list[str],         # 可选项列表（可选，不提供则为开放式问答）
    "multi_select": bool          # 是否多选，默认 False
}
```

**返回格式：**
```python
{
    "success": bool,
    "answer": str | list[str] | None,  # 单选返回 str，多选返回 list[str]
    "error": str | None                # 失败时的错误信息
}
```

**参数验证规则：**
- `multi_select=True` 时，`options` 必须非空
- 开放式问答（`options=None`）不能使用 `multi_select=True`

**LLM 调用示例：**
```json
{
  "name": "ask_user",
  "arguments": {
    "question": "选择部署环境？",
    "options": ["dev", "staging", "prod"],
    "multi_select": false
  }
}
```

### user.question_asked 事件 payload

```python
{
    "question_id": str,           # UUID，关联问答对
    "question": str,
    "options": list[str] | None,
    "multi_select": bool,
    "timeout": int
}
```

### user.question_answered 事件 payload

```python
{
    "question_id": str,           # 对应 question_asked 的 ID
    "answer": str | list[str] | None,  # 用户答案
    "cancelled": bool             # 用户是否取消
}
```

### 配置文件

```yaml
tools:
  ask_user:
    timeout: 300       # 默认 5 分钟
    max_retries: 3     # CLI 无效输入最大重试次数
```

## 实现细节

### AskUserTool 实现

```python
class AskUserTool(Tool):
    name = "ask_user"
    description = "向用户提问并等待回答"

    async def execute(self, **kwargs):
        # 工具本身只做参数验证，返回特殊标记
        # 实际的问答逻辑由 ToolRuntime 处理
        question = kwargs.get("question")
        options = kwargs.get("options")
        multi_select = kwargs.get("multi_select", False)

        # 参数验证
        if multi_select and not options:
            return {"success": False, "error": "多选模式必须提供 options"}

        # 返回特殊标记，让 ToolRuntime 识别并处理
        return {
            "_ask_user": True,
            "question": question,
            "options": options,
            "multi_select": multi_select
        }
```

**说明：** AskUserTool 不直接调用 ToolRuntime 方法，而是返回特殊标记 `_ask_user: True`，由 ToolRuntime 在工具执行后识别并进入问答流程。

### ToolRuntime 扩展

在 `ToolSessionWorker` 中新增：

```python
class ToolSessionWorker:
    def __init__(self):
        self._pending_questions: dict[str, asyncio.Future] = {}

    async def _execute_tool(self, tool_call):
        """执行工具，检查是否为 ask_user 特殊工具"""
        result = await tool.execute(**kwargs)

        # 检查是否为 ask_user 工具
        if isinstance(result, dict) and result.get("_ask_user"):
            return await self._handle_ask_user(result, tool_call_id)

        return result

    async def _handle_ask_user(self, params: dict, tool_call_id: str) -> dict:
        """处理 ask_user 工具的问答流程"""
        question_id = str(uuid.uuid4())
        timeout = config.get("tools.ask_user.timeout", 300)

        # 检查并发
        if self._pending_questions:
            return {"success": False, "error": "已有待回答问题"}

        # 创建 Future
        future = asyncio.Future()
        self._pending_questions[question_id] = future

        # 发布事件到 PrivateEventBus
        event = EventEnvelope(
            type="user.question_asked",
            session_id=self.session_id,
            trace_id=tool_call_id,  # 用于关联问答对
            source="tool_runtime",
            payload={
                "question_id": question_id,
                "question": params["question"],
                "options": params.get("options"),
                "multi_select": params.get("multi_select", False),
                "timeout": timeout
            }
        )
        await self._private_bus.publish(event)

        try:
            result = await asyncio.wait_for(future, timeout)
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": f"用户未在 {timeout} 秒内回答"}
        finally:
            self._pending_questions.pop(question_id, None)

    async def _handle_question_answered(self, event: EventEnvelope):
        """监听 user.question_answered，完成对应 Future"""
        question_id = event.payload["question_id"]
        future = self._pending_questions.get(question_id)

        if not future or future.done():
            return

        if event.payload.get("cancelled"):
            future.set_result({"success": False, "error": "用户取消了回答"})
        else:
            future.set_result({"success": True, "answer": event.payload["answer"]})

    async def stop(self):
        """Session 销毁时清理所有待处理的 Future"""
        for future in self._pending_questions.values():
            if not future.done():
                future.cancel()
        self._pending_questions.clear()
```

### Channel 适配

各 Channel 需要监听 `user.question_asked` 事件并渲染 UI：

**CLI Channel（简单文本菜单）：**

**单选示例：**
```
Agent 问题：选择部署环境？
1. dev
2. staging
3. prod

请输入选项编号 (1-3) 或自定义输入 (输入 'c' 取消):
```

**多选示例：**
```
Agent 问题：启用哪些功能？
1. 日志
2. 监控
3. 缓存

请输入选项编号，用逗号分隔 (如: 1,3) 或输入 'c' 取消:
```

**输入验证：**
- 单选：接受数字（1-N）选择选项，或任意文本作为自定义输入
- 多选：接受 "1,3" 格式选择选项，或任意文本作为自定义输入
- 开放式问答：接受任意非空文本，空字符串视为取消
- 用户始终可以输入自定义内容，不限于提供的选项

**Web Channel：**
- 显示模态对话框，阻塞其他消息输入
- 单选：Radio buttons
- 多选：Checkboxes
- 开放式：Text input
- 提供"确认"和"取消"按钮
- 对话框显示剩余超时时间

**TUI Channel：**
- 使用 Rich 的 Prompt 组件
- 类似 CLI 的文本菜单

## 错误处理

### 错误场景

1. **超时** - 返回 `{"success": False, "error": "用户未在 X 秒内回答"}`

2. **用户取消** - Channel 发送 `cancelled: True`，工具返回 `{"success": False, "error": "用户取消了回答"}`

3. **无效答案处理**
   - **有 options 时**：用户可以输入选项编号或任意自定义文本
   - **无 options 时**：接受任意非空文本，空字符串视为取消

4. **Session 断开** - Future 被取消，工具抛出 `asyncio.CancelledError`

5. **重复问题** - 同一 question_id 只能有一个 Future，重复调用返回错误

### 并发控制

- 同一 session 同时只能有一个待回答问题
- 如果 `ask_user` 工具被并发调用，后续调用立即返回错误："已有待回答问题"
- 其他工具可以正常并发执行，不受 `ask_user` 阻塞影响
- Agent 可以在等待用户回答期间调用其他工具（如 `read_file`），但不能再次调用 `ask_user`

### 清理机制

- 超时或完成后，从 `_pending_questions` 移除
- Session 销毁时，调用 `ToolSessionWorker.stop()` 取消所有待处理的 Future
- 利用现有的 `BusRouter.on_destroy()` 回调机制触发清理

## 扩展设计

### 问答历史存储

将问答记录存储到 `SessionStateStore`，便于：
- 调试和追踪用户决策
- 在对话上下文中引用历史问答
- 审计和分析用户行为

**存储结构：**
```python
{
    "question_id": str,
    "question": str,
    "options": list[str] | None,
    "answer": str | list[str] | None,
    "timestamp": float,
    "cancelled": bool
}
```

## 测试策略

### 单元测试

1. AskUserTool 参数验证
2. ToolRuntime Future 管理（创建、完成、超时、清理）
3. 事件 payload 序列化/反序列化

### 集成测试

1. 完整问答流程（发布事件 → 模拟回答 → 验证返回）
2. 超时场景
3. 用户取消场景
4. 并发调用拒绝
5. 自定义输入处理

### E2E 测试

1. Web 端：Playwright 模拟点击选项按钮
2. CLI 端：模拟终端输入

## 实现文件清单

### 新增文件

- `agentos/capabilities/tools/ask_user_tool.py` - AskUserTool 实现

### 修改文件

- `agentos/kernel/events/types.py` - 新增事件类型常量
- `agentos/kernel/runtime/workers/tool_worker.py` - 扩展 ToolSessionWorker
- `agentos/adapters/channels/*/channel.py` - 各 Channel 适配问题渲染
- `agentos/app/web/components/chat/QuestionDialog.tsx` - Web 端问题对话框组件
- `config.yml` - 新增 ask_user 配置
- `tests/unit/test_ask_user_tool.py` - 单元测试
- `tests/integration/test_ask_user_flow.py` - 集成测试
- `tests/e2e/test_ask_user_e2e.py` - E2E 测试

## 实现优先级

1. **Phase 1** - 核心功能
   - 事件类型定义
   - AskUserTool 实现
   - ToolRuntime 扩展
   - 单元测试

2. **Phase 2** - CLI 适配
   - CLI Channel 文本菜单
   - 集成测试

3. **Phase 3** - Web 适配
   - Web Channel 对话框组件
   - E2E 测试

4. **Phase 4** - TUI 适配（可选）
   - TUI Channel 适配

