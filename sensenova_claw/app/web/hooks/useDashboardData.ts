'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { authGet, API_BASE } from '@/lib/authFetch';
import { useSession, useMessages } from '@/contexts/ws';
import type { ProactiveResultItem } from '@/contexts/ws/MessageContext';

// ── 类型定义 ──

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  status: string;
  sessionCount: number;
  lastActive: string;
  tools: string[];
  skills: string[];
}

export interface CronJob {
  id: string;
  name: string;
  description: string;
  schedule_type: string;
  schedule_value: string;
  text: string;
  enabled: boolean;
  next_run_at_ms: number | null;
  running_at_ms: number | null;
  last_run_at_ms: number | null;
  last_run_status: 'ok' | 'error' | 'skipped' | null;
  last_error: string | null;
  last_duration_ms: number | null;
}

export interface CronRun {
  id: number;
  job_id: string;
  job_name: string;
  text: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  status: 'ok' | 'error' | 'running' | null;
  error: string | null;
  duration_ms: number | null;
}

export interface KanbanTask {
  sessionId: string;
  title: string;
  owner: string;
  meta: string;
  progress?: number;
  action?: string;
  checklist?: string[];
}

export interface KanbanColumn {
  title: string;
  tone: 'blue' | 'amber' | 'emerald';
  tasks: KanbanTask[];
}

export interface RecentOutput {
  id: string;
  title: string;
  agentName: string;
  timeLabel: string;
  tone: 'blue' | 'emerald' | 'amber' | 'violet' | 'neutral';
  /** agent 最终输出的 markdown 预览（长度 > 100 时截取前 150 字符） */
  preview?: string;
}

export interface ProactiveItem {
  id: string;
  title: string;
  desc: string;
  primaryAction: string;
  secondaryAction: string;
  tone: 'blue' | 'emerald' | 'amber' | 'violet' | 'neutral';
  details: string[];
}

export interface RecommendationItem {
  id: string;
  title: string;
  prompt: string;
  category?: string;
  sourceSessionId: string;
  receivedAt: number;
}

export interface RecommendationGroup {
  sourceSessionId: string;
  items: RecommendationItem[];
  receivedAt: number;
}

export interface DashboardData {
  agents: AgentInfo[];
  cronJobs: CronJob[];
  cronRuns: CronRun[];
  activeCount: number;
  completedCount: number;
  pendingCount: number;
  reminderCount: number;
  kanbanColumns: KanbanColumn[];
  recentOutputs: RecentOutput[];
  proactiveItems: ProactiveItem[];
  proactiveOutputs: RecentOutput[];
  recommendations: RecommendationGroup[];
  loading: boolean;
  error: string | null;
}

const OUTPUT_TONES: Array<'blue' | 'emerald' | 'amber' | 'violet' | 'neutral'> = [
  'neutral', 'blue', 'violet', 'emerald', 'amber',
];

function guessOutputType(title: string): string {
  const t = title.toLowerCase();
  if (t.includes('ppt') || t.includes('演示') || t.includes('deck')) return 'PPT';
  if (t.includes('报告') || t.includes('report') || t.includes('分析')) return 'Report';
  if (t.includes('简报') || t.includes('brief') || t.includes('摘要')) return 'Brief';
  if (t.includes('邮') || t.includes('email')) return 'Email';
  return 'Task';
}

// ── 辅助函数 ──

function getSessionTitle(meta: string | undefined): string {
  if (!meta) return '未命名会话';
  try {
    const parsed = JSON.parse(meta);
    return parsed.title || '未命名会话';
  } catch {
    return '未命名会话';
  }
}

function getSessionAgentId(meta: string | undefined): string {
  if (!meta) return '';
  try {
    const parsed = JSON.parse(meta);
    return parsed.agent_id || '';
  } catch {
    return '';
  }
}

function timeLabel(ts: string | number): string {
  const n = typeof ts === 'number' ? ts : Number(ts);
  const ms = n < 1e12 ? n * 1000 : n;
  const date = new Date(ms);
  const diffMs = Date.now() - ms;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  if (diffHour < 24) return `${diffHour} 小时前`;
  if (diffDay === 1) return '昨天';
  if (diffDay < 7) return `${diffDay} 天前`;
  return date.toLocaleDateString('zh-CN');
}

