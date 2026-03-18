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
