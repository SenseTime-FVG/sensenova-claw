'use client';

import { Clock } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { CronJob } from '@/hooks/useDashboardData';
import type { ToneName } from './widgetTones';

interface ScheduledTasksProps {
  cronJobs: CronJob[];
}

function cronTone(job: CronJob): ToneName {
  if (job.running_at_ms) return 'blue';
  if (job.last_run_status === 'error') return 'amber';
  if (!job.enabled) return 'neutral';
  return 'emerald';
}

function cronStatusText(job: CronJob): string {
  if (job.running_at_ms) return '运行中';
  if (!job.enabled) return '已暂停';
  if (job.last_run_status === 'error') return '出错';
  if (job.last_run_status === 'ok') return '正常';
  return '等待中';
}

function cronTimeText(job: CronJob): string {
  if (job.running_at_ms) {
    const elapsed = Date.now() - job.running_at_ms;
    const sec = Math.floor(elapsed / 1000);
    return `${sec}s`;
  }
  if (job.next_run_at_ms) {
    const diff = job.next_run_at_ms - Date.now();
    if (diff <= 0) return '即将运行';
    const min = Math.floor(diff / 60000);
    if (min < 60) return `${min}m 后`;
    const hour = Math.floor(min / 60);
    return `${hour}h 后`;
  }
  if (job.last_run_at_ms) {
    return new Date(job.last_run_at_ms).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  return job.schedule_value;
}

function ScheduledTaskCard({ job }: { job: CronJob }) {
  const toneName = cronTone(job);
  const tone = getTone(toneName);

  return (
    <div className="relative overflow-hidden rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 shadow-[0_2px_8px_rgba(15,23,42,0.03)] dark:shadow-[0_2px_8px_rgba(0,0,0,0.12)] backdrop-blur-xl">
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface} opacity-40`} />
      <div className="relative z-10 flex items-start gap-2.5">
        <div className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${tone.dot} shadow-sm`} />
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-semibold text-[var(--glass-text)] truncate">{job.name || job.text}</div>
          <div className="mt-0.5 flex items-center gap-2">
            <span className="text-[10px] text-[var(--glass-text-muted)]">{cronStatusText(job)}</span>
            <span className="rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg)] px-1.5 py-[1px] text-[9px] font-medium shadow-sm text-[var(--glass-text-muted)]">
              {cronTimeText(job)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ScheduledTasks({ cronJobs }: ScheduledTasksProps) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-sky-50/70 via-background/90 to-cyan-50/50 dark:from-sky-950/30 dark:via-background/90 dark:to-cyan-950/20" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="定时任务"
          subtitle="执行状态"
          tag="Cron"
          tagTone="blue"
          icon={<Clock className="h-4 w-4 text-blue-500" />}
        />
        {cronJobs.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-[var(--glass-bg-light)]">
            <span className="text-[11px] text-muted-foreground">暂无定时任务</span>
          </div>
        ) : (
          <div className="flex-1 space-y-2 overflow-auto thin-scrollbar">
            {cronJobs.map(job => (
              <ScheduledTaskCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
