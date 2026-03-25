'use client';

/**
 * Storyboard 大纲面板 —— 左栏
 *
 * 读取 storyboard.json，展示卡片式大纲视图。
 * 支持：
 *   - 每页一张卡片，显示标题、page_type、narrative_role
 *   - 点击选中跳转到对应幻灯片
 *   - 缩略图模式切换
 */

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import {
  GripVertical, Layers, LayoutList, Grid3x3,
  AlertCircle, ChevronRight, ChevronDown,
} from 'lucide-react';

// ── Storyboard 数据类型（对齐 skill schema） ──

export interface StoryboardPage {
  page_id: string;
  page_number: number;
  title: string;
  page_type: string;
  section: string;
  narrative_role: string;
  audience_takeaway: string;
  layout_intent: string;
  style_variant: string;
  content_blocks: { block_id: string; heading: string; summary: string }[];
  visual_requirements: string[];
  data_requirements: string[];
  asset_requirements: string[];
  unresolved_issues: string[];
  presenter_intent: string;
}

export interface Storyboard {
  schema_version: string;
  ppt_title: string;
  language: string;
  total_pages: number;
  mode: 'fast' | 'guided' | 'surgical';
  pages: StoryboardPage[];
}

// ── 页面类型颜色映射 ──

const PAGE_TYPE_COLORS: Record<string, string> = {
  cover:      'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  toc:        'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  section:    'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  content:    'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  chart:      'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  comparison: 'bg-orange-500/15 text-orange-600 dark:text-orange-400',
  timeline:   'bg-teal-500/15 text-teal-600 dark:text-teal-400',
  closing:    'bg-rose-500/15 text-rose-600 dark:text-rose-400',
};

function pageTypeColor(type: string): string {
  const key = type.toLowerCase();
  for (const [k, v] of Object.entries(PAGE_TYPE_COLORS)) {
    if (key.includes(k)) return v;
  }
  return 'bg-muted text-muted-foreground';
}

// ── 大纲卡片 ──

