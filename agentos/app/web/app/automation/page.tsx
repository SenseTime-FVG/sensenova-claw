'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Zap, Play, Pause } from 'lucide-react';

const automations = [
  { id: 1, name: '自动整理每日邮件摘要', description: '每天早上9点自动生成昨日邮件摘要', status: 'active', lastRun: '今天 09:00', frequency: '每日' },
  { id: 2, name: '周报自动生成', description: '每周五下午生成本周工作总结', status: 'active', lastRun: '3月14日', frequency: '每周' },
  { id: 3, name: '重要邮件提醒', description: '检测到重要邮件时立即推送通知', status: 'paused', lastRun: '3月15日', frequency: '实时' },
];

export default function AutomationPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <h1 className="text-xl font-semibold text-foreground">自动化</h1>
              <Button className="gap-2" size="sm">
                <Zap className="w-4 h-4" />
                创建新自动化
              </Button>
            </div>

            <div className="space-y-3">
              {automations.map((auto) => (
                <Card key={auto.id} className="p-5 hover:shadow-md transition-shadow">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <Zap className="w-4 h-4 text-primary" />
                        <h3 className="font-medium text-foreground text-sm">{auto.name}</h3>
                        <Badge variant={auto.status === 'active' ? 'default' : 'secondary'} className="text-[10px]">
                          {auto.status === 'active' ? '运行中' : '已暂停'}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mb-2 ml-7">{auto.description}</p>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground ml-7">
                        <span>频率: {auto.frequency}</span>
                        <span>上次运行: {auto.lastRun}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {auto.status === 'active' ? (
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Pause className="w-3.5 h-3.5" />
                          暂停
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Play className="w-3.5 h-3.5" />
                          启动
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
