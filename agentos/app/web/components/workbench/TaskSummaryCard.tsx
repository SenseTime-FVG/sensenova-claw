'use client';

import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface TaskSummaryCardProps {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

const statusConfig = {
  idle: { label: '待处理', className: 'bg-muted text-muted-foreground' },
  running: { label: '执行中', className: 'bg-blue-500/10 text-blue-600 border-blue-500/20' },
  completed: { label: '已完成', className: 'bg-green-500/10 text-green-600 border-green-500/20' },
  error: { label: '失败', className: 'bg-red-500/10 text-red-600 border-red-500/20' },
};

export function TaskSummaryCard({ title, goal, stage, status }: TaskSummaryCardProps) {
  const config = statusConfig[status];

  return (
    <Card className="p-6 mb-6">
      <div className="flex items-start justify-between mb-3">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        <Badge variant="outline" className={cn('text-xs', config.className)}>
          {config.label}
        </Badge>
      </div>
      <p className="text-foreground/80 text-sm mb-2">{goal}</p>
      <p className="text-xs text-muted-foreground">当前阶段：{stage}</p>
    </Card>
  );
}
