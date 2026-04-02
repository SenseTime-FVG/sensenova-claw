# 统一弹窗队列 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 合并 NotificationToast 和 ActionToast 为统一的 toast 队列，消除重复弹窗和位置重叠。

**Architecture:** 将 NotificationProvider 中的 `notifications[]` 和 `actionToasts[]` 合并为 `toasts[]`，所有弹窗通过 `pushToast()` 统一入口创建，`pushCard()` 仅管理通知中心卡片不再自动衍生弹窗。调用方（MessageContext、InteractionContext 等）迁移为显式调用 `pushToast`。

**Tech Stack:** React 18, TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-31-unified-toast-queue-design.md`

---

## File Structure

| File | Role | Action |
|------|------|--------|
| `sensenova_claw/app/web/components/notification/NotificationProvider.tsx` | 核心状态管理 | Modify: 合并状态, 新增 pushToast/dismissToast/resolveToast, 移除 ActionToast 自动衍生 |
| `sensenova_claw/app/web/components/notification/NotificationToast.tsx` | Toast 渲染组件 | Rewrite: 合并为 ToastContainer + ToastItem |
| `sensenova_claw/app/web/hooks/useNotification.ts` | 消费入口 | Modify: 暴露 pushToast 替代 pushNotification |
| `sensenova_claw/app/web/contexts/ws/MessageContext.tsx` | 事件处理 | Modify: 迁移调用点 |
| `sensenova_claw/app/web/contexts/ws/InteractionContext.tsx` | 交互事件处理 | Modify: 迁移调用点 |
| `sensenova_claw/app/web/app/cron/page.tsx` | Cron 页面 | Modify: pushNotification → pushToast |
| `sensenova_claw/app/web/components/dashboard/Dashboard.tsx` | Dashboard | Modify: pushNotification → pushToast |
| `sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx` | Proactive 面板 | Modify: pushNotification → pushToast |
| `sensenova_claw/app/web/components/notification/NotificationDropdown.tsx` | 通知中心下拉 | Modify: 移除 setOnActionToastAction 注册 |

---

### Task 1: 定义统一 Toast 类型并改造 NotificationProvider 状态

**Files:**
- Modify: `sensenova_claw/app/web/components/notification/NotificationProvider.tsx:1-103`

- [ ] **Step 1: 在 NotificationProvider.tsx 中新增 UnifiedToast 类型定义**

在文件顶部（imports 之后，约第 54 行之后）新增类型：

```typescript
// ── 统一弹窗类型 ──

export type ToastKind =
  | 'info'
  | 'tool_confirmation'
  | 'user_question'
  | 'task_completed'
  | 'proactive'
  | 'general';

export interface ToastAction {
  label: string;
  value: string;
}

export interface UnifiedToast {
  id: string;
  kind: ToastKind;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  questionData?: QuestionData;
  onAction?: (actionValue: string, inputValue?: string) => void;
  autoDismissMs: number;
  createdAtMs: number;       // 与 NotificationCard.createdAtMs 字段名一致
  pending: boolean;
  cardId?: string;
  sessionId?: string;
  eventKey?: string;
}

export interface PushToastConfig {
  kind?: ToastKind;
  title: string;
  body: string;
  level?: 'info' | 'warning' | 'error' | 'success';
  source?: string;
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  questionData?: QuestionData;
  autoDismissMs?: number;
  sessionId?: string;
  cardId?: string;
  eventKey?: string;
  onAction?: (actionValue: string, inputValue?: string) => void;
  browser?: boolean;         // 是否同时触发浏览器原生通知
}
```

注：`QuestionData` 类型已在 `NotificationToast.tsx` 中定义，需从那里导入或移动到 Provider。

- [ ] **Step 2: 替换状态声明**

将第 93-99 行的三个独立状态：

```typescript
// 旧代码（删除）
const [notifications, setNotifications] = useState<ToastNotification[]>([]);
const [cards, setCards] = useState<NotificationCard[]>([]);
const [actionToasts, setActionToasts] = useState<ActionToast[]>([]);
```

替换为：

```typescript
// 新代码
const [toasts, setToasts] = useState<UnifiedToast[]>([]);
const [cards, setCards] = useState<NotificationCard[]>([]);
// actionToasts 已移除，合并到 toasts
```

- [ ] **Step 3: 更新 NotificationContextValue 接口**

将第 59-81 行的 interface 中：
- 移除 `notifications`、`actionToasts`、`pushNotification`、`dismissNotification`
- 移除 `onActionToastAction`、`setOnActionToastAction`、`handleActionToastAction`、`handleActionToastDismiss`
- 新增 `toasts`、`pushToast`、`dismissToast`、`resolveToast`

```typescript
export interface NotificationContextValue {
  // Toast 队列（统一弹窗）
  toasts: UnifiedToast[];
  pushToast: (config: PushToastConfig) => string;
  dismissToast: (id: string) => void;
  resolveToast: (id: string, action?: string) => void;
  markToastPending: (id: string) => void;

