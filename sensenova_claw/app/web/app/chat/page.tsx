'use client';

import { Suspense, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Loader2, Bot, MessageSquare, Plus, Search, RefreshCw, Trash2,
  ChevronDown, ChevronRight, GitBranch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession, type RecommendationSendMeta } from '@/contexts/ChatSessionContext';
import { useFilePanel } from '@/contexts/FilePanelContext';
import { useI18n } from '@/contexts/I18nContext';
import { type SessionItem, type SessionTreeNode, type ContextFileRef, buildSessionTree, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';
import { MessageArea } from '@/components/chat/MessageArea';
import { ChatInput } from '@/components/chat/ChatInput';
import { InlinePreview } from '@/components/chat/InlinePreview';
import { useSlideSet } from '@/components/ppt/PPTViewer';
import { type FilePreviewType } from '@/components/files/fileTypes';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { useResizablePreview } from '@/hooks/useResizablePreview';

/* ── workdir 根目录缓存 ── */
let _workdirRootCache: string | null | undefined;
async function fetchWorkdirRoot(): Promise<string | null> {
  if (_workdirRootCache !== undefined) return _workdirRootCache as string | null;
  let result: string | null = null;
  try {
    const res = await authFetch(`${API_BASE}/api/files/roots`);
    if (res.ok) {
      const data = await res.json();
      const entry = (data.roots || []).find((r: { name: string }) => r.name === 'Agent 工作区');
      result = entry?.path ?? null;
    }
  } catch { /* ignore */ }
  _workdirRootCache = result;
  return result;
}

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
  const { t } = useI18n();
  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-start gap-3 px-4 py-3.5 cursor-pointer transition-all border-b border-border/60',
        isSelected
          ? 'bg-blue-100 shadow-md border-l-[3px] border-l-blue-500 dark:bg-blue-900/40'
          : 'hover:bg-muted/50',
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
              {t('common.agent')}
            </span>
          </div>
          {lastActiveDate && (
            <span className="text-[11px] text-muted-foreground shrink-0 ml-2">{lastActiveDate}</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground truncate pr-2">
            {lastSessionPreview || agent.description || t('chat.noConversation')}
          </p>
          {hasUnread && <span className="w-2.5 h-2.5 rounded-full bg-red-500 shrink-0" />}
        </div>
      </div>
    </div>
  );
}

/* ── Session 列表项（中栏） ── */
function SessionListItem({
  session, isActive, onClick, onDelete, index, isChild, isLast, noMargin,
}: {
  session: SessionItem;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
  index: number;
  isChild?: boolean;
  isLast?: boolean;
  noMargin?: boolean;
}) {
  const { locale, t } = useI18n();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const hasChildren = Boolean(session.has_children);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (hasChildren) {
      onDelete();
      return;
    }
    if (confirmDelete) {
      onDelete();
      setConfirmDelete(false);
      return;
    }
    setConfirmDelete(true);
    setTimeout(() => setConfirmDelete(false), 3000);
  };

  if (isChild) {
    return (
      <div className="flex items-stretch">
        <div className="w-5 shrink-0 flex flex-col items-center">
          <div className={cn(
            'w-px flex-1 bg-violet-300/40 dark:bg-violet-500/25',
            isLast && 'max-h-[50%]',
          )} />
          {isLast && <div className="flex-1" />}
        </div>
        <div className="flex items-center -ml-[3px]">
          <div className="w-2.5 h-px bg-violet-300/40 dark:bg-violet-500/25" />
        </div>
        <div
          onClick={onClick}
          className={cn(
            'flex items-center gap-2 flex-1 min-w-0 px-2.5 py-2 rounded-lg cursor-pointer transition-all group',
            isActive
              ? 'bg-violet-100/80 text-foreground shadow-sm dark:bg-violet-900/30'
              : 'hover:bg-violet-50/60 text-foreground/70 dark:hover:bg-violet-900/10',
          )}
        >
          <div className={cn(
            'w-1.5 h-1.5 rounded-full shrink-0',
            isActive ? 'bg-violet-500' : 'bg-violet-300/60 dark:bg-violet-500/40',
          )} />
          <div className="flex-1 min-w-0">
            <div className="truncate text-[11px] font-medium">{getTitle(session.meta, locale)}</div>
            <div className="text-[9px] text-muted-foreground/50 mt-0.5">{timeLabel(session.last_active, locale)}</div>
          </div>
          <button data-testid={`chat-delete-session-${session.session_id}`} onClick={handleDelete} className={cn('shrink-0 p-0.5 rounded transition-colors', confirmDelete ? 'opacity-100 text-destructive hover:bg-destructive/10' : 'opacity-0 group-hover:opacity-100 text-muted-foreground/50 hover:text-destructive')}>
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
        'flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all text-sm group relative',
        !noMargin && 'mx-2',
        isActive ? 'bg-blue-100 dark:bg-blue-900/40 text-foreground shadow-md' : 'hover:bg-muted/60 text-foreground/80',
      )}
    >
      <MessageSquare className={cn('w-4 h-4 shrink-0', isActive ? 'text-blue-500' : 'text-muted-foreground')} />
      <div className="flex-1 min-w-0">
        <div className="truncate font-medium text-xs">{getTitle(session.meta, locale)}</div>
        <div className="text-[10px] text-muted-foreground mt-0.5">{timeLabel(session.last_active, locale)}</div>
      </div>
      <button data-testid={`chat-delete-session-${session.session_id}`} onClick={handleDelete} className={cn('shrink-0 p-1 rounded transition-colors', confirmDelete ? 'opacity-100 text-destructive' : 'opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive')}>
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

function SessionTreeBranch({
  children,
  isChild,
  isLast,
}: {
  children: React.ReactNode;
  isChild?: boolean;
  isLast?: boolean;
}) {
  if (!isChild) return <>{children}</>;

  return (
    <div className="flex items-stretch">
      <div className="w-6 shrink-0 flex flex-col items-center">
        <div className={cn('w-px flex-1 bg-violet-300/40 dark:bg-violet-400/30', isLast && 'max-h-[50%]')} />
        {isLast && <div className="flex-1" />}
      </div>
      <div className="flex items-center -ml-[3px]">
        <div className="w-3 h-px bg-violet-300/40 dark:bg-violet-400/30" />
      </div>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}

function SessionListGroup({
  node, currentSessionId, switchSession, deleteSession, index, isChild = false, isLast = false,
}: {
  node: SessionTreeNode;
  currentSessionId: string | null;
  switchSession: (sid: string) => void;
  deleteSession: (sid: string) => Promise<void>;
  index: number;
  isChild?: boolean;
  isLast?: boolean;
}) {
  const { t } = useI18n();
  const { session, children: childSessions } = node;
  const hasActiveChild = childSessions.some(child => child.session.session_id === currentSessionId);
  const [expanded, setExpanded] = useState(hasActiveChild);

  useEffect(() => {
    if (hasActiveChild && !expanded) setExpanded(true);
  }, [expanded, hasActiveChild]);

  return (
    <SessionTreeBranch isChild={isChild} isLast={isLast}>
      <div className={cn('rounded-xl transition-colors', expanded && 'bg-violet-50/40 dark:bg-violet-950/20 pb-1.5')}>
        <SessionListItem session={session} isActive={currentSessionId === session.session_id} onClick={() => switchSession(session.session_id)} onDelete={() => deleteSession(session.session_id)} index={index} noMargin />
        <button onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }} className={cn('flex items-center gap-1.5 w-full pr-3 py-1 text-[10px] font-medium', 'pl-6', expanded ? 'text-violet-500' : 'text-muted-foreground/50')}>
        <div className="flex items-center gap-1">
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          <GitBranch className="w-3 h-3" />
        </div>
        <span>{t('chat.teamSessionsCount', { count: childSessions.length })}</span>
        </button>
        {expanded && (
          <div className="pl-4 pr-1">
            {childSessions.map((child, childIdx) => (
              child.children.length > 0 ? (
                <SessionListGroup
                  key={child.session.session_id}
                  node={child}
                  currentSessionId={currentSessionId}
                  switchSession={switchSession}
                  deleteSession={deleteSession}
                  index={index + 1 + childIdx}
                  isChild
                  isLast={childIdx === childSessions.length - 1}
                />
              ) : (
                <SessionListItem key={child.session.session_id} session={child.session} isActive={currentSessionId === child.session.session_id} onClick={() => switchSession(child.session.session_id)} onDelete={() => deleteSession(child.session.session_id)} index={index + 1 + childIdx} isChild isLast={childIdx === childSessions.length - 1} />
              )
            ))}
          </div>
        )}
      </div>
    </SessionTreeBranch>
  );
}

