# 前端质量修复设计

## 背景

EventDispatcher 重构完成后，前端仍存在 7 个已确认的问题，按优先级分为 P0/P1/P2 三档。本 spec 覆盖全部 7 个问题的修复设计，分为 3 个 sub-project 按序执行。

## Sub-project A: Context 消费优化

### A1: `sessions/[id]/page.tsx` 复用 Context 体系

#### 问题

`app/sessions/[id]/page.tsx`（~700 行）完全绕开 Context 体系，自建 WebSocket 连接（L370）、独立事件 switch（L390-581）、独立交互队列（L305-354）、独立 turn 追踪。与 Context 体系行为不一致（如跨会话放行逻辑只在新架构中有）。

#### 设计

将页面改为薄壳，复用 Context 体系：

1. **URL param 驱动 session 切换**：`useEffect` 监听 `params.id`，调用 `useSession().switchSession(id)` 切换当前会话
2. **复用共享 chat 组件**：使用 `ChatPanel`（含 MessageList + ChatInput + TypingIndicator）。交互对话框（tool confirmation / user question）当前内联在 `chat/page.tsx` 中渲染，sessions page 需从 `useInteraction()` 取 `activeInteraction` 并内联渲染相同 UI（或抽取为共享 `InteractionPanel` 组件）
3. **保留页面特有 UI**：header 区域显示 session 元数据（ID、创建时间、标题），通过 `useSession().sessions` 获取
4. **删除全部重复实现**：独立 WS 连接、事件 switch、交互队列、send/cancel 函数、内联 MessageBubble/ToolCallGroup 等（~500 行）

**时序处理**：

```
页面 mount → useEffect 触发 switchSession(params.id)
  → WS 发送 load_session
  → MessageContext 收到 session_loaded → 加载历史消息
  → 页面渲染 MessageList（已有消息）
```

这个流程已在主 chat 的 `switchSession` 中验证过。

**需要确认**：sessions/[id] 页面是否还有 chat/page 或 ChatPanel 中不存在的独特功能。经排查：
- Turn 取消追踪（`cancelledTurnIdsRef`）— MessageContext 已有
- 交互队列 — InteractionContext 已有
- IME 输入组合处理（`isComposingRef`）— ChatInput 已有
- 自动调整 textarea 高度 — ChatInput 已有

结论：**无独特功能，全部可复用**。

### A2: `useChatSession()` 精确订阅迁移

#### 问题

14 个消费者全用 `useChatSession()` 全量订阅，任一子 Context 变化触发所有消费者重渲染。拆分后的性能收益未兑现。

#### 设计

将只取少量字段的组件迁移到精确的子 hook。

**迁移映射表**：

| 组件 | 改为 | 取用字段 |
|------|------|---------|
| `DashboardNav` | `useSession()` | `startNewChat` |
| `DashboardLayout` | `useSession()` | `startNewChat` |
| `LeftNav` | `useSession()` | `sessions, currentSessionId, switchSession, deleteSession, startNewChat, refreshTaskGroups, loadingSessions` |
| `GlobalFilePanel` | `useSession()` + `useMessages()` | `currentSessionId, taskProgress` |
| `RightContext` | `useMessages()` | `steps, taskProgress` |
| `useOfficeState` | `useMessages()` + `useEventDispatcher()` | `isTyping, steps, messages, globalActivity` |
| `useDashboardData` | `useSession()` + `useMessages()` | `sessions, proactiveResults` |
| `Dashboard` | `useSession()` | `switchSession, createSession` |
| `NotificationDropdown` | `useSession()` + `useWebSocket()` + `useInteraction()` | `sessions, switchSession, wsSend, resolveInteractionFromNotification` |

**保留 `useChatSession()` 的组件**（取用字段多、跨多个子 Context）：

| 组件 | 理由 |
|------|------|
| `ChatPanel` | 取用 ~11 个字段，横跨 4 个子 Context |
| `chat/page.tsx` | 取用 ~18 个字段 |
| `ppt/page.tsx` | 取用 ~10 个字段 |
| `features/[slug]/page.tsx` | 待确认，暂保留 |

**`useChatSession()` 保留为 backward-compatible facade**，不删除，新代码应直接用子 hook。

---

## Sub-project B: 可靠性基础设施

### B1: 请求竞态取消（P1-3）

#### 问题

所有 REST 请求都是裸 `authFetch`，无去重、无竞态取消。快速切换会话时可能产生竞态（旧请求的响应覆盖新请求的状态）。

#### 设计

不引入 SWR/React Query（避免大依赖），在关键路径加 **AbortController 竞态取消**：

1. **SessionContext.loadSessionList**：加去重守卫，同时只允许一个 inflight 请求
   ```typescript
   const loadingRef = useRef(false);
   const loadSessionList = useCallback(async () => {
     if (loadingRef.current) return; // 去重
     loadingRef.current = true;
     try { ... } finally { loadingRef.current = false; }
   }, []);
   ```

