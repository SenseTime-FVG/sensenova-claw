'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, RefreshCw, ChevronRight, ChevronDown, Folder, File, FolderOpen,
  MessageSquare, Bot, X, Clock, Loader2, Trash2,
} from 'lucide-react';
import { useDrag } from 'react-dnd';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type SessionItem, type FileItem, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';

// ── 拖拽文件项 ──

function DraggableFileItem({ item, depth = 0 }: { item: FileItem; depth?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<FileItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const isFolder = item.type === 'folder';

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: 'FILE',
    item: { name: item.name, path: item.path },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  }), [item]);

  const toggleFolder = async () => {
    if (!isFolder) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (!children) {
      setLoading(true);
      try {
        const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent(item.path)}`);
        const data = await res.json();
        setChildren(data.items || []);
      } catch {
        setChildren([]);
      } finally {
        setLoading(false);
      }
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
        {isFolder && (
          expanded
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
          {children.map((child) => (
            <DraggableFileItem key={child.path} item={child} depth={depth + 1} />
          ))}
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

// ── 文件面板 ──

function FilePanel() {
  const [roots, setRoots] = useState<FileItem[]>([]);
  const [agentFiles, setAgentFiles] = useState<FileItem[]>([]);

  const loadRoots = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/files/roots`);
      if (!res.ok) { setRoots([]); return; }
      const data = await res.json();
      setRoots(data.roots || []);
    } catch {
      setRoots([]);
    }
  }, []);

  const loadAgentFiles = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent('workspace')}`);
      if (!res.ok) { setAgentFiles([]); return; }
      const data = await res.json();
      setAgentFiles(data.items || []);
    } catch {
      setAgentFiles([]);
    }
  }, []);

  useEffect(() => {
    loadRoots();
    loadAgentFiles();
  }, [loadRoots, loadAgentFiles]);

  return (
    <div className="flex flex-col h-full">
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
            <div className="text-[10px] text-muted-foreground/50 px-3 py-4 text-center">
              暂无文件
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

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
        'flex items-start gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer transition-colors group',
        isActive
          ? 'bg-primary/10 text-foreground border border-primary/20'
          : 'hover:bg-muted text-foreground/80 border border-transparent',
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
          'shrink-0 p-1 rounded transition-colors mt-0.5',
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
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/60">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
          最近对话
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-0.5 text-xs text-primary hover:text-primary/80 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleRefresh}
            disabled={loadingAgents || loadingSessions}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3 h-3', (loadingAgents || loadingSessions) && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {loadingSessions && recentSessions.length === 0 ? (
          <p className="text-xs text-muted-foreground/50 px-1 py-8 text-center">加载中...</p>
        ) : recentSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Clock className="w-8 h-8 text-muted-foreground/20 mb-2" />
            <p className="text-xs text-muted-foreground/50 mb-2">暂无对话记录</p>
            <button
              onClick={handleNewChat}
              className="text-xs text-primary hover:text-primary/80 transition-colors"
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
      <Tabs defaultValue="chats" className="flex-1 flex flex-col">
        <TabsList className="w-full grid grid-cols-2 rounded-none border-b border-border bg-transparent p-0 h-auto">
          <TabsTrigger
            value="chats"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            最近对话
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            文件区
          </TabsTrigger>
        </TabsList>

        <TabsContent value="chats" className="flex-1 mt-0 overflow-hidden flex flex-col">
          <RecentChatsPanel agentFilter={agentFilter} />
        </TabsContent>

        <TabsContent value="files" className="flex-1 mt-0 overflow-hidden">
          <FilePanel />
        </TabsContent>
      </Tabs>
    </nav>
  );
}
