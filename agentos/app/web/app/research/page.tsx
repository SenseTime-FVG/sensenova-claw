'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BookOpen, TrendingUp, Users, DollarSign, Sparkles } from 'lucide-react';

const researchItems = [
  {
    id: 1,
    title: '2024年企业SaaS市场趋势分析',
    summary: 'AI驱动的自动化工具正在重塑企业办公场景，预计未来三年市场规模将增长42%...',
    category: '市场趋势',
    icon: TrendingUp,
    date: '2024-03-18',
    sources: 5,
    highlights: ['AI自动化', '市场增长42%', '智能协作'],
    status: 'latest' as const,
  },
  {
    id: 2,
    title: '竞品功能对比：Notion vs Monday.com',
    summary: '深度对比两款主流协作工具的核心功能、定价策略和用户体验...',
    category: '竞品分析',
    icon: Users,
    date: '2024-03-17',
    sources: 8,
    highlights: ['功能对比', '定价策略', '用户体验'],
    status: 'completed' as const,
  },
  {
    id: 3,
    title: '用户调研报告：办公效率痛点分析',
    summary: '基于500+企业用户访谈，发现三大核心痛点：信息分散(67%)、重复性任务(58%)、协作效率低(52%)...',
    category: '用户研究',
    icon: Users,
    date: '2024-03-15',
    sources: 12,
    highlights: ['500+用户', '三大痛点', '数据洞察'],
    status: 'completed' as const,
  },
  {
    id: 4,
    title: 'AI Agent技术发展趋势与应用场景',
    summary: '探索大语言模型在办公自动化领域的最新进展，重点关注Multi-Agent协作...',
    category: '技术趋势',
    icon: Sparkles,
    date: '2024-03-14',
    sources: 15,
    highlights: ['Multi-Agent', '工具调用', '场景应用'],
    status: 'completed' as const,
  },
  {
    id: 5,
    title: '企业级SaaS定价策略研究',
    summary: '分析Top20 SaaS产品的定价模型，订阅制仍是主流(65%)，按需付费增长迅速(年增长38%)...',
    category: '商业模式',
    icon: DollarSign,
    date: '2024-03-12',
    sources: 6,
    highlights: ['订阅制65%', '按需付费增长', '定价模型'],
    status: 'completed' as const,
  },
];

export default function ResearchPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-xl font-semibold text-foreground mb-1">深度研究</h1>
                <p className="text-sm text-muted-foreground">
                  AI Agent 自动调研的市场洞察与竞品分析
                </p>
              </div>
              <Button className="gap-2" size="sm">
                <BookOpen className="w-4 h-4" />
                新建调研任务
              </Button>
            </div>

            <div className="space-y-4">
              {researchItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Card key={item.id} className="p-5 hover:shadow-lg transition-shadow cursor-pointer group">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <Icon className="w-5 h-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant="outline" className="text-[10px]">{item.category}</Badge>
                          {item.status === 'latest' && (
                            <Badge className="text-[10px] bg-green-500">最新</Badge>
                          )}
                          <span className="text-xs text-muted-foreground ml-auto">{item.date}</span>
                        </div>
                        <h3 className="font-semibold text-foreground mb-1.5 group-hover:text-primary transition-colors">
                          {item.title}
                        </h3>
                        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{item.summary}</p>
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {item.highlights.map((h, i) => (
                            <span key={i} className="px-2 py-0.5 bg-muted text-muted-foreground text-[10px] rounded">
                              {h}
                            </span>
                          ))}
                        </div>
                        <span className="text-[10px] text-muted-foreground">基于 {item.sources} 个信息源</span>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
