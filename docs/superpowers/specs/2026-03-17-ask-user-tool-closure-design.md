# AskUserTool 一次性补齐设计文档

**日期**: 2026-03-17  
**状态**: 评审中  
**作者**: Codex + 用户协作

## 1. 背景与问题

当前 `ask_user` 已完成部分后端能力，但端到端仍存在关键断点：

1. `ask_user` 未真正注册进 `ToolRegistry`，模型不可见不可调。
2. Web 端未消费 `user_question_asked`、未回传 `user_question_answered`。
3. 多 agent 配置下，大部分 `tools` 白名单不包含 `ask_user`。
4. ask_user 专项集成/E2E 覆盖缺失，真实 API 回归未闭环。

## 2. 目标与非目标

### 2.1 目标

1. 一次性打通 `ask_user` 在 **后端 + CLI + Web + 配置 + 测试** 的完整链路。
2. 保持现有事件架构不大改，仅做必要收口。
3. 完成真实 API 全量回归（后端 + 前端）。

### 2.2 非目标

1. 不进行聊天系统状态机级重构。
2. 不改动非 ask_user 相关工具协议与业务流程。
3. 不新增与本需求无关的 UI/交互优化。

## 3. 方案选型

### 3.1 备选方案

1. 最小补丁：直接在现有页面堆逻辑，快速但后续维护差。
2. **方案B（本次采用）**：小步组件化补齐，风险与维护性平衡。
3. 状态机重构：长期最优，但改动过大、交付风险高。

### 3.2 采用方案

采用 **方案B：小步组件化补齐**。

## 4. 总体架构

### 4.1 后端边界

1. `ToolRegistry` 注册 `AskUserTool`。
2. 保持 `ToolSessionWorker` 当前 Future 等待机制。
3. 保持 `WebSocketChannel` 事件映射与 `Gateway` 回传机制，仅补日志和必要保护。

### 4.2 前端边界

1. 新增复用组件 `QuestionDialog`。
2. 在 `chat/page.tsx` 与 `sessions/[id]/page.tsx` 接入同一套问答状态。
3. 待回答时禁用普通输入，避免并发冲突。

### 4.3 组件接口契约（明确边界）

`QuestionDialog` 统一使用以下输入/输出接口，避免两页实现分叉：

```python
from typing import Any, Callable, Optional


class QuestionDialogProps:
    open: bool
    question_id: str
    question: str
    options: Optional[list[str]]
    multi_select: bool
    timeout: int
    created_at: float
    submitting: bool
    ws_connected: bool
    on_submit: Callable[[Any], None]      # answer: str | list[str]
    on_cancel: Callable[[], None]
```

### 4.4 配置边界

1. 在 `config.yml` 所有 `agents.*.tools` 中加入 `ask_user`。
2. 保留 `tools.ask_user.timeout`，由后端作为超时权威。

## 5. 数据流设计

### 5.1 事件链路

`LLM tool_call(ask_user)`  
→ `tool.call_requested`  
→ `user.question_asked`  
→ WebSocket `user_question_asked`  
→ 用户回答  
→ WebSocket `user_question_answered`  
→ `user.question_answered`  
→ `tool.call_result`  
→ 二轮 `llm.call_requested`  
→ `agent.step_completed`

### 5.2 核心伪代码（Python）

```python
from typing import Any, Optional


class AskUserQuestionState:
    question_id: str
    question: str
    options: Optional[list[str]]
    multi_select: bool
    timeout: int
    created_at: float


class ToolSessionWorker:
    _pending_questions: dict[str, Any]

    async def _handle_ask_user(self, params: dict, tool_call_id: str, event: Any) -> dict:
        # 若已有待回答问题，直接拒绝并返回错误
        # 生成 question_id 并创建 Future
        # 发布 user.question_asked 事件（包含 question_id/question/options/timeout）
        # await 等待用户回答或超时
        # 无论成功失败都清理 _pending_questions
        pass

    async def _handle_question_answered(self, event: Any) -> None:
        # 根据 question_id 命中 pending future
        # cancelled=True -> 返回用户取消
        # 否则返回 success + answer
        pass


class WebChatPage:
    pending_question: AskUserQuestionState | None

    def handle_ws_message(self, data: dict[str, Any]) -> None:
        # 收到 user_question_asked:
        #   设置 pending_question，弹出 QuestionDialog，禁用普通输入
        # 收到 turn_completed 或错误:
        #   关闭等待态
        pass

    async def submit_question_answer(self, answer: Any, cancelled: bool) -> None:
        # 发送 user_question_answered
        # payload: {question_id, answer, cancelled}
        # 成功后清理 pending_question
        pass
```

