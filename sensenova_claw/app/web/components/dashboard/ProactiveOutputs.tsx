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
      className={`relative w-full overflow-hidden rounded-[24px] border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] p-4 text-left shadow-[0_14px_32px_rgba(15,23,42,0.05)] dark:shadow-[0_14px_32px_rgba(0,0,0,0.2)] backdrop-blur-xl transition duration-200 ${
        resolved ? 'opacity-50' : 'hover:-translate-y-0.5'
      }`}
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface}`} />
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-[var(--glass-text)]">{item.title}</div>
              {resolved && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  resolvedAction === 'accepted'
                    ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                    : 'bg-muted text-muted-foreground'
                }`}>
                  {resolvedAction === 'accepted' ? '已采纳' : '已忽略'}
                </span>
              )}
            </div>
            <div className="mt-2 text-xs leading-6 text-muted-foreground">{item.desc}</div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {/* 打钩/打叉按钮 */}
            {!resolved && (
              <>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onAccept?.(); }}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 shadow-sm transition hover:bg-emerald-100 dark:hover:bg-emerald-900/50 hover:scale-105"
                  title="采纳建议"
                >
                  <Check className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onReject?.(); }}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-900/30 text-rose-500 dark:text-rose-400 shadow-sm transition hover:bg-rose-100 dark:hover:bg-rose-900/50 hover:scale-105"
                  title="忽略建议"
                >
                  <X className="h-4 w-4" />
                </button>
              </>
            )}
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] text-xs text-muted-foreground shadow-sm transition hover:bg-[var(--glass-bg-heavy)]"
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
          <div className="rounded-[18px] border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] p-3 backdrop-blur-xl">
            <div className="space-y-2">
              {item.details.map(detail => (
                <div key={detail} className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                  <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${tone.dot}`} />
                  <span>{detail}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onAction?.('primary'); }}
                className="rounded-full border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] px-3 py-1.5 text-[11px] font-medium text-[var(--glass-text)] shadow-sm transition hover:bg-[var(--glass-bg)]"
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
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/70 via-background/90 to-purple-50/50 dark:from-violet-950/30 dark:via-background/90 dark:to-purple-950/20" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="主动建议"
          subtitle="Proactive Agent 今日建议"
          tag="Proactive"
          tagTone="violet"
          icon={<Lightbulb className="h-4 w-4 text-violet-500" />}
        />
        {items.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-[var(--glass-bg-light)]">
            <span className="text-[11px] text-muted-foreground">暂无主动建议</span>
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
