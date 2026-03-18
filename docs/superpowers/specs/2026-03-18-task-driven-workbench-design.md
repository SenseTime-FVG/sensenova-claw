# 任务驱动工作台设计

## 概述

将 Figma 设计文档（`docs_raw/ui/任务驱动工作台设计/`）中的任务驱动工作台整合到现有 Next.js 14 前端中，作为主页面。保持现有 DashboardLayout 风格不变，扩展导航结构，新增工作台、深度研究、PPT、自动化四个页面，并将工作台主页对接后端 WebSocket 事件流。

## 架构方案

**方案 A：扩展现有 DashboardLayout**（已选定）

- 扩展 `DashboardNav` 导航项，新增工作台相关页面入口，现有管理页面收入"管理"下拉菜单
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
│(w-56)│                                  │  · Thought Trace │
│      │                                  │  · Sources       │
│ Tab: │                                  │  · 参数          │
│·工作台│                                 │  · 多步任务进度   │
│·文件区│                                 │                  │
│      │        BottomInput               │                  │
│      │  [快捷意图按钮]                   │                  │
│      │  [输入框..................  发送]  │                  │
└──────┴──────────────────────────────────┴──────────────────┘
```

- LeftNav、RightContext、BottomInput 由 `WorkbenchShell` 组合，仅在工作台相关页面（`/`、`/research`、`/ppt`、`/automation`）中使用
- `/chat` 保留现有布局（左侧会话列表 + 右侧聊天区）
- 管理页面保持原样

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
- "管理"下拉菜单：Dashboard `/agents` | Sessions `/sessions` | Gateway `/gateway` | Tools `/tools` | Skills `/skills`

## 组件设计

### 新增组件

#### WorkbenchShell

工作台页面的布局壳，组合 LeftNav + 内容区 + RightContext + BottomInput。

```typescript
interface WorkbenchShellProps {
  children: React.ReactNode;
  // RightContext 数据
  thoughtTrace?: { steps: string[] };
  sources?: { name: string; type: "file" | "web"; url?: string }[];
  parameters?: { label: string; value: string }[];
  taskProgress?: { task: string; step: number; total: number; status: "running" | "completed" }[];
  isRightCollapsed?: boolean;
  // BottomInput
  onSubmit?: (message: string) => void;
}
```

#### LeftNav

左侧导航栏，两个 Tab：

1. **工作台 Tab**：页面导航项（工作台/Chat/深度研究/PPT/自动化），使用 Next.js `Link` + `usePathname()` 高亮
2. **文件区 Tab**：文件树展示，调用 `/api/workspace/files` API 获取文件列表，点击选择文件（不使用 react-dnd）

#### RightContext

右侧可折叠面板，展示：

- **Thought Trace**：思维链步骤列表
- **Sources**：引用来源（文件/网页）
- **参数**：键值对参数展示
- **多步任务进度**：任务名 + 步骤进度 + 状态指示

默认收起，通过 header 点击展开/收起。

#### BottomInput

底部输入区：

- 快捷意图按钮行（写邮件/安排会议/总结文档/生成周报）
- 文本输入框 + 发送按钮
- Enter 发送，Shift+Enter 换行

#### MainStage

工作台主内容区，四种状态：

1. **empty**：引导页，4 个任务模板卡片 + 最近任务列表（从 `/api/sessions` 获取）
2. **processing**：TaskSummaryCard + 执行步骤列表（动画进度指示）
3. **completed**：TaskSummaryCard + ResultCard
4. **approval**：审批卡片（橙色警告样式，列出待执行操作，批准/取消按钮）

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

复用现有 Chat 页面的 WebSocket 连接模式（页面内创建实例，页面卸载断开）。

事件映射：

| 后端事件 | UI 响应 |
|----------|---------|
| `agent_thinking` | MainStage state → "processing" |
| `tool_execution` | RightContext.taskProgress 追加步骤（status: running） |
| `tool_result` | RightContext.taskProgress 更新步骤（status: completed） |
| `llm_result` | RightContext.thoughtTrace 追加思维步骤 |
| `turn_completed` | MainStage state → "completed"，final_response → ResultCard |
| `error` | 错误提示 |

### 工作台任务发送流程

```
用户在 BottomInput 输入任务描述
  → WebSocket send: create_session + user_input
  → MainStage 切到 processing
  → 后端事件流实时更新 RightContext
  → turn_completed 时切到 completed，展示 ResultCard
```

### 其他页面数据

ResearchPage、PPTPage、AutomationPage 使用硬编码示例数据，不对接后端。

## 文件变更清单

### 修改

| 文件 | 变更 |
|------|------|
| `components/layout/DashboardNav.tsx` | 导航项更新为新页面 + "管理"下拉菜单 |
| `app/page.tsx` | 从重定向改为渲染 WorkbenchPage |

### 新增

| 文件 | 说明 |
|------|------|
| `components/workbench/WorkbenchShell.tsx` | 工作台布局壳 |
| `components/workbench/LeftNav.tsx` | 左侧导航（Tab 切换 + 文件区） |
| `components/workbench/RightContext.tsx` | 右侧可折叠面板 |
| `components/workbench/BottomInput.tsx` | 底部输入区 |
| `components/workbench/MainStage.tsx` | 工作台主内容（4 种状态） |
| `components/workbench/TaskSummaryCard.tsx` | 任务摘要卡片 |
| `components/workbench/ResultCard.tsx` | 结果展示卡片 |
| `app/research/page.tsx` | 深度研究页面 |
| `app/ppt/page.tsx` | PPT 页面 |
| `app/automation/page.tsx` | 自动化页面 |

### 不修改

- `DashboardLayout.tsx`：结构不变
- `app/chat/page.tsx`：逻辑不变
- 所有管理页面：不动
- contexts/、lib/、types/：不新增不修改

### 依赖

无新 npm 依赖。不使用 react-dnd。所有 UI 复用现有 shadcn/ui 组件。

## 风格规范

- 统一使用现有 shadcn/ui 主题变量：`bg-background`、`text-foreground`、`bg-muted`、`border-border`、`bg-card` 等
- 延续 DashboardLayout 的设计语言：简洁顶部导航、无多余装饰、紧凑间距
- 组件使用 `cn()` 工具函数组合 Tailwind 类名
- 图标使用 lucide-react
