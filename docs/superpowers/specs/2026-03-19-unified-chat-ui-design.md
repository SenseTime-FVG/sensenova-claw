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

## 2. 整体布局

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

### 页面默认 Agent 映射

| 页面 | 路由 | 默认 Agent |
|------|------|-----------|
| 主页（工作台） | `/` | 办公主助手 (`default`) |
| Chat | `/chat` | 办公主助手 (`default`) |
| 深度研究 | `/research` | 深度调研 (`deep_research`) |
| PPT | `/ppt` | PPT生成助手 (`ppt_generator`) |
| 自动化 | `/automation` | 办公主助手 (`default`) |

## 3. 任务分组导航（LeftNav 任务 Tab）

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
- 用户在某个任务上下文中"新建对话"时，新 session 的 `meta` 中携带 `taskId` 字段关联到父任务
- 按 `lastActive` 降序排列

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

1. **「选择」按钮**：用户指定本地文件夹路径，保存在 localStorage
2. **Agent 工作区**：展示 `workspace/` 目录下的文件
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
│   └── SlashCommandMenu（/skill 自动补全）
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

单连接共享：在 `WorkbenchShell` 层管理唯一 WebSocket 连接，所有页面共享。

```
WorkbenchShell
├── WebSocket 单例连接
├── 当前 sessionId 状态
├── LeftNav（读取任务列表，切换 sessionId）
├── ChatPanel（使用当前 sessionId 收发消息）
└── RightContext（订阅当前 session 的执行步骤）
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
  sendMessage: (content: string, attachments?: FileAttachment[]) => void;

  // 任务列表
  taskGroups: TaskGroup[];
  refreshTaskGroups: () => void;

  // 执行步骤
  steps: StepItem[];
  taskProgress: TaskProgressItem[];
}
```

替代现有的 `useWorkbenchSession.ts`（合并其逻辑）。

### 页面切换行为

- 切换页面 → WebSocket 不断开，保持当前 session
- 从 LeftNav 点击任何 session → 加载该 session 消息
- 在新页面发送消息 → 用该页面 `defaultAgentId` 创建新 session

### 文件拖拽数据流

```
LeftNav 文件 Tab → react-dnd type="FILE" item={name,path,type}
    ↓
ChatInput (DroppableTextarea) → useDrop 接收 → Badge 标签
    ↓
发送 → WebSocket user_input payload.context_files = ["/path/to/file"]
```

现有后端 `user_input` 已支持 `context_files` 字段，无需后端改动。

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

`agentos/interfaces/http/routes.py` 新增路由。

## 8. 改动清单

| 层面 | 改动 |
|------|------|
| **新增组件** | `ChatPanel.tsx`, `ChatInput.tsx`, `MessageBubble.tsx`(独立文件), `useChatSession.ts` |
| **重构组件** | `LeftNav.tsx`（任务分组 + 文件区 Tab + react-dnd）, `WorkbenchShell.tsx`（WebSocket 提升） |
| **简化页面** | `/`, `/chat`, `/research`, `/ppt`, `/automation` → 薄页面 + ChatPanel |
| **删除/替代** | `useWorkbenchSession.ts`（合并入 useChatSession）, `MainStage.tsx`（被 ChatPanel 替代）, `BottomInput.tsx`（被 ChatInput 替代）, chat/page.tsx 内联逻辑 |
| **后端新增** | `GET /api/files` 文件列表 API |
| **依赖新增** | `react-dnd`, `react-dnd-html5-backend` |

## 9. 不改动的部分

- DashboardLayout 顶部导航结构
- DashboardNav 导航项
- RightContext 组件（保持现有设计）
- WebSocket 协议和后端事件格式
- Session API（`GET /api/sessions`、WebSocket create/load）
- 后端 AgentRuntime / LLMRuntime / ToolRuntime
