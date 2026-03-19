'use client';

import { useCallback, useEffect, useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';

import {
  Bell, Clock, CheckCircle2, XCircle, AlertCircle, Loader2, RefreshCw,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface CronRunItem {
  id: number;
  job_id: string;
  job_name: string;
  text: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  status: string | null;
  error: string | null;
  duration_ms: number | null;
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (isToday) return `今天 ${time}`;
  if (isYesterday) return `昨天 ${time}`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' ' + time;
}

function StatusIcon({ status }: { status: string | null }) {
  if (status === 'ok') return <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />;
  if (status === 'error') return <XCircle className="w-4 h-4 text-destructive shrink-0" />;
  if (status === 'running') return <Loader2 className="w-4 h-4 text-primary animate-spin shrink-0" />;
  return <AlertCircle className="w-4 h-4 text-muted-foreground shrink-0" />;
}

function AutomationEmptyState() {
  const [runs, setRuns] = useState<CronRunItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/api/cron/runs?limit=50`);
      const data = await res.json();
      setRuns(data.runs || []);
    } catch {
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRuns(); }, [fetchRuns]);

  return (
    <div className="flex-1 flex flex-col p-6">
      <div className="max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Bell className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">定时提醒记录</h2>
              <p className="text-xs text-muted-foreground">通过 cron_manage 创建的定时任务提醒消息</p>
            </div>
          </div>
          <button
            onClick={fetchRuns}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">加载提醒记录…</span>
          </div>
        ) : runs.length === 0 ? (
          <div className="text-center py-16">
            <Clock className="w-12 h-12 text-muted-foreground/15 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground/50">暂无定时提醒记录</p>
            <p className="text-xs text-muted-foreground/40 mt-1">在下方输入框使用对话创建定时提醒</p>
          </div>
        ) : (
          <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 320px)' }}>
            {runs.map((run) => (
              <div
                key={run.id}
                className={cn(
                  'flex items-start gap-3 rounded-xl px-4 py-3 border transition-colors',
                  run.status === 'error'
                    ? 'border-destructive/20 bg-destructive/5'
                    : 'border-border/40 bg-card/60 hover:bg-muted/40',
                )}
              >
                <StatusIcon status={run.status} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-foreground truncate">{run.job_name}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 shrink-0">
                      {run.status || 'unknown'}
                    </Badge>
                  </div>
                  {run.text && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{run.text}</p>
                  )}
                  {run.error && (
                    <p className="text-[11px] text-destructive mt-1 line-clamp-1">{run.error}</p>
                  )}
                </div>
                <span className="text-[11px] text-muted-foreground/60 shrink-0 pt-0.5 whitespace-nowrap">
                  {formatTime(run.started_at_ms)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AutomationPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell agentFilter="default">
        <ChatPanel
          defaultAgentId="default"
          lockAgent
          emptyState={<AutomationEmptyState />}
        />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
