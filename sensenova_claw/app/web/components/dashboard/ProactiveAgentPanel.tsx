'use client';

import { Bot, Lightbulb, MessageCircleMore, MessageSquare, Search, Zap } from 'lucide-react';
import { getTone } from './widgetTones';
import { SectionHeader } from './SectionHeader';
import type { RecentOutput, RecommendationGroup, RecommendationItem } from '@/hooks/useDashboardData';

interface ProactiveAgentPanelProps {
  items: RecentOutput[];
  onItemClick?: (id: string) => void;
  // 推荐卡片
  recommendations?: RecommendationGroup[];
  onRecommendationClick?: (sourceSessionId: string, prompt: string) => void;
}

// 推荐卡片分类图标
function getRecommendationIcon(category?: string) {
  switch (category) {
    case 'research':
      return Search;
    case 'action':
      return Zap;
    case 'follow-up':
      return MessageCircleMore;
    default:
      return Lightbulb;
  }
}

function RecommendationCard({
  item,
  onClick,
}: {
  item: RecommendationItem;
  onClick: () => void;
}) {
  const Icon = getRecommendationIcon(item.category);
  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full text-left px-2.5 py-2 rounded-lg hover:bg-white/10 dark:hover:bg-white/5 transition-colors flex items-start gap-2"
    >
      <span className="mt-0.5 shrink-0 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg-heavy)] p-1">
        <Icon className="h-3.5 w-3.5 text-violet-500" />
      </span>
      <span className="text-[12px] leading-[1.4] text-[var(--glass-text)] group-hover:text-foreground line-clamp-2">
        {item.title}
      </span>
    </button>
  );
}

function ProactiveCard({ item, onClick }: { item: RecentOutput; onClick?: () => void }) {
  const tone = getTone(item.tone);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative w-full overflow-hidden rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 text-left shadow-[0_2px_12px_rgba(15,23,42,0.04)] dark:shadow-[0_2px_12px_rgba(0,0,0,0.15)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_6px_20px_rgba(0,0,0,0.25)]"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface} opacity-50`} />
      <div className={`absolute -right-4 -top-4 h-14 w-14 rounded-full ${tone.orb} blur-2xl`} />
      <div className="relative z-10">
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] shadow-sm">
            <MessageSquare className="h-2.5 w-2.5 text-violet-400" />
          </div>
          <span className="text-[10px] text-[var(--glass-text-muted)] truncate">{item.timeLabel}</span>
        </div>
        <div className="line-clamp-2 text-[12px] font-semibold leading-[1.35] text-[var(--glass-text)]">
          {item.title}
        </div>
        {item.preview && (
          <div className="mt-1 line-clamp-2 text-[10px] leading-[1.5] text-muted-foreground whitespace-pre-line">
            {item.preview}…
          </div>
        )}
      </div>
    </button>
  );
}

export function ProactiveAgentPanel({ items, onItemClick, recommendations, onRecommendationClick }: ProactiveAgentPanelProps) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/70 via-background/90 to-purple-50/50 dark:from-violet-950/30 dark:via-background/90 dark:to-purple-950/20" />
      <div className="relative z-10 flex h-full flex-col">
        <SectionHeader
          title="主动推送"
          subtitle={items.length > 0 ? `${items.length} 条推送` : 'proactive agent 今日建议'}
          tag="Proactive"
          tagTone="violet"
          icon={<Bot className="h-4 w-4 text-violet-500" />}
        />

        {recommendations && recommendations.length > 0 && (
          <div className="mb-3 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg-light)] p-2.5">
            <div className="mb-1.5 px-0.5 text-[11px] font-medium text-[var(--glass-text-muted)]">推荐操作</div>
            <div className="space-y-2">
              {recommendations.map(group => (
                <div key={group.sourceSessionId} className="space-y-1">
                  {group.items.map(item => (
                    <RecommendationCard
                      key={item.id}
                      item={item}
                      onClick={() => onRecommendationClick?.(group.sourceSessionId, item.prompt)}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {items.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-[var(--glass-bg-light)]">
            <div className="flex flex-col items-center gap-1.5">
              <Bot className="h-6 w-6 text-muted-foreground/30" />
              <span className="text-[11px] text-muted-foreground">暂无主动产出</span>
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
