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

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  GripVertical, Layers, LayoutList, Grid3x3,
  AlertCircle, ChevronRight,
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
  onClick,
}: {
  page: StoryboardPage;
  isActive: boolean;
  onClick: () => void;
}) {
  const hasIssues = page.unresolved_issues.length > 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-xl border p-3 transition-all duration-150 group',
        isActive
          ? 'border-primary/40 bg-primary/5 shadow-sm ring-1 ring-primary/20'
          : 'border-border/40 hover:border-border/60 hover:bg-muted/30',
      )}
    >
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
          {page.content_blocks.length > 0 && (
            <div className="mt-1.5 space-y-0.5">
              {page.content_blocks.slice(0, 2).map(block => (
                <div key={block.block_id} className="flex items-center gap-1 text-[10px] text-muted-foreground/50">
                  <ChevronRight className="w-2.5 h-2.5 shrink-0" />
                  <span className="truncate">{block.heading}</span>
                </div>
              ))}
              {page.content_blocks.length > 2 && (
                <div className="text-[10px] text-muted-foreground/30 pl-3.5">
                  +{page.content_blocks.length - 2} 更多
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
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
