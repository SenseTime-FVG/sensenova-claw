# P0 Context 消费优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `sessions/[id]/page.tsx` 的重复 WS 实现，并将 9 个组件从 `useChatSession()` 全量订阅迁移到精确子 hook。

**Architecture:** sessions/[id] 页面重写为薄壳，复用 `ChatPanel` + `useInteraction()` 渲染聊天 UI；9 个轻量消费者从 `useChatSession()` 迁移到 `useSession()` / `useMessages()` / `useInteraction()` / `useEventDispatcher()` 精确订阅。`useChatSession()` 保留为 backward-compatible facade。

**Tech Stack:** Next.js 14, TypeScript, React Context

**Design spec:** `docs/superpowers/specs/2026-03-27-frontend-quality-fixes-design.md` (Sub-project A)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/sessions/[id]/page.tsx` | **Rewrite** | 薄壳：URL param → switchSession → ChatPanel + header |
| `components/layout/DashboardNav.tsx` | Modify (1 line) | `useChatSession()` → `useSession()` |
| `components/layout/DashboardLayout.tsx` | Modify (1 line) | `useChatSession()` → `useSession()` |
| `components/workbench/LeftNav.tsx` | Modify (2 lines) | `useChatSession()` → `useSession()` |
| `components/files/GlobalFilePanel.tsx` | Modify (2 lines) | `useChatSession()` → `useSession()` + `useMessages()` |
| `components/workbench/RightContext.tsx` | Modify (2 lines) | `useChatSession()` → `useMessages()` |
| `hooks/useOfficeState.ts` | Modify (2 lines) | `useChatSession()` → `useMessages()` + `useEventDispatcher()` |
| `hooks/useDashboardData.ts` | Modify (2 lines) | `useChatSession()` → `useSession()` + `useMessages()` |
| `components/dashboard/Dashboard.tsx` | Modify (2 lines) | `useChatSession()` → `useSession()` |
| `components/notification/NotificationDropdown.tsx` | Modify (2 lines) | `useChatSession()` → `useSession()` + `useWebSocket()` + `useInteraction()` |
| `app/features/[slug]/page.tsx` | Modify (2 lines) | `useChatSession()` → `useSession()` + `useMessages()` |

---

### Task 1: Rewrite `sessions/[id]/page.tsx`

**Files:**
- Rewrite: `sensenova_claw/app/web/app/sessions/[id]/page.tsx`

当前这个文件 ~843 行，自建 WebSocket 连接、独立事件处理、独立交互队列。重写为 ~120 行的薄壳，复用 Context 体系 + ChatPanel。

- [ ] **Step 1: Read existing file and understand the session header UI**

需要保留的独特 UI：session 元数据 header（标题、session ID、创建时间、状态）。其余全部复用。

- [ ] **Step 2: Rewrite the file**

将整个文件替换为：

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useSession, useWebSocket } from '@/contexts/ws';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { getAgentId } from '@/lib/chatTypes';

// ── 类型 ──

interface SessionInfo {
  session_id: string;
  created_at: number;
  last_active: number;
  status: string;
  meta: string;
}

function parseTitle(meta: string): string {
  try {
    const m = JSON.parse(meta);
    return m.title || m.name || '未命名会话';
  } catch {
    return '未命名会话';
  }
}

function formatTimestamp(ts: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString('zh-CN');
}

// ── 页面组件 ──

export default function SessionDetailPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const { switchSession, sessions, currentSessionId } = useSession();
  const { wsConnected } = useWebSocket();
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // URL param 驱动 session 切换
  useEffect(() => {
    if (sessionId) {
      switchSession(sessionId);
    }
  }, [sessionId, switchSession]);

  // 加载 session 元数据
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await authFetch(`${API_BASE}/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error('Session not found');
        const data = await res.json();
        setSessionInfo(data.session || data);
      } catch (e: any) {
        setError(e.message || '加载会话失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  // 从 session 列表获取 agentId
  const activeSession = sessions.find(s => s.session_id === sessionId);
  const agentId = activeSession ? (getAgentId(activeSession.meta) || 'default') : 'default';

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-full">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center h-full gap-4">
          <p className="text-destructive">{error}</p>
          <Link href="/sessions" className="text-primary hover:underline">返回会话列表</Link>
        </div>
      </DashboardLayout>
    );
  }

  const title = sessionInfo ? parseTitle(sessionInfo.meta) : '会话详情';

  return (
    <DashboardLayout>
      <div className="flex flex-col h-full">
        {/* ── Header ── */}
        <div className="sticky top-0 z-10 bg-background border-b px-4 py-3 flex items-center gap-3">
          <Link href="/sessions" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold truncate">{title}</h1>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-mono">{sessionId.slice(0, 8)}...</span>
              {sessionInfo?.created_at && (
                <span>创建于 {formatTimestamp(sessionInfo.created_at)}</span>
              )}
              <span className={`inline-flex items-center gap-1 ${wsConnected ? 'text-green-500' : 'text-red-400'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-400'}`} />
                {wsConnected ? '已连接' : '未连接'}
              </span>
            </div>
          </div>
        </div>

        {/* ── Chat Area (复用 ChatPanel) ── */}
        <div className="flex-1 overflow-hidden">
          <ChatPanel defaultAgentId={agentId} hideAgentSelector lockAgent />
        </div>
      </div>
    </DashboardLayout>
  );
}
```

这把 ~843 行缩减为 ~130 行。删除了：
- 独立 WebSocket 连接（L370 `new WebSocket(WS_URL)`）
- 独立事件 switch（L390-581，~190 行）
- 独立交互队列（L300-366，~66 行）
- 内联 MessageBubble / ToolCallGroup / TypingIndicator 组件（L80-286，~206 行）
- 独立 sendMessage / cancelTurn / sendQuestionAnswer / sendConfirmationResponse（L623-702，~80 行）

全部复用 Context 体系 + ChatPanel。

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd sensenova_claw/app/web && npx tsc --noEmit 2>&1 | grep -E 'sessions|error'`
Expected: No new errors in sessions/[id]/page.tsx

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/app/web/app/sessions/[id]/page.tsx
git commit -m "refactor(web): sessions/[id] 复用 Context 体系，删除 ~700 行重复实现"
```

---

### Task 2: Migrate `DashboardNav` to `useSession()`

**Files:**
- Modify: `sensenova_claw/app/web/components/layout/DashboardNav.tsx:13,87`

- [ ] **Step 1: Change import and hook call**

Replace line 13:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession } from '@/contexts/ws';
```

