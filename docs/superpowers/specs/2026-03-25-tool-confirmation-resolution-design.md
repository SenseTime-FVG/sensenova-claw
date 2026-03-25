# tool_confirmation 收口协议设计

## 概述

当前工具审批链路存在两类问题：

- 后端在确认超时后会按 `approve/reject/block` 策略继续推进，但前端没有收到一个明确的“审批已结束”信号，导致弹窗可能继续停留。
- `/chat` 工作台与 `/sessions/[id]` 详情页各自维护了一套审批收口逻辑，行为不一致，导致同一条审批在不同页面上的关闭时机不同。

本设计的目标是把“用户提交审批意图”和“服务端完成审批裁决”拆成两个明确事件，让前端只根据服务端权威裁决来关闭审批 UI，从而保证：

- 用户及时点击时，前端能稳定收口
- 后端超时自动批准/拒绝时，前端能立刻收口
- `block` 模式下，前端不会误关闭
- `/chat` 与 `/sessions/[id]` 使用同一套审批生命周期语义

## 当前问题

### 1. 前端缺少权威收口信号

当前后端会发送 `tool_confirmation_requested`，前端据此展示审批弹窗。但当后端因为用户点击或超时而结束等待时，没有专门的下行事件告诉前端“审批已结束”。

现状导致前端只能依赖以下信号间接猜测何时关闭：

- 用户本地点击按钮后立即关闭
- 前端本地倒计时归零后自行关闭
- 后续 `tool_result`
- 再后续的 `turn_completed/error`

这会导致“后端已经结束审批等待，但前端仍未关闭”的错位。

### 2. `tool_result` 语义过载

当前前端在部分页面上把 `tool_result` 同时用作：

- 工具执行结果
- 审批生命周期结束的近似信号

这两个语义不应混在一起。尤其在 `timeout_action = approve` 场景下，后端会先结束审批等待，再开始执行工具；如果前端要等 `tool_result` 才关弹窗，弹窗就会无意义地多停留一段时间。

### 3. 两套前端交互链路并存

当前前端同时存在两套审批交互实现：

- `/chat`：基于 `ChatSessionContext + NotificationProvider`
- `/sessions/[id]`：页面本地 WebSocket + `InteractionDialog`

两套实现都还在使用，因此必须统一审批事件语义，不能只修其中一侧。

## 设计目标

### 必须达成

- 用户点击批准/拒绝时，后端能收到请求并完成裁决
- 后端超时自动批准/拒绝时，前端能在收到服务端事件后立即关闭审批 UI
- `block` 模式不自动关闭
- 同一个 `tool_call_id` 只允许完成一次审批裁决
- `/chat` 与 `/sessions/[id]` 使用相同的裁决事件完成收口

### 非目标

- 本次不重构掉 `/sessions/[id]` 页面
- 本次不改变工具权限策略本身，只修正审批生命周期协议
- 本次不调整工具结果展示样式，只调整收口依据

## 方案概述

保留现有前端上行事件 `tool_confirmation_response`，新增后端下行事件 `tool_confirmation_resolved`。

职责划分如下：

- `tool_confirmation_requested`
  - 后端 -> 前端
  - 含义：服务端开始等待用户审批

- `tool_confirmation_response`
  - 前端 -> 后端
  - 含义：用户提交了批准/拒绝意图
  - 这是“请求”，不是最终结果

- `tool_confirmation_resolved`
  - 后端 -> 前端
  - 含义：服务端已经结束该次审批等待，并给出最终裁决
  - 前端只根据该事件关闭审批 UI

- `tool_result`
  - 后端 -> 前端
  - 含义：工具执行或拒绝执行后的结果
  - 只负责更新工具消息，不再负责关闭审批 UI

## 事件协议

### `tool_confirmation_requested`

在现有字段基础上，补充服务端真实超时参数：

```python
from typing import Literal, TypedDict


class ToolConfirmationRequestedPayload(TypedDict):
    tool_call_id: str
    tool_name: str
    arguments: dict
    risk_level: str
    timeout: float
    timeout_action: Literal["approve", "reject", "block"]
    requested_at_ms: int
```

说明：

- `timeout` 必须由后端真实配置填充，前端不再自行默认假定 300 秒
- `timeout_action` 必须显式下发，避免前端写死“超时后拒绝”

### `tool_confirmation_response`

保持现状，不额外拆字段：

```python
class ToolConfirmationResponsePayload(TypedDict):
    tool_call_id: str
    approved: bool
```

### `tool_confirmation_resolved`

新增服务端权威裁决事件：

