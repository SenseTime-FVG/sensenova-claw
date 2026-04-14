'use client';

/**
 * 审查报告面板 —— 右栏 Tab
 *
 * 支持两种审查格式：
 * - 旧格式: { overall_score, overall_conclusion, page_issues, strengths, recommendations }
 * - 新格式 (schema_version: "1.0"): { overall_status, review_summary, task_satisfaction,
 *     style_execution, narrative_consistency, payload_budget_review, page_issues, recommended_actions }
 */

import { cn } from '@/lib/utils';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Wand2, ArrowRight, PackageCheck, Palette, BookOpen,
  LayoutGrid, ClipboardCheck,
} from 'lucide-react';

// ── 旧格式类型 ──

export interface PageIssue {
  page_number: number;
  page_title: string;
  severity: 'info' | 'warning' | 'error';
  category: string;
  description: string;
  suggested_skill: string;
}

export interface ReviewReport {
  // 旧格式字段
  overall_score?: number;
  overall_conclusion?: string;
  page_issues?: PageIssue[];
  strengths?: string[];
  recommendations?: string[];

  // 新格式字段 (schema_version: "1.0")
  schema_version?: string;
  overall_status?: string;
  review_summary?: {
    total_pages: number;
    pages_reviewed: number;
    issues_found: number;
    blocking_issues: number;
    minor_notes: number;
  };
  task_satisfaction?: {
    status: string;
    checks: Array<{ item: string; expected?: string; actual?: string; passed: boolean }>;
  };
  style_execution?: {
    status: string;
    checks: Array<{ item: string; detail?: string; passed: boolean }>;
  };
  narrative_consistency?: {
    status: string;
    checks: Array<{ item: string; page_id?: string; title_match?: boolean; content_match?: boolean }>;
  };
  payload_budget_review?: Array<{
    page_id: string;
    claim_count: number;
    structure_block_count?: number;
    evidence_count?: number;
    status: string;
  }>;
  recommended_actions?: string[];
  delivery_readiness?: string;
  next_step?: string;
}

// ── 工具函数 ──

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

// ── 问题卡片（旧格式）──

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

// ── 检查项行（新格式）──

function CheckRow({ passed, label, detail }: { passed: boolean; label: string; detail?: string }) {
  return (
    <div className="flex items-start gap-2 py-1">
      {passed
        ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
        : <XCircle className="w-3.5 h-3.5 text-destructive shrink-0 mt-0.5" />
      }
      <div className="flex-1 min-w-0">
        <span className="text-[11px] text-foreground/80">{label}</span>
        {detail && <div className="text-[10px] text-muted-foreground/60 mt-0.5 leading-relaxed">{detail}</div>}
      </div>
    </div>
  );
}

// ── 分组标题 ──

function SectionHeader({ icon, title, status }: { icon: React.ReactNode; title: string; status?: string }) {
  const isOk = status && (status === '符合' || status === '通过' || status === '满足' || status === '一致');
  return (
    <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
      <span className="text-muted-foreground/50">{icon}</span>
      <span className="text-[10px] font-bold text-foreground/60 uppercase tracking-wider flex-1">{title}</span>
      {status && (
        <span className={cn(
          'text-[9px] px-1.5 py-0.5 rounded font-medium',
          isOk ? 'bg-emerald-500/10 text-emerald-500' : 'bg-destructive/10 text-destructive'
        )}>
          {status}
        </span>
      )}
    </div>
  );
}

// ── 新格式审查面板 ──

