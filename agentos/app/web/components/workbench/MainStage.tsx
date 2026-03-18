'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, CheckCircle2, Clock, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TaskSummaryCard } from './TaskSummaryCard';
import { ResultCard } from './ResultCard';
import { authFetch, API_BASE } from '@/lib/authFetch';
import type { TaskState } from '@/hooks/useWorkbenchSession';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface CurrentTask {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

interface MainStageProps {
  state: TaskState;
  currentTask: CurrentTask | null;
  steps: StepItem[];
  result: string | null;
  onQuickTask?: (task: string) => void;
}

function getTitle(meta: string): string {
  try { return JSON.parse(meta).title || '未命名任务'; } catch { return '未命名任务'; }
}

function timeLabel(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

const taskTemplates = [
  { title: '回复重要邮件', desc: '自动分析收件箱，起草专业回复' },
  { title: '准备周会议题', desc: '基于本周日历和任务，生成议程' },
  { title: '总结项目进展', desc: '汇总文档和对话，生成周报草稿' },
  { title: '安排团队会议', desc: '检查成员日历，推荐最佳时间' },
];

export function MainStage({ state, currentTask, steps, result, onQuickTask }: MainStageProps) {
  const router = useRouter();
  const [recentSessions, setRecentSessions] = useState<SessionItem[]>([]);

  useEffect(() => {
    if (state === 'empty') {
      authFetch(`${API_BASE}/api/sessions`)
        .then((r) => r.json())
        .then((d) => setRecentSessions((d.sessions || []).slice(0, 5)))
        .catch(() => {});
    }
  }, [state]);

  // 空状态
  if (state === 'empty') {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">开始新任务</h2>
            <p className="text-muted-foreground text-sm mb-8">
              使用下方快捷动作快速开始，或描述你需要完成的任务
            </p>
          </div>

          {/* 任务模板 */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            {taskTemplates.map((tmpl, i) => (
              <Card
                key={i}
                className="p-4 hover:shadow-md transition-shadow cursor-pointer hover:border-primary/30"
                onClick={() => onQuickTask?.(tmpl.title)}
              >
                <h3 className="font-semibold text-foreground mb-1 text-sm">{tmpl.title}</h3>
                <p className="text-xs text-muted-foreground">{tmpl.desc}</p>
              </Card>
            ))}
          </div>

          {/* 最近任务 */}
          {recentSessions.length > 0 && (
            <div>
              <h3 className="font-semibold text-foreground mb-3 text-sm">最近任务</h3>
              <div className="space-y-2">
                {recentSessions.map((s) => (
                  <Card
                    key={s.session_id}
                    className="p-3 flex items-center justify-between hover:shadow-sm transition-shadow cursor-pointer"
                    onClick={() => router.push(`/chat?session=${s.session_id}`)}
                  >
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      <span className="text-sm text-foreground">{getTitle(s.meta)}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{timeLabel(s.last_active)}</span>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    );
  }

  // 执行中
  if (state === 'processing' && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />
          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <Loader2 className="w-5 h-5 text-primary animate-spin" />
              <h2 className="font-semibold text-foreground">正在执行</h2>
            </div>
            <div className="space-y-3">
              {steps.map((step, i) => (
                <div key={i} className="flex items-center gap-3">
                  {step.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                  {step.status === 'running' && (
                    <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  )}
                  {step.status === 'pending' && (
                    <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30" />
                  )}
                  <span className={`text-sm ${
                    step.status === 'done' ? 'text-muted-foreground' :
                    step.status === 'running' ? 'text-foreground' :
                    'text-muted-foreground/50'
                  }`}>
                    {step.label}
                  </span>
                </div>
              ))}
              {steps.length === 0 && (
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  <span className="text-sm text-foreground">正在分析任务...</span>
                </div>
              )}
            </div>
          </Card>
        </div>
      </main>
    );
  }

  // 已完成
  if (state === 'completed' && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />
          <ResultCard
            summary={result || '任务已完成'}
            nextActions={[
              { label: '开始新任务', onClick: () => window.location.reload() },
            ]}
          />
        </div>
      </main>
    );
  }

  return null;
}
