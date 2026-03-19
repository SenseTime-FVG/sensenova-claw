'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { TaskTemplates } from '@/components/workbench/TaskTemplates';

export default function Page() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="office-main"
          emptyState={<TaskTemplates />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
