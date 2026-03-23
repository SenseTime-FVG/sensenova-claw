'use client';

import { LayoutDashboard } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { KanbanColumn, KanbanTask } from '@/hooks/useDashboardData';

interface KanbanBoardProps {
  columns: KanbanColumn[];
  onTaskClick?: (sessionId: string) => void;
}

function TaskCard({
  task,
  tone,
  onClick,
}: {
  task: KanbanTask;
  tone: ReturnType<typeof getTone>;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-white/70 bg-white/65 p-3 text-left shadow-[0_2px_8px_rgba(15,23,42,0.03)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_4px_16px_rgba(15,23,42,0.07)]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-neutral-800">{task.title}</div>
          <div className="mt-0.5 text-[11px]" style={{ color: '#94a3b8' }}>{task.owner}</div>
        </div>
        {task.action && (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${tone.pill}`}>
            {task.action}
          </span>
        )}
      </div>

      {task.meta && (
        <div className="mt-1.5 text-[11px] leading-4" style={{ color: '#94a3b8' }}>{task.meta}</div>
      )}

      {typeof task.progress === 'number' && (
        <div className="mt-2">
          <div className="mb-1 flex items-center justify-between text-[10px]" style={{ color: '#94a3b8' }}>
            <span>进度</span>
            <span className="font-medium">{task.progress}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-black/[0.04]">
            <div
              className={`h-1.5 rounded-full ${tone.progress} transition-all duration-500`}
              style={{ width: `${task.progress}%` }}
            />
          </div>
        </div>
      )}

      {task.checklist && (
        <div className="mt-2 space-y-1">
          {task.checklist.map(item => (
            <div key={item} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
              <div className="h-3.5 w-3.5 rounded border border-neutral-200 bg-white/80" />
              <span>{item}</span>
            </div>
          ))}
        </div>
      )}
    </button>
  );
}

export function KanbanBoard({ columns, onTaskClick }: KanbanBoardProps) {
  return (
    <div className="flex h-full flex-col p-4 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-slate-50/80 via-white/90 to-zinc-50/60" />
      <div className="relative z-10 flex h-full flex-col min-h-0">
        <SectionHeader
          title="任务看板"
          subtitle="实时概览"
          tag="Board"
          tagTone="neutral"
          icon={<LayoutDashboard className="h-4 w-4 text-slate-500" />}
        />

        <div className="flex-1 min-h-0 overflow-x-auto overflow-y-auto thin-scrollbar">
          <div className="inline-flex gap-3" style={{ minWidth: 'max-content' }}>
            {columns.map(column => {
              const tone = getTone(column.tone);
              return (
                <div
                  key={column.title}
                  className="flex w-[200px] shrink-0 flex-col rounded-xl border border-black/[0.03] bg-white/50 p-3"
                >
                  <div className="mb-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <div className={`h-2 w-2 rounded-full ${tone.dot}`} />
                      <div className="text-[12px] font-semibold text-neutral-700">{column.title}</div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${tone.pill}`}>
                      {column.tasks.length}
                    </span>
                  </div>

                  <div className="flex-1 space-y-2">
                    {column.tasks.length === 0 ? (
                      <div className="flex h-full min-h-[60px] items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-white/40">
                        <span className="text-[11px] text-neutral-300">空</span>
                      </div>
                    ) : (
                      column.tasks.map(task => (
                        <TaskCard
                          key={task.sessionId}
                          task={task}
                          tone={tone}
                          onClick={() => onTaskClick?.(task.sessionId)}
                        />
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