```python
class ToolConfirmationResolvedPayload(TypedDict):
    tool_call_id: str
    tool_name: str
    approved: bool
    status: Literal["approved", "rejected"]
    reason: Literal[
        "user_approved",
        "user_rejected",
        "timeout_approved",
        "timeout_rejected",
    ]
    resolved_by: Literal["user", "timeout"]
    resolved_at_ms: int
```

说明：

- `status` 用于前端快速判断审批最终结果
- `reason` 用于区分是用户操作还是超时兜底
- `resolved_by` 便于前端文案和日志归类

## 状态机

审批状态以 `tool_call_id` 为唯一键，由后端维护权威状态。

```python
from typing import Literal

ConfirmationState = Literal["pending", "resolved"]


class ConfirmationRecord:
    tool_call_id: str
    state: ConfirmationState
    approved: bool | None
    reason: str | None


def resolve_confirmation(record: ConfirmationRecord, approved: bool, reason: str):
    if record.state == "resolved":
        # 已完成裁决的审批，忽略重复点击或晚到响应
        return None

    record.state = "resolved"
    record.approved = approved
    record.reason = reason
    return {
        "tool_call_id": record.tool_call_id,
        "approved": approved,
        "reason": reason,
    }
```

核心原则：

- 同一个 `tool_call_id` 只能从 `pending -> resolved` 转换一次
- 首个完成裁决的来源获胜
- 后续重复点击、重复投递、晚到响应一律忽略并记录 DEBUG 日志

## 时序

### 场景 1：用户在超时前点击批准/拒绝

```python
def flow_user_response():
    # 1. 服务端发起审批
    publish("tool_confirmation_requested")

    # 2. 前端展示审批 UI
    # 3. 用户点击按钮
    receive("tool_confirmation_response")

    # 4. 服务端立即完成裁决
    publish("tool_confirmation_resolved", reason="user_approved")

    # 5. 前端收到 resolved，立即关闭弹窗/卡片
    # 6. 后续工具继续执行，最终产出 tool_result
```

### 场景 2：超时自动批准/拒绝

```python
def flow_timeout_response():
    publish("tool_confirmation_requested")

    # 超时到达，服务端按配置自动裁决
    publish("tool_confirmation_resolved", reason="timeout_approved")

    # 前端收到 resolved 立刻关闭审批 UI
    # 如果是 approve，工具继续执行，稍后产出 tool_result
    # 如果是 reject，直接产出拒绝执行的 tool_result
```

### 场景 3：`block` 模式

```python
def flow_block_mode():
    publish("tool_confirmation_requested", timeout_action="block")

    # 到达 timeout 后不自动裁决
    # 前端可以显示“仍在等待审批”，但不能关闭 UI

    receive("tool_confirmation_response")
    publish("tool_confirmation_resolved", reason="user_approved")
```

## 后端设计

### `ToolSessionWorker`

目标文件：

- `sensenova_claw/kernel/runtime/workers/tool_worker.py`

改动点：

1. 在 `_request_confirmation()` 发布 `tool_confirmation_requested` 时补充：
   - `timeout`
   - `timeout_action`
   - `requested_at_ms`

2. 在两类分支中统一发布 `tool_confirmation_resolved`：
   - 用户响应分支
   - 超时兜底分支

3. 为挂起审批引入显式 resolved 状态，确保单次裁决：
   - 用户点击先到时，timeout 分支不可再次裁决
   - timeout 先到时，晚到的用户点击不可再次裁决

4. `stop()` 过程中若存在仍处于 `pending` 的审批，可只清理等待对象，不必额外新增 stop 裁决事件；本次范围先不扩展到“worker 停止原因”的前端展示。

### 事件类型

目标文件：

- `sensenova_claw/kernel/events/types.py`

新增：

- `TOOL_CONFIRMATION_RESOLVED = "tool.confirmation_resolved"`

### WebSocket 映射

目标文件：

- `sensenova_claw/adapters/channels/websocket_channel.py`

改动点：

1. 将新的内核事件映射为前端事件：
   - `tool.confirmation_resolved -> tool_confirmation_resolved`

2. 将 `tool_confirmation_requested` 的 payload 增补：
   - `timeout`
   - `timeout_action`
   - `requested_at_ms`

3. `tool_confirmation_resolved` 应按连接级广播发送，和 `tool_confirmation_requested` 保持一致，保证跨窗口都能及时收口。

## 前端设计

### `/chat` 工作台

目标文件：

- `sensenova_claw/app/web/contexts/ChatSessionContext.tsx`
- `sensenova_claw/app/web/components/notification/NotificationProvider.tsx`

