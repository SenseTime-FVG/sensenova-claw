'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';

import { Zap } from 'lucide-react';
import { Card } from '@/components/ui/card';

const automationTemplates = [
  { title: '定时发送报告', desc: '设置定时任务，自动汇总并发送日报/周报' },
  { title: '监控数据变化', desc: '自动监测关键指标，异常时即时通知' },
  { title: '批量处理文件', desc: '自动批量转换、整理或归档指定文件' },
  { title: '自动化工作流', desc: '串联多个步骤，自动执行复杂业务流程' },
];

function AutomationTemplates({ onQuickTask }: { onQuickTask: (msg: string) => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Zap className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">创建自动化任务</h2>
          <p className="text-muted-foreground text-sm mb-8">
            使用下方快捷动作快速开始，或在下方输入框描述你的自动化需求
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {automationTemplates.map((tmpl, i) => (
            <Card
              key={i}
              className="p-4 hover:shadow-md transition-shadow cursor-pointer hover:border-primary/30"
              onClick={() => onQuickTask(tmpl.title)}
            >
              <h3 className="font-semibold text-foreground mb-1 text-sm">{tmpl.title}</h3>
              <p className="text-xs text-muted-foreground">{tmpl.desc}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function AutomationPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="office-main"
          emptyState={(fillInput) => <AutomationTemplates onQuickTask={fillInput} />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
