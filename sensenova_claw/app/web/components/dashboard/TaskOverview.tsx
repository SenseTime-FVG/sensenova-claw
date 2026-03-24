'use client';

import { getTone } from './widgetTones';
import type { ToneName } from './widgetTones';
import { GlassPanel } from './GlassPanel';
import { SectionHeader } from './SectionHeader';

interface SummaryItem {
  label: string;
  value: string;
  desc: string;
  icon: string;
  tone: ToneName;
}

interface TaskOverviewProps {
  activeCount: number;
  completedCount: number;
  pendingCount: number;
  reminderCount: number;
}

function SummaryCard({ item }: { item: SummaryItem }) {
  const tone = getTone(item.tone);

  return (
    <div className="relative overflow-hidden rounded-[26px] border border-white/80 bg-white/75 p-5 shadow-[0_14px_36px_rgba(15,23,42,0.05)] backdrop-blur-xl">
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface}`} />
      <div className={`absolute -right-8 -top-8 h-24 w-24 rounded-full ${tone.orb} blur-3xl`} />
      <div className="relative z-10 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">
            {item.label}
          </div>
          <div className="mt-3 text-4xl font-semibold tracking-tight text-neutral-900">
            {item.value}
          </div>
          <div className="mt-1 text-xs text-neutral-500">{item.desc}</div>
        </div>
        <div className="flex h-12 w-12 items-center justify-center rounded-[18px] border border-white/80 bg-white/75 text-lg shadow-sm backdrop-blur-xl">
          {item.icon}
        </div>
      </div>
    </div>
  );
}

export function TaskOverview({ activeCount, completedCount, pendingCount, reminderCount }: TaskOverviewProps) {
  const pad = (n: number) => String(n).padStart(2, '0');

  const items: SummaryItem[] = [
    { label: '进行中', value: pad(activeCount), desc: 'Agent 正在执行', icon: '◔', tone: 'blue' },
    { label: '已完成', value: pad(completedCount), desc: '支持完成提醒', icon: '✓', tone: 'emerald' },
    { label: '等待中', value: pad(pendingCount), desc: '待确认 / 待调度', icon: '⏸', tone: 'amber' },
    { label: '提醒', value: pad(reminderCount), desc: '到点通知 / 完成通知', icon: '🔔', tone: 'violet' },
  ];

  return (
    <GlassPanel tone="neutral" className="p-5">
      <SectionHeader
        title="任务概览"
        subtitle="将进行中、已完成、等待中与提醒统一放在顶部面板，减少来回扫视"
        tag="Overview"
        tagTone="neutral"
      />
      <div className="grid grid-cols-4 gap-4">
        {items.map(item => (
          <SummaryCard key={item.label} item={item} />
        ))}
      </div>
    </GlassPanel>
  );
}