Replace line 87:
```tsx
// Before
const { startNewChat } = useChatSession();
// After
const { startNewChat } = useSession();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/layout/DashboardNav.tsx
git commit -m "refactor(web): DashboardNav 从 useChatSession 迁移到 useSession"
```

---

### Task 3: Migrate `DashboardLayout` to `useSession()`

**Files:**
- Modify: `sensenova_claw/app/web/components/layout/DashboardLayout.tsx:18,35`

- [ ] **Step 1: Change import and hook call**

Replace line 18:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession } from '@/contexts/ws';
```

Replace line 35:
```tsx
// Before
const { startNewChat } = useChatSession();
// After
const { startNewChat } = useSession();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/layout/DashboardLayout.tsx
git commit -m "refactor(web): DashboardLayout 从 useChatSession 迁移到 useSession"
```

---

### Task 4: Migrate `LeftNav` to `useSession()`

**Files:**
- Modify: `sensenova_claw/app/web/components/workbench/LeftNav.tsx:11,228-236`

- [ ] **Step 1: Change import and hook call**

Replace line 11:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession } from '@/contexts/ws';
```

Replace lines 228-236:
```tsx
// Before
const {
  sessions,
  currentSessionId,
  switchSession,
  deleteSession,
  startNewChat,
  refreshTaskGroups,
  loadingSessions,
} = useChatSession();
// After
const {
  sessions,
  currentSessionId,
  switchSession,
  deleteSession,
  startNewChat,
  refreshTaskGroups,
  loadingSessions,
} = useSession();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/workbench/LeftNav.tsx
git commit -m "refactor(web): LeftNav 从 useChatSession 迁移到 useSession"
```

---

### Task 5: Migrate `GlobalFilePanel` to `useSession()` + `useMessages()`

**Files:**
- Modify: `sensenova_claw/app/web/components/files/GlobalFilePanel.tsx:15,215`

- [ ] **Step 1: Change import and hook call**

Replace line 15:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession, useMessages } from '@/contexts/ws';
```

Replace line 215:
```tsx
// Before
const { currentSessionId, taskProgress } = useChatSession();
// After
const { currentSessionId } = useSession();
const { taskProgress } = useMessages();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/files/GlobalFilePanel.tsx
git commit -m "refactor(web): GlobalFilePanel 从 useChatSession 迁移到精确子 hook"
```

---

### Task 6: Migrate `RightContext` to `useMessages()`

**Files:**
- Modify: `sensenova_claw/app/web/components/workbench/RightContext.tsx:7,10`

- [ ] **Step 1: Change import and hook call**

Replace line 7:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useMessages } from '@/contexts/ws';
```

Replace line 10:
```tsx
// Before
const { steps, taskProgress } = useChatSession();
// After
const { steps, taskProgress } = useMessages();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/workbench/RightContext.tsx
git commit -m "refactor(web): RightContext 从 useChatSession 迁移到 useMessages"
```

---

### Task 7: Migrate `useOfficeState` to `useMessages()` + `useEventDispatcher()`

**Files:**
- Modify: `sensenova_claw/app/web/hooks/useOfficeState.ts:8,64`

- [ ] **Step 1: Change import and hook call**

