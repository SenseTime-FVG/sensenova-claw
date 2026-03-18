# 任务驱动工作台 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Figma 设计文档中的任务驱动工作台整合到现有 Next.js 14 前端中，作为主页面，对接 WebSocket 事件流。

**Architecture:** 扩展现有 DashboardLayout 导航栏，新增 WorkbenchShell 布局组件（LeftNav + 内容区 + RightContext + BottomInput），新建 useWorkbenchSession hook 封装 WebSocket 连接和任务状态管理。工作台主页对接后端事件流，Research/PPT/Automation 页面使用硬编码数据。

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, WebSocket

**Spec:** `docs/superpowers/specs/2026-03-18-task-driven-workbench-design.md`

---

## File Structure

### Modified Files

| File | Responsibility |
|------|---------------|
| `agentos/app/web/components/layout/DashboardNav.tsx` | 导航项更新 + "管理"下拉菜单 |
| `agentos/app/web/app/page.tsx` | 渲染工作台主页（不再重定向） |

### New Files

| File | Responsibility |
|------|---------------|
| `agentos/app/web/hooks/useWorkbenchSession.ts` | WebSocket 连接管理 + 任务状态机 |
| `agentos/app/web/components/workbench/BottomInput.tsx` | 底部输入区（快捷意图 + 文本输入） |
| `agentos/app/web/components/workbench/RightContext.tsx` | 右侧可折叠面板（步骤/来源/参数/进度） |
| `agentos/app/web/components/workbench/LeftNav.tsx` | 左侧导航（任务历史 + 文件区） |
| `agentos/app/web/components/workbench/WorkbenchShell.tsx` | 布局壳（组合 LeftNav + content + RightContext + BottomInput） |
| `agentos/app/web/components/workbench/TaskSummaryCard.tsx` | 任务摘要卡片 |
| `agentos/app/web/components/workbench/ResultCard.tsx` | 结果展示卡片 |
| `agentos/app/web/components/workbench/MainStage.tsx` | 工作台主内容（4 种状态） |
| `agentos/app/web/app/research/page.tsx` | 深度研究页面 |
| `agentos/app/web/app/ppt/page.tsx` | PPT 管理页面 |
| `agentos/app/web/app/automation/page.tsx` | 自动化任务页面 |

---

## Chunk 1: 导航栏更新 + 基础布局组件

### Task 1: 更新 DashboardNav 导航栏

**Files:**
- Modify: `agentos/app/web/components/layout/DashboardNav.tsx`

- [ ] **Step 1: 替换 DashboardNav 内容**

将现有导航项替换为工作台页面导航 + "管理"下拉菜单：

```tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Settings } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const mainNavItems = [
  { path: '/', label: '工作台', exact: true },
  { path: '/chat', label: 'Chat' },
  { path: '/research', label: '深度研究' },
  { path: '/ppt', label: 'PPT' },
  { path: '/automation', label: '自动化' },
];

const adminNavItems = [
  { path: '/agents', label: 'Dashboard' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/gateway', label: 'Gateway' },
  { path: '/tools', label: 'Tools' },
  { path: '/skills', label: 'Skills' },
];

export function DashboardNav({
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const pathname = usePathname();

  const isActive = (item: { path: string; exact?: boolean }) => {
    if (item.exact) return pathname === item.path;
    return pathname?.startsWith(item.path);
  };

  const isAdminActive = adminNavItems.some((item) =>
    pathname?.startsWith(item.path)
  );

  return (
    <nav
      className={cn('flex items-center space-x-4 lg:space-x-6', className)}
      {...props}
    >
      {mainNavItems.map((item) => (
        <Link
          key={item.path}
          href={item.path}
          className={cn(
            'text-sm font-medium transition-colors hover:text-primary',
            isActive(item) ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {item.label}
        </Link>
      ))}

      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            'text-sm font-medium transition-colors hover:text-primary flex items-center gap-1',
            isAdminActive ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          <Settings className="h-3.5 w-3.5" />
          管理
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {adminNavItems.map((item) => (
            <DropdownMenuItem key={item.path} asChild>
              <Link
                href={item.path}
                className={cn(
                  pathname?.startsWith(item.path) && 'font-medium'
                )}
              >
                {item.label}
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </nav>
  );
}
```

- [ ] **Step 2: 验证导航栏渲染**

Run: `cd agentos/app/web && npx next build 2>&1 | head -20`
Expected: 构建成功，无 TypeScript 错误

- [ ] **Step 3: Commit**

```bash
git add agentos/app/web/components/layout/DashboardNav.tsx
git commit -m "feat(web): 更新导航栏，新增工作台页面入口和管理下拉菜单"
```

---

### Task 2: 创建 BottomInput 组件

**Files:**
- Create: `agentos/app/web/components/workbench/BottomInput.tsx`

- [ ] **Step 1: 创建 BottomInput**

