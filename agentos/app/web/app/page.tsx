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
