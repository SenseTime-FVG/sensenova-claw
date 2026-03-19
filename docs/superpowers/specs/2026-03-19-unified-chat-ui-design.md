# 统一对话风格与任务导航重构设计

**日期**: 2026-03-19
**状态**: 待审核
**分支**: syy/frontend

## 1. 概述

将 AgentOS 前端的 5 个页面（主页、Chat、深度研究、PPT、自动化）统一为一致的对话交互风格，合并左侧导航栏为按任务分组的 session 列表，并实现支持拖拽的文件区。

### 核心目标

1. **统一对话风格**：所有页面内嵌完整 chat 对话能力（消息气泡、工具调用显示、历史消息、typing 指示器），仅默认 agent 不同
2. **任务分组导航**：左侧统一导航栏，用户第一条消息自动成为任务标题，同一任务下可创建多个 session
3. **文件区**：左侧 Tab 切换（任务 | 文件），文件区上下分两个 panel（用户文件夹 + agent workdir），文件可拖拽到 chat 输入区

## 2. 页面定位与区别

| 页面 | 路由 | 默认 Agent | 空状态 |
|------|------|-----------|--------|
| 主页（工作台） | `/` | 办公主助手 (`default`) | 显示快捷任务模板卡片（回复邮件、准备周会等）+ 最近任务列表 |
| Chat | `/chat` | 办公主助手 (`default`) | 简洁的 "How can I help you?" 空状态 |
| 深度研究 | `/research` | 深度调研 (`deep_research`) | 简洁的 "开始一个新的调研任务" 空状态 |
| PPT | `/ppt` | PPT生成助手 (`ppt_generator`) | 简洁的 "创建一个新的演示文稿" 空状态 |
| 自动化 | `/automation` | 办公主助手 (`default`) | 简洁的 "创建一个新的自动化任务" 空状态 |

**主页与 Chat 的区别**：主页保留快捷任务模板功能（从现有 `MainStage` 的 empty state 迁移），作为任务入口；Chat 是纯对话界面。两者共享 `ChatPanel`，但主页在无 session 时显示 `TaskTemplates` 组件替代 ChatPanel 的空状态。一旦用户选中某个 session 或发送消息，主页也切换为 ChatPanel 视图。

## 3. 整体布局

```
┌─ DashboardLayout TopBar ─────────────────────────────────────┐
│ [AO] AgentOS  [工作台][Chat][深度研究][PPT][自动化] [管理▾] [搜索][头像] │
├──────────┬───────────────────────────────┬────────────────────┤
│ LeftNav  │       ChatPanel              │   RightContext     │
│ w-64     │       (所有页面统一)            │   (可折叠, w-80)  │
│          │                               │                    │
│[任务|文件]│  ┌─────────────────────┐      │   · 执行步骤       │
│          │  │  消息列表             │     │   · Sources        │
│ 任务Tab:  │  │  · 用户消息气泡       │     │   · 参数           │
│ ▼ 任务1   │  │  · Agent 回复气泡    │     │   · 任务进度       │
│   session1│  │  · 工具调用卡片      │     │                    │
│   session2│  │  · typing 指示器     │     │                    │
│ ▼ 任务2   │  └─────────────────────┘     │                    │
│   session3│                               │                    │
│          │  ┌─────────────────────────┐   │                    │
│ 文件Tab:  │  │ [Agent选择] [状态]      │   │                    │
│ ─我的文件─│  │ [输入框...] [发送]      │   │                    │
│  📁项目文档│  │ (支持文件拖入)         │   │                    │
│ ─Agent区─│  └─────────────────────────┘   │                    │
│  📁生成内容│                               │                    │
└──────────┴───────────────────────────────┴────────────────────┘
```

## 4. 任务分组导航（LeftNav 任务 Tab）

### 数据模型（纯前端）

"任务"不是后端概念，前端用 session 的 `meta.title` 作为任务标题：

```typescript
interface TaskGroup {
  taskId: string;          // 第一个 session 的 session_id
  title: string;           // 来自 session meta.title
  lastActive: number;      // 组内最新 session 的 last_active
  sessions: SessionItem[]; // 该任务下的所有 session
}
```

### 分组规则

