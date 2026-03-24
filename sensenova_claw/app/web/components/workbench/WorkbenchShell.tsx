'use client';

import { LeftNav } from './LeftNav';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

interface WorkbenchShellProps {
  children: React.ReactNode;
  agentFilter?: string;
}

export function WorkbenchShell({ children, agentFilter }: WorkbenchShellProps) {
  return (
    <ResizablePanelGroup orientation="horizontal" className="h-full gap-2.5">
      <ResizablePanel
        id="workbench-left"
        defaultSize="20%"
        minSize="10%"
        maxSize="30%"
        className="rounded-[var(--panel-radius)] border border-border/40 overflow-hidden bg-background shadow-sm"
      >
        <LeftNav agentFilter={agentFilter} />
      </ResizablePanel>
      <ResizableHandle invisible />
      <ResizablePanel
        id="workbench-main"
        defaultSize="80%"
        minSize="40%"
        className="rounded-[var(--panel-radius)] border border-border/40 overflow-hidden shadow-sm"
      >
        <div className="flex flex-col h-full min-w-0 bg-background">
          {children}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
