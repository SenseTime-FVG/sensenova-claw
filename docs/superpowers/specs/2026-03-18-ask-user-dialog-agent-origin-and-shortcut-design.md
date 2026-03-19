# ask_user 弹窗来源 Agent 展示与快捷键交互设计

- 日期：2026-03-18
- 状态：Draft（已完成用户对设计分节确认）
- 关联需求：前端 `ask_user` 弹窗增加“来源 Agent”展示；支持 `Enter` 确认、`Shift+Enter` 换行；弹窗内增加快捷键提示。

## 1. 背景与目标

当前 `ask_user` 弹窗仅展示来源会话 `session_id`，用户在多 Agent/跨会话场景下无法快速判断是谁在提问。

同时，弹窗自定义输入区缺少键盘快捷提交能力，效率低于主聊天输入框，也没有明确提示文案。

本次目标：

1. 在弹窗中展示来源 Agent 名称（拿不到时回退到 `agent_id`）。
2. 保留来源会话展示。
3. 在弹窗自定义输入框中实现：`Enter` 提交、`Shift+Enter` 换行。
4. 增加快捷键提示文案。
5. 保持现有 ask_user 事件闭环和跨会话提交行为不回归。

## 2. 范围与非目标

### 2.1 范围内

1. 后端 ask_user 事件 payload 增强（来源 Agent 信息）。
2. WebSocket 事件映射增强（下发 `source_agent_id/source_agent_name`）。
3. 前端 `QuestionDialog` UI 与键盘交互调整。
4. 相关单元测试与前端 Playwright e2e 用例更新。

### 2.2 非目标（YAGNI）

1. 不重构整个 WebSocket 协议结构。
2. 不改主聊天输入框（页面底部 textarea）行为。
3. 不引入新的后端 API 供前端二次查询会话元数据。
4. 不新增与本需求无关的样式系统改造。

## 3. 方案对比与选型

### 方案 A（采用）：后端事件直接携带来源 Agent

- 做法：在 ask_user 事件链路中补齐来源 Agent 信息，前端直接渲染。
- 优点：前端稳定、无额外请求、跨页面一致性好。
- 成本：需要改后端事件构造与映射。

### 方案 B：前端根据 `sourceSessionId` 二次查询

- 优点：后端改动小。
- 缺点：弹窗出现后还需异步补数，易闪烁、失败路径复杂。

### 方案 C：WebSocketChannel 映射时查库补齐

- 优点：工具层不改。
- 缺点：通道层职责变重，事件推送路径增加查询成本。

结论：采用方案 A。

## 4. 目标架构与边界

### 4.1 组件职责

1. `AgentSessionWorker`
- 负责在工具调用请求事件中携带当前会话 Agent 身份（`agent_id`）。

2. `ToolSessionWorker`
- 负责发布 `USER_QUESTION_ASKED` 时沿用来源 Agent 身份。

3. `WebSocketChannel`
- 负责将 `USER_QUESTION_ASKED` 映射到前端事件，补 `source_agent_id/source_agent_name`。

4. `QuestionDialog`
- 负责展示来源 Agent + 来源会话。
- 负责 textarea 内键盘行为：`Enter` 提交、`Shift+Enter` 换行。

### 4.2 边界原则

1. Agent 来源信息由后端事件链路提供，前端只消费不推断。
2. 键盘行为只在弹窗 textarea 生效，避免影响选项区和主输入区。
3. 若来源信息缺失，前端/后端都要有可预测回退值，且不得阻断提问流程。

## 5. 事件与数据流设计

### 5.1 事件字段设计

`user_question_asked` 下发 payload 新增字段：

- `source_agent_id: str`
- `source_agent_name: str`

兼容要求：

- 旧服务端无这两个字段时，前端回退展示默认值（`default` 或 `未知 Agent`）。

### 5.2 数据流（文本）

1. LLM 触发 `ask_user` 工具调用。
2. `AgentSessionWorker` 发布 `TOOL_CALL_REQUESTED`，携带 `agent_id`。
3. `ToolSessionWorker` 在 `ask_user handler` 中发布 `USER_QUESTION_ASKED`，写入来源 `agent_id`。
4. `WebSocketChannel._map` 映射为 `user_question_asked`：
- 透传 `source_agent_id`
- 通过 `gateway.agent_registry` 解析 `source_agent_name`
- 解析失败则回退为 `source_agent_id`。
5. 前端 `chat` / `sessions/[id]` 页面收到事件，写入 `PendingQuestion`。
6. `QuestionDialog` 渲染来源 Agent 与来源会话。

