'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, RefreshCw,
  MessageSquare, Bot, Clock, Loader2, Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type SessionItem, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';

// ── 最近对话列表项 ──

function RecentChatItem({
  session,
  agentName,
  isActive,
  onClick,
  onDelete,
}: {
  session: SessionItem;
  agentName: string;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
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

// ── 最近对话面板 ──

function RecentChatsPanel({ agentFilter }: { agentFilter?: string }) {
  const {
    sessions,
    currentSessionId,
    switchSession,
    createSession,
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
          map[String(a.id)] = String(a.name || a.id);
        }
      }
      setAgentMap(map);
    } catch { /* ignore */ }
    finally { setLoadingAgents(false); }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const recentSessions = [...sessions]
    .filter(s => !agentFilter || getAgentId(s.meta) === agentFilter)
    .sort((a, b) => b.last_active - a.last_active);

  const handleNewChat = () => {
    const newAgentId = agentFilter || Object.keys(agentMap)[0] || 'default';
    startNewChat();
    createSession(newAgentId);
  };

  const handleRefresh = () => {
    loadAgents();
    refreshTaskGroups();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.15em]">
          最近对话
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-0.5 p-1 rounded-lg text-primary hover:bg-primary/10 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleRefresh}
            disabled={loadingAgents || loadingSessions}
            className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3 h-3', (loadingAgents || loadingSessions) && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 py-2.5 space-y-1">
        {loadingSessions && recentSessions.length === 0 ? (
          <p className="text-xs text-muted-foreground/50 px-1 py-8 text-center">加载中...</p>
        ) : recentSessions.length === 0 ? (
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
          recentSessions.map(session => (
            <RecentChatItem
              key={session.session_id}
              session={session}
              agentName={agentMap[getAgentId(session.meta)] || getAgentId(session.meta)}
              isActive={currentSessionId === session.session_id}
              onClick={() => switchSession(session.session_id)}
              onDelete={() => deleteSession(session.session_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── LeftNav ──

export function LeftNav({ agentFilter }: { agentFilter?: string }) {
  return (
    <nav className="h-full flex flex-col">
      <RecentChatsPanel agentFilter={agentFilter} />
    </nav>
  );
}