function OutlineCard({
  page,
  isActive,
  isExpanded,
  onToggleExpand,
  onClick,
}: {
  page: StoryboardPage;
  isActive: boolean;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onClick: () => void;
}) {
  const hasIssues = page.unresolved_issues.length > 0;
  const hasDetails = page.content_blocks.length > 0
    || page.audience_takeaway
    || page.narrative_role
    || page.visual_requirements.length > 0
    || page.unresolved_issues.length > 0;

  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleExpand();
  }, [onToggleExpand]);

  return (
    <div
      className={cn(
        'w-full text-left rounded-xl border transition-all duration-150 group',
        isActive
          ? 'border-primary/40 bg-primary/5 shadow-sm ring-1 ring-primary/20'
          : 'border-border/40 hover:border-border/60 hover:bg-muted/30',
      )}
    >
      {/* 卡片头部（点击选中页面） */}
      <button type="button" onClick={onClick} className="w-full text-left p-3 pb-1.5">
        <div className="flex items-start gap-2">
          <div className="flex items-center gap-1 shrink-0 mt-0.5">
            <GripVertical className="w-3 h-3 text-muted-foreground/30 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab" />
            <span className="text-[10px] font-bold text-muted-foreground/50 tabular-nums w-4 text-right">
              {page.page_number}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span className={cn(
                'text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded',
                pageTypeColor(page.page_type),
              )}>
                {page.page_type}
              </span>
              {hasIssues && (
                <AlertCircle className="w-3 h-3 text-amber-500 shrink-0" />
              )}
            </div>
            <div className="text-xs font-semibold text-foreground/90 truncate mb-0.5">
              {page.title}
            </div>
            {page.section && (
              <div className="text-[10px] text-muted-foreground/60 truncate">
                {page.section}
              </div>
            )}
          </div>
        </div>
      </button>

      {/* 内容块摘要 + 展开按钮 */}
      {hasDetails && (
        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={handleExpandClick}
            className="w-full flex items-center gap-1 text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors py-0.5"
          >
            {isExpanded
              ? <ChevronDown className="w-2.5 h-2.5 shrink-0" />
              : <ChevronRight className="w-2.5 h-2.5 shrink-0" />
            }
            <span>
              {page.content_blocks.length > 0
                ? `${page.content_blocks.length} 个内容块`
                : '查看详情'
              }
            </span>
          </button>

          {/* 收起状态：只显示前 2 个 heading */}
          {!isExpanded && page.content_blocks.length > 0 && (
            <div className="ml-3.5 space-y-0.5">
              {page.content_blocks.slice(0, 2).map(block => (
                <div key={block.block_id} className="flex items-center gap-1 text-[10px] text-muted-foreground/40">
                  <span className="w-1 h-1 rounded-full bg-muted-foreground/30 shrink-0" />
                  <span className="truncate">{block.heading}</span>
                </div>
              ))}
              {page.content_blocks.length > 2 && (
                <div className="text-[10px] text-muted-foreground/30">
                  +{page.content_blocks.length - 2} 更多
                </div>
              )}
            </div>
          )}

          {/* 展开状态：显示完整信息 */}
          {isExpanded && (
            <div className="ml-3.5 mt-1 space-y-2">
              {/* 内容块列表 */}
              {page.content_blocks.length > 0 && (
                <div className="space-y-1.5">
                  {page.content_blocks.map(block => (
                    <div key={block.block_id} className="space-y-0.5">
                      <div className="text-[10px] font-medium text-foreground/70">
                        {block.heading}
                      </div>
                      {block.summary && (
                        <div className="text-[10px] text-muted-foreground/50 leading-relaxed">
                          {block.summary}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 叙事角色 */}
              {page.narrative_role && (
                <DetailRow label="叙事角色" value={page.narrative_role} />
              )}

              {/* 受众收获 */}
              {page.audience_takeaway && (
                <DetailRow label="受众收获" value={page.audience_takeaway} />
              )}

              {/* 布局意图 */}
              {page.layout_intent && (
                <DetailRow label="布局意图" value={page.layout_intent} />
              )}

              {/* 视觉需求 */}
              {page.visual_requirements.length > 0 && (
                <DetailList label="视觉需求" items={page.visual_requirements} />
              )}

              {/* 数据需求 */}
              {page.data_requirements.length > 0 && (
                <DetailList label="数据需求" items={page.data_requirements} />
              )}

              {/* 未解决问题 */}
              {page.unresolved_issues.length > 0 && (
                <DetailList label="待解决" items={page.unresolved_issues} variant="warn" />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[9px] font-semibold text-muted-foreground/40 uppercase tracking-wider">{label}</div>
      <div className="text-[10px] text-muted-foreground/60 leading-relaxed">{value}</div>
    </div>
  );
}

function DetailList({ label, items, variant }: { label: string; items: string[]; variant?: 'warn' }) {
  return (
    <div>
      <div className="text-[9px] font-semibold text-muted-foreground/40 uppercase tracking-wider">{label}</div>
      <div className="space-y-0.5 mt-0.5">
        {items.map((item, i) => (
          <div key={i} className={cn(
            'flex items-start gap-1 text-[10px] leading-relaxed',
            variant === 'warn' ? 'text-amber-600/70 dark:text-amber-400/70' : 'text-muted-foreground/50',
          )}>
            <span className={cn(
              'w-1 h-1 rounded-full shrink-0 mt-1.5',
              variant === 'warn' ? 'bg-amber-500/50' : 'bg-muted-foreground/30',
            )} />
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 缩略图模式卡片 ──

function ThumbnailCard({
  page,
  isActive,
  onClick,
}: {
  page: StoryboardPage;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-lg border overflow-hidden transition-all duration-150',
        'aspect-[16/9] flex flex-col items-center justify-center p-2',
        isActive
          ? 'border-primary/50 ring-2 ring-primary/20 shadow-sm'
          : 'border-border/40 hover:border-border/60 opacity-70 hover:opacity-100',
      )}
    >
      <span className="text-[10px] font-bold text-muted-foreground/60 mb-0.5">
        {page.page_number}
      </span>
      <span className="text-[9px] text-foreground/70 text-center truncate w-full">
        {page.title}
      </span>
    </button>
  );
}

// ── 主面板 ──

type ViewMode = 'outline' | 'thumbnail';

export function StoryboardPanel({
  storyboard,
  activePage,
  onPageSelect,
}: {
  storyboard: Storyboard | null;
  activePage: number;
  onPageSelect: (pageNumber: number) => void;
}) {
  const [viewMode, setViewMode] = useState<ViewMode>('outline');
  const [expandedPages, setExpandedPages] = useState<Set<string>>(new Set());

  const toggleExpand = useCallback((pageId: string) => {
    setExpandedPages(prev => {
      const next = new Set(prev);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  }, []);

  if (!storyboard) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Layers className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          大纲将在 AI 生成 storyboard 后显示
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40 shrink-0">
        <div className="min-w-0">
          <div className="text-xs font-bold text-foreground/80 truncate">
            {storyboard.ppt_title}
          </div>
          <div className="text-[10px] text-muted-foreground/50">
            {storyboard.total_pages} 页 · {storyboard.mode} 模式
          </div>
        </div>
        <div className="flex items-center gap-0.5 bg-muted/50 rounded-md p-0.5">
          <button
            type="button"
            onClick={() => setViewMode('outline')}
            className={cn(
              'p-1 rounded transition-colors',
              viewMode === 'outline' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <LayoutList className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setViewMode('thumbnail')}
            className={cn(
              'p-1 rounded transition-colors',
              viewMode === 'thumbnail' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Grid3x3 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        {viewMode === 'outline' ? (
          <div className="space-y-1.5">
            {storyboard.pages.map(page => (
              <OutlineCard
                key={page.page_id}
                page={page}
                isActive={page.page_number === activePage}
                isExpanded={expandedPages.has(page.page_id)}
                onToggleExpand={() => toggleExpand(page.page_id)}
                onClick={() => onPageSelect(page.page_number)}
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-1.5">
            {storyboard.pages.map(page => (
              <ThumbnailCard
                key={page.page_id}
                page={page}
                isActive={page.page_number === activePage}
                onClick={() => onPageSelect(page.page_number)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