function NewFormatReview({ review }: { review: ReviewReport }) {
  const summary = review.review_summary;
  const isPass = review.overall_status === '通过' || review.delivery_readiness === 'ready';

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      {/* 总体状态卡 */}
      <div className="p-3 border-b border-border/40">
        <div className="flex items-center gap-3">
          <div className={cn(
            'w-14 h-14 rounded-full flex items-center justify-center shrink-0 text-lg font-bold',
            isPass ? 'bg-emerald-500/10 text-emerald-500' : 'bg-destructive/10 text-destructive'
          )}>
            {isPass ? <ShieldCheck className="w-7 h-7" /> : <XCircle className="w-7 h-7" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-foreground/80 mb-1">
              审查结果：{review.overall_status}
            </div>
            {summary && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                <span className="text-[10px] text-muted-foreground">共 {summary.total_pages} 页</span>
                {summary.issues_found === 0
                  ? <span className="text-[10px] text-emerald-500">无问题</span>
                  : <span className="text-[10px] text-amber-500">{summary.issues_found} 个问题</span>
                }
                {summary.blocking_issues > 0 && (
                  <span className="text-[10px] text-destructive">{summary.blocking_issues} 阻塞</span>
                )}
              </div>
            )}
            {review.next_step && (
              <div className="text-[10px] text-muted-foreground/60 mt-1">
                下一步：{review.next_step}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 任务满足度 */}
      {review.task_satisfaction && (
        <div className="border-b border-border/30">
          <SectionHeader
            icon={<ClipboardCheck className="w-3.5 h-3.5" />}
            title="任务满足度"
            status={review.task_satisfaction.status}
          />
          <div className="px-3 pb-2">
            {review.task_satisfaction.checks.map((c, i) => (
              <CheckRow
                key={i}
                passed={c.passed}
                label={c.item}
                detail={c.expected && c.actual ? `期望：${c.expected}　实际：${c.actual}` : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* 风格执行 */}
      {review.style_execution && (
        <div className="border-b border-border/30">
          <SectionHeader
            icon={<Palette className="w-3.5 h-3.5" />}
            title="风格执行"
            status={review.style_execution.status}
          />
          <div className="px-3 pb-2">
            {review.style_execution.checks.map((c, i) => (
              <CheckRow key={i} passed={c.passed} label={c.item} detail={c.detail} />
            ))}
          </div>
        </div>
      )}

      {/* 叙事一致性 */}
      {review.narrative_consistency && (
        <div className="border-b border-border/30">
          <SectionHeader
            icon={<BookOpen className="w-3.5 h-3.5" />}
            title="叙事一致性"
            status={review.narrative_consistency.status}
          />
          <div className="px-3 pb-2">
            {review.narrative_consistency.checks.map((c, i) => (
              <CheckRow
                key={i}
                passed={!!(c.title_match && c.content_match)}
                label={c.item}
                detail={c.page_id}
              />
            ))}
          </div>
        </div>
      )}

      {/* 内容预算 */}
      {review.payload_budget_review && review.payload_budget_review.length > 0 && (
        <div className="border-b border-border/30">
          <SectionHeader
            icon={<LayoutGrid className="w-3.5 h-3.5" />}
            title="各页内容预算"
          />
          <div className="px-3 pb-2 space-y-1">
            {review.payload_budget_review.map((p, i) => {
              const ok = p.status === '满足';
              return (
                <div key={i} className="flex items-center gap-2 py-0.5">
                  {ok
                    ? <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    : <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
                  }
                  <span className="text-[10px] font-mono text-muted-foreground/60 w-16 shrink-0">{p.page_id}</span>
                  <span className="text-[10px] text-foreground/70 flex-1">
                    {p.claim_count} 核心点
                    {p.structure_block_count != null && `  ·  ${p.structure_block_count} 结构块`}
                  </span>
                  <span className={cn(
                    'text-[9px] px-1 py-0.5 rounded',
                    ok ? 'text-emerald-500 bg-emerald-500/10' : 'text-amber-500 bg-amber-500/10'
                  )}>
                    {p.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 页面级问题（如有） */}
      {review.page_issues && review.page_issues.length > 0 && (
        <div className="border-b border-border/30">
          <SectionHeader
            icon={<AlertTriangle className="w-3.5 h-3.5" />}
            title="页面问题"
          />
          <div className="px-2 pb-2 space-y-1.5">
            {review.page_issues.map((issue, idx) => (
              <IssueCard key={idx} issue={issue} />
            ))}
          </div>
        </div>
      )}

      {/* 建议动作 */}
      {review.recommended_actions && review.recommended_actions.length > 0 && (
        <div>
          <SectionHeader
            icon={<PackageCheck className="w-3.5 h-3.5" />}
            title="建议动作"
          />
          <div className="px-3 pb-3 space-y-1">
            {review.recommended_actions.map((a, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px] text-foreground/70">
                <ArrowRight className="w-3 h-3 text-primary/50 shrink-0 mt-0.5" />
                <span>{a}</span>
              </div>
            ))}
          </div>
        </div>
      )}
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

  // 检测新格式（有 schema_version 或 overall_status 字段）
  if (review.schema_version || review.overall_status) {
    return <NewFormatReview review={review} />;
  }

  // 旧格式
  const pageIssues = review.page_issues || [];
  const strengths = review.strengths || [];
  const errorCount = pageIssues.filter(i => i.severity === 'error').length;
  const warningCount = pageIssues.filter(i => i.severity === 'warning').length;

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      {/* 评分卡 */}
      <div className="p-3 border-b border-border/40">
        <div className="flex items-center gap-3">
          <ScoreRing score={review.overall_score ?? 0} />
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
