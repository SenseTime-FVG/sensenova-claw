'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, RefreshCw,
  MessageSquare, Bot, Clock, Loader2, Trash2, Sparkles,
  ChevronDown, ChevronRight, GitBranch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, authGet, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type SessionItem, getAgentId, getParentSessionId, getTitle, timeLabel } from '@/lib/chatTypes';
import type { CronJob } from '@/hooks/useDashboardData';

// ── 最近对话列表项 ──

function RecentChatItem({
  session,
  agentName,
  isActive,
  onClick,
  onDelete,
  isChild,
  isLast,
}: {
  session: SessionItem;
  agentName: string;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
  isChild?: boolean;
  isLast?: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const title = getTitle(session.meta);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete();
      setConfirmDelete(false);
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  if (isChild) {
    return (
      <div className="flex items-stretch">
        {/* 树形连线 */}
        <div className="w-6 shrink-0 flex flex-col items-center">
          <div className={cn(
            'w-px flex-1 bg-indigo-300/40 dark:bg-indigo-500/30',
            isLast && 'max-h-[50%]',
          )} />
          {isLast && <div className="flex-1" />}
        </div>
        <div className="flex items-center -ml-[3px]">
          <div className="w-3 h-px bg-indigo-300/40 dark:bg-indigo-500/30" />
        </div>
        <div
          onClick={onClick}
          className={cn(
            'flex items-center gap-2 flex-1 min-w-0 px-2.5 py-2 rounded-lg cursor-pointer transition-all group',
            isActive
              ? 'bg-indigo-100/80 text-foreground shadow-sm dark:bg-indigo-900/30'
              : 'hover:bg-indigo-50/60 text-foreground/70 dark:hover:bg-indigo-900/10',
          )}
        >
          <div className={cn(
            'w-1.5 h-1.5 rounded-full shrink-0',
            isActive ? 'bg-indigo-500' : 'bg-indigo-300/60 dark:bg-indigo-500/40',
          )} />
          <div className="flex-1 min-w-0">
            <div className="truncate text-[11px] font-medium">{title}</div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-[9px] text-muted-foreground/60 truncate">{agentName}</span>
              <span className="text-[9px] text-muted-foreground/30">·</span>
              <span className="text-[9px] text-muted-foreground/50 shrink-0">{timeLabel(session.last_active)}</span>
            </div>
          </div>
          <button
            onClick={handleDelete}
            className={cn(
              'shrink-0 p-0.5 rounded transition-colors',
              confirmDelete
                ? 'opacity-100 text-destructive hover:bg-destructive/10'
                : 'opacity-0 group-hover:opacity-100 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10',
            )}
            title={confirmDelete ? '确认删除' : '删除会话'}
          >
            <Trash2 className="w-2.5 h-2.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-start gap-2.5 px-3 py-3 rounded-xl cursor-pointer transition-all group',
        isActive
          ? 'bg-blue-100 text-foreground border border-blue-200 shadow-sm dark:bg-blue-900/40 dark:border-blue-800'
          : 'hover:bg-muted/60 text-foreground/80 border border-transparent',
      )}
    >
      <MessageSquare className={cn(
        'w-3.5 h-3.5 shrink-0 mt-0.5',
        isActive ? 'text-primary' : 'text-muted-foreground',
      )} />
      <div className="flex-1 min-w-0">
        <div className="truncate font-medium text-xs">{title}</div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <Bot className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />
          <span className="text-[10px] text-muted-foreground truncate">{agentName}</span>
          <span className="text-[10px] text-muted-foreground/40 shrink-0">·</span>
          <span className="text-[10px] text-muted-foreground/60 shrink-0">{timeLabel(session.last_active)}</span>
        </div>
      </div>
      <button
        onClick={handleDelete}
        className={cn(
          'shrink-0 p-1 rounded-lg transition-colors mt-0.5',
          confirmDelete
            ? 'opacity-100 text-destructive hover:bg-destructive/10'
            : 'opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10',
        )}
        title={confirmDelete ? '确认删除' : '删除会话'}
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

// ── 可展开的主会话项（包含子会话下拉） ──

function ParentSessionGroup({
  session,
  children: childSessions,
  agentMap,
  currentSessionId,
  switchSession,
  deleteSession,
}: {
  session: SessionItem;
  children: SessionItem[];
  agentMap: Record<string, string>;
  currentSessionId: string | null;
  switchSession: (sid: string) => void;
  deleteSession: (sid: string) => Promise<void>;
}) {
  const hasActiveChild = childSessions.some(c => c.session_id === currentSessionId);
  const [expanded, setExpanded] = useState(hasActiveChild);

  useEffect(() => {
    if (hasActiveChild && !expanded) setExpanded(true);
  }, [hasActiveChild]);

  const toggleExpand = (e: React.MouseEvent) => {
    e.stopPropagation();
    setExpanded(prev => !prev);
  };

  return (
    <div className={cn(
      'rounded-xl transition-colors',
      expanded && 'bg-indigo-50/40 dark:bg-indigo-950/20 pb-1.5',
    )}>
      {/* 主会话 */}
      <RecentChatItem
        session={session}
        agentName={agentMap[getAgentId(session.meta)] || getAgentId(session.meta)}
        isActive={currentSessionId === session.session_id}
        onClick={() => switchSession(session.session_id)}
        onDelete={() => deleteSession(session.session_id)}
      />

      {/* 展开/收起按钮 */}
      <button
        onClick={toggleExpand}
        className={cn(
          'flex items-center gap-1.5 w-full pl-6 pr-3 py-1 transition-colors',
          'text-[10px] font-medium',
          expanded
            ? 'text-indigo-500 dark:text-indigo-400'
            : 'text-muted-foreground/50 hover:text-indigo-500 dark:hover:text-indigo-400',
        )}
      >
        <div className="flex items-center gap-1">
          {expanded
            ? <ChevronDown className="w-3 h-3" />
            : <ChevronRight className="w-3 h-3" />
          }
          <GitBranch className="w-3 h-3" />
        </div>
        <span>{childSessions.length} 个团队会话</span>
        <div className="flex-1 h-px bg-current opacity-10 ml-1" />
      </button>

      {/* 子会话列表 */}
      {expanded && (
        <div className="pl-4 pr-1">
          {childSessions.map((child, idx) => (
            <RecentChatItem
              key={child.session_id}
              session={child}
              agentName={agentMap[getAgentId(child.meta)] || getAgentId(child.meta)}
              isActive={currentSessionId === child.session_id}
              onClick={() => switchSession(child.session_id)}
              onDelete={() => deleteSession(child.session_id)}
              isChild
              isLast={idx === childSessions.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 最近对话面板 ──

function RecentChatsPanel({ agentFilter }: { agentFilter?: string }) {
  const {
    sessions,
    currentSessionId,
    switchSession,
    deleteSession,
    startNewChat,
    refreshTaskGroups,
    loadingSessions,
  } = useChatSession();

  const [agentMap, setAgentMap] = useState<Record<string, string>>({});
  const [loadingAgents, setLoadingAgents] = useState(true);

  const loadAgents = useCallback(async () => {
    setLoadingAgents(true);
    try {
      const res = await authFetch(`${API_BASE}/api/agents`);
      const data = await res.json();
      const map: Record<string, string> = {};
      if (Array.isArray(data)) {
        for (const a of data) {
          const id = String(a.id);
          map[id] = String(a.name || a.id);
        }
      }
      setAgentMap(map);
    } catch { /* ignore */ }
    finally { setLoadingAgents(false); }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  // 将 sessions 按父子关系分组
  const { rootSessions, childrenMap } = (() => {
    const filtered = [...sessions]
      .filter(s => !agentFilter || getAgentId(s.meta) === agentFilter)
      .sort((a, b) => b.last_active - a.last_active);

    const sessionIdSet = new Set(filtered.map(s => s.session_id));
    const cMap: Record<string, SessionItem[]> = {};
    const roots: SessionItem[] = [];

    for (const s of filtered) {
      const parentId = getParentSessionId(s.meta);
      if (parentId && sessionIdSet.has(parentId)) {
        if (!cMap[parentId]) cMap[parentId] = [];
        cMap[parentId].push(s);
      } else {
        roots.push(s);
      }
    }

    return { rootSessions: roots, childrenMap: cMap };
  })();

  const handleNewChat = () => {
    startNewChat();
  };

  const handleRefresh = () => {
    loadAgents();
    refreshTaskGroups();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-primary/60" />
          <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-[0.15em]">
            最近对话
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={handleNewChat}
            data-testid="recent-chats-new-button"
            className="flex items-center gap-0.5 p-1 rounded-lg text-primary hover:bg-primary/10 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleRefresh}
            disabled={loadingAgents || loadingSessions}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground/50 hover:text-foreground transition-all disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3 h-3', (loadingAgents || loadingSessions) && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 py-2.5 space-y-1">
        {loadingSessions && rootSessions.length === 0 ? (
          <p className="text-xs text-muted-foreground/50 px-1 py-8 text-center">加载中...</p>
        ) : rootSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Clock className="w-8 h-8 text-muted-foreground/20 mb-2" />
            <p className="text-xs text-muted-foreground/50 mb-2">暂无对话记录</p>
            <button
              onClick={handleNewChat}
              className="text-xs text-primary hover:text-primary/80 font-medium transition-colors"
            >
              开始新对话
            </button>
          </div>
        ) : (
          rootSessions.map(session => {
            const children = childrenMap[session.session_id] || [];
            if (children.length === 0) {
              return (
                <RecentChatItem
                  key={session.session_id}
                  session={session}
                  agentName={agentMap[getAgentId(session.meta)] || getAgentId(session.meta)}
                  isActive={currentSessionId === session.session_id}
                  onClick={() => switchSession(session.session_id)}
                  onDelete={() => deleteSession(session.session_id)}
                />
              );
            }
            return (
              <ParentSessionGroup
                key={session.session_id}
                session={session}
                agentMap={agentMap}
                currentSessionId={currentSessionId}
                switchSession={switchSession}
                deleteSession={deleteSession}
              >
                {children}
              </ParentSessionGroup>
            );
          })
        )}
      </div>

    </div>
  );
}

// ── 定时任务紧凑面板 ──

function cronStatusDot(job: CronJob): string {
  if (job.running_at_ms) return 'bg-blue-400 animate-pulse';
  if (job.last_run_status === 'error') return 'bg-amber-400';
  if (!job.enabled) return 'bg-neutral-300';
  return 'bg-emerald-400';
}

function cronNextText(job: CronJob): string {
  if (job.running_at_ms) return '运行中';
  if (!job.enabled) return '已暂停';
  if (job.next_run_at_ms) {
    const diff = job.next_run_at_ms - Date.now();
    if (diff <= 0) return '即将运行';
    const min = Math.floor(diff / 60000);
    if (min < 60) return `${min}m 后`;
    const hour = Math.floor(min / 60);
    return `${hour}h 后`;
  }
  return job.schedule_value;
}

function CronSidebarPanel() {
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);

  const loadCron = useCallback(async () => {
    try {
      const data = await authGet(`${API_BASE}/api/cron/jobs`);
      if (Array.isArray(data)) setCronJobs(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadCron();
    const timer = setInterval(loadCron, 30_000);
    return () => clearInterval(timer);
  }, [loadCron]);

  if (cronJobs.length === 0) return null;

  return (
    <div className="border-t border-border/40">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <Clock className="w-3 h-3 text-muted-foreground/60" />
        <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-[0.15em]">
          定时任务
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground/40">{cronJobs.length}</span>
      </div>
      <div className="px-2.5 pb-2.5 space-y-1 max-h-[160px] overflow-y-auto thin-scrollbar">
        {cronJobs.map(job => (
          <div
            key={job.id}
            className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-muted/30 hover:bg-muted/60 transition-colors"
          >
            <div className={cn('w-1.5 h-1.5 rounded-full shrink-0', cronStatusDot(job))} />
            <span className="text-[11px] font-medium text-foreground/80 truncate flex-1">
              {job.name || job.text}
            </span>
            <span className="text-[10px] text-muted-foreground/60 shrink-0 tabular-nums">
              {cronNextText(job)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 主动推送紧凑面板 ──

const PROACTIVE_AGENT_ID = 'proactive-agent';

function proactiveTimeLabel(ts: number): string {
  const ms = ts < 1e12 ? ts * 1000 : ts;
  const diff = Date.now() - ms;
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min}分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}小时前`;
  return `${Math.floor(hour / 24)}天前`;
}

function ProactiveSidebarPanel() {
  const { sessions, switchSession } = useChatSession();

  const proactiveSessions = [...sessions]
    .filter(s => {
      try {
        const meta = JSON.parse(s.meta || '{}');
        return meta.agent_id === PROACTIVE_AGENT_ID;
      } catch { return false; }
    })
    .sort((a, b) => b.last_active - a.last_active)
    .slice(0, 5);

  if (proactiveSessions.length === 0) return null;

  return (
    <div className="border-t border-border/40">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <Sparkles className="w-3 h-3 text-violet-400" />
        <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-[0.15em]">
          主动推送
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground/40">{proactiveSessions.length}</span>
      </div>
      <div className="px-2.5 pb-2.5 space-y-1 max-h-[160px] overflow-y-auto thin-scrollbar">
        {proactiveSessions.map(s => {
          let title = '未命名';
          try { title = JSON.parse(s.meta || '{}').title || '未命名'; } catch {}
          return (
            <button
              key={s.session_id}
              type="button"
              onClick={() => switchSession(s.session_id)}
              className="flex items-start gap-2 w-full px-2.5 py-2 rounded-lg bg-violet-50/50 hover:bg-violet-100/60 dark:bg-violet-900/10 dark:hover:bg-violet-900/20 transition-colors text-left"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0 mt-1.5" />
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-medium text-foreground/80 truncate">{title}</div>
                <div className="text-[10px] text-muted-foreground/50 mt-0.5">{proactiveTimeLabel(s.last_active)}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── LeftNav ──

export function LeftNav({ agentFilter }: { agentFilter?: string }) {
  return (
    <nav className="h-full flex flex-col">
      <RecentChatsPanel agentFilter={agentFilter} />
      <ProactiveSidebarPanel />
      <CronSidebarPanel />
    </nav>
  );
}
