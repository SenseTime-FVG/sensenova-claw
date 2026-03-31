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

### 调用方迁移

每个事件只调一次 `pushToast`（屏幕上只出现一个弹窗），按需调 `pushCard`（通知中心历史记录）：

| 事件 | pushToast（弹窗） | pushCard（通知中心） |
|------|-------------------|---------------------|
| `notification` | 1 次（有 action 就带按钮，没有就纯通知） | 1 次 |
| `proactive_result` | 1 次（带"查看会话→"按钮） | 1 次 |
| `turn_completed`（跨会话） | 1 次（带"查看会话→"按钮） | 1 次 |
| `tool_confirmation_requested` | 1 次（带批准/拒绝按钮） | 1 次 |
| `user_question_asked` | 1 次（带输入框/选项） | 1 次 |
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
