'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';

import { Presentation } from 'lucide-react';
import { Card } from '@/components/ui/card';

const pptTemplates = [
  { title: '制作项目汇报PPT', desc: '根据项目进展，自动生成专业汇报演示文稿' },
  { title: '制作培训课件', desc: '输入培训主题，自动设计课件内容与排版' },
  { title: '制作数据分析报告', desc: '将数据转化为图表丰富的分析演示文稿' },
  { title: '制作产品介绍PPT', desc: '根据产品信息，生成吸引力强的介绍文稿' },
];

function PPTTemplates({ onQuickTask }: { onQuickTask: (msg: string) => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Presentation className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">创建演示文稿</h2>
          <p className="text-muted-foreground text-sm mb-8">
            使用下方快捷动作快速开始，或在下方输入框描述你的 PPT 需求
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {pptTemplates.map((tmpl, i) => (
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

export default function PPTPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell>
        <ChatPanel
          defaultAgentId="ppt_generator"
          emptyState={(fillInput) => <PPTTemplates onQuickTask={fillInput} />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