  // Card（通知中心，不变）
  cards: NotificationCard[];
  pushCard: (card: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }) => string;
  markCardRead: (id: string) => void;
  markAllRead: () => void;
  markCardPending: (id: string, action?: string) => void;
  resolveCard: (id: string, action?: string) => void;
  dismissCard: (id: string) => void;
  clearAllCards: () => void;
  unreadCount: number;

  // 浏览器通知权限（不变）
  permission: NotificationPermission | 'default';
  requestBrowserPermission: () => void;
}
```

- [ ] **Step 4: 确认 TypeScript 编译报错**

Run: `cd sensenova_claw/app/web && npx tsc --noEmit 2>&1 | head -50`
Expected: 大量类型错误（因为旧接口被移除但调用方还在用），确认改动已生效。

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/app/web/components/notification/NotificationProvider.tsx
git commit -m "refactor(notification): define UnifiedToast type and update context interface"
```

---

### Task 2: 实现 pushToast / dismissToast / resolveToast 核心逻辑

**Files:**
- Modify: `sensenova_claw/app/web/components/notification/NotificationProvider.tsx:105-341`

- [ ] **Step 1: 重写定时器管理**

替换第 99 行的 `actionToastTimeoutsRef` 和第 105-110 行的 `clearActionToastTimer`、第 112-115 行的 `removeActionToast`、第 125-160 行的两个 timer useEffect，改为统一的 toast 定时器管理：

```typescript
const toastTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

const clearToastTimer = useCallback((toastId: string) => {
  const timer = toastTimersRef.current.get(toastId);
  if (timer) {
    clearTimeout(timer);
    toastTimersRef.current.delete(toastId);
  }
}, []);

const clearAllToastTimers = useCallback(() => {
  toastTimersRef.current.forEach((timer) => clearTimeout(timer));
  toastTimersRef.current.clear();
}, []);

// 组件卸载时清理所有定时器
useEffect(() => {
  return () => clearAllToastTimers();
}, [clearAllToastTimers]);
```

- [ ] **Step 2: 实现 pushToast**

替换第 176-211 行的 `pushNotification` 函数：

```typescript
const pushToast = useCallback((config: PushToastConfig): string => {
  const id = makeNotificationId();
  const hasInteraction = (config.actions && config.actions.length > 0) || config.allowsInput;
  const autoDismissMs = config.autoDismissMs ?? (hasInteraction ? 60_000 : 5_000);

  const toast: UnifiedToast = {
    id,
    kind: config.kind ?? 'info',
    title: config.title,
    body: config.body,
    level: config.level ?? 'info',
    source: config.source ?? 'system',
    actions: config.actions,
    allowsInput: config.allowsInput,
    inputPlaceholder: config.inputPlaceholder,
    questionData: config.questionData,
    onAction: config.onAction,
    autoDismissMs,
    createdAtMs: Date.now(),
    pending: false,
    cardId: config.cardId,
    sessionId: config.sessionId,
    eventKey: config.eventKey,
  };

  setToasts((prev) => {
    // eventKey 去重：如果旧 toast pending 则不替换
    if (config.eventKey) {
      const existing = prev.find((t) => t.eventKey === config.eventKey);
      if (existing?.pending) return prev; // 旧 toast 正在处理中，不替换
      const filtered = prev.filter((t) => t.eventKey !== config.eventKey);
      // 替换旧 toast 时清理其定时器
      if (existing) clearToastTimer(existing.id);
      return [toast, ...filtered].slice(0, 20);
    }
    return [toast, ...prev].slice(0, 20);
  });

  // 启动自动消失定时器
  if (autoDismissMs > 0) {
    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      toastTimersRef.current.delete(id);
    }, autoDismissMs);
    toastTimersRef.current.set(id, timer);
  }

  // 浏览器原生通知（保留原 pushNotification 的 browser 选项）
  if (
    config.browser &&
    permission === 'granted' &&
    typeof window !== 'undefined' &&
    'Notification' in window
  ) {
    new window.Notification(config.title, { body: config.body });
  }

  return id;
}, [clearToastTimer, permission]);
```

- [ ] **Step 3: 实现 dismissToast**

替换第 162-164 行的 `dismissNotification`：

