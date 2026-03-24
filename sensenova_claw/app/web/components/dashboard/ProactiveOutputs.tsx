'use client';

import { useState } from 'react';
import { Lightbulb, Check, X } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { ProactiveItem } from '@/hooks/useDashboardData';

interface ProactiveOutputsProps {
  items: ProactiveItem[];
  onAction?: (itemId: string, action: 'primary' | 'secondary') => void;
  onAccept?: (itemId: string) => void;
  onReject?: (itemId: string) => void;
}

function ProactiveWidget({
  item,
  expanded,
  onToggle,
  onAction,
  onAccept,
  onReject,
  resolved,
  resolvedAction,
}: {
  item: ProactiveItem;
  expanded: boolean;
  onToggle: () => void;
  onAction?: (action: 'primary' | 'secondary') => void;
  onAccept?: () => void;
  onReject?: () => void;
  resolved?: boolean;
  resolvedAction?: 'accepted' | 'rejected';
}) {
  const tone = getTone(item.tone);

  return (
    <div
      className={`relative w-full overflow-hidden rounded-[24px] border border-white/80 bg-white/75 p-4 text-left shadow-[0_14px_32px_rgba(15,23,42,0.05)] backdrop-blur-xl transition duration-200 ${
        resolved ? 'opacity-50' : 'hover:-translate-y-0.5'
      }`}
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface}`} />
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-neutral-900">{item.title}</div>
              {resolved && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  resolvedAction === 'accepted'
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-neutral-100 text-neutral-500'
                }`}>
                  {resolvedAction === 'accepted' ? '已采纳' : '已忽略'}
                </span>
              )}
            </div>
            <div className="mt-2 text-xs leading-6 text-neutral-500">{item.desc}</div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {/* 打钩/打叉按钮 */}
            {!resolved && (
              <>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onAccept?.(); }}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-600 shadow-sm transition hover:bg-emerald-100 hover:scale-105"
                  title="采纳建议"
                >
                  <Check className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onReject?.(); }}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-rose-200 bg-rose-50 text-rose-500 shadow-sm transition hover:bg-rose-100 hover:scale-105"
                  title="忽略建议"
                >
                  <X className="h-4 w-4" />
                </button>
              </>
            )}
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-white/80 bg-white/75 text-xs text-neutral-600 shadow-sm transition hover:bg-white"
            >
              {expanded ? '−' : '+'}
            </button>
          </div>
        </div>

        <div
          className={`overflow-hidden transition-all duration-300 ${
            expanded ? 'mt-4 max-h-[280px] opacity-100' : 'max-h-0 opacity-0'
          }`}
        >
          <div className="rounded-[18px] border border-white/80 bg-white/65 p-3 backdrop-blur-xl">
            <div className="space-y-2">
              {item.details.map(detail => (
                <div key={detail} className="flex items-start gap-2 text-xs leading-5 text-neutral-600">
                  <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${tone.dot}`} />
                  <span>{detail}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onAction?.('primary'); }}
                className="rounded-full border border-white/80 bg-white/78 px-3 py-1.5 text-[11px] font-medium text-neutral-700 shadow-sm transition hover:bg-white"
              >
                {item.primaryAction}
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onAction?.('secondary'); }}
                className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition hover:opacity-80 ${tone.pill}`}
              >
                {item.secondaryAction}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ProactiveOutputs({ items, onAction, onAccept, onReject }: ProactiveOutputsProps) {
  const [expandedIndex, setExpandedIndex] = useState(0);
  // 记录每个 item 的处理状态
  const [resolvedItems, setResolvedItems] = useState<Record<string, 'accepted' | 'rejected'>>({});

  const handleAccept = (itemId: string) => {
    setResolvedItems(prev => ({ ...prev, [itemId]: 'accepted' }));
    onAccept?.(itemId);
  };

  const handleReject = (itemId: string) => {
    setResolvedItems(prev => ({ ...prev, [itemId]: 'rejected' }));
    onReject?.(itemId);
  };

  return (
    <div className="flex h-full flex-col p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/70 via-white/90 to-purple-50/50" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="主动建议"
          subtitle="Proactive Agent 今日建议"
          tag="Proactive"
          tagTone="violet"
          icon={<Lightbulb className="h-4 w-4 text-violet-500" />}
        />
        {items.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-white/40">
            <span className="text-[11px] text-neutral-300">暂无主动建议</span>
          </div>
        ) : (
          <div className="flex-1 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 overflow-auto thin-scrollbar content-start">
            {items.map((item, index) => (
              <ProactiveWidget
                key={item.id}
                item={item}
                expanded={expandedIndex === index}
                onToggle={() => setExpandedIndex(expandedIndex === index ? -1 : index)}
                onAction={(action) => onAction?.(item.id, action)}
                onAccept={() => handleAccept(item.id)}
                onReject={() => handleReject(item.id)}
                resolved={!!resolvedItems[item.id]}
                resolvedAction={resolvedItems[item.id]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