改动原则：

1. 将 `tool_confirmation_resolved` 纳入全局 interaction 事件
2. 收到该事件后：
   - 关闭当前对应的审批交互
   - 结束 `interactionSubmitting`
   - 将通知卡片移出待处理区，标记为 resolved
   - 移除 action toast
3. 不再依赖 `tool_result` 关闭审批 UI
4. `tool_result` 仅负责更新工具消息为完成/失败

推荐展示：

- action toast 立即消失
- 通知卡片保留为 resolved 状态
- 若 `reason` 为 `timeout_approved/timeout_rejected`，卡片文案显示“已按超时策略自动批准/拒绝”

### `/sessions/[id]` 详情页

目标文件：

- `sensenova_claw/app/web/app/sessions/[id]/page.tsx`

改动原则：

1. 将 `tool_confirmation_resolved` 视为可跨 session 接收的 interaction 事件
2. 收到该事件后按 `tool_call_id` 调用 `resolveInteraction("confirmation", tool_call_id)`
3. `tool_result` 分支保留为工具消息更新逻辑，不再承担关闭审批弹窗职责

### 审批弹窗

目标文件：

- `sensenova_claw/app/web/components/chat/QuestionDialog.tsx`

改动原则：

1. 保留倒计时展示
2. 当倒计时归零时：
   - 若 `timeout_action` 为 `approve/reject`，前端不再本地直接关闭，只显示“等待服务端确认超时处理结果”
   - 若 `timeout_action` 为 `block`，继续显示等待中状态
3. 弹窗实际关闭统一依赖 `tool_confirmation_resolved`

## 幂等与竞态处理

### 晚到点击

“晚到点击”不是新的业务路径，而是审批已经 resolved 后，前端又发来一次过期 `tool_confirmation_response`。

处理策略：

- 后端忽略，不再改变最终结果
- 记录 DEBUG 日志，便于追踪
- 前端最终以已收到的 `tool_confirmation_resolved` 为准

### 多窗口同时点击

多个窗口可以对同一个审批发起响应，但后端只接受首个成功裁决的请求。

结果：

- 第一个到达的响应完成裁决
- 第二个及后续响应被忽略
- 所有窗口都通过广播收到同一个 `tool_confirmation_resolved`

### `tool_result` 晚于 `resolved`

这是正常行为，不应视为异常。

约束：

- `resolved` 负责关闭审批 UI
- `tool_result` 负责更新工具执行结果
- 二者互不替代

## 测试

### 后端单元测试

1. 用户批准时，先产生 `tool_confirmation_resolved(reason=user_approved)`，再执行工具
2. 用户拒绝时，先产生 `tool_confirmation_resolved(reason=user_rejected)`，再产生拒绝结果 `tool_result`
3. `timeout_action = approve` 时，先产生 `tool_confirmation_resolved(reason=timeout_approved)`，再产生工具结果
4. `timeout_action = reject` 时，先产生 `tool_confirmation_resolved(reason=timeout_rejected)`，再产生拒绝结果
5. `timeout_action = block` 时，超时后不产生 resolved
6. 晚到 `tool_confirmation_response` 不会重复裁决

### 前端回归

1. `/chat` 收到 `tool_confirmation_resolved` 后立即关闭审批 UI
2. `/sessions/[id]` 收到 `tool_confirmation_resolved` 后立即关闭审批弹窗
3. `tool_result` 晚到时不会再次触发关闭逻辑
4. 超时自动批准/拒绝时，弹窗在服务端裁决后立即关闭
5. `block` 模式不会因为本地倒计时结束而误关闭
6. 多窗口场景下，所有窗口都能收到同一个 resolved 事件并同步收口

## 改动范围

- `sensenova_claw/kernel/events/types.py`
- `sensenova_claw/kernel/runtime/workers/tool_worker.py`
- `sensenova_claw/adapters/channels/websocket_channel.py`
- `sensenova_claw/app/web/contexts/ChatSessionContext.tsx`
- `sensenova_claw/app/web/app/sessions/[id]/page.tsx`
- `sensenova_claw/app/web/components/chat/QuestionDialog.tsx`
- `sensenova_claw/app/web/components/notification/NotificationProvider.tsx`
- 对应单元测试与前端回归测试

## 推荐实施顺序

1. 先补后端 `resolved` 事件与 WebSocket 映射
2. 再让两个前端入口都改为依赖 `resolved` 收口
3. 最后调整通知卡片与弹窗超时文案，并补齐回归测试

这样可以先解决“后端已裁决但前端不收口”的核心 bug，再逐步把提示文案和体验收敛完整。