```typescript
const dismissToast = useCallback((id: string) => {
  clearToastTimer(id);
  setToasts((prev) => prev.filter((t) => t.id !== id));
  // 注：dismiss 不 resolve 关联的 card（用户主动关闭弹窗 ≠ 操作完成）
}, [clearToastTimer]);
```

- [ ] **Step 4: 实现 resolveToast**

```typescript
const resolveToast = useCallback((id: string, action?: string) => {
  clearToastTimer(id);
  setToasts((prev) => {
    const toast = prev.find((t) => t.id === id);
    // 同步 resolve 关联的 card
    if (toast?.cardId) {
      resolveCard(toast.cardId, action);
    }
    return prev.filter((t) => t.id !== id);
  });
}, [clearToastTimer, resolveCard]);
```

- [ ] **Step 5: 实现 markToastPending**

```typescript
const markToastPending = useCallback((id: string) => {
  clearToastTimer(id); // pending 时暂停定时器
  setToasts((prev) =>
    prev.map((t) => (t.id === id ? { ...t, pending: true } : t))
  );
}, [clearToastTimer]);
```

- [ ] **Step 6: 移除旧的 pushNotification、dismissNotification、ActionToast 相关函数**

删除以下函数/代码段：
- `pushNotification` (第 176-211 行) — 已被 `pushToast` 替代
- `dismissNotification` (第 162-164 行) — 已被 `dismissToast` 替代
- `handleActionToastAction` (第 324-336 行) — 不再需要
- `handleActionToastDismiss` (第 338-341 行) — 不再需要
- `onActionToastAction` state + `setOnActionToastAction` (第 98 行) — 不再需要

- [ ] **Step 7: 修改 pushCard，移除自动衍生 ActionToast 逻辑**

将第 215-266 行的 `pushCard` 函数简化，删除第 228-265 行的 ActionToast 自动创建逻辑。`pushCard` 只做：

```typescript
const pushCard = useCallback((cardInput: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }): string => {
  const card: NotificationCard = {
    ...cardInput,
    id: cardInput.id || makeNotificationId(),
    createdAtMs: cardInput.createdAtMs || Date.now(),
    read: false,
  };

  setCards((prev) => {
    if (prev.some((c) => c.id === card.id)) return prev;
    return [card, ...prev].slice(0, MAX_CARDS);
  });

  return card.id;
}, []);
```

- [ ] **Step 8: 修改 resolveCard，移除旧 ActionToast 清理并改为联动移除统一 toast**

`resolveCard` (第 289-307 行) 中替换旧的 `actionToasts` 清理为统一 toast 清理：

```typescript
const resolveCard = useCallback((id: string, action?: string) => {
  setCards((prev) =>
    prev.map((c) =>
      c.id === id ? { ...c, resolved: true, resolvedAction: action } : c
    )
  );
  // 联动移除关联的 toast
  setToasts((prev) => {
    const toast = prev.find((t) => t.cardId === id);
    if (toast) clearToastTimer(toast.id);
    return prev.filter((t) => t.cardId !== id);
  });
}, [clearToastTimer]);
```

- [ ] **Step 9: 修改 dismissCard，移除 ActionToast 清理逻辑**

`dismissCard` (第 309-316 行) 简化为：

```typescript
const dismissCard = useCallback((id: string) => {
  setCards((prev) => prev.filter((c) => c.id !== id));
}, []);
```

- [ ] **Step 10: 修改 clearAllCards，联动清除关联 toast**

```typescript
const clearAllCards = useCallback(() => {
  setCards([]);
  // 移除所有与 card 关联的 toast
  setToasts((prev) => {
    const removed = prev.filter((t) => t.cardId);
    removed.forEach((t) => clearToastTimer(t.id));
    return prev.filter((t) => !t.cardId);
  });
}, [clearToastTimer]);
```

- [ ] **Step 11: 修改 markCardPending，不再同步 ActionToast**

`markCardPending` (第 276-287 行) 中删除同步到 `actionToasts` 的逻辑，只保留 card 自身更新：

```typescript
const markCardPending = useCallback((id: string, action?: string) => {
  setCards((prev) =>
    prev.map((c) =>
      c.id === id ? { ...c, pending: true, read: true, resolvedAction: action } : c
    )
  );
  // 同步标记关联 toast 为 pending
  setToasts((prev) => {
    const toast = prev.find((t) => t.cardId === id);
    if (toast) {
      clearToastTimer(toast.id);
      return prev.map((t) =>
        t.cardId === id ? { ...t, pending: true } : t
      );
    }
    return prev;
  });
}, [clearToastTimer]);
```

- [ ] **Step 12: 更新 Provider 的 value 和 JSX 渲染**

更新第 345-374 行的 Provider value 和 JSX：

