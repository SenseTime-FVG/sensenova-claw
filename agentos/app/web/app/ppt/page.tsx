'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { Presentation } from 'lucide-react';

export default function PPTPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="ppt_generator"
          emptyState={
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-4">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                <Presentation className="w-8 h-8 text-primary" />
              </div>
              <p className="text-lg font-medium text-foreground">创建一个新的演示文稿</p>
              <p className="text-sm">在下方输入你的需求，PPT 生成助手将为你制作</p>
            </div>
          }
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