```tsx
'use client';

import { useState } from 'react';
import { Send, Mail, Calendar, FileText, BarChart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface BottomInputProps {
  onSubmit?: (message: string) => void;
  disabled?: boolean;
  connected?: boolean;
}

const quickActions = [
  { id: 'email', label: '写邮件', icon: Mail },
  { id: 'meeting', label: '安排会议', icon: Calendar },
  { id: 'summary', label: '总结文档', icon: FileText },
  { id: 'report', label: '生成周报', icon: BarChart },
];

export function BottomInput({ onSubmit, disabled, connected = true }: BottomInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = () => {
    const content = message.trim();
    if (!content || disabled) return;
    onSubmit?.(content);
    setMessage('');
  };

  const handleQuickAction = (label: string) => {
    if (disabled) return;
    onSubmit?.(label);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border bg-card/50 backdrop-blur-sm shrink-0">
      {/* 快捷意图 */}
      <div className="px-4 pt-3 pb-2 border-b border-border">
        <div className="flex gap-2">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Button
                key={action.id}
                variant="outline"
                size="sm"
                onClick={() => handleQuickAction(action.label)}
                disabled={disabled}
                className="gap-1.5 text-xs"
              >
                <Icon className="w-3.5 h-3.5" />
                {action.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* 输入区 */}
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={cn(
            'flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full border',
            connected
              ? 'text-muted-foreground bg-muted/50'
              : 'text-destructive bg-destructive/10 border-destructive/20'
          )}>
            <span className={cn(
              'w-2 h-2 rounded-full',
              connected ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'
            )} />
            {connected ? '已连接' : '未连接'}
          </span>
        </div>

        <div className="flex items-end gap-3 bg-background border border-border/80 rounded-2xl shadow-sm focus-within:ring-2 focus-within:ring-primary/10 focus-within:border-primary transition-all p-3">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={connected ? '描述你需要完成的任务...' : '等待连接...'}
            disabled={disabled || !connected}
            rows={1}
            className="flex-1 bg-transparent border-none px-3 py-2 text-sm text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed min-h-[40px] max-h-[120px]"
          />
          <Button
            onClick={handleSubmit}
            size="icon"
            disabled={!message.trim() || disabled || !connected}
            className="shrink-0 w-10 h-10 rounded-xl"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground/70 mt-2 px-3">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/components/workbench/BottomInput.tsx
git commit -m "feat(web): 创建 BottomInput 底部输入组件"
```

---

### Task 3: 创建 RightContext 组件

**Files:**
- Create: `agentos/app/web/components/workbench/RightContext.tsx`

- [ ] **Step 1: 创建 RightContext**

```tsx
'use client';

import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, FileText, Globe } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface Source {
  name: string;
  type: 'file' | 'web';
  url?: string;
}

interface Parameter {
  label: string;
  value: string;
}

interface TaskProgress {
  task: string;
  step: number;
  total: number;
  status: 'running' | 'completed';
}

interface RightContextProps {
  steps?: StepItem[];
  sources?: Source[];
  parameters?: Parameter[];
  taskProgress?: TaskProgress[];
  isCollapsed?: boolean;
}

export function RightContext({
  steps,
  sources,
  parameters,
  taskProgress,
  isCollapsed = true,
}: RightContextProps) {
  const [expanded, setExpanded] = useState(!isCollapsed);

  // 当 isCollapsed 从外部变化时同步
  useEffect(() => {
    if (!isCollapsed) setExpanded(true);
  }, [isCollapsed]);

  const hasContent = (steps && steps.length > 0) ||
    (sources && sources.length > 0) ||
    (parameters && parameters.length > 0) ||
    (taskProgress && taskProgress.length > 0);

  if (!hasContent && !expanded) return null;

  return (
    <aside className="w-80 border-l border-border bg-muted/20 flex flex-col overflow-y-auto shrink-0">
      <div className="p-4">
        {/* Header */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center justify-between w-full text-left mb-4"
        >
          <div>
            <h2 className="font-semibold text-foreground text-sm">AI 工作区</h2>
            <p className="text-xs text-muted-foreground">任务执行详情</p>
          </div>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
        </button>

        {expanded && (
          <div className="space-y-3">
            {/* 执行步骤 */}
            {steps && steps.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">执行步骤</h3>
                <div className="space-y-2">
                  {steps.map((step, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <div className={cn(
                        'w-2 h-2 rounded-full shrink-0',
                        step.status === 'done' && 'bg-green-500',
                        step.status === 'running' && 'bg-blue-500 animate-pulse',
                        step.status === 'pending' && 'bg-muted-foreground/30'
                      )} />
                      <span className={cn(
                        'text-sm',
                        step.status === 'running' && 'text-foreground font-medium',
                        step.status === 'done' && 'text-muted-foreground',
                        step.status === 'pending' && 'text-muted-foreground/50'
                      )}>
                        {step.label}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Sources */}
            {sources && sources.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">Sources</h3>
                <div className="space-y-2">
                  {sources.map((source, index) => (
                    <div key={index} className="flex items-start gap-2 text-sm">
                      {source.type === 'file' ? (
                        <FileText className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                      ) : (
                        <Globe className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                      )}
                      <span className="text-foreground/80 truncate">{source.name}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 参数 */}
            {parameters && parameters.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">参数</h3>
                <div className="text-sm space-y-1">
                  {parameters.map((param, index) => (
                    <div key={index} className="flex justify-between">
                      <span className="text-muted-foreground">{param.label}</span>
                      <span className="text-foreground font-medium">{param.value}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 多步任务进度 */}
            {taskProgress && taskProgress.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">任务进度</h3>
                <div className="space-y-3">
                  {taskProgress.map((task, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div className={cn(
                        'w-2.5 h-2.5 rounded-full shrink-0',
                        task.status === 'completed' ? 'bg-muted-foreground/40' : 'bg-green-500'
                      )} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground truncate">{task.task}</p>
                      </div>
                      <span className="text-xs text-amber-500 font-medium shrink-0">
                        {task.step}/{task.total}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/components/workbench/RightContext.tsx
git commit -m "feat(web): 创建 RightContext 右侧面板组件"
```

