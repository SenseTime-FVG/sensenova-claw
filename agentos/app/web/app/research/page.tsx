'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';

import { BookOpen } from 'lucide-react';
import { Card } from '@/components/ui/card';

const researchTemplates = [
  { title: '行业趋势调研', desc: '深入分析指定行业的最新发展趋势和市场动态' },
  { title: '竞品分析报告', desc: '全面调研竞争对手的产品、策略和市场表现' },
  { title: '技术方案调研', desc: '搜索并整理特定技术领域的解决方案和最佳实践' },
  { title: '学术文献综述', desc: '检索和梳理相关领域的研究论文和关键发现' },
];

function ResearchTemplates({ onQuickTask }: { onQuickTask: (msg: string) => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <BookOpen className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">开始深度调研</h2>
          <p className="text-muted-foreground text-sm mb-8">
            使用下方快捷动作快速开始，或在下方输入框描述你的调研需求
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {researchTemplates.map((tmpl, i) => (
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

export default function ResearchPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell agentFilter="deep_research">
        <ChatPanel
          defaultAgentId="deep_research"
          lockAgent
          emptyState={(fillInput) => <ResearchTemplates onQuickTask={fillInput} />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
