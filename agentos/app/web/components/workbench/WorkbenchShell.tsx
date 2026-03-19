'use client';

import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { LeftNav } from './LeftNav';
import { RightContext } from './RightContext';

interface WorkbenchShellProps {
  children: React.ReactNode;
}

export function WorkbenchShell({ children }: WorkbenchShellProps) {
  return (
    <DndProvider backend={HTML5Backend}>
      <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
        <LeftNav />
        <div className="flex-1 flex flex-col min-w-0">
          {children}
        </div>
        <RightContext />
      </div>
    </DndProvider>
  );
}