function ChatContent() {
  const { locale, t } = useI18n();
  const {
    wsConnected, currentSessionId, sessions, messages, isTyping, turnActive, activeInteraction, currentSessionQuestionInteraction, interactionSubmitting,
    sendMessage, sendCurrentSessionQuestionAnswer, switchSession, createSession, deleteSession, startNewChat,
    refreshTaskGroups, loadingSessions, handleSkillInvoke, cancelTurn, cleanupEmptySession,
  } = useChatSession();

  const { openToPath } = useFilePanel();
  const searchParams = useSearchParams();
  const agentFromUrl = searchParams.get('agent');

  const [agents, setAgents] = useState<AgentBrief[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(agentFromUrl);
  const [searchQuery, setSearchQuery] = useState('');
  const [slidePreviewDir, setSlidePreviewDir] = useState<string | null>(null);
  const [filePreview, setFilePreview] = useState<{ path: string; type: FilePreviewType } | null>(null);

  const { previewHeight, onPreviewResize } = useResizablePreview(350);
  const slideSet = useSlideSet(slidePreviewDir);
  
  const requiredCheckDone = useRef(false);
  const creatingSessionForAgent = useRef<string | null>(null);

  // PPT Viewer Logic
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { dir: string; isAbsolute: boolean };
      let resolvedDir: string;
      if (detail.isAbsolute) {
        resolvedDir = detail.dir;
      } else {
        const curSession = sessions.find(s => s.session_id === currentSessionId);
        const agentId = (curSession ? getAgentId(curSession.meta) : null) || selectedAgentId || 'default';
        resolvedDir = detail.dir.startsWith(agentId) ? detail.dir : `${agentId}/${detail.dir}`;
        fetchWorkdirRoot().then(root => {
          if (root) {
            const sep = root.includes('\\') ? '\\' : '/';
            openToPath([root, resolvedDir.replace(/\//g, sep)].join(sep));
          }
        });
      }
      setSlidePreviewDir(resolvedDir);
      setFilePreview(null);
    };
    window.addEventListener('sensenova-claw:open-slide-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-slide-preview', handler);
  }, [selectedAgentId, currentSessionId, sessions, openToPath]);

  // File Preview Logic：聊天气泡里的 [..](#sensenova-claw-file:...) 链接点击会
  // 派发此事件，这里与 slide 预览互斥共存。之前 /chat 页面漏接此事件，
  // 导致 md 文件点击只定位到文件面板，对话区无预览。
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { path: string; type: FilePreviewType };
      setFilePreview(detail);
      setSlidePreviewDir(null);
    };
    window.addEventListener('sensenova-claw:open-file-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-file-preview', handler);
  }, []);

  useEffect(() => {
    setSlidePreviewDir(null);
    setFilePreview(null);
  }, [currentSessionId]);

  const loadAgents = useCallback(async () => {
    setLoadingAgents(true);
    try {
      const res = await authFetch(`${API_BASE}/api/agents`);
      const data = await res.json();
      setAgents(Array.isArray(data) ? data.map((a: any) => ({
        id: String(a.id), name: String(a.name), description: String(a.description || ''), status: String(a.status || 'active'), model: String(a.model || ''),
      })) : []);
    } catch { setAgents([]); } finally { setLoadingAgents(false); }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const sessionsByAgent = useMemo(() => sessions.reduce<Record<string, SessionItem[]>>((acc, s) => {
    const aid = getAgentId(s.meta);
    if (!acc[aid]) acc[aid] = [];
    acc[aid].push(s);
    return acc;
  }, {}), [sessions]);

  useEffect(() => {
    if (agents.length > 0 && !selectedAgentId) setSelectedAgentId(agents[0].id);
  }, [agents, selectedAgentId]);

  useEffect(() => { if (selectedAgentId) refreshTaskGroups(); }, [selectedAgentId, refreshTaskGroups]);

  const selectedSessionTree = useMemo(() => {
    const all = selectedAgentId ? (sessionsByAgent[selectedAgentId] || []).sort((a, b) => b.last_active - a.last_active) : [];
    return buildSessionTree(all);
  }, [sessionsByAgent, selectedAgentId]);

  useEffect(() => {
    if (!selectedAgentId || !currentSessionId) return;
    const currentSession = sessions.find(s => s.session_id === currentSessionId);
    if (!currentSession || getAgentId(currentSession.meta) === selectedAgentId) return;
    if (creatingSessionForAgent.current === selectedAgentId) return;
    
    const agentSessions = sessionsByAgent[selectedAgentId] || [];
    if (agentSessions.length > 0) {
      switchSession(agentSessions.sort((a, b) => b.last_active - a.last_active)[0].session_id);
    } else {
      creatingSessionForAgent.current = selectedAgentId;
      startNewChat();
      createSession(selectedAgentId);
    }
  }, [selectedAgentId, currentSessionId, sessions, sessionsByAgent, switchSession, startNewChat, createSession]);

  const filteredAgents = searchQuery.trim()
    ? agents.filter(a => a.name.toLowerCase().includes(searchQuery.toLowerCase()) || a.description.toLowerCase().includes(searchQuery.toLowerCase()))
    : agents;

  // 必配清单检查：进入 system-admin 新 session 时自动发送缺失配置提醒
  useEffect(() => {
    if (requiredCheckDone.current) return;
    if (selectedAgentId !== 'system-admin') return;
    if (!agentFromUrl || agentFromUrl !== 'system-admin') return;
    if (!wsConnected || agents.length === 0) return;

    // 仅在没有现有 session 时触发（首次进入）
    const existingSessions = sessionsByAgent['system-admin'] || [];
    if (existingSessions.length > 0) return;

    requiredCheckDone.current = true;

    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/api/config/required-check`);
        const data = await res.json();
        const missing: string[] = [];
        for (const [, info] of Object.entries(data)) {
          const item = info as { configured: boolean; message: string };
          if (!item.configured) missing.push(item.message);
        }
        if (missing.length > 0) {
          const text = `以下系统配置尚未完成，请帮我配置：\n${missing.map((m, i) => `${i + 1}. ${m}`).join('\n')}`;
          startNewChat();
          sendMessage(text, [], 'system-admin');
        }
      } catch (e) {
        console.error('必配清单检查失败:', e);
      }
    })();
  }, [selectedAgentId, agentFromUrl, wsConnected, agents, sessionsByAgent, startNewChat, sendMessage]);

  const handleNewChat = () => {
    if (!selectedAgentId) return;
    creatingSessionForAgent.current = selectedAgentId;
    startNewChat();
    createSession(selectedAgentId);
  };
  const handleSend = useCallback((
    content: string,
    contextFiles?: ContextFileRef[],
    recommendation?: RecommendationSendMeta | null,
  ) => {
    if (currentSessionQuestionInteraction) {
      sendCurrentSessionQuestionAnswer(content, false);
    } else {
      sendMessage(content, contextFiles, selectedAgentId || 'default', recommendation);
    }
  }, [currentSessionQuestionInteraction, sendCurrentSessionQuestionAnswer, sendMessage, selectedAgentId]);

  const emptyState = useMemo(() => (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground animate-in fade-in zoom-in-95 duration-500">
      <div className="w-20 h-20 rounded-3xl bg-primary/5 flex items-center justify-center shadow-inner">
        <Bot size={40} className="text-primary/20" />
      </div>
      <p className="text-sm font-medium">
        {t('chat.startConversationWith', {
          agent: agents.find(a => a.id === selectedAgentId)?.name || t('common.agent'),
        })}
      </p>
    </div>
  ), [agents, selectedAgentId, t]);
  const isCurrentSessionQuestionInteraction = Boolean(currentSessionQuestionInteraction);

  return (
    <ResizablePanelGroup orientation="horizontal" className="h-full overflow-hidden gap-3 bg-slate-50/50 dark:bg-slate-900/20">
      {/* Agent List */}
      <ResizablePanel id="agent-list" defaultSize="22%" minSize="12%" className="flex flex-col rounded-2xl border border-border/60 overflow-hidden bg-background">
        <div className="px-4 py-3.5 border-b border-border/60">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder={t('chat.searchConversations')} className="w-full pl-10 pr-3 py-2.5 text-sm bg-background rounded-xl border border-border/60 outline-none focus:ring-2 focus:ring-primary/15 transition-all" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingAgents && agents.length === 0 ? <div className="flex items-center justify-center py-16"><Loader2 className="animate-spin text-muted-foreground" size={20} /></div>
            : filteredAgents.map((agent, idx) => (
              <AgentContactItem key={agent.id} agent={agent} index={idx} isSelected={selectedAgentId === agent.id} lastSessionPreview={getTitle((sessionsByAgent[agent.id]?.sort((a,b)=>b.last_active-a.last_active)[0])?.meta ?? '', locale)} lastActiveDate={timeLabel((sessionsByAgent[agent.id]?.sort((a,b)=>b.last_active-a.last_active)[0])?.last_active, locale)} hasUnread={false} onClick={() => { cleanupEmptySession(); creatingSessionForAgent.current = null; setSelectedAgentId(agent.id); }} />
            ))}
        </div>
        <div className="border-t border-border/60 px-4 py-2.5 flex items-center justify-between text-[10px] text-muted-foreground uppercase tracking-widest font-bold">
          <span>{t('chat.agentCount', { count: agents.length })}</span>
          <button onClick={() => { loadAgents(); refreshTaskGroups(); }} className="p-1.5 rounded-lg hover:bg-muted transition-colors"><RefreshCw size={12} className={loadingAgents ? 'animate-spin' : ''} /></button>
        </div>
      </ResizablePanel>

      <ResizableHandle invisible />

      {/* Session List */}
      {selectedAgentId && (
        <ResizablePanel id="session-list" defaultSize="18%" minSize="10%" className="flex flex-col rounded-2xl border border-border/60 overflow-hidden bg-background">
          <div className="px-4 py-3.5 border-b border-border/60 flex items-center justify-between">
            <div className="font-bold text-sm truncate">{agents.find(a => a.id === selectedAgentId)?.name}</div>
            <button onClick={handleNewChat} className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold text-primary hover:bg-primary/10 transition-colors"><Plus size={14} /> {t('chat.newChat')}</button>
          </div>
          <div className="flex-1 overflow-y-auto py-2">
            {selectedSessionTree.map((node, idx) => {
              return node.children.length > 0 ? <SessionListGroup key={node.session.session_id} node={node} currentSessionId={currentSessionId} switchSession={switchSession} deleteSession={deleteSession} index={idx} />
                : <SessionListItem key={node.session.session_id} session={node.session} isActive={currentSessionId === node.session.session_id} onClick={() => switchSession(node.session.session_id)} onDelete={() => deleteSession(node.session.session_id)} index={idx} />;
            })}
          </div>
        </ResizablePanel>
      )}

      <ResizableHandle invisible />

      {/* Chat Area */}
      <ResizablePanel id="chat-area" defaultSize="60%" minSize="30%" className="flex flex-col min-w-0 relative rounded-2xl border border-border/60 overflow-hidden bg-background shadow-sm">
        {!currentSessionId ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-5 text-muted-foreground bg-slate-50/30 dark:bg-slate-900/10">
            <div className="w-28 h-28 rounded-3xl bg-gradient-to-br from-primary/10 to-primary/5 flex items-center justify-center shadow-inner"><Bot size={56} className="text-primary/30" /></div>
            <p className="text-base font-medium text-foreground/60">{t('chat.selectConversation')}</p>
          </div>
        ) : (
          <>
            <div className="px-4 py-1.5 border-b border-border/40 bg-muted/20 flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground/60 font-medium uppercase tracking-wider">{t('chat.sessionId')}:</span>
              <span className="text-[10px] text-muted-foreground/60 font-mono select-all bg-background border px-1.5 py-0.5 rounded">{currentSessionId}</span>
            </div>
            
            <MessageArea messages={messages} isTyping={isTyping} currentSessionId={currentSessionId} emptyState={emptyState} />

            <InlinePreview
              previewHeight={previewHeight}
              onPreviewResize={onPreviewResize}
              slideSet={slideSet}
              onCloseSlides={() => setSlidePreviewDir(null)}
              filePreview={filePreview}
              onCloseFile={() => setFilePreview(null)}
            />

            <ChatInput
              defaultAgentId={selectedAgentId || 'default'}
              selectedAgent={selectedAgentId || 'default'}
              onSelectAgent={() => {}}
              onSend={handleSend}
              onSlashSubmit={() => false}
              onStop={cancelTurn}
              disabled={activeInteraction?.kind === 'confirmation'}
              showStopButton={turnActive && !isCurrentSessionQuestionInteraction}
              wsConnected={wsConnected}
              handleSkillInvoke={handleSkillInvoke}
              hideAgentSelector
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
      <Suspense fallback={<div className="flex items-center justify-center h-[calc(100vh-4rem)] bg-background"><Loader2 className="animate-spin text-muted-foreground" size={32} /></div>}>
        <ChatContent />
      </Suspense>
    </DashboardLayout>
  );
}
