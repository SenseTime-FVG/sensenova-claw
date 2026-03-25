'use client';

/**
 * PPT 流水线进度条 —— 展示当前 deck 生成进度
 *
 * 从 deck_dir 中读取各阶段产物是否存在来推断进度：
 *   task-pack.json  → 任务分析
 *   research-pack   → 素材研究
 *   style-spec.json → 风格定义
 *   storyboard.json → 大纲编排
 *   asset-plan.json → 资产准备
 *   pages/          → 页面生成
 *   review.json     → 质量审查
 */

import { cn } from '@/lib/utils';
import {
  ClipboardList, Search, Palette, BookOpen, Image, FileText, ShieldCheck,
  Check, Loader2, ArrowRight,
} from 'lucide-react';

export type StageStatus = 'pending' | 'active' | 'done' | 'error';

export interface PipelineStage {
  id: string;
  label: string;
  status: StageStatus;
}

const STAGE_META: Record<string, { icon: React.ElementType; color: string }> = {
  'task-pack':    { icon: ClipboardList, color: 'text-blue-500' },
  'research':     { icon: Search,        color: 'text-amber-500' },
  'style-spec':   { icon: Palette,       color: 'text-violet-500' },
  'storyboard':   { icon: BookOpen,      color: 'text-sky-500' },
  'asset-plan':   { icon: Image,         color: 'text-emerald-500' },
  'page-html':    { icon: FileText,      color: 'text-rose-500' },
  'review':       { icon: ShieldCheck,   color: 'text-teal-500' },
};

export const DEFAULT_STAGES: PipelineStage[] = [
  { id: 'task-pack',  label: '任务分析', status: 'pending' },
  { id: 'research',   label: '素材研究', status: 'pending' },
  { id: 'style-spec', label: '风格定义', status: 'pending' },
  { id: 'storyboard', label: '大纲编排', status: 'pending' },
  { id: 'asset-plan', label: '资产准备', status: 'pending' },
  { id: 'page-html',  label: '页面生成', status: 'pending' },
  { id: 'review',     label: '质量审查', status: 'pending' },
];

function statusBg(status: StageStatus) {
  switch (status) {
    case 'done':   return 'bg-emerald-500';
    case 'active': return 'bg-primary animate-pulse';
    case 'error':  return 'bg-destructive';
    default:       return 'bg-muted-foreground/20';
  }
}

export function PipelineProgress({
  stages,
  compact = false,
  onStageClick,
}: {
  stages: PipelineStage[];
  compact?: boolean;
  onStageClick?: (stageId: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto scrollbar-none px-1">
      {stages.map((stage, idx) => {
        const meta = STAGE_META[stage.id] || { icon: FileText, color: 'text-muted-foreground' };
        const Icon = meta.icon;
        const isDone = stage.status === 'done';
        const isActive = stage.status === 'active';
        const isError = stage.status === 'error';

        return (
          <div key={stage.id} className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => onStageClick?.(stage.id)}
              disabled={!onStageClick}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all',
                'disabled:cursor-default',
                isDone && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                isActive && 'bg-primary/10 text-primary ring-1 ring-primary/30',
                isError && 'bg-destructive/10 text-destructive',
                !isDone && !isActive && !isError && 'text-muted-foreground/60',
                onStageClick && !compact && 'hover:bg-muted/60 cursor-pointer',
              )}
            >
              {isDone ? (
                <Check className="w-3 h-3" />
              ) : isActive ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Icon className={cn('w-3 h-3', !isDone && !isActive && !isError && 'opacity-40')} />
              )}
              {!compact && <span>{stage.label}</span>}
              {compact && (
                <span className="sr-only">{stage.label}</span>
              )}
            </button>
            {idx < stages.length - 1 && (
              <ArrowRight className={cn(
                'w-2.5 h-2.5 shrink-0',
                isDone ? 'text-emerald-400/50' : 'text-muted-foreground/20',
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** 从 deck 的文件列表推断流水线进度 */
export function inferStagesFromFiles(fileNames: string[]): PipelineStage[] {
  const has = (pattern: string) => fileNames.some(f => f.includes(pattern));
  const stages = DEFAULT_STAGES.map(s => ({ ...s }));

  if (has('task-pack'))    stages[0].status = 'done';
  if (has('research-pack')) stages[1].status = 'done';
  if (has('style-spec'))   stages[2].status = 'done';
  if (has('storyboard'))   stages[3].status = 'done';
  if (has('asset-plan'))   stages[4].status = 'done';
  if (has('page_'))        stages[5].status = 'done';
  if (has('review'))       stages[6].status = 'done';

  // 找到第一个未完成的阶段标记为 active
  const firstPending = stages.findIndex(s => s.status === 'pending');
  if (firstPending > 0) {
    stages[firstPending].status = 'active';
  }

  return stages;
}
