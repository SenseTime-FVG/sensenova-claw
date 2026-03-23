'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { Dashboard } from '@/components/dashboard';

export default function Page() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="office-main"
          emptyState={({ selectAgent }) => <Dashboard onSelectAgent={selectAgent} />}
          returnToMainLabel="返回工作台"
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