## 6. 交互与校验规则

### 6.1 回答规则

1. 单选：支持选项 + 自定义输入。
2. 多选：支持多选 + 自定义输入。
3. 空输入：按取消处理。
4. 用户取消：发送 `cancelled: true`。

### 6.2 答案归一化规则（消除歧义）

1. 单选模式：始终返回 `str`。
2. 多选模式：
   - 选项选择：返回 `list[str]`
   - 自定义输入：返回 `str`
3. 前后端均按上述规则处理，不做隐式类型猜测。

### 6.3 历史回放

1. 会话回放中，`user.question_asked` 仅展示系统提示，不重放弹窗。
2. 刷新页面不恢复旧问题回答态，避免误答过期 `question_id`。

## 7. 错误处理与并发策略

1. 后端并发限制：同 session 仅允许一个 pending question（沿用现状）。
2. 前端并发保护：有 `pending_question` 时禁止发送普通消息。
3. 前端倒计时只展示，不本地主动超时提交；以后端超时结果为准。
4. WS 断线时保留对话框并禁用提交，提示等待重连。
5. 增加日志：问答事件收发、`question_id` 命中/未命中、超时与取消。

## 8. 测试设计（真实 API 全量回归）

### 8.1 单元测试

1. `ToolRegistry` 包含 `ask_user` 的注册断言。
2. `AskUserTool` 参数与返回标记测试。
3. `ToolSessionWorker` 的并发/超时/取消/清理测试。
4. CLI 多选单值返回类型一致性测试（应返回 list 或按约定统一）。

### 8.2 集成测试（后端）

1. 覆盖 ask_user 事件链完整顺序。
2. 断言二轮 LLM 触发与最终完成事件。
3. 断言 DEBUG 日志中包含 LLM 输入与问答事件关键字段。

### 8.3 前端 E2E（Playwright）

1. 触发 ask_user 问题弹窗。
2. 单选、多选、自定义输入、取消四种交互路径。
3. 待回答期间普通输入禁用。
4. 提交后最终 assistant 响应非空。
5. 迁移现有 `chat.spec.ts` 选择器为当前页面真实结构（避免旧断言导致假失败）。

### 8.4 真实 API 回归

1. 使用真实 API key 跑后端 ask_user 全链路回归。
2. 使用真实 API key 跑前端无头浏览器回归。
3. 若缺少 key 或系统依赖，明确输出阻断点，不宣称通过。

## 9. 变更清单

### 9.1 代码文件

1. `agentos/capabilities/tools/registry.py`
2. `agentos/app/web/app/chat/page.tsx`
3. `agentos/app/web/app/sessions/[id]/page.tsx`
4. `agentos/app/web/components/chat/QuestionDialog.tsx`（新增）
5. `config.yml`
6. ask_user 相关测试文件（新增/扩展）

### 9.2 文档文件

1. 本文档（收口设计）
2. 视实现结果回写原始 ask_user 设计文档中的状态说明

## 10. 验收标准（DoD）

1. `ask_user` 能出现在 `ToolRegistry.as_llm_tools()` 中。
2. CLI 与 Web 都能完成提问、回答、取消、超时闭环。
3. 默认及多 agent 场景都可调用 `ask_user`。
4. 单元/集成/E2E（含真实 API）全部通过。
5. DEBUG 日志可追踪问答全链路。
