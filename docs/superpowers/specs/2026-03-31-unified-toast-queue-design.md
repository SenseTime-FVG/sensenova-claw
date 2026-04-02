# 统一弹窗队列设计

## 背景

当前前端通知系统存在两套独立的弹窗机制：

- **NotificationToast**：`pushNotification()` 触发，5 秒自动消失，位于 `top-20 z-[250]`
- **ActionToast**：`pushCard()` 自动衍生（当 Card 带 actions 时），60 秒超时，位于 `top-16 z-[300]`

两套系统互不感知，导致两个问题：

1. **重复弹窗**：`proactive_result`、`notification` 等事件同时调用 `pushNotification` + `pushCard`，当 `pushCard` 带 actions 时衍生出 ActionToast，用户看到两个内容几乎相同的弹窗
2. **位置重叠**：两种弹窗分别定位在 `top-16` 和 `top-20`，仅差 16px，视觉上互相遮挡

## 设计目标

- 同一事件在屏幕上只出现一个弹窗
- 所有弹窗进同一个队列、用同一个渲染容器，消除位置重叠
- 弹窗（即时提醒）与通知中心卡片（历史记录）职责分离，互不自动衍生

## 设计方案

### 统一数据模型

合并 `notifications[]` 和 `actionToasts[]` 为一个 `toasts[]` 队列：

```typescript
type ToastKind =
  | 'info'               // 纯通知（原 pushNotification 场景）
  | 'tool_confirmation'  // 工具授权（批准/拒绝）
  | 'user_question'      // Agent 提问（带选项/输入）
  | 'task_completed'     // 跨会话任务完成
  | 'proactive'          // 主动推送结果
  | 'general';           // 通用带操作

interface UnifiedToast {
  id: string;
  kind: ToastKind;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;

  // 交互配置
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  onAction?: (actionValue: string, inputValue?: string) => void;  // action 回调

  // 生命周期
  autoDismissMs: number;     // 无 action: 5000, 有 action: 60000
  createdAt: number;

  // 状态
  pending: boolean;          // 提交中，暂停倒计时

  // 关联
  cardId?: string;           // 对应的通知中心卡片 id
  sessionId?: string;
  eventKey?: string;         // 去重 key（同 eventKey 只保留最新一个）
}
```

### 统一入口 pushToast

```typescript
function pushToast(config: {
  kind?: ToastKind;           // 默认 'info'
  title: string;
  body: string;
  level?: 'info' | 'warning' | 'error' | 'success';
  source?: string;
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  autoDismissMs?: number;     // 不传则自动推导
  sessionId?: string;
  cardId?: string;
  eventKey?: string;
  onAction?: (actionValue: string, inputValue?: string) => void;  // action 回调
}): string;                   // 返回 toast id
```

`autoDismissMs` 不传时的推导规则：
- 有 `actions` 或 `allowsInput` → `60000`
- 否则 → `5000`

### 生命周期规则

```
pushToast(config)
    │
    ├── eventKey 去重：同 eventKey 的旧 Toast 被替换
    │
    ├── 加入 toasts[] 数组头部
    │
    ├── 最多显示 5 个
    │
    └── 启动 autoDismiss 定时器
            │
            ├── pending=true → 暂停定时器
            │
            ├── 用户点击 action →
            │     设 pending=true，回调处理函数，
            │     等 resolveToast() 后移除
            │
            ├── 用户点 × → 立即移除
            │
            └── 定时器到期 → 自动移除
```

### pushCard 解耦

`pushCard` 不再自动衍生弹窗，只管通知中心（铃铛下拉面板）的卡片记录。需要弹窗的地方由调用方显式调用 `pushToast`。

### Action 回调机制

当前 ActionToast 的按钮操作通过 `onActionToastAction` 回调桥接到 `NotificationDropdown.handleResolve`，由后者发送 WebSocket 消息。统一后，改为 `pushToast` 时直接传入 `onAction` 回调：

```typescript
// InteractionContext 中的调用示例
const cardId = pushCard({ kind: 'tool_confirmation', title, body, actions });
pushToast({
  kind: 'tool_confirmation',
  title, body, actions,
  cardId,
  onAction: (actionValue) => {
    // 直接发送 WebSocket 响应
    wsSend({
      type: 'tool_confirmation_response',
      session_id: sessionId,
      payload: { tool_call_id: toolCallId, approved: actionValue === 'approve' },
    });
  },
});
```

`ToastItem` 按钮点击时：
1. 调用 `toast.onAction(actionValue, inputValue)`
2. 设 `pending=true`
3. 等 `resolveToast()` 被调用后移除 toast 并同步 resolve 关联 card

这样不再依赖 `NotificationDropdown` 注册回调的间接桥接，逻辑更直接。

### eventKey 去重规则

- `eventKey` 由调用方传入，格式建议为 `${事件类型}_${唯一标识}`（如 `proactive_${jobId}`、`confirm_${toolCallId}`）
- 不传 `eventKey` 时不做去重
- 去重时如果旧 toast 处于 `pending=true` 状态（用户已点击按钮等待确认），**不替换**，保留旧 toast
- resolve 后 toast 被移除，eventKey 随之释放

### 当前 session 交互与 toast 的并存规则