```typescript
const value: NotificationContextValue = useMemo(
  () => ({
    toasts,
    pushToast,
    dismissToast,
    resolveToast,
    markToastPending,
    cards,
    pushCard,
    markCardRead,
    markAllRead,
    markCardPending,
    resolveCard,
    dismissCard,
    clearAllCards,
    unreadCount,
    permission,
    requestBrowserPermission,
  }),
  [toasts, cards, unreadCount, permission, /* ... 其他依赖 */]
);

return (
  <NotificationContext.Provider value={value}>
    {children}
    <ToastContainer toasts={toasts} onDismiss={dismissToast} onMarkPending={markToastPending} />
  </NotificationContext.Provider>
);
```

注：`<NotificationToast>` 和 `<ActionToastPanel>` 的旧渲染代码（第 367-372 行）全部删除，替换为 `<ToastContainer>`。

- [ ] **Step 13: Commit**

```bash
git add sensenova_claw/app/web/components/notification/NotificationProvider.tsx
git commit -m "refactor(notification): implement unified pushToast/dismissToast/resolveToast and remove dual-toast system"
```

---

### Task 3: 重写 NotificationToast.tsx 为统一 ToastContainer + ToastItem

**Files:**
- Modify: `sensenova_claw/app/web/components/notification/NotificationToast.tsx`

- [ ] **Step 1: 移除旧类型和旧组件**

删除以下旧代码：
- `ToastNotification` interface (第 9-16 行)
- `ActionToast` interface (第 30-46 行)
- `NotificationToast` component (第 69-124 行)
- `ActionToastPanel` component (第 394-420 行)

保留以下可复用代码：
- `QuestionData` interface (第 20-26 行) — 移动到 Provider 或保留在此文件并导出
- `QuestionToastBody` component (第 128-259 行) — user_question 的富交互 UI
- `ActionToastItem` component (第 263-392 行) — 可作为 ToastItem 的基础重构
- Level icon/style maps (第 48-65 行) — 复用

- [ ] **Step 2: 更新 QuestionToastBody 接口**

当前 `QuestionToastBody` (第 128 行) 接受 `{ toast: ActionToast, onAction: (toastId, cardId, actionValue) => void }` 类型参数。需要更新为接受 `UnifiedToast` 类型和新的回调签名：

```typescript
// 旧接口
interface QuestionToastBodyProps {
  toast: ActionToast;
  onAction: (toastId: string, cardId: string, actionValue: string, inputValue?: string) => void;
}

// 新接口
interface QuestionToastBodyProps {
  toast: UnifiedToast;
  onSubmit: (actionValue: string, inputValue?: string) => void;
}
```

内部引用 `toast.cardId` 和 `toast.id` 等字段不变（UnifiedToast 包含这些字段）。将所有 `onAction(toast.id, toast.cardId, ...)` 调用替换为 `onSubmit(...)`。

- [ ] **Step 3: 实现 ToastItem 组件**

基于现有 `ActionToastItem` (第 263-392 行) 重构为通用 `ToastItem`。核心变化：
- 接收 `UnifiedToast` 类型而非旧 `ActionToast`
- 纯通知类型（无 actions/allowsInput）渲染简化版（仅标题+正文+关闭按钮）
- 有 actions 时渲染操作按钮
- 有 questionData 时渲染 `QuestionToastBody`
- pending 时显示"已提交，等待确认"

