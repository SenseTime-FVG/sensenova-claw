'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { TaskTemplates } from '@/components/workbench/TaskTemplates';
import { useChatSession } from '@/contexts/ChatSessionContext';

export default function Page() {
  const { sendMessage } = useChatSession();

  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="default"
          emptyState={<TaskTemplates onQuickTask={(msg) => sendMessage(msg)} />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