2. **MessageContext 历史加载**：切换 session 时用 `AbortController` 取消前一个请求
   ```typescript
   const abortRef = useRef<AbortController | null>(null);
   // 切换时
   abortRef.current?.abort();
   abortRef.current = new AbortController();
   const data = await authGet(url, { signal: abortRef.current.signal });
   ```

3. **authFetch 支持 signal 透传**：`authFetch` 的 options 参数已支持 `RequestInit`，`signal` 可直接传入，无需改 authFetch 本身。

不做通用缓存层（YAGNI）。

### B2: 关键路径错误提示（P1-4）

#### 问题

79 个 catch 块大部分空处理，用户无感知。WS 断连虽已有绿点指示，但消息区无提示。

#### 设计

**策略**：只处理用户能感知的关键路径，其余静默 catch 保留（如 metadata JSON 解析失败不需要打扰用户）。

1. **WS 断连提示**：在 MessageContext 中，当 `wsConnected` 从 true 变为 false 时，向消息列表插入一条系统消息（`role: 'system'`, `content: '连接已断开，正在重连...'`）。重连成功时插入另一条（`'已重新连接'`）。

2. **关键 API 失败 toast**：为以下操作的 catch 块添加用户提示：
   - `sendMessage` 失败 → toast "发送失败，请重试"
   - `deleteSession` 失败 → toast "删除失败"
   - `switchSession` 失败 → toast "切换会话失败"

3. **Toast 实现**：项目已有 `NotificationProvider` + `NotificationToast`（基于 `@radix-ui/react-toast`），支持 `info/warning/error/success` 级别。直接复用 `NotificationProvider` 的 `addToast` 方法推送错误提示。

### B3: Error Boundary（P1-5）

#### 问题

整个 app 没有 `error.tsx`，渲染异常（如 ChunkLoadError）导致白屏。

#### 设计

1. **`app/error.tsx`**（Next.js 约定的页面级 Error Boundary）：
   - 捕获页面组件的渲染异常
   - 显示："出错了" + error.message + "重试"按钮（调用 `reset()`）
   - 样式与现有 UI 一致（Tailwind）

2. **`app/global-error.tsx`**（Next.js 约定的 layout 级 Error Boundary）：
   - 捕获 layout 组件的异常（如 Provider 崩溃）
   - 显示："应用出错了" + "刷新页面"按钮
   - 必须自带 `<html><body>` 因为 layout 已崩溃

不在每个组件加 boundary（过度防御）。

---

## Sub-project C: 渲染性能

### C1: 消息列表虚拟化（P2-6）

#### 问题

MessageList 用 `.map()` 一次渲染所有消息，长对话（500+ 条）会卡。

#### 设计

引入 `react-virtuoso`（比 react-window 更适合聊天场景 — 支持动态高度、自动滚到底部、`followOutput` 模式）：

1. **安装**：`npm install react-virtuoso`
2. **替换 MessageList 渲染**：
   ```tsx
   import { Virtuoso } from 'react-virtuoso';

   <Virtuoso
     data={groupedMessages}
     followOutput="smooth"
     itemContent={(index, group) => <GroupRenderer group={group} />}
   />
   ```
3. **保留现有 `groupMessages` 逻辑**：虚拟化发生在 group 级别（每个 group 是一个虚拟化 item）
4. **滚到底部行为**：`followOutput="smooth"` 替代现有的 `scrollIntoView` useEffect

**影响范围**：仅修改 `components/chat/MessageBubble.tsx` 中的 `MessageList` 函数（或 `components/chat/MessageList.tsx`，视实际使用的组件而定）。

### C2: MessageBubble React.memo（P2-7）

#### 问题

每条消息状态更新都导致所有消息气泡重渲染。

#### 设计

1. **`MessageBubble`** 包装 `React.memo`，自定义比较函数：
   ```typescript
   export const MessageBubble = React.memo(function MessageBubble({ msg }: { msg: ChatMessage }) {
     // ... 现有实现
   }, (prev, next) => {
     return prev.msg === next.msg; // 引用相等即跳过
   });
   ```
   注意：流式更新时 MessageContext 每次 delta 都会创建新的 msg 对象，所以正在流式的最后一条消息仍会重渲染（正确行为），但之前的消息不会。

2. **`ToolCallGroup`** 同样包装 `React.memo`。

3. **`ToolCallItem`** 如果是独立导出的组件，也包装 memo。

---

## 执行顺序

```
Sub-project A（P0）
  Task 1: sessions/[id]/page.tsx 复用 Context
  Task 2: 精确订阅迁移（9 个组件）

Sub-project B（P1）
  Task 3: 请求竞态取消
  Task 4: 关键路径错误提示
  Task 5: Error Boundary

Sub-project C（P2）
  Task 6: react-virtuoso 虚拟化
  Task 7: MessageBubble/ToolCallGroup memo
```

## 不在本次范围

- 通用 REST 缓存层（SWR/React Query） — YAGNI，当前无高频读场景
- 修复所有 79 个空 catch 块 — 只处理关键路径
- 每个组件独立 Error Boundary — 过度防御
- 消息历史分页加载 — 独立优化
- `sessions/[id]/page.tsx` 的独立路由是否保留 — 保留路由，只改实现
