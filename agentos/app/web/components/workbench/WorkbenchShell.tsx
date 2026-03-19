'use client';

import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { LeftNav } from './LeftNav';
import { RightContext } from './RightContext';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

interface WorkbenchShellProps {
  children: React.ReactNode;
}

export function WorkbenchShell({ children }: WorkbenchShellProps) {
  return (
    <DndProvider backend={HTML5Backend}>
      <ResizablePanelGroup orientation="horizontal" className="h-[calc(100vh-4rem)]">
        <ResizablePanel id="workbench-left" defaultSize="16%" minSize="10%" maxSize="30%" className="bg-muted/20">
          <LeftNav />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="workbench-main" defaultSize="62%" minSize="30%">
          <div className="flex flex-col h-full min-w-0">
            {children}
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="workbench-right" defaultSize="22%" minSize="10%" maxSize="35%" className="bg-muted/20">
          <RightContext />
        </ResizablePanel>
      </ResizablePanelGroup>
    </DndProvider>
  );
}