对于 `tool_confirmation_requested` 和 `user_question_asked` 事件，当前 session 会同时触发聊天内嵌的 QuestionDialog / ConfirmationDialog（通过 `enqueueInteraction`）。迁移后需遵循以下规则：

- **当前 session**：仅 `enqueueInteraction`（内嵌展示），**不** `pushToast`。用户已在聊天界面，内嵌交互足够。
- **跨 session**（用户不在该会话页面时）：`pushToast` + `pushCard`。弹窗提醒用户有需要操作的事项。

迁移表中 `tool_confirmation_requested` 和 `user_question_asked` 的 pushToast 列应理解为"仅跨 session 时弹窗"。

### 调用方迁移

每个事件只调一次 `pushToast`（屏幕上只出现一个弹窗），按需调 `pushCard`（通知中心历史记录）：

| 事件 | pushToast（弹窗） | pushCard（通知中心） |
|------|-------------------|---------------------|
| `notification` | 1 次（有 action 就带按钮，没有就纯通知） | 1 次 |
| `proactive_result` | 1 次（带"查看会话→"按钮） | 1 次 |
| `turn_completed`（跨会话） | 1 次（带"查看会话→"按钮） | 1 次 |
| `tool_confirmation_requested`（跨 session） | 1 次（带批准/拒绝按钮） | 1 次 |
| `tool_confirmation_requested`（当前 session） | 不弹窗（内嵌 ConfirmationDialog） | 1 次 |
| `user_question_asked`（跨 session） | 1 次（带输入框/选项） | 1 次 |
| `user_question_asked`（当前 session） | 不弹窗（内嵌 QuestionDialog） | 1 次 |
| Skill 执行失败 | 1 次（纯通知） | 不需要 |
| Cron 触发 | 1 次（纯通知） | 不需要 |

Toast 与 Card 通过 `cardId` 关联。Toast 被 resolve 时同步 resolve 关联的 Card。

### 统一渲染

替代 `NotificationToast` + `ActionToastPanel` 两个独立渲染区域为单一容器：

```tsx
<div className="fixed right-4 top-16 z-[300] flex flex-col gap-3"
     style={{ width: 'min(28rem, calc(100vw - 2rem))' }}>
  {toasts.slice(0, 5).map(toast => (
    <ToastItem key={toast.id} toast={toast} />
  ))}
</div>
```

`ToastItem` 根据 toast 配置渲染不同样式：
- 所有 Toast 都有标题、正文、关闭按钮、level 色条
- 有 `actions` 时渲染操作按钮
- 有 `allowsInput` 时渲染输入框 + 提交按钮
- `pending=true` 时显示"已提交，等待确认"覆盖按钮区域

### 改动范围

#### 移除

| 移除 | 替代 |
|------|------|
| `notifications[]` 状态 | `toasts[]` |
| `actionToasts[]` 状态 | `toasts[]` |
| `NotificationToast` 组件 | `ToastItem` |
| ActionToastPanel 渲染逻辑 | `ToastContainer` + `ToastItem` |
| `pushNotification()` | `pushToast()` |
| `pushCard` 内自动衍生 ActionToast 的逻辑 | 删除 |
| 两套独立的 dismiss/resolve 函数 | 统一 `dismissToast` / `resolveToast` |
| 两套独立的定时器管理 | 统一定时器管理 |

#### 保留不变

| 保留 | 原因 |
|------|------|
| `cards[]` 状态 + `pushCard()` | 通知中心（铃铛下拉）职责不变 |
| `NotificationDropdown` 组件 | 通知中心 UI 不变 |
| Card 的 resolve/dismiss 逻辑 | 不影响 |
| `useNotification` hook | 对外接口改为暴露 `pushToast` 替代 `pushNotification` |

#### 需修改的文件

| 文件 | 改动 |
|------|------|
| `NotificationProvider.tsx` | 合并状态，实现 `pushToast` / `dismissToast` / `resolveToast`，移除 ActionToast 自动衍生逻辑 |
| `NotificationToast.tsx` | 重写为通用 `ToastItem` 组件 |
| `hooks/useNotification.ts` | 暴露 `pushToast` 替代 `pushNotification` |
| `MessageContext.tsx` | 调用点迁移为 `pushToast` + `pushCard` |
| `InteractionContext.tsx` | 调用点迁移为 `pushToast` + `pushCard` |
| `cron/page.tsx` | `pushNotification` → `pushToast` |
| `Dashboard.tsx` | `pushNotification` → `pushToast` |

## 非目标

- 不改通知中心（铃铛下拉面板）的 UI 和逻辑
- 不改 `QuestionDialog`（聊天内嵌交互）的行为
- 不做 `pushNotification` 的去重（问题 #4，用户明确排除）

## 补充说明

### 定时器与 resolve 语义

- `pending=true` 暂停定时器，但 resolve 后直接移除 toast，不恢复倒计时
- `resolveToast(id, action)` 同时 resolve 关联的 card（通过 `cardId`）
- `dismissToast(id)` 移除 toast 但**不** resolve card（用户主动关闭弹窗不等于操作完成）
- `clearAllCards()` 联动移除与 card 关联的 toast

### 动画

保留现有 ActionToastItem 的进入动画（`slide-in-from-top-4 fade-in duration-300`），统一应用到所有 `ToastItem`。

### 宽度

统一使用 `min(28rem, calc(100vw - 2rem))`，与现有 NotificationToast 保持一致。