```typescript
import { UnifiedToast } from './NotificationProvider';

interface ToastItemProps {
  toast: UnifiedToast;
  onDismiss: (id: string) => void;
  onAction: (toastId: string, actionValue: string, inputValue?: string) => void;
}

export function ToastItem({ toast, onDismiss, onAction }: ToastItemProps) {
  const hasInteraction = (toast.actions && toast.actions.length > 0) || toast.allowsInput;

  return (
    <div className={cn(
      'rounded-lg border shadow-lg p-4 animate-in slide-in-from-top-4 fade-in duration-300',
      levelStyles[toast.level] ?? levelStyles.info,
    )}>
      {/* 头部：level 图标 + 标题 + 关闭按钮 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          {levelIcons[toast.level]}
          <span className="font-medium text-sm">{toast.title}</span>
        </div>
        <button onClick={() => onDismiss(toast.id)} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 正文 */}
      {toast.body && (
        <p className="text-sm text-muted-foreground mt-1 whitespace-pre-wrap">{toast.body}</p>
      )}

      {/* 交互区域 */}
      {toast.pending ? (
        <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          已提交，等待服务端确认…
        </div>
      ) : hasInteraction && (
        <>
          {toast.questionData ? (
            <QuestionToastBody
              toast={toast}
              onSubmit={(value, input) => onAction(toast.id, value, input)}
            />
          ) : toast.actions && (
            <div className="mt-3 flex gap-2 flex-wrap">
              {toast.actions.map((action) => (
                <button
                  key={action.value}
                  onClick={() => onAction(toast.id, action.value)}
                  className={cn(
                    'px-3 py-1.5 text-xs rounded-md transition-colors',
                    action.value === 'approve'
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : action.value === 'deny'
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : 'bg-primary text-primary-foreground hover:bg-primary/90'
                  )}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 实现 ToastContainer 组件**

```typescript
interface ToastContainerProps {
  toasts: UnifiedToast[];
  onDismiss: (id: string) => void;
  onMarkPending: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss, onMarkPending }: ToastContainerProps) {
  const handleAction = useCallback((toastId: string, actionValue: string, inputValue?: string) => {
    const toast = toasts.find((t) => t.id === toastId);
    if (!toast) return;
    // 标记 pending
    onMarkPending(toastId);
    // 调用 onAction 回调（发送 WebSocket 等）
    toast.onAction?.(actionValue, inputValue);
  }, [toasts, onMarkPending]);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed right-4 top-16 z-[300] flex flex-col gap-3 pointer-events-auto"
      style={{ width: 'min(28rem, calc(100vw - 2rem))' }}
    >
      {toasts.slice(0, 5).map((toast) => (
        <ToastItem
          key={toast.id}
          toast={toast}
          onDismiss={onDismiss}
          onAction={handleAction}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: 更新文件的导出**

确保文件导出 `ToastContainer`、`ToastItem`，移除 `NotificationToast` 和 `ActionToastPanel` 的导出。更新文件名保持不变（避免大面积 import 变更）或重命名文件：

```typescript
// 文件末尾导出
export { ToastContainer, ToastItem };
// 移除: export { NotificationToast, ActionToastPanel };
```

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/app/web/components/notification/NotificationToast.tsx
git commit -m "refactor(notification): rewrite NotificationToast as unified ToastContainer + ToastItem"
```

---

### Task 4: 更新 useNotification hook 和 NotificationDropdown

**Files:**
- Modify: `sensenova_claw/app/web/hooks/useNotification.ts:1-13`
- Modify: `sensenova_claw/app/web/components/notification/NotificationDropdown.tsx:258,327-336`

- [ ] **Step 1: 更新 useNotification hook**

hook 本身只是 `useContext(NotificationContext)` 的封装，类型会自动跟随 `NotificationContextValue` 变化。确认导出的类型正确即可。如果 hook 中有解构特定字段，更新解构。

- [ ] **Step 2: 修改 NotificationDropdown，移除 setOnActionToastAction 注册**

在 `NotificationDropdown.tsx`：
- 第 258 行：从 `useNotification()` 的解构中移除 `setOnActionToastAction`
- 第 327-336 行：删除注册 `setOnActionToastAction` 的 `useEffect` 和 `handleResolveRef`

这段代码不再需要，因为 action 回调现在通过 `pushToast` 的 `onAction` 直接传入。

`NotificationDropdown` 中仍然需要保留对 card 的操作（`handleResolve` 在下拉面板中操作 card 时使用），但不再桥接到 toast。

- [ ] **Step 3: Commit**

```bash
git add sensenova_claw/app/web/hooks/useNotification.ts sensenova_claw/app/web/components/notification/NotificationDropdown.tsx
git commit -m "refactor(notification): update useNotification hook and remove ActionToast callback bridge from dropdown"
```

---

### Task 5: 迁移 MessageContext 调用点

**Files:**
- Modify: `sensenova_claw/app/web/contexts/ws/MessageContext.tsx:5,90,376-471,540-572`

- [ ] **Step 1: 更新 import 和解构**

第 5 行 import 和第 90 行解构：
```typescript
// 旧
const { pushNotification, pushCard } = useNotification();
// 新
const { pushToast, pushCard } = useNotification();
```

- [ ] **Step 2: 迁移 turn_completed 处理 (第 379-393 行)**

```typescript
case 'turn_completed': {
  // ... 已有的跨 session 判断逻辑 ...
  const cardId = pushCard({
    kind: 'task_completed',
    title: `会话任务完成`,
    body: /* 现有内容 */,
    source: 'agent',
    sessionId: event.session_id,
    actions: [{ label: '查看会话 →', value: 'view_session' }],
  });
  pushToast({
    kind: 'task_completed',
    title: `会话任务完成`,
    body: /* 现有内容 */,
    actions: [{ label: '查看会话 →', value: 'view_session' }],
    cardId,
    sessionId: event.session_id,
    eventKey: `turn_completed_${event.session_id}_${event.payload.turn_id}`,
    onAction: (actionValue) => {
      if (actionValue === 'view_session' && event.session_id) {
        // 跳转到该会话（复用现有的跳转逻辑）
      }
    },
  });
  break;
}
```

- [ ] **Step 3: 迁移 notification 处理 (第 394-418 行)**

将 `pushNotification()` + `pushCard()` 替换为 `pushToast()` + `pushCard()`：

```typescript
case 'notification': {
  const title = String(event.payload.title || '通知');
  const body = String(event.payload.body || '');
  const notifSessionId = event.session_id;
  const actions = notifSessionId
    ? [{ label: '查看会话 →', value: 'view_session' }]
    : undefined;

  const cardId = pushCard({
    kind: 'general',
    title, body,
    level: (event.payload.level || 'info') as any,
    source: event.payload.source || 'system',
    sessionId: notifSessionId,
    actions,
  });

  pushToast({
    kind: 'general',
    title, body,
    level: (event.payload.level || 'info') as any,
    source: event.payload.source || 'system',
    actions,
    cardId,
    sessionId: notifSessionId,
    eventKey: `notification_${event.event_id}`,
    onAction: (actionValue) => {
      if (actionValue === 'view_session' && notifSessionId) {
        // 复用现有跳转逻辑
      }
    },
  });
  break;
}
```

- [ ] **Step 4: 迁移 proactive_result 处理 (第 428-466 行)**

```typescript
case 'proactive_result': {
  const { job_id: jobId, job_name: jobName, result: resultText } = event.payload;
  const resultSessionId = event.payload.session_id || event.session_id || '';
  // ... 现有的 setProactiveResults 等逻辑保留 ...

  if (resultText) {
    // ... setProactiveResults / refreshTaskGroups 保留 ...

    const actions = resultSessionId
      ? [{ label: '查看会话 →', value: 'view_session' }]
      : undefined;

    const cardId = pushCard({
      kind: 'general',
      title: `主动推送 — ${jobName || 'Proactive Agent'}`,
      body: resultText.slice(0, 300),
      level: 'info',
      source: 'proactive',
      sessionId: resultSessionId || undefined,
      actions,
    });

    pushToast({
      kind: 'proactive',
      title: `主动推送 — ${jobName || 'Proactive Agent'}`,
      body: resultText.slice(0, 300),
      actions,
      cardId,
      sessionId: resultSessionId || undefined,
      eventKey: `proactive_${jobId}_${resultSessionId}`,
      onAction: (actionValue) => {
        if (actionValue === 'view_session' && resultSessionId) {
          // 复用跳转逻辑
        }
      },
    });
  }
  break;
}
```

- [ ] **Step 5: 迁移 handleSkillInvoke 错误处理 (第 540-572 行)**

三处 `pushNotification` 调用改为 `pushToast`：

```typescript
// 示例（对每一处 pushNotification 做同样替换）：
pushToast({
  kind: 'info',
  title: 'Skill 启动失败',
  body: '未找到当前活跃会话',
  level: 'error',
  source: 'skill',
});
```

- [ ] **Step 6: 更新 useEffect 依赖数组 (第 471 行)**

将 `pushNotification` 替换为 `pushToast`：
```typescript
}, [subscribeGlobal, pushCard, pushToast, refreshTaskGroups, sessionIdRef]);
```

- [ ] **Step 7: Commit**

```bash
git add sensenova_claw/app/web/contexts/ws/MessageContext.tsx
git commit -m "refactor(notification): migrate MessageContext from pushNotification to pushToast"
```

---

### Task 6: 迁移 InteractionContext 调用点

**Files:**
- Modify: `sensenova_claw/app/web/contexts/ws/InteractionContext.tsx:4,38,135-224`
- Modify: `sensenova_claw/app/web/contexts/ws/EventDispatcherContext.tsx` (确认事件路由)

**重要背景：** `InteractionContext` 使用 `subscribeCurrentSession`，只接收当前 session 的事件。跨 session 的 `tool_confirmation_requested` / `user_question_asked` 事件通过 `INTERACTION_EVENT_TYPES` 路由，会同时发送到 `currentSessionSubs`（当前 session 事件处理）和 `globalSubs`（当非当前 session 的 turn 时）。需要确认 `InteractionContext` 是否同时订阅了 `subscribeGlobal`。如果没有，跨 session 的交互弹窗需要在 `MessageContext`（使用 `subscribeGlobal`）或直接在 `InteractionContext` 中增加 `subscribeGlobal` 处理。

- [ ] **Step 1: 确认事件路由机制**

阅读 `EventDispatcherContext.tsx` 中 `INTERACTION_EVENT_TYPES` 的路由逻辑，确认跨 session 的 `tool_confirmation_requested` / `user_question_asked` 事件是否会发送到 `globalSubs`。

如果跨 session 交互事件会到达 `globalSubs`，则需要在 `InteractionContext` 中增加 `subscribeGlobal` 来处理跨 session 弹窗。

- [ ] **Step 2: 更新 import 和解构**

第 4 行和第 38 行：
```typescript
// 旧
const { pushCard, resolveCard, markCardPending } = useNotification();
// 新
const { pushCard, pushToast, resolveCard, markCardPending } = useNotification();
```

同时新增 `subscribeGlobal` 解构（如果需要处理跨 session 事件）：
```typescript
const { subscribeCurrentSession, subscribeGlobal } = useEventDispatcher();
```

- [ ] **Step 3: 迁移 tool_confirmation_requested（当前 session 处理不变）**

当前 session 的处理保持原样——`enqueueInteraction` + `pushCard`，**不** `pushToast`（用户已在该会话页面，内嵌 ConfirmationDialog 足够）：

```typescript
case 'tool_confirmation_requested': {
  const toolCallId = event.payload.tool_call_id;
  // 内嵌交互（当前 session）
  enqueueInteraction({ /* 现有逻辑不变 */ });
  // 通知中心卡片（始终）
  pushCard({
    kind: 'tool_confirmation',
    id: `confirm_${toolCallId}`,
    /* 现有的 title/body/actions 不变 */
  });
  break;
}
```

- [ ] **Step 4: 新增 subscribeGlobal handler 处理跨 session 交互弹窗**

在 `InteractionContext` 中新增一个 `useEffect`，订阅 `subscribeGlobal` 处理跨 session 的 `tool_confirmation_requested` 和 `user_question_asked` 事件：

```typescript
// ── 跨 session 交互弹窗 ──
useEffect(() => {
  return subscribeGlobal((event: WsInboundEvent) => {
    switch (event.type) {
      case 'tool_confirmation_requested': {
        const toolCallId = event.payload.tool_call_id;
        const cardId = `confirm_${toolCallId}`;
        // pushCard 已在 currentSession handler 中调用，这里跳过
        // 仅弹窗
        pushToast({
          kind: 'tool_confirmation',
          title: /* 与 pushCard 相同标题 */,
          body: /* 与 pushCard 相同内容 */,
          actions: [
            { label: '批准', value: 'approve' },
            { label: '拒绝', value: 'deny' },
          ],
          cardId,
          sessionId: event.session_id,
          eventKey: `confirm_${toolCallId}`,
          onAction: (actionValue) => {
            wsSend({
              type: 'tool_confirmation_response',
              session_id: event.session_id,
              payload: { tool_call_id: toolCallId, approved: actionValue === 'approve' },
              timestamp: Date.now() / 1000,
            });
            markCardPending(cardId, actionValue);
          },
        });
        break;
      }
      case 'user_question_asked': {
        const questionId = event.payload.question_id;
        const cardId = `question_${questionId}`;
        pushToast({
          kind: 'user_question',
          title: /* 与 pushCard 相同标题 */,
          body: /* 与 pushCard 相同内容 */,
          allowsInput: /* 根据现有逻辑 */,
          questionData: /* 现有 questionData */,
          cardId,
          sessionId: event.session_id,
          eventKey: `question_${questionId}`,
          onAction: (actionValue, inputValue) => {
            submitQuestionResponse(event.session_id, questionId, actionValue, inputValue);
            markCardPending(cardId, actionValue);
          },
        });
        break;
      }
    }
  });
}, [subscribeGlobal, pushToast, wsSend, markCardPending, submitQuestionResponse]);
```

**注意：** `subscribeGlobal` 只在事件 session 不等于当前 session 时触发，所以这里不需要 `isCurrentSession` 检查。`pushCard` 已在 `subscribeCurrentSession` handler 中调用，全局 handler 只负责弹窗。但需要确认：如果 `EventDispatcherContext` 对 `INTERACTION_EVENT_TYPES` 的路由是"总是发到 currentSessionSubs，非当前 turn 时也发到 globalSubs"，那么跨 session 事件会同时到达两处。这种情况下 `pushCard` 会被调用两次（currentSession handler + global handler），需要利用 `pushCard` 的 id 去重来避免重复 card。

- [ ] **Step 5: 迁移 resolveCard 调用点（不变）**

第 162-166 行 `tool_confirmation_resolved` 和第 227-238 行 `user_question_answered_event` 中的 `resolveCard` 调用保持不变。`resolveCard` 内部已在 Task 2 Step 8 中增加了联动移除 toast 的逻辑。

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/app/web/contexts/ws/InteractionContext.tsx sensenova_claw/app/web/components/notification/NotificationProvider.tsx
git commit -m "refactor(notification): migrate InteractionContext to pushToast with current/cross-session rules"
```

---

### Task 7: 迁移剩余调用方 (cron, Dashboard, ProactiveAgentPanel)

**Files:**
- Modify: `sensenova_claw/app/web/app/cron/page.tsx:196,368-387`
- Modify: `sensenova_claw/app/web/components/dashboard/Dashboard.tsx:125,194-202`
- Modify: `sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx:106,119-147`

- [ ] **Step 1: 迁移 cron/page.tsx**

第 196 行：`const { pushNotification } = useNotification()` → `const { pushToast } = useNotification()`

第 368-387 行（`triggerJob` 中的两处 `pushNotification` 调用）：

```typescript
// 成功
pushToast({
  kind: 'info',
  title: '定时任务已触发',
  body: `已手动触发 ${jobName}`,
  level: 'success',
  source: 'cron',
});

// 失败
pushToast({
  kind: 'info',
  title: '定时任务触发失败',
  body: errorMessage,
  level: 'error',
  source: 'cron',
});
```

- [ ] **Step 2: 迁移 Dashboard.tsx**

第 125 行：`const { pushNotification } = useNotification()` → `const { pushToast } = useNotification()`

第 194-202 行：

```typescript
pushToast({
  kind: 'info',
  title: '会话切换失败',
  body: /* 现有错误信息 */,
  level: 'error',
  source: 'dashboard',
});
```

- [ ] **Step 3: 迁移 ProactiveAgentPanel.tsx**

第 106 行：`const { pushNotification } = useNotification()` → `const { pushToast } = useNotification()`

第 119-147 行（4 处 `pushNotification` 调用）全部改为 `pushToast`，保留现有的 title/body/level。

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/app/web/app/cron/page.tsx sensenova_claw/app/web/components/dashboard/Dashboard.tsx sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx
git commit -m "refactor(notification): migrate cron, Dashboard, ProactiveAgentPanel to pushToast"
```

---

### Task 8: 编译验证与最终清理

**Files:**
- All modified files

- [ ] **Step 1: TypeScript 编译检查**

Run: `cd sensenova_claw/app/web && npx tsc --noEmit 2>&1 | head -100`
Expected: 无类型错误

- [ ] **Step 2: 全局搜索残留引用**

Run: `grep -rn 'pushNotification\|ActionToastPanel\|actionToasts\|setOnActionToastAction\|onActionToastAction\|handleActionToastAction\|handleActionToastDismiss\|dismissNotification' sensenova_claw/app/web/ --include='*.tsx' --include='*.ts' | grep -v node_modules | grep -v '.next'`

Expected: 无结果（所有旧 API 引用已清理）

- [ ] **Step 3: 移除 ACTIONABLE_KINDS 常量**

`NotificationProvider.tsx` 第 57 行的 `ACTIONABLE_KINDS` 不再需要（pushCard 不再自动衍生），确认删除。

- [ ] **Step 4: 清理未使用的导入**

检查每个修改过的文件，移除不再使用的 import。

- [ ] **Step 5: 最终编译确认**

Run: `cd sensenova_claw/app/web && npx tsc --noEmit`
Expected: 成功，无错误

- [ ] **Step 6: Commit**

```bash
git add -A sensenova_claw/app/web/
git commit -m "refactor(notification): final cleanup - remove all legacy dual-toast references"
```

---

### Task 9: 手动验证

- [ ] **Step 1: 启动前端**

Run: `npm run dev:web`

- [ ] **Step 2: 验证纯通知弹窗**

触发一个 Skill 执行失败或 Cron 任务 → 应看到单个 info Toast，5 秒后消失。

- [ ] **Step 3: 验证 proactive_result 弹窗**

触发一个 proactive agent 推送 → 应看到**一个**弹窗（带"查看会话→"按钮），不再有重复弹窗。

- [ ] **Step 4: 验证工具确认弹窗**

在非当前会话触发工具授权 → 应看到弹窗带批准/拒绝按钮。在当前会话触发 → 应只有内嵌 ConfirmationDialog，无弹窗。

- [ ] **Step 5: 验证通知中心**

铃铛下拉面板应正常显示所有事件的卡片记录，不受弹窗改造影响。

- [ ] **Step 6: 验证弹窗堆叠**

同时触发多个事件 → 弹窗应在同一容器内按 gap-3 堆叠，最多 5 个，无位置重叠。
