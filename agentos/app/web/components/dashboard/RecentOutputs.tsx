'use client';

import { Zap, MessageSquare } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { RecentOutput } from '@/hooks/useDashboardData';

interface RecentOutputsProps {
  items: RecentOutput[];
  onItemClick?: (id: string) => void;
}

function OutputCard({ item, onClick }: { item: RecentOutput; onClick?: () => void }) {
  const tone = getTone(item.tone);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative overflow-hidden rounded-xl border border-white/70 bg-white/65 p-3 text-left shadow-[0_2px_12px_rgba(15,23,42,0.04)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(15,23,42,0.08)]"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface} opacity-50`} />
      <div className={`absolute -right-4 -top-4 h-14 w-14 rounded-full ${tone.orb} blur-2xl`} />
      <div className="relative z-10">
        <div className="flex items-center gap-1.5 mb-2">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-white/80 bg-white/85 shadow-sm">
            <MessageSquare className="h-3 w-3 text-neutral-400" />
          </div>
          <span className={`rounded-full px-1.5 py-[1px] text-[9px] font-semibold ${tone.pill}`}>
            {item.agentName}
          </span>
        </div>
        <div className="line-clamp-2 text-[12px] font-semibold leading-[1.35] text-neutral-800">
          {item.title}
        </div>
        <div className="mt-1.5 text-[10px]" style={{ color: '#a1a1aa' }}>{item.timeLabel}</div>
      </div>
    </button>
  );
}

export function RecentOutputs({ items, onItemClick }: RecentOutputsProps) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-amber-50/60 via-white/90 to-orange-50/40" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="今日产出"
          subtitle="会话与结果"
          tag="Today"
          tagTone="amber"
          icon={<Zap className="h-4 w-4 text-amber-500" />}
        />

        {items.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-white/40">
            <span className="text-[11px] text-neutral-300">今日暂无产出</span>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto thin-scrollbar">
            <div className="grid grid-cols-2 gap-2.5">
              {items.map(item => (
                <OutputCard
                  key={item.id}
                  item={item}
                  onClick={() => onItemClick?.(item.id)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
