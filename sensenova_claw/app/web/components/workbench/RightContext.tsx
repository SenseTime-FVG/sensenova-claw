'use client';

import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, FileText, Globe } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { useChatSession } from '@/contexts/ChatSessionContext';

export function RightContext() {
  const { steps, taskProgress } = useChatSession();

  const isCollapsed = steps.length === 0 && taskProgress.length === 0;
  const [expanded, setExpanded] = useState(!isCollapsed);

  useEffect(() => {
    if (!isCollapsed) setExpanded(true);
  }, [isCollapsed]);

  const hasContent = steps.length > 0 || taskProgress.length > 0;

  if (!hasContent && !expanded) return null;

  return (
    <aside className="h-full flex flex-col overflow-y-auto">
      <div className="p-4">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center justify-between w-full text-left mb-4"
        >
          <div>
            <h2 className="font-semibold text-foreground text-sm">AI 工作区</h2>
            <p className="text-xs text-muted-foreground">任务执行详情</p>
          </div>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
        </button>

        {expanded && (
          <div className="space-y-3">
            {steps.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">执行步骤</h3>
                <div className="space-y-2">
                  {steps.map((step, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <div className={cn(
                        'w-2 h-2 rounded-full shrink-0',
                        step.status === 'done' && 'bg-green-500',
                        step.status === 'running' && 'bg-blue-500 animate-pulse',
                        step.status === 'pending' && 'bg-muted-foreground/30'
                      )} />
                      <span className={cn(
                        'text-sm',
                        step.status === 'running' && 'text-foreground font-medium',
                        step.status === 'done' && 'text-muted-foreground dark:text-muted-foreground/80',
                        step.status === 'pending' && 'text-muted-foreground/50 dark:text-muted-foreground/40'
                      )}>
                        {step.label}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {taskProgress.length > 0 && (
              <Card className="p-4">
                <h3 className="font-semibold mb-3 text-xs text-muted-foreground uppercase tracking-wider">任务进度</h3>
                <div className="space-y-3">
                  {taskProgress.map((task, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div className={cn(
                        'w-2.5 h-2.5 rounded-full shrink-0',
                        task.status === 'completed' ? 'bg-muted-foreground/40' : 'bg-green-500'
                      )} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground truncate">{task.task}</p>
                      </div>
                      <span className="text-xs text-amber-600 dark:text-amber-400 font-medium shrink-0">
                        {task.step}/{task.total}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
