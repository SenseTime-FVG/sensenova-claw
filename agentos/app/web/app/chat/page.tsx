'use client';

import { Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';

function ChatContent() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel defaultAgentId="default" />
      </WorkbenchShell>
    </DashboardLayout>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
          <Loader2 className="animate-spin text-muted-foreground" size={32} />
        </div>
      </DashboardLayout>
    }>
      <ChatContent />
    </Suspense>
  );
}