---

### Task 4: 创建 LeftNav 组件

**Files:**
- Create: `agentos/app/web/components/workbench/LeftNav.tsx`

- [ ] **Step 1: 创建 LeftNav**

```tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Clock, Folder, File, ChevronRight } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

interface FileNode {
  name: string;
  type: 'file' | 'folder';
  children?: FileNode[];
}

// 硬编码的 mock 文件树
const mockFileTree: FileNode[] = [
  {
    name: '项目文档',
    type: 'folder',
    children: [
      { name: 'Q1产品路线图.pdf', type: 'file' },
      { name: '技术架构设计.docx', type: 'file' },
    ],
  },
  {
    name: '数据分析',
    type: 'folder',
    children: [
      { name: 'sales_data.xlsx', type: 'file' },
      { name: '用户行为报告.pdf', type: 'file' },
    ],
  },
  { name: '会议记录.txt', type: 'file' },
  { name: 'OKR规划表.xlsx', type: 'file' },
];

function getTitle(meta: string): string {
  try { return JSON.parse(meta).title || '未命名任务'; } catch { return '未命名任务'; }
}

function timeLabel(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function FileTreeItem({ node }: { node: FileNode }) {
  const [expanded, setExpanded] = useState(false);
  const isFolder = node.type === 'folder';

  return (
    <div>
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded hover:bg-muted cursor-pointer text-sm"
        onClick={() => isFolder && setExpanded(!expanded)}
      >
        {isFolder && (
          <ChevronRight className={cn(
            'w-3 h-3 text-muted-foreground transition-transform',
            expanded && 'rotate-90'
          )} />
        )}
        {isFolder ? (
          <Folder className="w-4 h-4 text-primary" />
        ) : (
          <File className="w-4 h-4 text-muted-foreground" />
        )}
        <span className="text-foreground/80 truncate">{node.name}</span>
      </div>
      {isFolder && expanded && node.children && (
        <div className="ml-4 mt-0.5 space-y-0.5">
          {node.children.map((child, i) => (
            <FileTreeItem key={i} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}

export function LeftNav() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionItem[]>([]);

  useEffect(() => {
    authFetch(`${API_BASE}/api/sessions`)
      .then((r) => r.json())
      .then((d) => setSessions((d.sessions || []).slice(0, 10)))
      .catch(() => {});
  }, []);

  return (
    <nav className="w-56 border-r border-border bg-muted/20 flex flex-col shrink-0">
      <Tabs defaultValue="tasks" className="flex-1 flex flex-col">
        <TabsList className="w-full grid grid-cols-2 rounded-none border-b border-border bg-transparent p-0 h-auto">
          <TabsTrigger
            value="tasks"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            任务
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            文件区
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="flex-1 p-3 mt-0 overflow-y-auto">
          <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
            最近任务
          </h3>
          <div className="space-y-1">
            {sessions.length === 0 && (
              <p className="text-xs text-muted-foreground/50 px-1 py-4 text-center">
                暂无任务记录
              </p>
            )}
            {sessions.map((s) => (
              <div
                key={s.session_id}
                onClick={() => router.push(`/chat?session=${s.session_id}`)}
                className="px-3 py-2 rounded-lg cursor-pointer hover:bg-muted transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Clock className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className="text-sm text-foreground truncate">
                    {getTitle(s.meta)}
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground ml-5">
                  {timeLabel(s.last_active)}
                </span>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="files" className="flex-1 p-3 mt-0 overflow-y-auto">
          <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
            我的文件
          </h3>
          <div className="space-y-0.5">
            {mockFileTree.map((node, i) => (
              <FileTreeItem key={i} node={node} />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </nav>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/components/workbench/LeftNav.tsx
git commit -m "feat(web): 创建 LeftNav 左侧导航组件"
```

---

### Task 5: 创建 WorkbenchShell 布局壳

**Files:**
- Create: `agentos/app/web/components/workbench/WorkbenchShell.tsx`

- [ ] **Step 1: 创建 WorkbenchShell**

```tsx
'use client';

import { LeftNav } from './LeftNav';
import { RightContext } from './RightContext';
import { BottomInput } from './BottomInput';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface WorkbenchShellProps {
  children: React.ReactNode;
  steps?: StepItem[];
  sources?: { name: string; type: 'file' | 'web'; url?: string }[];
  parameters?: { label: string; value: string }[];
  taskProgress?: { task: string; step: number; total: number; status: 'running' | 'completed' }[];
  isRightCollapsed?: boolean;
  onSubmit?: (message: string) => void;
  inputDisabled?: boolean;
  wsConnected?: boolean;
}

export function WorkbenchShell({
  children,
  steps,
  sources,
  parameters,
  taskProgress,
  isRightCollapsed = true,
  onSubmit,
  inputDisabled,
  wsConnected = true,
}: WorkbenchShellProps) {
  return (
    <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
      <LeftNav />
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            {children}
          </div>
          <RightContext
            steps={steps}
            sources={sources}
            parameters={parameters}
            taskProgress={taskProgress}
            isCollapsed={isRightCollapsed}
          />
        </div>
        <BottomInput
          onSubmit={onSubmit}
          disabled={inputDisabled}
          connected={wsConnected}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/components/workbench/WorkbenchShell.tsx
git commit -m "feat(web): 创建 WorkbenchShell 布局壳组件"
```