const FIVE_MINUTES_MS = 5 * 60 * 1000;
const RECOMMENDATION_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export function aggregateRecommendations(proactiveResults: ProactiveResultItem[]): RecommendationGroup[] {
  const cutoff = Date.now() - RECOMMENDATION_MAX_AGE_MS;
  const latestBySession = new Map<string, ProactiveResultItem>();

  for (const result of proactiveResults) {
    const sourceSessionId = result.sourceSessionId || result.sessionId;
    if (!sourceSessionId) continue;
    if (result.recommendationType !== 'turn_end') continue;
    if (!Array.isArray(result.items) || result.items.length === 0) continue;
    if (result.receivedAt < cutoff) continue;

    const existing = latestBySession.get(sourceSessionId);
    if (!existing || result.receivedAt > existing.receivedAt) {
      latestBySession.set(sourceSessionId, result);
    }
  }

  return Array.from(latestBySession.entries())
    .map(([sourceSessionId, result]) => ({
      sourceSessionId,
      receivedAt: result.receivedAt,
      items: (result.items || []).slice(0, 5).map(item => ({
        id: item.id,
        title: item.title,
        prompt: item.prompt,
        category: item.category,
        sourceSessionId,
        receivedAt: result.receivedAt,
      })),
    }))
    .sort((a, b) => b.receivedAt - a.receivedAt)
    .slice(0, 3);
}

// ── Hook ──