- 每个 session 默认独立对应一个任务（1:1 映射）
- 用户在某个任务上下文中"新建对话"时，新 session 的 `meta` 中携带 `task_id` 字段关联到父任务
- 按 `lastActive` 降序排列

### Meta Schema 约定

Session `meta` JSON 中用于任务分组的字段：

```json
{
  "title": "回复重要邮件",
  "agent_id": "default",
  "task_id": "parent_session_id_here"   // 可选，仅子 session 携带
}
```

- `task_id` 缺失或为空 → 该 session 自身就是一个独立任务
- `task_id` 有值 → 该 session 归入以 `task_id` 对应的 session 为首的任务组
- 后端 `create_session` handler 会原样保存 `meta` 中的所有字段（已验证），无需后端改动
- 前端加载 session 列表后，先按 `task_id` 分组，再按 `lastActive` 排序

### UI 交互

```
┌────────────────────────┐
│ + 新建任务    🔄 刷新   │
├────────────────────────┤
│ ▼ 回复重要邮件          │  ← 任务标题（可折叠）
│    ├ 💬 办公主助手 · 刚刚 │  ← session 1（选中高亮）
│    └ 💬 深度调研 · 5分钟前│  ← session 2
│                         │
│ ▶ 近期黄金价格PPT制作    │  ← 折叠状态
│ ▶ 这是 mock 回复        │
└────────────────────────┘
```

- 点击任务标题 → 展开/折叠 session 列表
- 点击 session → 加载该 session 消息到 ChatPanel
- 单 session 的任务不显示展开箭头，直接点击加载
- 「+ 新建任务」→ 用当前页面默认 agent 创建新 session
- 已展开任务内的 `+` → 在该任务下新建 session（可选 agent）

## 4. 文件区（LeftNav 文件 Tab）

### 布局

上下两个 panel，中间分隔线：

```
┌────────────────────────┐
│ ─── 我的文件 ─── [选择] │  ← 上半区
│  📁 项目文档             │
│    📄 Q1产品路线图.pdf   │
│    📄 技术架构设计.docx   │
│  📁 数据分析             │
│    📄 sales_data.xlsx    │
│                         │
│ ─────── 分隔线 ──────── │
│                         │
│ ─── Agent 工作区 ────── │  ← 下半区
│  📁 生成的内容           │
│    📄 市场分析报告.pdf   │
│  📁 调研资料             │
│    📄 行业趋势总结.docx  │
└────────────────────────┘
```

### 交互

1. **「选择」按钮**：用户输入**服务端文件系统路径**（非浏览器本地文件），前端通过文本输入框让用户指定路径（如 `/home/user/documents`），保存在 localStorage，通过 `GET /api/files` 列出该目录内容
2. **Agent 工作区**：展示 `workspace/` 目录下的文件（服务端路径）
3. **拖拽**：使用 `react-dnd`，文件可拖到 ChatPanel 输入区
4. **拖入效果**：输入区高亮 + 文件 Badge 标签（可移除），发送时附带 `context_files`
5. **按需加载**：只返回一层目录，展开子文件夹时再请求

### 数据源

后端新增 `GET /api/files` API（见 §7）。

## 5. ChatPanel 统一组件

### 组件接口

```typescript
interface ChatPanelProps {
  defaultAgentId: string;
  sessionId?: string;
  taskId?: string;
  onSessionCreated?: (session: SessionItem) => void;
  onTitleUpdated?: (sessionId: string, title: string) => void;
}
```

### 内部结构

```
ChatPanel
├── MessageList（消息列表，滚动区域）
│   ├── MessageBubble (user) — 右对齐，主色背景
│   ├── MessageBubble (assistant) — 左对齐，Bot 图标
│   ├── ToolCallCard — 可折叠的工具调用卡片
│   ├── SystemMessage — 居中，淡色背景
│   └── TypingIndicator — 三点动画
│
├── ChatInput（底部输入区）
│   ├── AgentSelector（agent 下拉选择）
│   ├── ConnectionStatus（WebSocket 状态）
│   ├── DroppableTextarea（支持文件拖入）
│   │   └── 拖入文件显示为 Badge 标签
│   ├── SendButton
│   └── SlashCommandMenu（/skill 自动补全，复用现有 useSlashCommand hook）
│
├── InteractionDialog（交互对话框，复用现有 QuestionDialog.tsx）
│   ├── 工具确认对话框（tool_confirmation_requested）
│   ├── 用户问题对话框（user_question_asked）
│   ├── 交互队列管理（多个确认/问题排队处理）
│   └── 超时处理
│
└── WebSocket 事件处理（通过 useChatSession hook）
```

