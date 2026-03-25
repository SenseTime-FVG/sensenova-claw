'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  Image as ImageIcon, Check, X, AlertTriangle,
  ExternalLink, ChevronDown, ChevronRight, Search,
} from 'lucide-react';
import type { AssetPlan, AssetSlot } from '@/hooks/useDeckData';
import { API_BASE } from '@/lib/authFetch';

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  selected:   { label: '已选定', color: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/15', icon: Check },
  unresolved: { label: '未解决', color: 'text-amber-600 dark:text-amber-400 bg-amber-500/15',      icon: AlertTriangle },
  skipped:    { label: '已跳过', color: 'text-muted-foreground bg-muted/50',                        icon: X },
};

function statusInfo(status: string) {
  const key = status.toLowerCase();
  for (const [k, v] of Object.entries(STATUS_CONFIG)) {
    if (key.includes(k)) return v;
  }
  return { label: status, color: 'text-muted-foreground bg-muted/50', icon: ImageIcon };
}

function SlotCard({ slot, deckDir }: { slot: AssetSlot; deckDir: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const info = statusInfo(slot.status);
  const StatusIcon = info.icon;

  const localImageUrl = slot.selected_image?.local_path && deckDir
    ? `${API_BASE}/api/files/workdir/${deckDir}/${slot.selected_image.local_path.replace(/^.*?images\//, 'images/')}`
    : null;

  return (
    <div className={cn(
      'rounded-xl border transition-all duration-150',
      slot.selected
        ? 'border-emerald-500/30 bg-emerald-500/5'
        : slot.status === 'unresolved'
          ? 'border-amber-500/30 bg-amber-500/5'
          : 'border-border/40',
    )}>
      {/* 头部 */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full text-left p-3 flex items-start gap-2"
      >
        {/* 缩略图 */}
        <div className="w-10 h-10 rounded-lg bg-muted/50 border border-border/30 shrink-0 overflow-hidden flex items-center justify-center">
          {localImageUrl ? (
            <img
              src={localImageUrl}
              alt={slot.purpose}
              className="w-full h-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          ) : (
            <ImageIcon className="w-4 h-4 text-muted-foreground/30" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={cn(
              'text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded inline-flex items-center gap-0.5',
              info.color,
            )}>
              <StatusIcon className="w-2.5 h-2.5" />
              {info.label}
            </span>
            <span className="text-[9px] text-muted-foreground/40">{slot.page_title}</span>
          </div>
          <div className="text-[11px] font-medium text-foreground/80 truncate">
            {slot.purpose}
          </div>
          {slot.query && (
            <div className="flex items-center gap-1 text-[10px] text-muted-foreground/50 mt-0.5">
              <Search className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{slot.query}</span>
            </div>
          )}
        </div>

        <div className="shrink-0 mt-1">
          {expanded
            ? <ChevronDown className="w-3 h-3 text-muted-foreground/40" />
            : <ChevronRight className="w-3 h-3 text-muted-foreground/40" />
          }
        </div>
      </button>

      {/* 展开详情 */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-border/20 pt-2">
          {/* 已选图片 */}
          {slot.selected_image && (
            <div className="space-y-1">
              <div className="text-[9px] font-semibold text-muted-foreground/40 uppercase tracking-wider">已选图片</div>
              <div className="rounded-lg border border-border/30 overflow-hidden">
                {localImageUrl && (
                  <img
                    src={localImageUrl}
                    alt={slot.selected_image.title}
                    className="w-full max-h-36 object-contain bg-muted/20"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                )}
                <div className="px-2 py-1.5 space-y-0.5">
                  <div className="text-[10px] font-medium text-foreground/70 truncate">
                    {slot.selected_image.title}
                  </div>
                  {slot.selected_image.source_domain && (
                    <div className="flex items-center gap-1 text-[9px] text-muted-foreground/40">
                      <ExternalLink className="w-2.5 h-2.5" />
                      <span className="truncate">{slot.selected_image.source_domain}</span>
                    </div>
                  )}
                  {slot.selected_image.local_path && (
                    <div className="text-[9px] text-muted-foreground/30 truncate">
                      {slot.selected_image.local_path}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 搜索说明 */}
          {slot.source_caption && (
            <div>
              <div className="text-[9px] font-semibold text-muted-foreground/40 uppercase tracking-wider">描述</div>
              <div className="text-[10px] text-muted-foreground/60 leading-relaxed">{slot.source_caption}</div>
            </div>
          )}

          {/* 失败原因 */}
          {slot.reason && slot.status !== 'selected' && (
            <div>
              <div className="text-[9px] font-semibold text-amber-500/60 uppercase tracking-wider">原因</div>
              <div className="text-[10px] text-amber-600/70 dark:text-amber-400/70 leading-relaxed">{slot.reason}</div>
            </div>
          )}

          {/* 被拒候选 */}
          {Array.isArray(slot.rejected_candidates) && slot.rejected_candidates.length > 0 && (
            <div>
              <div className="text-[9px] font-semibold text-muted-foreground/40 uppercase tracking-wider">
                被拒候选 ({slot.rejected_candidates.length})
              </div>
              <div className="space-y-1 mt-0.5">
                {slot.rejected_candidates.slice(0, 3).map((c, i) => (
                  <div key={i} className="flex items-start gap-1 text-[10px] text-muted-foreground/40">
                    <X className="w-2.5 h-2.5 shrink-0 mt-0.5 text-red-400/50" />
                    <span className="leading-relaxed">
                      <span className="text-muted-foreground/30">[{c.rejection_stage}]</span>{' '}
                      {c.reason}
                    </span>
                  </div>
                ))}
                {slot.rejected_candidates.length > 3 && (
                  <div className="text-[9px] text-muted-foreground/30 pl-3.5">
                    +{slot.rejected_candidates.length - 3} 更多
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AssetPanel({
  assetPlan,
  deckDir,
}: {
  assetPlan: AssetPlan | null;
  deckDir: string | null;
}) {
  if (!assetPlan) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <ImageIcon className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          资产计划将在 AI 完成资产规划后显示
        </p>
      </div>
    );
  }

  const selectedCount = assetPlan.slots.filter(s => s.selected).length;
  const unresolvedCount = assetPlan.slots.filter(s => s.status === 'unresolved').length;

  return (
    <div className="flex flex-col h-full">
      {/* 头部统计 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40 shrink-0">
        <div className="min-w-0">
          <div className="text-xs font-bold text-foreground/80">
            资产计划
          </div>
          <div className="text-[10px] text-muted-foreground/50">
            {assetPlan.slots.length} 个槽位
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selectedCount > 0 && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-medium">
              {selectedCount} 已选
            </span>
          )}
          {unresolvedCount > 0 && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium">
              {unresolvedCount} 待解决
            </span>
          )}
        </div>
      </div>

      {/* 资产槽位列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5 scrollbar-thin">
        {assetPlan.slots.map(slot => (
          <SlotCard key={slot.slot_id} slot={slot} deckDir={deckDir} />
        ))}
      </div>
    </div>
  );
}
