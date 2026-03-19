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
  // 可选插槽：自定义左侧导航，不传则使用默认 LeftNav
  leftNav?: React.ReactNode;
  // 可选插槽：自定义底部输入区，不传则使用默认 BottomInput，传 null 可隐藏
  bottomInput?: React.ReactNode | null;
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
  leftNav,
  bottomInput,
}: WorkbenchShellProps) {
  const leftNavContent = leftNav !== undefined ? leftNav : <LeftNav />;
  const bottomInputContent = bottomInput !== undefined
    ? bottomInput
    : <BottomInput onSubmit={onSubmit} disabled={inputDisabled} connected={wsConnected} />;

  return (
    <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
      {leftNavContent}
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
        {bottomInputContent}
      </div>
    </div>
  );
}