### 从现有代码提取

从 `chat/page.tsx`（~500 行）提取为：
- `ChatPanel.tsx` — 主组件
- `MessageBubble.tsx` — 消息气泡（独立文件）
- `ChatInput.tsx` — 输入区组件
- `useChatSession.ts` — 统一 session 管理 hook

### 页面使用

每个页面变为薄包装层：

```tsx
// /research/page.tsx
export default function ResearchPage() {
  return (
    <WorkbenchShell>
      <ChatPanel defaultAgentId="deep_research" />
    </WorkbenchShell>
  );
}
```

## 6. 状态管理与数据流

### WebSocket 连接策略

单连接共享：通过 React Context Provider 在 `app/layout.tsx` 层管理唯一 WebSocket 连接。

```
app/layout.tsx
└── ChatSessionProvider（Context Provider，管理 WebSocket 单例）
    └── DashboardLayout
        └── WorkbenchShell
            ├── LeftNav（通过 context 读取任务列表）
            ├── ChatPanel（通过 context 收发消息）
            └── RightContext（通过 context 订阅执行步骤）
```

将 WebSocket 连接放在 layout 级的 Context Provider 中，确保页面路由切换时（Next.js unmount/remount page 组件）连接不会断开。`ChatSessionProvider` 包含：
- WebSocket 连接管理（连接、重连、心跳）
- 当前 sessionId 状态
- 消息列表和 typing 状态
- 任务列表
- 步骤和进度数据

### DndProvider 位置

`react-dnd` 的 `<DndProvider backend={HTML5Backend}>` 需要包裹拖拽源（LeftNav 文件树）和放置目标（ChatInput）的共同祖先。放在 `WorkbenchShell` 组件中：

```tsx
// WorkbenchShell.tsx
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';

export function WorkbenchShell({ children }: Props) {
  return (
    <DndProvider backend={HTML5Backend}>
      <div className="flex flex-1 overflow-hidden">
        <LeftNav />
        <div className="flex-1 flex flex-col">{children}</div>
        <RightContext />
      </div>
    </DndProvider>
  );
}
```

### 统一 Hook

```typescript
// hooks/useChatSession.ts
interface UseChatSessionReturn {
  // 连接
  wsConnected: boolean;

  // Session 管理
  currentSessionId: string | null;
  switchSession: (sessionId: string) => void;
  createSession: (agentId: string, taskId?: string) => void;

  // 消息
  messages: ChatMessage[];
  isTyping: boolean;
  sendMessage: (content: string, contextFiles?: ContextFileRef[]) => void;

  // 任务列表
  taskGroups: TaskGroup[];
  refreshTaskGroups: () => void;

  // 执行步骤
  steps: StepItem[];
  taskProgress: TaskProgressItem[];

  // 交互对话框（来自现有 chat/page.tsx 的 interaction 逻辑）
  pendingInteraction: PendingInteraction | null;
  interactionSubmitting: boolean;
  submitQuestionAnswer: (answer: string | string[]) => void;
  cancelQuestion: () => void;
  submitConfirmation: (approved: boolean) => void;

  // 通知
  notifications: NotificationItem[];
}
```

### 类型定义

```typescript
// 文件拖拽时传递的引用（发送时转换为 context_files 字段）
interface ContextFileRef {
  name: string;
  path: string;  // 服务端文件系统路径
}

// 发送 user_input 时的 context_files payload 格式
// 后端 websocket_channel.py 将其作为 list[str] 传给 gateway.send_user_input()
// context_builder.py 再将路径转换为 ContextFile(name, content) 读取文件内容
// 因此前端只需发送路径字符串数组：
// payload.context_files = ["/path/to/file1", "/path/to/file2"]
```

### 替代 useWorkbenchSession

现有 `useWorkbenchSession.ts` 中的 `TaskState`（empty/processing/completed）、`CurrentTask`、`result`、`reset` 等概念不再需要。这些是为了 `MainStage` 的状态机设计的，而 `MainStage` 将被 `ChatPanel` 替代。ChatPanel 通过消息列表自然展示对话状态，不需要显式的 task 状态机。

