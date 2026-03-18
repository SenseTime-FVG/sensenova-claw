# 任务驱动工作台设计

## 概述

将 Figma 设计文档（`docs_raw/ui/任务驱动工作台设计/`）中的任务驱动工作台整合到现有 Next.js 14 前端中，作为主页面。保持现有 DashboardLayout 风格不变，扩展导航结构，新增工作台、深度研究、PPT、自动化四个页面，并将工作台主页对接后端 WebSocket 事件流。

## 架构方案

**方案 A：扩展现有 DashboardLayout**（已选定）

- 扩展 `DashboardNav` 导航项，新增工作台相关页面入口，现有管理页面收入"管理"下拉菜单（使用现有 `components/ui/dropdown-menu.tsx`）
- 工作台页面在页面内部使用 `WorkbenchShell` 组件（LeftNav + 内容区 + RightContext + BottomInput）
- 现有管理页面（agents/sessions/gateway/tools/skills）保持原样
- 所有页面共享同一 `DashboardLayout` 顶部导航栏

## 布局结构

```
┌────────────────────────────────────────────────────────────┐
│  DashboardLayout TopBar (h-16, border-b)                   │
│  [AO AgentOS] [工作台 Chat 深度研究 PPT 自动化 | 管理▾] [搜索] [👤] │
├──────┬──────────────────────────────────┬──────────────────┤
│ Left │         MainContent              │  RightContext    │
│ Nav  │         (各页面内容)              │  (可折叠, w-80)  │
│(w-56)│                                  │  · 执行步骤      │
│      │                                  │  · Sources       │
│ Tab: │                                  │  · 参数          │
│·任务 │                                  │  · 多步任务进度   │
│·文件区│                                 │                  │
│      │        BottomInput               │                  │
│      │  [快捷意图按钮]                   │                  │
│      │  [输入框..................  发送]  │                  │
└──────┴──────────────────────────────────┴──────────────────┘
```

- LeftNav、RightContext、BottomInput 由 `WorkbenchShell` 组合，仅在工作台相关页面（`/`、`/research`、`/ppt`、`/automation`）中使用
- `/chat` 保留现有布局（左侧会话列表 + 右侧聊天区）
- 管理页面保持原样
- `DashboardLayout` 的内容区（`flex-1 overflow-auto`）在工作台页面中需要 `overflow-hidden` 以避免双滚动条，由 `WorkbenchShell` 内部处理

## 路由

### 新增路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | WorkbenchPage | 任务驱动工作台主页（不再重定向到 /chat） |
| `/research` | ResearchPage | 深度研究列表 |
| `/ppt` | PPTPage | PPT 管理 |
| `/automation` | AutomationPage | 自动化任务管理 |

### 现有路由（保留不变）

| 路径 | 说明 |
|------|------|
| `/chat` | 实时对话（保留全部 WebSocket 逻辑） |
| `/agents`, `/agents/[id]` | Agent 管理 |
| `/sessions`, `/sessions/[id]` | 会话管理 |
| `/gateway` | Gateway 统计 |
| `/tools` | 工具管理 |
| `/skills` | Skills 管理 |
| `/login` | 登录页 |

### 导航结构

`DashboardNav` 更新为：

- 主导航项：工作台 `/` | Chat `/chat` | 深度研究 `/research` | PPT `/ppt` | 自动化 `/automation`
- "管理"下拉菜单（使用现有 `dropdown-menu.tsx` 组件）：Dashboard `/agents` | Sessions `/sessions` | Gateway `/gateway` | Tools `/tools` | Skills `/skills`

## 组件设计

### 新增组件

#### WorkbenchShell

工作台页面的布局壳，组合 LeftNav + 内容区 + RightContext + BottomInput。

