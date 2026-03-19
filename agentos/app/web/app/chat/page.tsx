'use client';

import { Suspense, useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2, Bot, MessageSquare, Plus, Search, RefreshCw,
  Folder, FolderOpen, File, ChevronRight, ChevronDown, PanelRightOpen, PanelRightClose, X,
} from 'lucide-react';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { useDrag } from 'react-dnd';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type SessionItem, type FileItem, type ContextFileRef, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';
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
        'flex items-start gap-3 px-4 py-3.5 cursor-pointer transition-colors border-b border-border/40',
        isSelected ? 'bg-primary/5' : 'hover:bg-muted/50',
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

function SessionItem({
  session, isActive, onClick,
}: {
  session: SessionItem;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-center gap-2.5 px-3 py-2.5 mx-2 rounded-lg cursor-pointer transition-colors text-sm',
        isActive ? 'bg-primary/10 text-foreground' : 'hover:bg-muted/60 text-foreground/80',
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
    </div>
  );
}

/* ── 拖拽文件项 ── */

function DraggableFileItem({ item, depth = 0 }: { item: FileItem; depth?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<FileItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const isFolder = item.type === 'folder';

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: 'FILE',
    item: { name: item.name, path: item.path },
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  }), [item]);

  const toggleFolder = async () => {
    if (!isFolder) return;
    if (expanded) { setExpanded(false); return; }
    if (!children) {
      setLoading(true);
      try {
        const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent(item.path)}`);
        const data = await res.json();
        setChildren(data.items || []);
      } catch { setChildren([]); }
      finally { setLoading(false); }
    }
    setExpanded(true);
  };

  return (
    <div style={{ opacity: isDragging ? 0.5 : 1 }}>
      <div
        ref={dragRef as unknown as React.Ref<HTMLDivElement>}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-muted cursor-grab active:cursor-grabbing text-sm transition-colors',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={toggleFolder}
      >
        {isFolder && (expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        )}
        {isFolder ? (
          expanded ? <FolderOpen className="w-4 h-4 text-primary shrink-0" /> : <Folder className="w-4 h-4 text-primary shrink-0" />
        ) : (
          <File className="w-4 h-4 text-muted-foreground shrink-0" />
        )}
        <span className="text-foreground/80 truncate text-xs">{item.name}</span>
        {loading && <span className="text-[10px] text-muted-foreground ml-auto">...</span>}
      </div>
      {isFolder && expanded && children && (
        <div>
          {children.map(child => <DraggableFileItem key={child.path} item={child} depth={depth + 1} />)}
          {children.length === 0 && (
            <div className="text-[10px] text-muted-foreground/50 py-1" style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}>
              空文件夹
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 文件面板 ── */

function FilePanel({ onClose }: { onClose: () => void }) {
  const [roots, setRoots] = useState<FileItem[]>([]);
  const [agentFiles, setAgentFiles] = useState<FileItem[]>([]);

  const loadRoots = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/files/roots`);
      if (!res.ok) { setRoots([]); return; }
      const data = await res.json();
      setRoots(data.roots || []);
    } catch { setRoots([]); }
  }, []);

  const loadAgentFiles = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent('workspace')}`);
      if (!res.ok) { setAgentFiles([]); return; }
      const data = await res.json();
      setAgentFiles(data.items || []);
    } catch { setAgentFiles([]); }
  }, []);

  useEffect(() => {
    loadRoots();
    loadAgentFiles();
  }, [loadRoots, loadAgentFiles]);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/60">
        <span className="text-xs font-semibold text-foreground">文件区</span>
        <button onClick={onClose} className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors">
          <PanelRightClose className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 本地文件浏览 */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex items-center justify-between px-3 py-2">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">本地文件</span>
          <button onClick={loadRoots} className="text-[10px] text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
        <div className="space-y-0.5 px-1">
          {roots.map(r => <DraggableFileItem key={r.path} item={r} />)}
          {roots.length === 0 && (
            <div className="text-[10px] text-muted-foreground/50 px-3 py-4 text-center">
              <Loader2 className="w-4 h-4 mx-auto mb-1 animate-spin opacity-40" />
              加载中…
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-border mx-3" />

      {/* Agent 工作区 */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex items-center justify-between px-3 py-2">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Agent 工作区</span>
          <button onClick={loadAgentFiles} className="text-[10px] text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
        <div className="space-y-0.5 px-1">
          {agentFiles.map(f => <DraggableFileItem key={f.path} item={f} />)}
          {agentFiles.length === 0 && (
            <div className="text-[10px] text-muted-foreground/50 px-3 py-4 text-center">暂无文件</div>
          )}
        </div>
      </div>
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
  } = useChatSession();

  const [agents, setAgents] = useState<AgentBrief[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilePanel, setShowFilePanel] = useState(false);
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
    <DndProvider backend={HTML5Backend}>
      <ResizablePanelGroup orientation="horizontal" className="h-full bg-background overflow-hidden">

        {/* ====== 左栏：Agent 列表 ====== */}
        <ResizablePanel id="agent-list" defaultSize="22%" minSize="12%" maxSize="35%" className="flex flex-col bg-muted/20">
          {/* 搜索栏 */}
          <div className="p-3 border-b border-border/60">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索对话"
                className="w-full pl-9 pr-3 py-2 text-sm bg-muted/50 rounded-lg border-none outline-none focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground/50"
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
                    onClick={() => setSelectedAgentId(agent.id)}
                  />
                );
              })
            )}
          </div>

          {/* 底部刷新 */}
          <div className="border-t border-border/60 px-4 py-2 flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">{agents.length} Agents</span>
            <button
              onClick={handleRefresh}
              disabled={loadingAgents || loadingSessions}
              className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', (loadingAgents || loadingSessions) && 'animate-spin')} />
            </button>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* ====== 中栏：Session 列表 ====== */}
        {selectedAgentId && (
          <>
            <ResizablePanel id="session-list" defaultSize="18%" minSize="10%" maxSize="30%" className="flex flex-col">
              {/* Agent 头部 */}
              <div className="px-4 py-3 border-b border-border/60 flex items-center justify-between">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className={cn(
                    'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                    AGENT_BG[agents.findIndex(a => a.id === selectedAgentId) % AGENT_BG.length] || 'bg-primary/10',
                  )}>
                    <Bot className={cn('w-4 h-4', AGENT_ACCENT[agents.findIndex(a => a.id === selectedAgentId) % AGENT_ACCENT.length] || 'text-primary')} />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-sm truncate">{selectedAgent?.name || selectedAgentId}</div>
                    {selectedAgent?.model && (
                      <div className="text-[10px] text-muted-foreground truncate">{selectedAgent.model}</div>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleNewChat}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-primary hover:bg-primary/10 transition-colors shrink-0"
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
                      <SessionItem
                        key={session.session_id}
                        session={session}
                        isActive={currentSessionId === session.session_id}
                        onClick={() => switchSession(session.session_id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />
          </>
        )}

        {/* ====== 右栏：聊天区 ====== */}
        <ResizablePanel id="chat-area" defaultSize="60%" minSize="30%" className="flex flex-col min-w-0 relative">
          {/* 文件面板切换按钮 */}
          {!showFilePanel && (
            <button
              onClick={() => setShowFilePanel(true)}
              className="absolute top-3 right-3 z-10 p-2 rounded-lg bg-background/80 backdrop-blur-sm border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shadow-sm"
              title="打开文件区"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
          )}

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

        {/* ====== 最右栏：文件面板（可折叠） ====== */}
        {showFilePanel && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="file-panel" defaultSize="16%" minSize="10%" maxSize="30%" className="bg-muted/20">
              <FilePanel onClose={() => setShowFilePanel(false)} />
            </ResizablePanel>
          </>
        )}

      </ResizablePanelGroup>
    </DndProvider>
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