---

## Chunk 2: 工作台主页 + WebSocket Hook

### Task 6: 创建 TaskSummaryCard 和 ResultCard

**Files:**
- Create: `agentos/app/web/components/workbench/TaskSummaryCard.tsx`
- Create: `agentos/app/web/components/workbench/ResultCard.tsx`

- [ ] **Step 1: 创建 TaskSummaryCard**

```tsx
'use client';

import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface TaskSummaryCardProps {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

const statusConfig = {
  idle: { label: '待处理', className: 'bg-muted text-muted-foreground' },
  running: { label: '执行中', className: 'bg-blue-500/10 text-blue-600 border-blue-500/20' },
  completed: { label: '已完成', className: 'bg-green-500/10 text-green-600 border-green-500/20' },
  error: { label: '失败', className: 'bg-red-500/10 text-red-600 border-red-500/20' },
};

export function TaskSummaryCard({ title, goal, stage, status }: TaskSummaryCardProps) {
  const config = statusConfig[status];

  return (
    <Card className="p-6 mb-6">
      <div className="flex items-start justify-between mb-3">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        <Badge variant="outline" className={cn('text-xs', config.className)}>
          {config.label}
        </Badge>
      </div>
      <p className="text-foreground/80 text-sm mb-2">{goal}</p>
      <p className="text-xs text-muted-foreground">当前阶段：{stage}</p>
    </Card>
  );
}
```

- [ ] **Step 2: 创建 ResultCard**

```tsx
'use client';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { CheckCircle2, ArrowRight } from 'lucide-react';

interface ResultCardProps {
  summary: string;
  preview?: React.ReactNode;
  sources?: string[];
  nextActions?: { label: string; primary?: boolean; onClick?: () => void }[];
}

export function ResultCard({ summary, preview, sources, nextActions }: ResultCardProps) {
  return (
    <Card className="p-6 mb-4">
      {/* 结论摘要 */}
      <div className="flex items-start gap-3 mb-4">
        <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
        <div>
          <h2 className="font-semibold text-foreground mb-2">结论摘要</h2>
          <p className="text-foreground/80 text-sm">{summary}</p>
        </div>
      </div>

      {/* 预览 */}
      {preview && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-3 text-sm">预览</h3>
            <div className="bg-muted/50 rounded-lg p-4 border border-border">{preview}</div>
          </div>
        </>
      )}

      {/* 来源 */}
      {sources && sources.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-2 text-sm">依据来源</h3>
            <div className="space-y-1">
              {sources.map((source, index) => (
                <div key={index} className="text-xs text-muted-foreground flex items-center gap-2">
                  <div className="w-1 h-1 rounded-full bg-muted-foreground/40" />
                  {source}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 下一步动作 */}
      {nextActions && nextActions.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-3 text-sm">下一步动作</h3>
            <div className="flex gap-2">
              {nextActions.map((action, index) => (
                <Button
                  key={index}
                  variant={action.primary ? 'default' : 'outline'}
                  size="sm"
                  onClick={action.onClick}
                  className="gap-1.5"
                >
                  {action.label}
                  {action.primary && <ArrowRight className="w-3.5 h-3.5" />}
                </Button>
              ))}
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add agentos/app/web/components/workbench/TaskSummaryCard.tsx agentos/app/web/components/workbench/ResultCard.tsx
git commit -m "feat(web): 创建 TaskSummaryCard 和 ResultCard 组件"
```

---

### Task 7: 创建 useWorkbenchSession hook

**Files:**
- Create: `agentos/app/web/hooks/useWorkbenchSession.ts`

- [ ] **Step 1: 创建 hook**

从现有 `chat/page.tsx` 中提取 WebSocket 连接模式，映射到任务驱动 UI 状态：

