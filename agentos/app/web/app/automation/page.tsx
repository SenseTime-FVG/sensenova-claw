'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { Zap } from 'lucide-react';

export default function AutomationPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="default"
          emptyState={
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-4">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                <Zap className="w-8 h-8 text-primary" />
              </div>
              <p className="text-lg font-medium text-foreground">创建一个新的自动化任务</p>
              <p className="text-sm">在下方输入你的自动化需求，Agent 将帮你完成</p>
            </div>
          }
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
