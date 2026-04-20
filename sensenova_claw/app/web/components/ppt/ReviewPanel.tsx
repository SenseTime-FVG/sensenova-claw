'use client';

/**
 * 审查报告面板 —— 右栏 Tab
 *
 * 支持两种审查格式：
 * - 旧格式: { overall_score, overall_conclusion, page_issues, strengths, recommendations }
 * - 新格式 (schema_version: "ppt-review.v1"): { status, can_export, summary, checks, issues, recommended_next_steps, notes }
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Wand2, ArrowRight, ChevronDown, ChevronRight,
  FileText, Ban,
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

// ── 新格式类型 (ppt-review.v1) ──

type ReviewStatus = '通过' | '有条件通过' | '阻塞';
type CheckStatus = 'pass' | 'warn' | 'fail' | 'not_applicable' | 'blocked';
type ReviewSeverity = 'warning' | 'blocking';
type IssueScope = 'deck' | 'page' | 'slot' | 'asset';
type NextStepPriority = 'high' | 'medium' | 'low';

interface ReviewEvidence {
  file: string;
  selector?: string | null;
  detail: string;
}

interface ReviewCheck {
  check_id: string;
  name: string;
  status: CheckStatus;
  summary: string;
  page_ids: string[];
  evidence: ReviewEvidence[];
}

interface ReviewIssue {
  issue_id: string;
  scope: IssueScope;
  page_id?: string | null;
  slot_id?: string | null;
  issue_type: string;
  severity: ReviewSeverity;
  title: string;
  detail: string;
  evidence: ReviewEvidence[];
  suggested_skill?: string | null;
  suggested_action: string;
  affected_files: string[];
}

interface ReviewNextStep {
  skill: string;
  reason: string;
  scope: IssueScope;
  page_ids: string[];
  slot_ids: string[];
  priority: NextStepPriority;
}

export interface ReviewReport {
  // 旧格式字段
  overall_score?: number;
  overall_conclusion?: string;
  page_issues?: PageIssue[];
  strengths?: string[];
  recommendations?: string[];

  // 新格式字段 (ppt-review.v1)
  schema_version?: string;
  deck_dir?: string;
  status?: ReviewStatus | string;
  can_export?: boolean;
  summary?: string;
  issue_count?: number;
  blocking_count?: number;
  warning_count?: number;
  missing_dependencies?: string[];
  checks?: ReviewCheck[];
  issues?: ReviewIssue[];
  recommended_next_steps?: ReviewNextStep[];
  notes?: string[];

  // 兼容旧版中间格式
  overall_status?: string;
  review_summary?: object;
  task_satisfaction?: object;
  style_execution?: object;
  narrative_consistency?: object;
  payload_budget_review?: unknown[];
  recommended_actions?: string[];
  delivery_readiness?: string;
  next_step?: string;
}

// ── 工具函数 ──

function severityIcon(severity: PageIssue['severity'] | ReviewSeverity) {
  switch (severity) {
    case 'error':
    case 'blocking':
      return <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" />;
    case 'warning':
      return <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
    default:
      return <CheckCircle2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
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

function checkStatusIcon(status: CheckStatus) {
  switch (status) {
    case 'pass':
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
    case 'warn':
      return <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
    case 'fail':
      return <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" />;
    case 'blocked':
      return <Ban className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0" />;
    case 'not_applicable':
      return <span className="w-3.5 h-3.5 shrink-0 text-center text-muted-foreground/40 text-[10px]">—</span>;
  }
}

function checkStatusLabel(status: CheckStatus) {
  switch (status) {
    case 'pass': return '通过';
    case 'warn': return '警告';
    case 'fail': return '失败';
    case 'blocked': return '阻塞';
    case 'not_applicable': return 'N/A';
  }
}

function statusBadgeClass(status: ReviewStatus | string) {
  switch (status) {
    case '通过':
      return 'bg-emerald-500/10 text-emerald-500';
    case '有条件通过':
      return 'bg-amber-500/10 text-amber-500';
    case '阻塞':
      return 'bg-destructive/10 text-destructive';
    default:
      return 'bg-muted/50 text-muted-foreground';
  }
}

function priorityLabel(priority: NextStepPriority) {
  switch (priority) {
    case 'high': return '高';
    case 'medium': return '中';
    case 'low': return '低';
  }
}

function priorityClass(priority: NextStepPriority) {
  switch (priority) {
    case 'high': return 'bg-destructive/10 text-destructive';
    case 'medium': return 'bg-amber-500/10 text-amber-500';
    case 'low': return 'bg-muted/50 text-muted-foreground';
  }
}

// ── 环形评分（旧格式）──

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

function LegacyIssueCard({
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

// ── 检查维度折叠卡（新格式）──

function CheckCard({ check }: { check: ReviewCheck }) {
  const [expanded, setExpanded] = useState(check.status === 'fail' || check.status === 'warn');
  const hasDetail = check.summary || check.evidence.length > 0 || check.page_ids.length > 0;

  return (
    <div className="border border-border/30 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => hasDetail && setExpanded(!expanded)}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-left transition-colors',
          hasDetail ? 'hover:bg-muted/20 cursor-pointer' : 'cursor-default',
        )}
      >
        {checkStatusIcon(check.status)}
        <span className="text-[11px] text-foreground/80 flex-1">{check.name}</span>
        <span className={cn(
          'text-[9px] px-1.5 py-0.5 rounded font-medium',
          check.status === 'pass' ? 'bg-emerald-500/10 text-emerald-500'
            : check.status === 'warn' ? 'bg-amber-500/10 text-amber-500'
            : check.status === 'fail' ? 'bg-destructive/10 text-destructive'
            : 'bg-muted/50 text-muted-foreground/60'
        )}>
          {checkStatusLabel(check.status)}
        </span>
        {hasDetail && (
          expanded
            ? <ChevronDown className="w-3 h-3 text-muted-foreground/40 shrink-0" />
            : <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
        )}
      </button>
      {expanded && hasDetail && (
        <div className="px-3 pb-2.5 pt-0.5 border-t border-border/20 space-y-1.5">
          {check.summary && (
            <div className="text-[10px] text-foreground/70 leading-relaxed">{check.summary}</div>
          )}
          {check.page_ids.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {check.page_ids.map((pid) => (
                <span key={pid} className="text-[9px] px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground/60 font-mono">
                  {pid}
                </span>
              ))}
            </div>
          )}
          {check.evidence.map((ev, i) => (
            <div key={i} className="text-[10px] text-muted-foreground/60 pl-2 border-l-2 border-border/30">
              {ev.file && <span className="font-mono text-[9px]">{ev.file}</span>}
              {ev.selector && <span className="text-[9px] text-muted-foreground/40 ml-1">{ev.selector}</span>}
              <div className="text-foreground/60 mt-0.5">{ev.detail}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Issue 卡片（新格式）──

function IssueCard({ issue }: { issue: ReviewIssue }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border/30 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-muted/20 transition-colors"
      >
        {severityIcon(issue.severity)}
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-foreground/80 font-medium">{issue.title}</div>
          <div className="flex items-center gap-2 mt-0.5">
            {issue.page_id && (
              <span className="text-[9px] font-mono text-muted-foreground/50">{issue.page_id}</span>
            )}
            <span className="text-[9px] px-1 py-0.5 rounded bg-muted/50 text-muted-foreground/60">
              {issue.issue_type}
            </span>
            <span className={cn(
              'text-[9px] px-1 py-0.5 rounded font-medium',
              issue.severity === 'blocking' ? 'bg-destructive/10 text-destructive' : 'bg-amber-500/10 text-amber-500'
            )}>
              {issue.severity === 'blocking' ? '阻塞' : '警告'}
            </span>
          </div>
        </div>
        {expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground/40 shrink-0 mt-1" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0 mt-1" />
        }
      </button>
      {expanded && (
        <div className="px-3 pb-2.5 pt-0.5 border-t border-border/20 space-y-1.5">
          <div className="text-[10px] text-foreground/70 leading-relaxed">{issue.detail}</div>
          {issue.suggested_action && (
            <div className="flex items-start gap-1.5 text-[10px] text-primary/80">
              <Wand2 className="w-3 h-3 shrink-0 mt-0.5" />
              <span>{issue.suggested_action}</span>
            </div>
          )}
          {issue.suggested_skill && (
            <span className="inline-block text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono">
              {issue.suggested_skill}
            </span>
          )}
          {issue.evidence.length > 0 && (
            <div className="space-y-1 mt-1">
              {issue.evidence.map((ev, i) => (
                <div key={i} className="text-[10px] text-muted-foreground/60 pl-2 border-l-2 border-border/30">
                  {ev.file && <span className="font-mono text-[9px]">{ev.file}</span>}
                  <div className="text-foreground/60 mt-0.5">{ev.detail}</div>
                </div>
              ))}
            </div>
          )}
          {issue.affected_files.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {issue.affected_files.map((f) => (
                <span key={f} className="text-[9px] px-1 py-0.5 rounded bg-muted/50 text-muted-foreground/50 font-mono">
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 新格式审查面板 (ppt-review.v1) ──

function V1ReviewPanel({ review }: { review: ReviewReport }) {
  const statusText = review.status || '未知';
  const isPass = statusText === '通过';
  const isBlock = statusText === '阻塞';
  const checks = review.checks || [];
  const issues = review.issues || [];
  const nextSteps = review.recommended_next_steps || [];
  const notes = review.notes || [];
  const missingDeps = review.missing_dependencies || [];

  const passCount = checks.filter(c => c.status === 'pass').length;
  const failCount = checks.filter(c => c.status === 'fail').length;
  const warnCount = checks.filter(c => c.status === 'warn').length;

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      {/* 总体状态卡 */}
      <div className="p-3 border-b border-border/40">
        <div className="flex items-center gap-3">
          <div className={cn(
            'w-14 h-14 rounded-full flex items-center justify-center shrink-0',
            isPass ? 'bg-emerald-500/10' : isBlock ? 'bg-destructive/10' : 'bg-amber-500/10'
          )}>
            {isPass
              ? <ShieldCheck className="w-7 h-7 text-emerald-500" />
              : isBlock
                ? <XCircle className="w-7 h-7 text-destructive" />
                : <AlertTriangle className="w-7 h-7 text-amber-500" />
            }
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-foreground/80">审查结果</span>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium', statusBadgeClass(statusText))}>
                {statusText}
              </span>
              {review.can_export && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500">可导出</span>
              )}
            </div>
            {review.summary && (
              <div className="text-[11px] text-muted-foreground leading-relaxed line-clamp-3">{review.summary}</div>
            )}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5">
              {review.issue_count != null && review.issue_count > 0 && (
                <span className="text-[10px] text-muted-foreground">{review.issue_count} 个问题</span>
              )}
              {review.blocking_count != null && review.blocking_count > 0 && (
                <span className="text-[10px] text-destructive">{review.blocking_count} 阻塞</span>
              )}
              {review.warning_count != null && review.warning_count > 0 && (
                <span className="text-[10px] text-amber-500">{review.warning_count} 警告</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 缺失依赖 */}
      {missingDeps.length > 0 && (
        <div className="px-3 py-2 border-b border-border/30 bg-destructive/5">
          <div className="text-[10px] font-bold text-destructive uppercase tracking-wider mb-1.5">缺失依赖</div>
          <div className="space-y-0.5">
            {missingDeps.map((dep, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[11px] text-destructive/80">
                <Ban className="w-3 h-3 shrink-0" />
                <span>{dep}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 检查维度 */}
      {checks.length > 0 && (
        <div className="border-b border-border/30">
          <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-muted-foreground/50" />
            <span className="text-[10px] font-bold text-foreground/60 uppercase tracking-wider flex-1">
              检查维度（{passCount}✓ {warnCount > 0 ? `${warnCount}⚠ ` : ''}{failCount > 0 ? `${failCount}✗` : ''}）
            </span>
          </div>
          <div className="px-2 pb-2 space-y-1">
            {checks.map((check) => (
              <CheckCard key={check.check_id} check={check} />
            ))}
          </div>
        </div>
      )}

      {/* 问题列表 */}
      {issues.length > 0 && (
        <div className="border-b border-border/30">
          <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-muted-foreground/50" />
            <span className="text-[10px] font-bold text-foreground/60 uppercase tracking-wider flex-1">
              问题（{issues.length}）
            </span>
          </div>
          <div className="px-2 pb-2 space-y-1">
            {issues.map((issue) => (
              <IssueCard key={issue.issue_id} issue={issue} />
            ))}
          </div>
        </div>
      )}

      {issues.length === 0 && checks.length > 0 && failCount === 0 && (
        <div className="text-center py-4 border-b border-border/30">
          <CheckCircle2 className="w-6 h-6 text-emerald-400/30 mx-auto mb-1" />
          <p className="text-[10px] text-muted-foreground/50">无问题</p>
        </div>
      )}

      {/* 建议下一步 */}
      {nextSteps.length > 0 && (
        <div className="border-b border-border/30">
          <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
            <Wand2 className="w-3.5 h-3.5 text-muted-foreground/50" />
            <span className="text-[10px] font-bold text-foreground/60 uppercase tracking-wider flex-1">建议修复</span>
          </div>
          <div className="px-3 pb-2.5 space-y-1.5">
            {nextSteps.map((step, i) => (
              <div key={i} className="flex items-start gap-2 py-1">
                <ArrowRight className="w-3 h-3 text-primary/50 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="text-[10px] font-mono text-primary/80">{step.skill}</span>
                    <span className={cn('text-[9px] px-1 py-0.5 rounded font-medium', priorityClass(step.priority))}>
                      {priorityLabel(step.priority)}
                    </span>
                  </div>
                  <div className="text-[10px] text-foreground/70">{step.reason}</div>
                  {step.page_ids.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {step.page_ids.map((pid) => (
                        <span key={pid} className="text-[9px] px-1 py-0.5 rounded bg-muted/50 text-muted-foreground/50 font-mono">
                          {pid}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 备注 */}
      {notes.length > 0 && (
        <div className="px-3 py-2.5">
          <div className="flex items-center gap-2 mb-1.5">
            <FileText className="w-3.5 h-3.5 text-muted-foreground/50" />
            <span className="text-[10px] font-bold text-foreground/60 uppercase tracking-wider">备注</span>
          </div>
          <div className="space-y-1">
            {notes.map((note, i) => (
              <div key={i} className="text-[10px] text-muted-foreground/70 leading-relaxed">{note}</div>
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

  // 新格式 ppt-review.v1（有 schema_version 含 "ppt-review" 或有 checks 数组）
  if (
    (review.schema_version && review.schema_version.startsWith('ppt-review'))
    || (review.checks && Array.isArray(review.checks))
  ) {
    return <V1ReviewPanel review={review} />;
  }

  // 旧版中间格式（有 overall_status 但没有 checks）
  if (review.overall_status || review.review_summary) {
    // 将旧中间格式映射为 v1 兼容展示
    return <V1ReviewPanel review={{
      ...review,
      status: review.overall_status || review.status,
      summary: review.next_step || review.summary || '',
      checks: [],
      issues: [],
      recommended_next_steps: (review.recommended_actions || []).map((a, i) => ({
        skill: 'ppt-page-polish' as string,
        reason: a,
        scope: 'deck' as IssueScope,
        page_ids: [],
        slot_ids: [],
        priority: 'medium' as NextStepPriority,
      })),
    }} />;
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
            <LegacyIssueCard key={idx} issue={issue} onFix={onFixIssue} />
          ))
        )}
      </div>
    </div>
  );
}