```tsx
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
const WS_RECONNECT_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;

export type TaskState = 'empty' | 'processing' | 'completed';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface TaskProgressItem {
  task: string;
  step: number;
  total: number;
  status: 'running' | 'completed';
}

interface CurrentTask {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

export interface UseWorkbenchSessionReturn {
  wsConnected: boolean;
  taskState: TaskState;
  currentTask: CurrentTask | null;
  steps: StepItem[];
  taskProgress: TaskProgressItem[];
  result: string | null;
  sendTask: (message: string) => void;
  reset: () => void;
}

export function useWorkbenchSession(): UseWorkbenchSessionReturn {
  const [wsConnected, setWsConnected] = useState(false);
  const [taskState, setTaskState] = useState<TaskState>('empty');
  const [currentTask, setCurrentTask] = useState<CurrentTask | null>(null);
  const [steps, setSteps] = useState<StepItem[]>([]);
  const [taskProgress, setTaskProgress] = useState<TaskProgressItem[]>([]);
  const [result, setResult] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const sessionIdRef = useRef<string | null>(null);
  const pendingInputRef = useRef<string | null>(null);
  const toolStepMapRef = useRef<Map<string, number>>(new Map());

  const wsSend = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const handleWsMessage = useCallback((data: Record<string, unknown>) => {
    const payload = (data.payload || {}) as Record<string, unknown>;

    switch (data.type) {
      case 'session_created': {
        const newSid = data.session_id as string;
        sessionIdRef.current = newSid;
        if (pendingInputRef.current) {
          wsSend({
            type: 'user_input',
            session_id: newSid,
            payload: { content: pendingInputRef.current, attachments: [], context_files: [] },
            timestamp: Date.now() / 1000,
          });
          pendingInputRef.current = null;
        }
        break;
      }
      case 'agent_thinking':
        setTaskState('processing');
        setCurrentTask((prev) => prev ? { ...prev, status: 'running', stage: '思考中' } : prev);
        break;
      case 'tool_execution': {
        const toolName = String(payload.tool_name || '');
        const toolCallId = String(payload.tool_call_id || '');
        setSteps((prev) => {
          const idx = prev.length;
          toolStepMapRef.current.set(toolCallId, idx);
          return [...prev, { label: `执行 ${toolName}`, status: 'running' as const }];
        });
        setTaskProgress((prev) => [...prev, {
          task: toolName,
          step: 0,
          total: 1,
          status: 'running' as const,
        }]);
        break;
      }
      case 'tool_result': {
        const toolCallId = String(payload.tool_call_id || '');
        const stepIdx = toolStepMapRef.current.get(toolCallId);
        if (stepIdx !== undefined) {
          setSteps((prev) => prev.map((s, i) =>
            i === stepIdx ? { ...s, status: 'done' as const } : s
          ));
        }
        setTaskProgress((prev) => {
          const toolName = String(payload.tool_name || '');
          const idx = prev.findIndex((t) => t.task === toolName && t.status === 'running');
          if (idx === -1) return prev;
          return prev.map((t, i) =>
            i === idx ? { ...t, step: 1, status: 'completed' as const } : t
          );
        });
        break;
      }
      case 'turn_completed': {
        const finalResponse = String(payload.final_response || '');
        if (finalResponse) {
          setResult(finalResponse);
        }
        setTaskState('completed');
        setCurrentTask((prev) => prev ? { ...prev, status: 'completed', stage: '已完成' } : prev);
        break;
      }
      case 'error': {
        const errMsg = String(payload.message || '未知错误');
        setResult(`错误：${errMsg}`);
        setCurrentTask((prev) => prev ? { ...prev, status: 'error', stage: '出错' } : prev);
        break;
      }
    }
  }, [wsSend]);

  const handleWsMessageRef = useRef(handleWsMessage);
  handleWsMessageRef.current = handleWsMessage;

  useEffect(() => {
    let cancelled = false;

    const scheduleReconnect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      if (reconnectAttemptsRef.current >= WS_MAX_RECONNECT_ATTEMPTS) return;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectAttemptsRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL_MS);
    };

    const connect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      const cookieMatch = document.cookie.match(/(?:^|; )agentos_token=([^;]*)/);
      const token = cookieMatch ? decodeURIComponent(cookieMatch[1]) : null;
      const wsUrl = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled || wsRef.current !== ws) return;
        setWsConnected(true);
        reconnectAttemptsRef.current = 0;
      };
      ws.onclose = () => {
        if (wsRef.current !== ws && wsRef.current !== null) return;
        if (wsRef.current === ws) wsRef.current = null;
        setWsConnected(false);
        scheduleReconnect();
      };
      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        setWsConnected(false);
        if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
      ws.onmessage = (event) => {
        try { handleWsMessageRef.current(JSON.parse(event.data)); } catch {}
      };
    };

    shouldReconnectRef.current = true;
    const timer = setTimeout(connect, 50);

    return () => {
      cancelled = true;
      shouldReconnectRef.current = false;
      clearTimeout(timer);
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        const activeSocket = wsRef.current;
        wsRef.current = null;
        activeSocket.close();
      }
    };
  }, []);

  const sendTask = useCallback((message: string) => {
    if (!wsConnected) return;
    // 重置状态
    setTaskState('processing');
    setSteps([]);
    setTaskProgress([]);
    setResult(null);
    toolStepMapRef.current.clear();
    setCurrentTask({
      title: message.slice(0, 30) + (message.length > 30 ? '...' : ''),
      goal: message,
      stage: '初始化',
      status: 'running',
    });

    if (!sessionIdRef.current) {
      pendingInputRef.current = message;
      wsSend({
        type: 'create_session',
        payload: { agent_id: 'default', meta: { title: message.slice(0, 20) || '新任务' } },
        timestamp: Date.now() / 1000,
      });
    } else {
      wsSend({
        type: 'user_input',
        session_id: sessionIdRef.current,
        payload: { content: message, attachments: [], context_files: [] },
        timestamp: Date.now() / 1000,
      });
    }
  }, [wsConnected, wsSend]);

  const reset = useCallback(() => {
    setTaskState('empty');
    setCurrentTask(null);
    setSteps([]);
    setTaskProgress([]);
    setResult(null);
    toolStepMapRef.current.clear();
    sessionIdRef.current = null;
    pendingInputRef.current = null;
  }, []);

  return {
    wsConnected,
    taskState,
    currentTask,
    steps,
    taskProgress,
    result,
    sendTask,
    reset,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/hooks/useWorkbenchSession.ts
git commit -m "feat(web): 创建 useWorkbenchSession hook"
```

---

### Task 8: 创建 MainStage 组件

**Files:**
- Create: `agentos/app/web/components/workbench/MainStage.tsx`