```typescript
interface WorkbenchShellProps {
  children: React.ReactNode;
  // RightContext 数据
  steps?: { label: string; status: "done" | "running" | "pending" }[];
  sources?: { name: string; type: "file" | "web"; url?: string }[];
  parameters?: { label: string; value: string }[];
  taskProgress?: { task: string; step: number; total: number; status: "running" | "completed" }[];
  isRightCollapsed?: boolean;  // 默认 true，收到 agent_thinking 时自动展开
  // BottomInput
  onSubmit?: (message: string) => void;
}
```

#### LeftNav

左侧导航栏，两个 Tab：

1. **任务 Tab**：当前任务状态 + 最近任务历史列表（从 `/api/sessions` 获取，使用 `meta.title` 作为任务标题），点击历史任务跳转到 `/chat` 并加载对应会话
2. **文件区 Tab**：使用硬编码 mock 文件树数据展示（后续对接文件 API），点击选择文件

注意：页面级导航（工作台/Chat/深度研究/PPT/自动化）已由顶部 `DashboardNav` 提供，LeftNav 不重复这些导航项。

#### RightContext

右侧可折叠面板，展示：

- **执行步骤**：当前任务的执行步骤列表（从 `tool_execution` / `tool_result` 事件构建，每个工具调用作为一个步骤）
- **Sources**：引用来源（文件/网页）
- **参数**：键值对参数展示
- **多步任务进度**：任务名 + 步骤进度 + 状态指示

**展开逻辑**：
- 默认收起
- 收到 `agent_thinking` 事件时自动展开
- 用户可通过点击 header 手动切换展开/收起

#### BottomInput

底部输入区：

- 快捷意图按钮行（写邮件/安排会议/总结文档/生成周报）
- 文本输入框（使用原生 `<textarea>`，与 Chat 页面一致）+ 发送按钮
- Enter 发送，Shift+Enter 换行
- WebSocket 断开时禁用输入，显示连接状态

#### MainStage

工作台主内容区，四种状态：

1. **empty**：引导页，4 个任务模板卡片 + 最近任务列表
2. **processing**：TaskSummaryCard + 执行步骤列表（动画进度指示）
3. **completed**：TaskSummaryCard + ResultCard
4. **approval**：审批卡片（纯 UI 展示，暂不对接后端审批机制。后端 `TOOL_CONFIRMATION_REQUESTED` 事件目前未通过 WebSocket 转发，待后续版本实现）

**最近任务列表**：
- 数据来源：`/api/sessions` 返回的 `SessionItem[]`
- 任务标题：从 `session.meta` JSON 中提取 `title` 字段（与 Chat 页面 `getTitle()` 逻辑一致）
- 点击行为：跳转到 `/chat?session=${session_id}`，在 Chat 页面加载对应会话

#### TaskSummaryCard

```typescript
interface TaskSummaryCardProps {
  title: string;
  goal: string;
  stage: string;
  status: "idle" | "running" | "completed" | "error";
}
```

#### ResultCard

```typescript
interface ResultCardProps {
  summary: string;
  preview?: React.ReactNode;
  sources?: string[];
  nextActions?: { label: string; primary?: boolean; onClick?: () => void }[];
}
```

## 数据流

### WorkbenchPage WebSocket 对接

新建 `hooks/useWorkbenchSession.ts` 自定义 hook，封装 WebSocket 连接和事件处理逻辑。该 hook 从现有 Chat 页面的 WebSocket 代码中提取核心模式（连接管理、重连、认证），但将事件映射到任务驱动 UI 状态。

```typescript
// hooks/useWorkbenchSession.ts
interface UseWorkbenchSessionReturn {
  // 连接状态
  wsConnected: boolean;
  // 任务状态
  taskState: "empty" | "processing" | "completed";
  currentTask: { title: string; goal: string; stage: string; status: string } | null;
  // RightContext 数据
  steps: { label: string; status: "done" | "running" | "pending" }[];
  taskProgress: { task: string; step: number; total: number; status: "running" | "completed" }[];
  // 结果
  result: { content: string } | null;
  // 操作
  sendTask: (message: string) => void;
  reset: () => void;
}
```

#### 事件映射