Replace line 8:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useMessages, useEventDispatcher } from '@/contexts/ws';
```

Replace line 64:
```tsx
// Before
const { isTyping, steps, messages, globalActivity } = useChatSession();
// After
const { isTyping, steps, messages } = useMessages();
const { globalActivity } = useEventDispatcher();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/hooks/useOfficeState.ts
git commit -m "refactor(web): useOfficeState 从 useChatSession 迁移到精确子 hook"
```

---

### Task 8: Migrate `useDashboardData` to `useSession()` + `useMessages()`

**Files:**
- Modify: `sensenova_claw/app/web/hooks/useDashboardData.ts:5,157`

- [ ] **Step 1: Change import and hook call**

Replace line 5:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession, useMessages } from '@/contexts/ws';
```

Replace line 157:
```tsx
// Before
const { sessions, proactiveResults } = useChatSession();
// After
const { sessions } = useSession();
const { proactiveResults } = useMessages();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/hooks/useDashboardData.ts
git commit -m "refactor(web): useDashboardData 从 useChatSession 迁移到精确子 hook"
```

---

### Task 9: Migrate `Dashboard` to `useSession()`

**Files:**
- Modify: `sensenova_claw/app/web/components/dashboard/Dashboard.tsx:7,121-122`

- [ ] **Step 1: Change import and hook call**

Replace line 7:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession } from '@/contexts/ws';
```

Replace lines 121-122:
```tsx
// Before
const { switchSession, createSession } = useChatSession();
// After
const { switchSession, createSession } = useSession();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/dashboard/Dashboard.tsx
git commit -m "refactor(web): Dashboard 从 useChatSession 迁移到 useSession"
```

---

### Task 10: Migrate `NotificationDropdown` to precise sub-hooks

**Files:**
- Modify: `sensenova_claw/app/web/components/notification/NotificationDropdown.tsx:18,365`

- [ ] **Step 1: Change import and hook call**

Replace line 18:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession, useWebSocket, useInteraction } from '@/contexts/ws';
```

Replace line 365:
```tsx
// Before
const { sessions, switchSession, wsSend, resolveInteractionFromNotification } = useChatSession();
// After
const { sessions, switchSession } = useSession();
const { wsSend } = useWebSocket();
const { resolveInteractionFromNotification } = useInteraction();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/components/notification/NotificationDropdown.tsx
git commit -m "refactor(web): NotificationDropdown 从 useChatSession 迁移到精确子 hook"
```

---

### Task 11: Migrate `features/[slug]/page.tsx` to `useSession()` + `useMessages()`

**Files:**
- Modify: `sensenova_claw/app/web/app/features/[slug]/page.tsx:9,224-227`

- [ ] **Step 1: Change import and hook call**

Replace line 9:
```tsx
// Before
import { useChatSession } from '@/contexts/ChatSessionContext';
// After
import { useSession, useMessages } from '@/contexts/ws';
```

Replace lines 224-227:
```tsx
// Before
const {
  sendMessage,
  switchSession,
  currentSessionId,
} = useChatSession();
// After
const { switchSession, currentSessionId } = useSession();
const { sendMessage } = useMessages();
```

- [ ] **Step 2: Commit**

```bash
git add sensenova_claw/app/web/app/features/[slug]/page.tsx
git commit -m "refactor(web): features/[slug] 从 useChatSession 迁移到精确子 hook"
```

---

### Task 12: TypeScript 全量检查 + 验证

- [ ] **Step 1: Run TypeScript check**

Run: `cd sensenova_claw/app/web && npx tsc --noEmit 2>&1 | tail -10`
Expected: No new errors in any modified files. Pre-existing errors in `app/settings/page.tsx` etc. are acceptable.

- [ ] **Step 2: Verify no remaining useChatSession imports in migrated files**

Run: `grep -rn "useChatSession" sensenova_claw/app/web/components/layout/DashboardNav.tsx sensenova_claw/app/web/components/layout/DashboardLayout.tsx sensenova_claw/app/web/components/workbench/LeftNav.tsx sensenova_claw/app/web/components/files/GlobalFilePanel.tsx sensenova_claw/app/web/components/workbench/RightContext.tsx sensenova_claw/app/web/hooks/useOfficeState.ts sensenova_claw/app/web/hooks/useDashboardData.ts sensenova_claw/app/web/components/dashboard/Dashboard.tsx sensenova_claw/app/web/components/notification/NotificationDropdown.tsx sensenova_claw/app/web/app/features/[slug]/page.tsx`
Expected: No matches.

- [ ] **Step 3: Count remaining useChatSession consumers**

Run: `grep -rn "useChatSession" sensenova_claw/app/web --include="*.tsx" --include="*.ts" | grep -v "ChatSessionContext.tsx" | grep -v "node_modules"`
Expected: Only `chat/page.tsx`, `ppt/page.tsx`, `ChatPanel.tsx` remain (大组件，按设计保留)。
