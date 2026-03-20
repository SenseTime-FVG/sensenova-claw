'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { cn } from '@/lib/utils';

import { BookOpen, TrendingUp, Target, Code2, GraduationCap } from 'lucide-react';

const researchTemplates = [
  { title: '行业趋势调研', desc: '深入分析指定行业的最新发展趋势和市场动态', icon: TrendingUp,
    bg: 'from-blue-100/40 via-blue-50/20 to-indigo-100/30 dark:from-blue-500/15 dark:via-blue-500/8 dark:to-indigo-500/10', iconBg: 'bg-blue-500/15', iconColor: 'text-blue-600 dark:text-blue-400', ring: 'ring-blue-200/60 hover:ring-blue-300/80 dark:ring-blue-500/15 dark:hover:ring-blue-500/30' },
  { title: '竞品分析报告', desc: '全面调研竞争对手的产品、策略和市场表现', icon: Target,
    bg: 'from-amber-100/40 via-amber-50/20 to-orange-100/30 dark:from-amber-500/15 dark:via-amber-500/8 dark:to-orange-500/10', iconBg: 'bg-amber-500/15', iconColor: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-200/60 hover:ring-amber-300/80 dark:ring-amber-500/15 dark:hover:ring-amber-500/30' },
  { title: '技术方案调研', desc: '搜索并整理特定技术领域的解决方案和最佳实践', icon: Code2,
    bg: 'from-violet-100/40 via-violet-50/20 to-purple-100/30 dark:from-violet-500/15 dark:via-violet-500/8 dark:to-purple-500/10', iconBg: 'bg-violet-500/15', iconColor: 'text-violet-600 dark:text-violet-400', ring: 'ring-violet-200/60 hover:ring-violet-300/80 dark:ring-violet-500/15 dark:hover:ring-violet-500/30' },
  { title: '学术文献综述', desc: '检索和梳理相关领域的研究论文和关键发现', icon: GraduationCap,
    bg: 'from-emerald-100/40 via-emerald-50/20 to-teal-100/30 dark:from-emerald-500/15 dark:via-emerald-500/8 dark:to-teal-500/10', iconBg: 'bg-emerald-500/15', iconColor: 'text-emerald-600 dark:text-emerald-400', ring: 'ring-emerald-200/60 hover:ring-emerald-300/80 dark:ring-emerald-500/15 dark:hover:ring-emerald-500/30' },
];

function ResearchTemplates({ onQuickTask }: { onQuickTask: (msg: string) => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-5 shadow-sm">
            <BookOpen className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-2 tracking-tight">开始深度调研</h2>
          <p className="text-muted-foreground text-sm mb-8">
            使用下方快捷动作快速开始，或在下方输入框描述你的调研需求
          </p>
        </div>

        <div className="grid grid-cols-2 gap-5">
          {researchTemplates.map((tmpl, i) => {
            const Icon = tmpl.icon;
            return (
              <div
                key={i}
                className={cn(
                  'relative rounded-2xl p-6 bg-gradient-to-br ring-1 transition-all duration-300 cursor-pointer',
                  'hover:shadow-lg hover:-translate-y-0.5',
                  tmpl.bg, tmpl.ring,
                )}
                onClick={() => onQuickTask(tmpl.title)}
              >
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center mb-4', tmpl.iconBg)}>
                  <Icon className={cn('w-5 h-5', tmpl.iconColor)} />
                </div>
                <h3 className="font-bold text-foreground mb-1.5 text-sm">{tmpl.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{tmpl.desc}</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function ResearchPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell agentFilter="search-agent">
        <ChatPanel
          defaultAgentId="search-agent"
          lockAgent
          emptyState={(fillInput) => <ResearchTemplates onQuickTask={fillInput} />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
