'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { BookOpen } from 'lucide-react';

export default function ResearchPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="deep_research"
          emptyState={
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-4">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                <BookOpen className="w-8 h-8 text-primary" />
              </div>
              <p className="text-lg font-medium text-foreground">开始一个新的调研任务</p>
              <p className="text-sm">在下方输入你的调研需求，深度调研 Agent 将为你分析</p>
            </div>
          }
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
