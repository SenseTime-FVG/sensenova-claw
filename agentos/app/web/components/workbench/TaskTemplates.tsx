'use client';

import { Sparkles } from 'lucide-react';
import { Card } from '@/components/ui/card';

const taskTemplates = [
  { title: '回复重要邮件', desc: '自动分析收件箱，起草专业回复' },
  { title: '准备周会议题', desc: '基于本周日历和任务，生成议程' },
  { title: '总结项目进展', desc: '汇总文档和对话，生成周报草稿' },
  { title: '安排团队会议', desc: '检查成员日历，推荐最佳时间' },
];

interface TaskTemplatesProps {
  onQuickTask: (message: string) => void;
}

export function TaskTemplates({ onQuickTask }: TaskTemplatesProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Sparkles className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">开始新任务</h2>
          <p className="text-muted-foreground text-sm mb-8">
            使用下方快捷动作快速开始，或在下方输入框描述你需要完成的任务
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {taskTemplates.map((tmpl, i) => (
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
