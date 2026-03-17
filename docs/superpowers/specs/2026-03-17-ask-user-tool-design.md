# AskUserQuestion 工具设计文档

**日期**: 2026-03-17
**版本**: v1.0

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
ToolRuntime 创建 Future，发布 user.question_asked 事件
  ↓
Gateway 路由到对应 Channel
  ↓
Channel 渲染问题 UI（Web 显示对话框，CLI 显示菜单）
  ↓
用户回答，Channel 发布 user.question_answered 事件
  ↓
ToolRuntime 接收事件，完成 Future
  ↓
工具返回答案给 Agent
```

## 数据结构

### AskUserTool 参数（模型可见）

```python
{
    "question": str,              # 问题文本
    "options": list[str],         # 可选项列表（可选，不提供则为开放式问答）
    "multi_select": bool          # 是否多选，默认 False
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
    timeout: 300  # 默认 5 分钟
```

## 实现细节

### AskUserTool 实现

```python
class AskUserTool(Tool):
    name = "ask_user"
    description = "向用户提问并等待回答"

    async def execute(self, **kwargs):
        1. 生成 question_id (UUID)
        2. 构造 user.question_asked 事件
        3. 调用 ToolRuntime 的 ask_question() 方法
        4. ToolRuntime 创建 Future 并发布事件
        5. 使用 asyncio.wait_for(future, timeout) 等待
        6. 超时返回错误，成功返回答案
```

### ToolRuntime 扩展

在 `ToolSessionWorker` 中新增：

```python
class ToolSessionWorker:
    def __init__(self):
        self._pending_questions: dict[str, asyncio.Future] =

    async def ask_question(self, event: EventEnvelope) -> dict:
        """创建 Future，发布事件，等待响应"""
        question_id = event.payload["question_id"]
        timeout = event.payload["timeout"]

        # 检查并发
        if self._pending_questions:
            raise RuntimeError("已有待回答问题")

        future = asyncio.Future()
        self._pending_questions[question_id] = future

        # 发布事件
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
```

### Channel 适配

各 Channel 需要监听 `user.question_asked` 事件并渲染 UI：

**CLI Channel（简单文本菜单）：**
```
Agent 问题：选择部署环境？
1. dev
2. staging
3. prod

请输入选项编号 (1-3) 或自定义输入:
```

**Web Channel：**
- 显示模态对话框
- 单选：Radio buttons
- 多选：Checkboxes
- 开放式：Text input
- 提供"取消"按钮

**TUI Channel：**
- 使用 Rich 的 Prompt 组件
- 类似 CLI 的文本菜单

## 错误处理

### 错误场景

1. **超时** - 返回 `{"success": False, "error": "用户未在 X 秒内回答"}`

2. **用户取消** - Channel 发送 `cancelled: True`，工具返回 `{"success": False, "error": "用户取消了回答"}`

3. **无效答案** - 用户输入不在 options 中时，接受为自定义输入

4. **Session 断开** - Future 被取消，工具抛出异常

5. **重复问题** - 同一 question_id 只能有一个 Future，重复调用返回错误

### 并发控制

- 同一 session 同时只能有一个待回答问题
- 如果工具被并发调用，后续调用立即返回错误："已有待回答问题"

### 清理机制

- 超时或完成后，从 `_pending_questions` 移除
- Session 销毁时，取消所有待处理的 Future

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

