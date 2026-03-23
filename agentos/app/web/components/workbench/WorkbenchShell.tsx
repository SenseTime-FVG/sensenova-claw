'use client';

import { LeftNav } from './LeftNav';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

interface WorkbenchShellProps {
  children: React.ReactNode;
  agentFilter?: string;
}

export function WorkbenchShell({ children, agentFilter }: WorkbenchShellProps) {
  return (
    <ResizablePanelGroup orientation="horizontal" className="h-full gap-3">
      <ResizablePanel id="workbench-left" defaultSize="18%" minSize="10%" maxSize="30%" className="rounded-2xl border border-border/60 overflow-hidden bg-gradient-to-br from-indigo-100/20 via-background to-blue-200/20 dark:from-indigo-500/[0.06] dark:via-background dark:to-blue-500/[0.06]">
        <LeftNav agentFilter={agentFilter} />
      </ResizablePanel>
      <ResizableHandle invisible />
      <ResizablePanel id="workbench-main" defaultSize="82%" minSize="40%" className="rounded-2xl border border-border/60 overflow-hidden">
        <div className="flex flex-col h-full min-w-0 bg-background">
          {children}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
