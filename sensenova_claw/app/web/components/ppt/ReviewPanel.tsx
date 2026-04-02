'use client';

/**
 * 审查报告面板 —— 右栏 Tab
 *
 * 展示 ppt-review 生成的质量审查结果：
 *   - 总体评分与摘要
 *   - 逐页问题列表
 *   - 一键修复按钮
 */

import { cn } from '@/lib/utils';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Wand2, ArrowRight,
} from 'lucide-react';

export interface PageIssue {
  page_number: number;
  page_title: string;
  severity: 'info' | 'warning' | 'error';
  category: string;       // 如 'style_deviation', 'content_missing', 'image_quality'
  description: string;
  suggested_skill: string; // 推荐触发的 skill
}

export interface ReviewReport {
  overall_score: number;      // 0-100
  overall_conclusion: string;
  page_issues: PageIssue[];
  strengths: string[];
  recommendations: string[];
}

function severityIcon(severity: PageIssue['severity']) {
  switch (severity) {
    case 'error':   return <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" />;
    case 'warning': return <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
    default:        return <CheckCircle2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
  }
}

function scoreColor(score: number) {
  if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
  if (score >= 60) return 'text-amber-600 dark:text-amber-400';
  return 'text-destructive';
}

function scoreRingColor(score: number) {
  if (score >= 80) return 'stroke-emerald-500';
  if (score >= 60) return 'stroke-amber-500';
  return 'stroke-destructive';
}

// ── 环形评分 ──

function ScoreRing({ score }: { score: number }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative w-16 h-16 shrink-0">
      <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="currentColor" strokeWidth="4" className="text-muted/40" />
        <circle
          cx="32" cy="32" r={radius}
          fill="none" strokeWidth="4" strokeLinecap="round"
          className={scoreRingColor(score)}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={cn('text-base font-bold', scoreColor(score))}>{score}</span>
      </div>
    </div>
  );
}

// ── 问题卡片 ──

function IssueCard({
  issue,
  onFix,
}: {
  issue: PageIssue;
  onFix?: (issue: PageIssue) => void;
}) {
  return (
    <div className="flex items-start gap-2 p-2.5 rounded-lg border border-border/40 hover:bg-muted/20 transition-colors">
      {severityIcon(issue.severity)}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-[10px] font-bold text-muted-foreground/60">P{issue.page_number}</span>
          <span className="text-[10px] text-muted-foreground/40">{issue.page_title}</span>
        </div>
        <div className="text-[11px] text-foreground/80 leading-relaxed">
          {issue.description}
        </div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground/60">
            {issue.category}
          </span>
          {onFix && (
            <button
              type="button"
              onClick={() => onFix(issue)}
              className="inline-flex items-center gap-1 text-[10px] font-medium text-primary hover:text-primary/80 transition-colors"
            >
              <Wand2 className="w-2.5 h-2.5" />
              修复
              <ArrowRight className="w-2.5 h-2.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 主面板 ──

export function ReviewPanel({
  review,
  onFixIssue,
}: {
  review: ReviewReport | null;
  onFixIssue?: (issue: PageIssue) => void;
}) {
  if (!review) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <ShieldCheck className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          审查报告将在生成完成后自动展示
        </p>
      </div>
    );
  }

  const pageIssues = review.page_issues || [];
  const strengths = review.strengths || [];
  const errorCount = pageIssues.filter(i => i.severity === 'error').length;
  const warningCount = pageIssues.filter(i => i.severity === 'warning').length;

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      {/* 评分卡 */}
      <div className="p-3 border-b border-border/40">
        <div className="flex items-center gap-3">
          <ScoreRing score={review.overall_score} />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-foreground/80 mb-1">整体评分</div>
            <div className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
              {review.overall_conclusion}
            </div>
            <div className="flex items-center gap-3 mt-1.5">
              {errorCount > 0 && (
                <span className="text-[10px] text-destructive font-medium">{errorCount} 错误</span>
              )}
              {warningCount > 0 && (
                <span className="text-[10px] text-amber-500 font-medium">{warningCount} 警告</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 亮点 */}
      {strengths.length > 0 && (
        <div className="px-3 py-2 border-b border-border/30">
          <div className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-1.5">亮点</div>
          <div className="space-y-1">
            {strengths.map((s, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px] text-foreground/70">
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" />
                <span>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 问题列表 */}
      <div className="flex-1 p-2 space-y-1.5">
        {pageIssues.length === 0 ? (
          <div className="text-center py-6">
            <CheckCircle2 className="w-8 h-8 text-emerald-400/30 mx-auto mb-2" />
            <p className="text-xs text-muted-foreground/50">无问题，质量通过</p>
          </div>
        ) : (
          pageIssues.map((issue, idx) => (
            <IssueCard key={idx} issue={issue} onFix={onFixIssue} />
          ))
        )}
      </div>
    </div>
  );
}