`useWorkbenchSession.ts` 将被删除，其中的 WebSocket 管理和事件处理逻辑合并入 `useChatSession.ts`。

### 页面切换行为

- 切换页面 → WebSocket 不断开，保持当前 session
- 从 LeftNav 点击任何 session → 加载该 session 消息
- 在新页面发送消息 → 用该页面 `defaultAgentId` 创建新 session

### 文件拖拽数据流

```
LeftNav 文件 Tab → react-dnd type="FILE" item={name, path, type}
    ↓
ChatInput (DroppableTextarea) → useDrop 接收 → Badge 标签显示文件名
    ↓
发送 → WebSocket user_input:
  {
    type: "user_input",
    session_id: "...",
    payload: {
      content: "分析这个文件",
      context_files: ["/server/path/to/file.xlsx"]  // 字符串数组
    }
  }
    ↓
后端 websocket_channel.py → gateway.send_user_input(context_files=[...])
    ↓
context_builder.py → 将路径转为 ContextFile(name, content) 读取文件内容注入 prompt
```

后端已支持此流程，无需改动。

### 错误处理

- **文件列表 API 失败**（403/404）→ 文件区显示错误提示 + 重试按钮
- **WebSocket 断开**→ ChatInput 禁用 + 状态指示器显示红色 + 自动重连（复用现有逻辑）
- **Session 列表加载失败**→ 任务 Tab 显示错误提示 + 刷新按钮

## 7. 后端改动：文件列表 API

### 端点

```
GET /api/files?path=<dir_path>
```

### 响应

```json
{
  "path": "/home/user/documents",
  "items": [
    { "name": "项目文档", "type": "folder", "path": "/home/user/documents/项目文档" },
    { "name": "会议记录.txt", "type": "file", "path": "/home/user/documents/会议记录.txt", "size": 2048 }
  ]
}
```

### 安全

- 利用 `agentos/platform/security/` 路径策略
- `workspace/` 目录始终允许
- 对 path 做 `os.path.realpath()` 防止路径遍历
- 路径不存在 → 404，无权限 → 403，不是目录 → 400

### 实现位置

新建 `agentos/interfaces/http/files.py` 作为独立路由模块（与现有 `workspace.py`、`agents.py` 等同级）。

注意：已有 `GET /api/workspace/files` 端点（在 `workspace.py` 中，仅列出 workspace 下的 `.md` 文件）。新 API 功能不同：
- `/api/workspace/files` → 只列 workspace 下的 markdown 文件（保留不动）
- `/api/files` → 通用目录浏览，支持任意允许的路径，返回所有文件类型

## 8. 改动清单

| 层面 | 改动 |
|------|------|
| **新增组件** | `ChatPanel.tsx`, `ChatInput.tsx`, `MessageBubble.tsx`(独立文件), `useChatSession.ts`, `ChatSessionProvider`(Context) |
| **重构组件** | `LeftNav.tsx`（任务分组 + 文件区 Tab + react-dnd）, `WorkbenchShell.tsx`（DndProvider + 简化布局） |
| **简化页面** | `/`, `/chat`, `/research`, `/ppt`, `/automation` → 薄页面 + ChatPanel |
| **删除/替代** | `useWorkbenchSession.ts`（合并入 useChatSession）, `MainStage.tsx`（主页空状态迁移为 TaskTemplates，其余被 ChatPanel 替代）, `BottomInput.tsx`（被 ChatInput 替代）, chat/page.tsx 内联逻辑 |
| **保留复用** | `QuestionDialog.tsx`（InteractionDialog，迁移到 ChatPanel 内使用）, `SlashCommandMenu.tsx` + `useSlashCommand`（迁移到 ChatInput 内使用） |
| **后端新增** | `agentos/interfaces/http/files.py`：`GET /api/files` 文件列表 API |
| **依赖新增** | `react-dnd`, `react-dnd-html5-backend` |

## 9. 不改动的部分

- DashboardLayout 顶部导航结构
- DashboardNav 导航项
- RightContext 组件（保持现有设计）
- WebSocket 协议和后端事件格式
- Session API（`GET /api/sessions`、WebSocket create/load）
- 后端 AgentRuntime / LLMRuntime / ToolRuntime
