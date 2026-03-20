'use client';

import { Suspense, useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2, Bot, MessageSquare, Plus, Search, RefreshCw, Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type SessionItem, type ContextFileRef, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';
import { MessageBubble } from '@/components/chat/MessageBubble';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
import { ChatInput } from '@/components/chat/ChatInput';
import { InteractionDialog } from '@/components/chat/QuestionDialog';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

interface AgentBrief {
  id: string;
  name: string;
  description: string;
  status: string;
  model: string;
}

const AGENT_ACCENT = [
  'text-blue-500', 'text-violet-500', 'text-emerald-500', 'text-orange-500',
  'text-pink-500', 'text-teal-500', 'text-indigo-500', 'text-rose-500',
];
const AGENT_BG = [
  'bg-blue-500/10', 'bg-violet-500/10', 'bg-emerald-500/10', 'bg-orange-500/10',
  'bg-pink-500/10', 'bg-teal-500/10', 'bg-indigo-500/10', 'bg-rose-500/10',
];

/* ── Agent 联系人卡片（左栏） ── */

function AgentContactItem({
  agent, index, isSelected, lastSessionPreview, lastActiveDate, hasUnread, onClick,
}: {
  agent: AgentBrief;
  index: number;
  isSelected: boolean;
  lastSessionPreview: string;
  lastActiveDate: string;
  hasUnread: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-start gap-3 px-4 py-3.5 cursor-pointer transition-all border-b border-border/60',
        isSelected ? 'bg-primary/5 shadow-sm' : 'hover:bg-muted/50',
      )}
    >
      <div className={cn(
        'w-10 h-10 rounded-xl flex items-center justify-center shrink-0',
        AGENT_BG[index % AGENT_BG.length],
      )}>
        <Bot className={cn('w-5 h-5', AGENT_ACCENT[index % AGENT_ACCENT.length])} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-sm text-foreground truncate">{agent.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium shrink-0">
              Agent
            </span>
          </div>
          {lastActiveDate && (
            <span className="text-[11px] text-muted-foreground shrink-0 ml-2">{lastActiveDate}</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground truncate pr-2">
            {lastSessionPreview || agent.description || '暂无对话'}
          </p>
          {hasUnread && <span className="w-2.5 h-2.5 rounded-full bg-red-500 shrink-0" />}
        </div>
      </div>
    </div>
  );
}

/* ── Session 列表项（中栏） ── */

function SessionListItem({
  session, isActive, onClick, onDelete,
}: {
  session: SessionItem;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

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
        'flex items-center gap-2.5 px-3 py-2.5 mx-2 rounded-xl cursor-pointer transition-all text-sm group relative',
        isActive ? 'bg-primary/8 text-foreground shadow-sm border border-primary/15' : 'hover:bg-muted/60 text-foreground/80 border border-transparent',
      )}
    >
      <MessageSquare className={cn(
        'w-4 h-4 shrink-0',
        isActive ? 'text-primary' : 'text-muted-foreground',
      )} />
      <div className="flex-1 min-w-0">
        <div className="truncate font-medium text-xs">{getTitle(session.meta)}</div>
        <div className="text-[10px] text-muted-foreground mt-0.5">{timeLabel(session.last_active)}</div>
      </div>
      <button
        onClick={handleDelete}
        className={cn(
          'shrink-0 p-1 rounded transition-colors',
          confirmDelete
            ? 'opacity-100 text-destructive hover:bg-destructive/10'
            : 'opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10',
        )}
        title={confirmDelete ? '确认删除' : '删除会话'}
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/* ── 主体内容 ── */

function ChatContent() {
  const {
    wsConnected,
    currentSessionId,
    sessions,
    messages,
    isTyping,
    sendMessage,
    switchSession,
    createSession,
    deleteSession,
    startNewChat,
    resetIfNeeded,
    refreshTaskGroups,
    loadingSessions,
    activeInteraction,
    interactionSubmitting,
    sendQuestionAnswer,
    sendConfirmationResponse,
    handleInteractionTimeout,
    handleSkillInvoke,
    cleanupEmptySession,
  } = useChatSession();

  const [agents, setAgents] = useState<AgentBrief[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadAgents = useCallback(async () => {
    setLoadingAgents(true);
    try {
      const res = await authFetch(`${API_BASE}/api/agents`);
      const data = await res.json();
      setAgents(Array.isArray(data) ? data.map((a: Record<string, unknown>) => ({
        id: String(a.id),
        name: String(a.name),
        description: String(a.description || ''),
        status: String(a.status || 'active'),
        model: String(a.model || ''),
      })) : []);
    } catch {
      setAgents([]);
    } finally {
      setLoadingAgents(false);
    }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  useEffect(() => {
    resetIfNeeded();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // 按 agent 分组 sessions
  const sessionsByAgent = sessions.reduce<Record<string, SessionItem[]>>((acc, s) => {
    const aid = getAgentId(s.meta);
    if (!acc[aid]) acc[aid] = [];
    acc[aid].push(s);
    return acc;
  }, {});

  useEffect(() => {
    if (agents.length > 0 && !selectedAgentId) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

  // 切换 agent 时刷新 session 列表
  useEffect(() => {
    if (selectedAgentId) {
      refreshTaskGroups();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgentId]);

  const selectedSessions = selectedAgentId
    ? (sessionsByAgent[selectedAgentId] || []).sort((a, b) => b.last_active - a.last_active)
    : [];

  const selectedAgent = agents.find(a => a.id === selectedAgentId);

  const filteredAgents = searchQuery.trim()
    ? agents.filter(a =>
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.description.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : agents;

  const handleNewChat = () => {
    if (!selectedAgentId) return;
    startNewChat();
    createSession(selectedAgentId);
  };

  const handleSend = useCallback((content: string, contextFiles?: ContextFileRef[]) => {
    sendMessage(content, contextFiles, selectedAgentId || 'default');
  }, [sendMessage, selectedAgentId]);

  const handleSlashSubmit = useCallback(() => false, []);

  const handleRefresh = () => {
    loadAgents();
    refreshTaskGroups();
  };

  return (
      <ResizablePanelGroup orientation="horizontal" className="h-full overflow-hidden gap-3">

        {/* ====== 左栏：Agent 列表 ====== */}
        <ResizablePanel id="agent-list" defaultSize="22%" minSize="12%" maxSize="35%" className="flex flex-col rounded-2xl border border-border/60 overflow-hidden bg-gradient-to-br from-sky-100/20 via-background to-blue-200/20 dark:from-sky-500/[0.06] dark:via-background dark:to-blue-500/[0.06]">
          {/* 搜索栏 */}
          <div className="px-4 py-3.5 border-b border-border/60">
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索对话"
                className="w-full pl-10 pr-3 py-2.5 text-sm bg-background rounded-xl border border-border/60 outline-none focus:ring-2 focus:ring-primary/15 focus:border-primary/40 placeholder:text-muted-foreground/50 shadow-inner transition-all"
              />
            </div>
          </div>

          {/* Agent 列表 */}
          <div className="flex-1 overflow-y-auto">
            {loadingAgents && agents.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="animate-spin text-muted-foreground" size={20} />
              </div>
            ) : filteredAgents.length === 0 ? (
              <div className="text-center text-muted-foreground text-xs py-16">
                {searchQuery ? '无匹配结果' : '暂无 Agent'}
              </div>
            ) : (
              filteredAgents.map((agent, idx) => {
                const agentSessions = sessionsByAgent[agent.id] || [];
                const sorted = [...agentSessions].sort((a, b) => b.last_active - a.last_active);
                const lastSession = sorted[0];
                return (
                  <AgentContactItem
                    key={agent.id}
                    agent={agent}
                    index={idx}
                    isSelected={selectedAgentId === agent.id}
                    lastSessionPreview={lastSession ? getTitle(lastSession.meta) : ''}
                    lastActiveDate={lastSession ? timeLabel(lastSession.last_active) : ''}
                    hasUnread={false}
                    onClick={() => {
                      cleanupEmptySession();
                      setSelectedAgentId(agent.id);
                    }}
                  />
                );
              })
            )}
          </div>

          {/* 底部刷新 */}
          <div className="border-t border-border/60 px-4 py-2.5 flex items-center justify-between">
            <span className="text-[10px] font-medium text-muted-foreground">{agents.length} Agents</span>
            <button
              onClick={handleRefresh}
              disabled={loadingAgents || loadingSessions}
              className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', (loadingAgents || loadingSessions) && 'animate-spin')} />
            </button>
          </div>
        </ResizablePanel>

        <ResizableHandle invisible />

        {/* ====== 中栏：Session 列表 ====== */}
        {selectedAgentId && (
          <>
            <ResizablePanel id="session-list" defaultSize="18%" minSize="10%" maxSize="30%" className="flex flex-col rounded-2xl border border-border/60 overflow-hidden bg-gradient-to-br from-purple-100/15 via-background to-violet-200/20 dark:from-purple-500/[0.05] dark:via-background dark:to-violet-500/[0.06]">
              {/* Agent 头部 */}
              <div className="px-4 py-3.5 border-b border-border/60 flex items-center justify-between">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className={cn(
                    'w-8 h-8 rounded-xl flex items-center justify-center shrink-0',
                    AGENT_BG[agents.findIndex(a => a.id === selectedAgentId) % AGENT_BG.length] || 'bg-primary/10',
                  )}>
                    <Bot className={cn('w-4 h-4', AGENT_ACCENT[agents.findIndex(a => a.id === selectedAgentId) % AGENT_ACCENT.length] || 'text-primary')} />
                  </div>
                  <div className="min-w-0">
                    <div className="font-bold text-sm truncate">{selectedAgent?.name || selectedAgentId}</div>
                    {selectedAgent?.model && (
                      <div className="text-[10px] text-muted-foreground truncate">{selectedAgent.model}</div>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleNewChat}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold text-primary hover:bg-primary/10 transition-colors shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                  新建
                </button>
              </div>

              {/* Session 列表 */}
              <div className="flex-1 overflow-y-auto py-2">
                {loadingSessions ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="animate-spin text-muted-foreground" size={16} />
                  </div>
                ) : selectedSessions.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center px-4">
                    <MessageSquare className="w-10 h-10 text-muted-foreground/20 mb-3" />
                    <p className="text-xs text-muted-foreground/60 mb-3">暂无会话</p>
                    <button
                      onClick={handleNewChat}
                      className="text-xs text-primary hover:text-primary/80 font-medium transition-colors"
                    >
                      开始新对话
                    </button>
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    {selectedSessions.map(session => (
                      <SessionListItem
                        key={session.session_id}
                        session={session}
                        isActive={currentSessionId === session.session_id}
                        onClick={() => switchSession(session.session_id)}
                        onDelete={() => deleteSession(session.session_id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </ResizablePanel>

            <ResizableHandle invisible />
          </>
        )}

        {/* ====== 右栏：聊天区 ====== */}
        <ResizablePanel id="chat-area" defaultSize="60%" minSize="30%" className="flex flex-col min-w-0 relative rounded-2xl border border-border/60 overflow-hidden bg-gradient-to-br from-rose-100/10 via-background to-amber-100/10 dark:from-rose-500/[0.03] dark:via-background dark:to-amber-500/[0.03]">
          {!currentSessionId ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-5 text-muted-foreground">
              <div className="w-28 h-28 rounded-3xl bg-gradient-to-br from-primary/10 to-primary/5 flex items-center justify-center shadow-inner">
                <Bot size={56} className="text-primary/30" />
              </div>
              <p className="text-base font-medium text-foreground/60">选择一个对话开始聊天</p>
              <p className="text-xs text-muted-foreground/50">从左侧选择 Agent，然后新建或选择一个会话</p>
            </div>
          ) : (
            <>
              {/* 消息区 */}
              <div className="flex-1 overflow-y-auto p-4 md:p-8">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
                    <Bot size={32} className="text-primary/30" />
                    <p className="text-sm">开始与 {selectedAgent?.name || 'Agent'} 的对话</p>
                  </div>
                ) : (
                  <>
                    {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
                    {isTyping && <TypingIndicator />}
                    <div ref={chatEndRef} />
                  </>
                )}
              </div>

              {/* 输入区 */}
              <ChatInput
                defaultAgentId={selectedAgentId || 'default'}
                selectedAgent={selectedAgentId || 'default'}
                onSelectAgent={() => {}}
                onSend={handleSend}
                onSlashSubmit={handleSlashSubmit}
                disabled={isTyping || !!activeInteraction || interactionSubmitting}
                wsConnected={wsConnected}
                handleSkillInvoke={handleSkillInvoke}
                hideAgentSelector
              />

              {/* 交互对话框 */}
              <InteractionDialog
                open={!!activeInteraction}
                interaction={activeInteraction}
                submitting={interactionSubmitting}
                wsConnected={wsConnected}
                onQuestionSubmit={(answer) => sendQuestionAnswer(answer, false)}
                onQuestionCancel={() => sendQuestionAnswer(null, true)}
                onConfirmationSubmit={sendConfirmationResponse}
                onTimeout={handleInteractionTimeout}
              />
            </>
          )}
        </ResizablePanel>

      </ResizablePanelGroup>
  );
}

export default function ChatPage() {
  return (
    <DashboardLayout>
      <Suspense fallback={
        <div className="flex items-center justify-center h-[calc(100vh-4rem)] bg-background">
          <Loader2 className="animate-spin text-muted-foreground" size={32} />
        </div>
      }>
        <ChatContent />
      </Suspense>
    </DashboardLayout>
  );
}