- [ ] **Step 1: 创建 MainStage**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, CheckCircle2, Clock, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TaskSummaryCard } from './TaskSummaryCard';
import { ResultCard } from './ResultCard';
import { authFetch, API_BASE } from '@/lib/authFetch';
import type { TaskState } from '@/hooks/useWorkbenchSession';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface CurrentTask {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

interface MainStageProps {
  state: TaskState;
  currentTask: CurrentTask | null;
  steps: StepItem[];
  result: string | null;
  onQuickTask?: (task: string) => void;
}

function getTitle(meta: string): string {
  try { return JSON.parse(meta).title || '未命名任务'; } catch { return '未命名任务'; }
}

function timeLabel(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

const taskTemplates = [
  { title: '回复重要邮件', desc: '自动分析收件箱，起草专业回复' },
  { title: '准备周会议题', desc: '基于本周日历和任务，生成议程' },
  { title: '总结项目进展', desc: '汇总文档和对话，生成周报草稿' },
  { title: '安排团队会议', desc: '检查成员日历，推荐最佳时间' },
];

export function MainStage({ state, currentTask, steps, result, onQuickTask }: MainStageProps) {
  const router = useRouter();
  const [recentSessions, setRecentSessions] = useState<SessionItem[]>([]);

  useEffect(() => {
    if (state === 'empty') {
      authFetch(`${API_BASE}/api/sessions`)
        .then((r) => r.json())
        .then((d) => setRecentSessions((d.sessions || []).slice(0, 5)))
        .catch(() => {});
    }
  }, [state]);

  // 空状态
  if (state === 'empty') {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">开始新任务</h2>
            <p className="text-muted-foreground text-sm mb-8">
              使用下方快捷动作快速开始，或描述你需要完成的任务
            </p>
          </div>

          {/* 任务模板 */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            {taskTemplates.map((tmpl, i) => (
              <Card
                key={i}
                className="p-4 hover:shadow-md transition-shadow cursor-pointer hover:border-primary/30"
                onClick={() => onQuickTask?.(tmpl.title)}
              >
                <h3 className="font-semibold text-foreground mb-1 text-sm">{tmpl.title}</h3>
                <p className="text-xs text-muted-foreground">{tmpl.desc}</p>
              </Card>
            ))}
          </div>

          {/* 最近任务 */}
          {recentSessions.length > 0 && (
            <div>
              <h3 className="font-semibold text-foreground mb-3 text-sm">最近任务</h3>
              <div className="space-y-2">
                {recentSessions.map((s) => (
                  <Card
                    key={s.session_id}
                    className="p-3 flex items-center justify-between hover:shadow-sm transition-shadow cursor-pointer"
                    onClick={() => router.push(`/chat?session=${s.session_id}`)}
                  >
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      <span className="text-sm text-foreground">{getTitle(s.meta)}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{timeLabel(s.last_active)}</span>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    );
  }

  // 执行中
  if (state === 'processing' && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />
          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <Loader2 className="w-5 h-5 text-primary animate-spin" />
              <h2 className="font-semibold text-foreground">正在执行</h2>
            </div>
            <div className="space-y-3">
              {steps.map((step, i) => (
                <div key={i} className="flex items-center gap-3">
                  {step.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                  {step.status === 'running' && (
                    <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  )}
                  {step.status === 'pending' && (
                    <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30" />
                  )}
                  <span className={`text-sm ${
                    step.status === 'done' ? 'text-muted-foreground' :
                    step.status === 'running' ? 'text-foreground' :
                    'text-muted-foreground/50'
                  }`}>
                    {step.label}
                  </span>
                </div>
              ))}
              {steps.length === 0 && (
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  <span className="text-sm text-foreground">正在分析任务...</span>
                </div>
              )}
            </div>
          </Card>
        </div>
      </main>
    );
  }

  // 已完成
  if (state === 'completed' && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />
          <ResultCard
            summary={result || '任务已完成'}
            nextActions={[
              { label: '开始新任务', onClick: () => window.location.reload() },
            ]}
          />
        </div>
      </main>
    );
  }

  return null;
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/components/workbench/MainStage.tsx
git commit -m "feat(web): 创建 MainStage 工作台主内容组件"
```

---

### Task 9: 更新主页面，渲染工作台

**Files:**
- Modify: `agentos/app/web/app/page.tsx`

- [ ] **Step 1: 替换 page.tsx 内容**

```tsx
'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { MainStage } from '@/components/workbench/MainStage';
import { useWorkbenchSession } from '@/hooks/useWorkbenchSession';

export default function Page() {
  const {
    wsConnected,
    taskState,
    currentTask,
    steps,
    taskProgress,
    result,
    sendTask,
  } = useWorkbenchSession();

  const isRightCollapsed = taskState === 'empty';

  return (
    <DashboardLayout>
      <WorkbenchShell
        steps={steps}
        taskProgress={taskProgress}
        isRightCollapsed={isRightCollapsed}
        onSubmit={sendTask}
        inputDisabled={taskState === 'processing'}
        wsConnected={wsConnected}
      >
        <MainStage
          state={taskState}
          currentTask={currentTask}
          steps={steps}
          result={result}
          onQuickTask={sendTask}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
```

- [ ] **Step 2: 验证构建**

Run: `cd agentos/app/web && npx next build 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add agentos/app/web/app/page.tsx
git commit -m "feat(web): 主页面改为任务驱动工作台"
```

---

## Chunk 3: Research / PPT / Automation 页面

### Task 10: 创建 ResearchPage

**Files:**
- Create: `agentos/app/web/app/research/page.tsx`

- [ ] **Step 1: 创建页面**

```tsx
'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BookOpen, TrendingUp, Users, DollarSign, Sparkles } from 'lucide-react';

const researchItems = [
  {
    id: 1,
    title: '2024年企业SaaS市场趋势分析',
    summary: 'AI驱动的自动化工具正在重塑企业办公场景，预计未来三年市场规模将增长42%...',
    category: '市场趋势',
    icon: TrendingUp,
    date: '2024-03-18',
    sources: 5,
    highlights: ['AI自动化', '市场增长42%', '智能协作'],
    status: 'latest' as const,
  },
  {
    id: 2,
    title: '竞品功能对比：Notion vs Monday.com',
    summary: '深度对比两款主流协作工具的核心功能、定价策略和用户体验...',
    category: '竞品分析',
    icon: Users,
    date: '2024-03-17',
    sources: 8,
    highlights: ['功能对比', '定价策略', '用户体验'],
    status: 'completed' as const,
  },
  {
    id: 3,
    title: '用户调研报告：办公效率痛点分析',
    summary: '基于500+企业用户访谈，发现三大核心痛点：信息分散(67%)、重复性任务(58%)、协作效率低(52%)...',
    category: '用户研究',
    icon: Users,
    date: '2024-03-15',
    sources: 12,
    highlights: ['500+用户', '三大痛点', '数据洞察'],
    status: 'completed' as const,
  },
  {
    id: 4,
    title: 'AI Agent技术发展趋势与应用场景',
    summary: '探索大语言模型在办公自动化领域的最新进展，重点关注Multi-Agent协作...',
    category: '技术趋势',
    icon: Sparkles,
    date: '2024-03-14',
    sources: 15,
    highlights: ['Multi-Agent', '工具调用', '场景应用'],
    status: 'completed' as const,
  },
  {
    id: 5,
    title: '企业级SaaS定价策略研究',
    summary: '分析Top20 SaaS产品的定价模型，订阅制仍是主流(65%)，按需付费增长迅速(年增长38%)...',
    category: '商业模式',
    icon: DollarSign,
    date: '2024-03-12',
    sources: 6,
    highlights: ['订阅制65%', '按需付费增长', '定价模型'],
    status: 'completed' as const,
  },
];

export default function ResearchPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-xl font-semibold text-foreground mb-1">深度研究</h1>
                <p className="text-sm text-muted-foreground">
                  AI Agent 自动调研的市场洞察与竞品分析
                </p>
              </div>
              <Button className="gap-2" size="sm">
                <BookOpen className="w-4 h-4" />
                新建调研任务
              </Button>
            </div>

            <div className="space-y-4">
              {researchItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Card key={item.id} className="p-5 hover:shadow-lg transition-shadow cursor-pointer group">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <Icon className="w-5 h-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant="outline" className="text-[10px]">{item.category}</Badge>
                          {item.status === 'latest' && (
                            <Badge className="text-[10px] bg-green-500">最新</Badge>
                          )}
                          <span className="text-xs text-muted-foreground ml-auto">{item.date}</span>
                        </div>
                        <h3 className="font-semibold text-foreground mb-1.5 group-hover:text-primary transition-colors">
                          {item.title}
                        </h3>
                        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{item.summary}</p>
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {item.highlights.map((h, i) => (
                            <span key={i} className="px-2 py-0.5 bg-muted text-muted-foreground text-[10px] rounded">
                              {h}
                            </span>
                          ))}
                        </div>
                        <span className="text-[10px] text-muted-foreground">基于 {item.sources} 个信息源</span>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/app/research/page.tsx
git commit -m "feat(web): 创建深度研究页面"
```

---

### Task 11: 创建 PPTPage

**Files:**
- Create: `agentos/app/web/app/ppt/page.tsx`

- [ ] **Step 1: 创建页面**

```tsx
'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Presentation, Plus, Search, Grid3X3, List } from 'lucide-react';

const presentations = [
  { id: 1, name: 'Q2产品发布会PPT', slides: 24, lastModified: '1小时前', owner: '我', gradient: 'from-blue-500 to-purple-600', status: 'editing' },
  { id: 2, name: '2024市场趋势分析', slides: 18, lastModified: '昨天', owner: '张经理', gradient: 'from-green-500 to-teal-600', status: 'completed' },
  { id: 3, name: '技术架构评审', slides: 32, lastModified: '3天前', owner: '李工程师', gradient: 'from-orange-500 to-red-600', status: 'completed' },
  { id: 4, name: '用户调研报告展示', slides: 15, lastModified: '1周前', owner: '设计团队', gradient: 'from-pink-500 to-rose-600', status: 'completed' },
  { id: 5, name: '团队OKR规划', slides: 12, lastModified: '2周前', owner: '王总监', gradient: 'from-indigo-500 to-blue-600', status: 'completed' },
  { id: 6, name: '竞品分析汇报', slides: 20, lastModified: '3周前', owner: '产品团队', gradient: 'from-yellow-500 to-orange-600', status: 'completed' },
];

export default function PPTPage() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-xl font-semibold text-foreground mb-1">PPT</h1>
                <p className="text-sm text-muted-foreground">管理和创建你的演示文稿</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input placeholder="搜索PPT..." className="pl-9 w-48 bg-muted/50" />
                </div>
                <div className="flex items-center gap-0.5 border border-border rounded-lg p-0.5">
                  <Button variant={viewMode === 'grid' ? 'secondary' : 'ghost'} size="icon" className="w-7 h-7" onClick={() => setViewMode('grid')}>
                    <Grid3X3 className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant={viewMode === 'list' ? 'secondary' : 'ghost'} size="icon" className="w-7 h-7" onClick={() => setViewMode('list')}>
                    <List className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <Button className="gap-2" size="sm">
                  <Plus className="w-4 h-4" />
                  创建PPT
                </Button>
              </div>
            </div>

            {viewMode === 'grid' && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {presentations.map((ppt) => (
                  <Card key={ppt.id} className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer group">
                    <div className={`h-32 bg-gradient-to-br ${ppt.gradient} relative`}>
                      {ppt.status === 'editing' && (
                        <Badge className="absolute bottom-2 left-2 bg-blue-500 text-[10px]">编辑中</Badge>
                      )}
                      <Presentation className="absolute bottom-2 right-2 w-6 h-6 text-white/60" />
                    </div>
                    <div className="p-3">
                      <h3 className="font-medium text-foreground mb-1 text-sm truncate">{ppt.name}</h3>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{ppt.slides} 张幻灯片</span>
                        <span>{ppt.lastModified}</span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}

            {viewMode === 'list' && (
              <div className="space-y-2">
                {presentations.map((ppt) => (
                  <Card key={ppt.id} className="p-4 hover:shadow-md transition-shadow cursor-pointer">
                    <div className="flex items-center gap-4">
                      <div className={`w-16 h-11 bg-gradient-to-br ${ppt.gradient} rounded flex items-center justify-center shrink-0`}>
                        <Presentation className="w-5 h-5 text-white/80" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <h3 className="font-medium text-foreground text-sm">{ppt.name}</h3>
                          {ppt.status === 'editing' && <Badge variant="secondary" className="text-[10px]">编辑中</Badge>}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{ppt.slides} 张幻灯片</span>
                          <span>{ppt.owner}</span>
                          <span>{ppt.lastModified}</span>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/app/ppt/page.tsx
git commit -m "feat(web): 创建PPT管理页面"
```

---

### Task 12: 创建 AutomationPage

**Files:**
- Create: `agentos/app/web/app/automation/page.tsx`

- [ ] **Step 1: 创建页面**

```tsx
'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Zap, Play, Pause } from 'lucide-react';

const automations = [
  { id: 1, name: '自动整理每日邮件摘要', description: '每天早上9点自动生成昨日邮件摘要', status: 'active', lastRun: '今天 09:00', frequency: '每日' },
  { id: 2, name: '周报自动生成', description: '每周五下午生成本周工作总结', status: 'active', lastRun: '3月14日', frequency: '每周' },
  { id: 3, name: '重要邮件提醒', description: '检测到重要邮件时立即推送通知', status: 'paused', lastRun: '3月15日', frequency: '实时' },
];

export default function AutomationPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <h1 className="text-xl font-semibold text-foreground">自动化</h1>
              <Button className="gap-2" size="sm">
                <Zap className="w-4 h-4" />
                创建新自动化
              </Button>
            </div>

            <div className="space-y-3">
              {automations.map((auto) => (
                <Card key={auto.id} className="p-5 hover:shadow-md transition-shadow">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <Zap className="w-4 h-4 text-primary" />
                        <h3 className="font-medium text-foreground text-sm">{auto.name}</h3>
                        <Badge variant={auto.status === 'active' ? 'default' : 'secondary'} className="text-[10px]">
                          {auto.status === 'active' ? '运行中' : '已暂停'}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mb-2 ml-7">{auto.description}</p>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground ml-7">
                        <span>频率: {auto.frequency}</span>
                        <span>上次运行: {auto.lastRun}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {auto.status === 'active' ? (
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Pause className="w-3.5 h-3.5" />
                          暂停
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Play className="w-3.5 h-3.5" />
                          启动
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agentos/app/web/app/automation/page.tsx
git commit -m "feat(web): 创建自动化任务页面"
```

---

### Task 13: 最终验证

- [ ] **Step 1: 构建验证**

Run: `cd agentos/app/web && npx next build 2>&1 | tail -30`
Expected: 构建成功，所有页面编译通过

- [ ] **Step 2: 启动开发服务器手动验证**

Run: `cd agentos/app/web && npx next dev`

验证清单：
- 访问 `/` → 工作台主页（空状态，任务模板卡片，最近任务列表）
- 导航栏显示：工作台 | Chat | 深度研究 | PPT | 自动化 | 管理▾
- 点击"管理" → 下拉菜单（Dashboard/Sessions/Gateway/Tools/Skills）
- 访问 `/chat` → 现有聊天界面正常
- 访问 `/research` → 深度研究列表
- 访问 `/ppt` → PPT 管理（网格/列表切换）
- 访问 `/automation` → 自动化任务列表
- 访问 `/agents` → 原有 Agent 管理页面正常
- 工作台输入任务 → WebSocket 连接，MainStage 切到执行中

- [ ] **Step 3: Commit 最终状态（如有修复）**

```bash
git add agentos/app/web/
git commit -m "feat(web): 任务驱动工作台完整实现"
```