export function useDashboardData(): DashboardData & { refresh: () => void } {
  const { sessions } = useSession();
  const { proactiveResults } = useMessages();

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [cronRuns, setCronRuns] = useState<CronRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, jobsRes, runsRes] = await Promise.all([
        authGet<AgentInfo[]>(`${API_BASE}/api/agents`).catch(() => []),
        authGet<{ jobs: CronJob[] }>(`${API_BASE}/api/cron/jobs`).catch(() => ({ jobs: [] })),
        authGet<{ runs: CronRun[] }>(`${API_BASE}/api/cron/runs?limit=50`).catch(() => ({ runs: [] })),
      ]);
      setAgents(Array.isArray(agentsRes) ? agentsRes : []);
      const jobs = Array.isArray(jobsRes) ? jobsRes : (jobsRes?.jobs ?? []);
      setCronJobs(Array.isArray(jobs) ? jobs : []);
      const runs = Array.isArray(runsRes) ? runsRes : (runsRes?.runs ?? []);
      setCronRuns(Array.isArray(runs) ? runs : []);
      setError(null);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // ── 从 sessions 派生统计 ──
  // 注意：后端 last_active / created_at / last_turn_ended_at 是秒级时间戳，需要 ×1000 转毫秒

  const now = Date.now();

  const toMs = (ts: string | number | null | undefined): number => {
    if (ts == null) return 0;
    const n = typeof ts === 'number' ? ts : Number(ts);
    return n < 1e12 ? n * 1000 : n;
  };

  const getLastActive = (s: { last_active: string | number }) => toMs(s.last_active);

  // 今日起始时间
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayStartMs = todayStart.getTime();

  // 有标题的会话
  const namedSessions = sessions.filter(s => getSessionTitle(s.meta) !== '未命名会话');

  // ── 基于 last_turn_status 精确分类 ──
  //   last_turn_status = 'started'     → 进行中（agent 还在处理）
  //   last_turn_status = 'completed'   → 已完成
  //   last_turn_status = 'error'/'cancelled' → 已完成（异常结束）
  //   last_turn_status = null          → 待处理（从未有 turn）
  //   没有标题                          → 待处理

  const activeSessions = namedSessions.filter(s => s.last_turn_status === 'started');

  const completedSessions = namedSessions.filter(s =>
    s.last_turn_status === 'completed' ||
    s.last_turn_status === 'error' ||
    s.last_turn_status === 'cancelled'
  );

  // 今日已完成（按完成时间倒序）
  const todayCompleted = [...completedSessions]
    .filter(s => getLastActive(s) >= todayStartMs)
    .sort((a, b) => getLastActive(b) - getLastActive(a));

  // 今日提醒数：今天的 cron 运行次数
  const todayRuns = cronRuns.filter(r => r.started_at_ms >= todayStartMs);

  // ── 看板列 ──

  const agentNameMap = new Map(agents.map(a => [a.id, a.name]));

  const resolveOwner = (meta: string) => {
    const aid = getSessionAgentId(meta);
    return agentNameMap.get(aid) || aid || 'Agent';
  };

  const kanbanColumns: KanbanColumn[] = [
    {
      title: '进行中',
      tone: 'blue',
      tasks: activeSessions.map(s => ({
        sessionId: s.session_id,
        title: getSessionTitle(s.meta),
        owner: resolveOwner(s.meta),
        meta: timeLabel(s.last_active),
        progress: 50,
      })),
    },
    {
      title: '已完成',
      tone: 'emerald',
      tasks: todayCompleted.map(s => ({
        sessionId: s.session_id,
        title: getSessionTitle(s.meta),
        owner: resolveOwner(s.meta),
        meta: timeLabel(s.last_active),
        action: '查看结果',
      })),
    },
  ];

  // ── 今日 Task 结果（只展示当天的有标题会话） ──
  // 只展示 agent 最终输出长度 > 100 的会话
  const todayAllSessions = [...namedSessions]
    .filter(s => getLastActive(s) >= todayStartMs && (s.last_agent_response || '').length > 100)
    .sort((a, b) => getLastActive(b) - getLastActive(a));

  const recentOutputs: RecentOutput[] = todayAllSessions.map((s, i) => ({
    id: s.session_id,
    title: getSessionTitle(s.meta),
    agentName: agentNameMap.get(getSessionAgentId(s.meta)) || 'Agent',
    timeLabel: timeLabel(s.last_active),
    tone: OUTPUT_TONES[i % OUTPUT_TONES.length],
    preview: (s.last_agent_response || '').slice(0, 150),
  }));

  // ── Proactive 输出（基于最近完成的 cron 和活跃会话生成建议） ──
  const proactiveItems: ProactiveItem[] = [];
  const recommendations = useMemo(
    () => aggregateRecommendations(proactiveResults || []),
    [proactiveResults],
  );

  // ── Proactive Agent 会话产出（session 派生 + 实时推送合并） ──
  const PROACTIVE_AGENT_ID = 'proactive-agent';
  const proactiveSessions = [...namedSessions]
    .filter(s => getSessionAgentId(s.meta) === PROACTIVE_AGENT_ID)
    .sort((a, b) => getLastActive(b) - getLastActive(a))
    .slice(0, 20);

  const sessionDerivedOutputs: RecentOutput[] = proactiveSessions.map((s, i) => ({
    id: s.session_id,
    title: getSessionTitle(s.meta),
    agentName: 'Proactive Agent',
    timeLabel: timeLabel(s.last_active),
    tone: OUTPUT_TONES[i % OUTPUT_TONES.length],
    preview: (s.last_agent_response || '').slice(0, 150) || undefined,
  }));

  // 合并实时推送结果：仅保留 session 列表中尚未出现的条目
  const existingSessionIds = new Set(sessionDerivedOutputs.map(o => o.id));
  const realtimeOnly = (proactiveResults || [])
    .filter(r => !existingSessionIds.has(r.sessionId))
    .map((r, i): RecentOutput => ({
      id: r.sessionId || r.jobId,
      title: r.jobName || '主动推送',
      agentName: 'Proactive Agent',
      timeLabel: timeLabel(r.receivedAt),
      tone: OUTPUT_TONES[(sessionDerivedOutputs.length + i) % OUTPUT_TONES.length],
      preview: r.result.slice(0, 150) || undefined,
    }));

  const proactiveOutputs: RecentOutput[] = [...realtimeOnly, ...sessionDerivedOutputs].slice(0, 20);

  return {
    agents,
    cronJobs,
    cronRuns,
    activeCount: activeSessions.length,
    completedCount: todayCompleted.length,
    pendingCount: 0,
    reminderCount: todayRuns.length,
    kanbanColumns,
    recentOutputs,
    proactiveItems,
    proactiveOutputs,
    recommendations,
    loading,
    error,
    refresh: fetchData,
  };
}

export { timeLabel, getSessionTitle };