## 6. 前端交互设计

### 6.1 展示规则

1. 第一行：`来源 Agent: <name>`（name 缺失则显示 `<agent_id>`）。
2. 第二行：保留 `来源会话: <sourceSessionId>`。

### 6.2 输入行为

仅当焦点在 `ask_user` 自定义输入 textarea：

1. `Enter`（无 Shift）
- `preventDefault`
- 若 `confirmDisabled=false`，触发确认提交
- 若禁用，则不提交

2. `Shift+Enter`
- 保持原生换行

### 6.3 提示文案

在自定义输入区新增：

- `提示：Enter 确认，Shift+Enter 换行`

## 7. 异常与回退策略

1. `source_agent_id` 缺失
- 后端映射层回退为 `event.agent_id`，再回退 `'default'`。

2. `source_agent_name` 解析失败
- 回退为 `source_agent_id`。

3. 前端收到旧事件（无新增字段）
- 回退展示 `default`/`未知 Agent`，不影响提交。

4. 弹窗提交禁用状态
- 与现有逻辑一致：无答案、正在提交、WS 断开、超时等均禁用。

## 8. 测试设计

### 8.1 后端单元测试

1. `WebSocketChannel` 映射 `USER_QUESTION_ASKED` 时包含 `source_agent_id/source_agent_name`。
2. `agent_registry` 查不到 agent 时，`source_agent_name` 回退为 `source_agent_id`。

### 8.2 前端 Playwright

在 `agentos/app/web/e2e/ask-user.spec.ts` 增补：

1. 弹窗展示来源 Agent（含 `data-testid` 断言）。
2. textarea `Enter` 提交回答。
3. textarea `Shift+Enter` 只换行不提交。
4. 快捷键提示文案可见。
5. 保留原有跨 session 提交断言（确保不回归）。

### 8.3 兼容性验证

1. 旧 payload（无 `source_agent_*`）下，前端仍可显示并提交。
2. Chat 页面与 Session 详情页都覆盖。

## 9. 验收标准

1. 用户在 ask_user 弹窗中可以看到来源 Agent 名称。
2. 弹窗中保留来源会话展示。
3. textarea 焦点下，`Enter` 可直接确认提交。
4. textarea 焦点下，`Shift+Enter` 可输入多行。
5. 提示文案可见且与行为一致。
6. 现有 ask_user 闭环与跨会话回答链路不回归。

## 10. 伪代码（Python 风格）

```python
from typing import Any, Optional


class AskUserEventPayload:
    question_id: str
    question: str
    options: Optional[list[str]]
    multi_select: bool
    timeout: int
    source_agent_id: str
    source_agent_name: str


class AgentSessionWorker:
    async def publish_tool_call_requested(self, call: dict[str, Any]) -> None:
        # 作用：发布工具调用请求，并带上当前会话 agent_id
        # 可能调用：PrivateEventBus.publish
        pass


class ToolSessionWorker:
    async def publish_user_question_asked(
        self,
        question: str,
        options: Optional[list[str]],
        multi_select: bool,
        source_agent_id: str,
    ) -> None:
        # 作用：发布 ask_user 问题事件
        # 可能调用：PrivateEventBus.publish
        # 约束：source_agent_id 缺失时回退 default
        pass


class WebSocketChannel:
    def map_user_question_asked(self, event: Any) -> dict[str, Any]:
        # 作用：映射 USER_QUESTION_ASKED 为前端可消费消息
        # 可能调用：gateway.agent_registry.get
        # 回退：name 不存在时回退 source_agent_id
        pass


class QuestionDialog:
    def on_textarea_keydown(self, key: str, shift: bool) -> None:
        # 作用：实现 Enter 提交、Shift+Enter 换行
        # 约束：仅 textarea 聚焦且 confirmEnabled 时触发提交
        pass
```

## 11. 实施注意事项

1. 当前仓库处于脏工作区，实现阶段需避免误提交与本需求无关文件。
2. 弹窗新增字段时，需同步更新 `PendingQuestion` 类型定义（`chat` + `sessions/[id]` 两处）。
3. 若 `WebSocketChannel._map` 需要访问 `gateway.agent_registry`，需确保空值安全。

