'use client';

import { Bot, MessageSquare } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { RecentOutput } from '@/hooks/useDashboardData';

interface ProactiveAgentPanelProps {
  items: RecentOutput[];
  onItemClick?: (id: string) => void;
}

function ProactiveCard({ item, onClick }: { item: RecentOutput; onClick?: () => void }) {
  const tone = getTone(item.tone);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative w-full overflow-hidden rounded-xl border border-white/70 bg-white/65 p-3 text-left shadow-[0_2px_12px_rgba(15,23,42,0.04)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(15,23,42,0.08)]"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface} opacity-50`} />
      <div className={`absolute -right-4 -top-4 h-14 w-14 rounded-full ${tone.orb} blur-2xl`} />
      <div className="relative z-10">
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-white/80 bg-white/85 shadow-sm">
            <MessageSquare className="h-2.5 w-2.5 text-violet-400" />
          </div>
          <span className="text-[10px] text-neutral-400 truncate">{item.timeLabel}</span>
        </div>
        <div className="line-clamp-2 text-[12px] font-semibold leading-[1.35] text-neutral-800">
          {item.title}
        </div>
        {item.preview && (
          <div className="mt-1 line-clamp-2 text-[10px] leading-[1.5] text-neutral-500 whitespace-pre-line">
            {item.preview}…
          </div>
        )}
      </div>
    </button>
  );
}

export function ProactiveAgentPanel({ items, onItemClick }: ProactiveAgentPanelProps) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/70 via-white/90 to-purple-50/50" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="主动推送"
          subtitle="proactive agent 今日建议"
          tag="Proactive"
          tagTone="violet"
          icon={<Bot className="h-4 w-4 text-violet-500" />}
        />

        {items.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-white/40">
            <div className="flex flex-col items-center gap-1.5">
              <Bot className="h-6 w-6 text-neutral-200" />
              <span className="text-[11px] text-neutral-300">暂无主动产出</span>
            </div>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto thin-scrollbar">
            <div className="space-y-2">
              {items.map(item => (
                <ProactiveCard
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
