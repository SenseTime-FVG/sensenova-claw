# AskUserQuestion 工具实现计划

**日期**: 2026-03-17
**关联设计**: docs/superpowers/specs/2026-03-17-ask-user-tool-design.md

## 实现范围

根据设计文档，分 4 个阶段实现：
1. Phase 1: 核心功能（事件、工具、ToolRuntime）
2. Phase 2: CLI 适配
3. Phase 3: Web 适配
4. Phase 4: TUI 适配（可选）

本计划覆盖 **Phase 1 和 Phase 2**（核心 + CLI），Phase 3/4 后续独立实现。

## 实现步骤

### Step 1: 添加事件类型常量

**文件**: `agentos/kernel/events/types.py`

**修改内容**:
```python
# 用户问答事件
USER_QUESTION_ASKED = "user.question_asked"
USER_QUESTION_ANSWERED = "user.question_answered"
```

**验证**: 无需测试，纯常量定义

---

### Step 2: 实现 AskUserTool

**文件**: `agentos/capabilities/tools/ask_user_tool.py` (新建)

**实现内容**:
- 继承 `Tool` 基类
- 参数验证：`multi_select=True` 时 `options` 必须非空
- 返回特殊标记 `{"_ask_user": True, ...}`

**验证**: 单元测试参数验证逻辑

---

### Step 3: 扩展 ToolSessionWorker

**文件**: `agentos/kernel/runtime/workers/tool_worker.py`

**修改内容**:
1. 添加 `_pending_questions: dict[str, asyncio.Future]` 字段
2. 修改 `_handle_tool_requested` 方法，在工具执行后检查 `_ask_user` 标记
3. 新增 `_handle_ask_user` 方法：创建 Future、发布事件、等待超时
4. 新增 `_handle_question_answered` 方法：监听回答事件、完成 Future
5. 修改 `_handle` 方法，添加 `USER_QUESTION_ANSWERED` 事件处理
6. 扩展 `stop` 方法，清理待处理的 Future

**关键逻辑**:
- 并发检查：`if self._pending_questions: return error`
- 超时使用 `asyncio.wait_for(future, timeout)`
- 使用 `trace_id=tool_call_id` 关联问答对

**验证**: 单元测试 Future 管理、超时、清理

---

### Step 4: 注册 AskUserTool

**文件**: `agentos/capabilities/tools/builtin.py`

**修改内容**:
在文件末尾导入并实例化：
```python
from agentos.capabilities.tools.ask_user_tool import AskUserTool
# 在模块级别实例化，供 registry 自动发现
ask_user_tool = AskUserTool()
```

**验证**: 启动后检查工具是否注册成功

---

### Step 5: CLI Channel 适配

**文件**: 需要先找到 CLI Channel 实现文件

**实现内容**:
1. 在 `event_filter()` 中添加 `USER_QUESTION_ASKED`
2. 在 `send_event()` 中处理 `USER_QUESTION_ASKED` 事件
3. 实现问题渲染逻辑：
   - 单选：显示编号列表
   - 多选：提示逗号分隔格式
   - 开放式：直接输入
4. 解析用户输入：
   - 数字 → 选择对应选项
   - "c" → 取消
   - 其他 → 自定义输入
5. 发布 `USER_QUESTION_ANSWERED` 事件

**验证**: 集成测试完整问答流程

---

### Step 6: 配置文件更新

**文件**: `config.yml`

**添加内容**:
```yaml
tools:
  ask_user:
    timeout: 300
```

**验证**: 启动后读取配置

---

### Step 7: 单元测试

**文件**: `tests/unit/test_ask_user_tool.py` (新建)

**测试用例**:
1. `test_ask_user_tool_valid_params` - 正常参数
2. `test_ask_user_tool_multi_select_requires_options` - 多选验证
3. `test_ask_user_tool_returns_marker` - 返回特殊标记

**文件**: `tests/unit/test_tool_worker_ask_user.py` (新建)

**测试用例**:
1. `test_handle_ask_user_creates_future` - Future 创建
2. `test_handle_ask_user_timeout` - 超时处理
3. `test_handle_ask_user_concurrent_reject` - 并发拒绝
4. `test_handle_question_answered_success` - 成功回答
5. `test_handle_question_answered_cancelled` - 用户取消
6. `test_stop_cleans_pending_questions` - 清理机制

---

### Step 8: 集成测试

**文件**: `tests/integration/test_ask_user_flow.py` (新建)

**测试用例**:
1. `test_ask_user_single_choice_flow` - 单选完整流程
2. `test_ask_user_multi_choice_flow` - 多选完整流程
3. `test_ask_user_open_ended_flow` - 开放式问答
4. `test_ask_user_custom_input` - 自定义输入
5. `test_ask_user_timeout_flow` - 超时场景
6. `test_ask_user_cancel_flow` - 取消场景

---

## 实现顺序

1. Step 1: 事件类型 (5 分钟)
2. Step 2: AskUserTool (15 分钟)
3. Step 3: ToolSessionWorker 扩展 (30 分钟)
4. Step 4: 工具注册 (5 分钟)
5. Step 7: 单元测试 (30 分钟)
6. Step 5: CLI Channel 适配 (30 分钟)
7. Step 8: 集成测试 (30 分钟)
8. Step 6: 配置文件 (5 分钟)

**总计**: 约 2.5 小时

## 关键文件清单

### 新增文件
- `agentos/capabilities/tools/ask_user_tool.py`
- `tests/unit/test_ask_user_tool.py`
- `tests/unit/test_tool_worker_ask_user.py`
- `tests/integration/test_ask_user_flow.py`

### 修改文件
- `agentos/kernel/events/types.py`
- `agentos/kernel/runtime/workers/tool_worker.py`
- `agentos/capabilities/tools/builtin.py`
- CLI Channel 文件 (待确定路径)
- `config.yml`

## 风险和依赖

1. **CLI Channel 路径未确定** - 需要先找到 CLI Channel 实现
2. **事件路由验证** - 确保 PrivateEventBus 正确路由到 Channel
3. **并发测试** - 需要模拟并发工具调用场景

## 验收标准

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] CLI 端可以正常问答（手动测试）
- [ ] 超时机制正常工作
- [ ] 并发调用正确拒绝
- [ ] Session 销毁时正确清理