| WebSocket 事件 | UI 响应 |
|----------|---------|
| `agent_thinking` | taskState → "processing"，RightContext 自动展开 |
| `tool_execution` | steps 追加新步骤（status: "running"），taskProgress 追加条目 |
| `tool_result` | steps 中对应步骤 status → "done"，taskProgress 更新 |
| `turn_completed` | taskState → "completed"，payload.final_response → ResultCard |
| `error` | 错误提示，taskState 保持不变 |

注意：后端 `LLM_CALL_COMPLETED` 事件目前**不通过 WebSocket 转发**（`websocket_channel.py` 中映射返回 `None`），因此无法获取中间 LLM 推理内容。执行步骤列表仅基于 `tool_execution` / `tool_result` 事件构建。

### 工作台任务发送流程

```
用户在 BottomInput 输入任务描述
  → useWorkbenchSession.sendTask(message)
  → WebSocket send: create_session + user_input
  → taskState 切到 "processing"
  → tool_execution/tool_result 事件实时更新 RightContext steps
  → turn_completed 时切到 "completed"，展示 ResultCard
```

### 其他页面数据

ResearchPage、PPTPage、AutomationPage 使用硬编码示例数据，不对接后端。

## 文件变更清单

### 修改

| 文件 | 变更 |
|------|------|
| `components/layout/DashboardNav.tsx` | 导航项更新为新页面 + "管理"下拉菜单（使用现有 `dropdown-menu.tsx`） |
| `app/page.tsx` | 从重定向改为渲染 WorkbenchPage |

### 新增

| 文件 | 说明 |
|------|------|
| `hooks/useWorkbenchSession.ts` | 工作台 WebSocket 会话管理 hook |
| `components/workbench/WorkbenchShell.tsx` | 工作台布局壳 |
| `components/workbench/LeftNav.tsx` | 左侧导航（任务 Tab + 文件区 Tab） |
| `components/workbench/RightContext.tsx` | 右侧可折叠面板 |
| `components/workbench/BottomInput.tsx` | 底部输入区 |
| `components/workbench/MainStage.tsx` | 工作台主内容（4 种状态） |
| `components/workbench/TaskSummaryCard.tsx` | 任务摘要卡片 |
| `components/workbench/ResultCard.tsx` | 结果展示卡片 |
| `app/research/page.tsx` | 深度研究页面 |
| `app/ppt/page.tsx` | PPT 页面 |
| `app/automation/page.tsx` | 自动化页面 |

### 不修改

- `DashboardLayout.tsx`：结构不变（DashboardNav 更新后自动生效）
- `app/chat/page.tsx`：逻辑不变（导航栏更新自动生效）
- 所有管理页面：不动
- `contexts/`：不新增不修改（新 hook 替代 context 扩展）
- `types/`：不新增（WebSocket 消息类型在 hook 内部定义）

### 依赖

无新 npm 依赖。不使用 react-dnd。UI 复用现有 shadcn/ui 组件（包括 `dropdown-menu.tsx`）。BottomInput 使用原生 `<textarea>`（与 Chat 页面一致）。

## 风格规范

- 统一使用现有 shadcn/ui 主题变量：`bg-background`、`text-foreground`、`bg-muted`、`border-border`、`bg-card` 等
- 延续 DashboardLayout 的设计语言：简洁顶部导航、无多余装饰、紧凑间距
- 组件使用 `cn()` 工具函数组合 Tailwind 类名
- 图标使用 lucide-react

## 已知限制（本期不实现）

- **LLM 推理过程展示**：后端 `LLM_CALL_COMPLETED` 未通过 WebSocket 转发，无法实时展示思维链。RightContext 的步骤列表仅基于工具调用事件。
- **审批流程**：后端 `TOOL_CONFIRMATION_REQUESTED` 未通过 WebSocket 转发，approval 状态为纯 UI 展示。
- **文件区真实数据**：现有 workspace API 仅支持 `.md` 文件，文件区使用 mock 数据。
- **拖拽交互**：不引入 react-dnd，文件选择通过点击完成。
