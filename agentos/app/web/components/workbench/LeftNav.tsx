'use client';

import { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, ChevronRight, ChevronDown, Folder, File, FolderOpen, MessageSquare } from 'lucide-react';
import { useDrag } from 'react-dnd';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { type TaskGroup, type SessionItem, type FileItem, getAgentId, timeLabel } from '@/lib/chatTypes';

// ── 拖拽文件项 ──

function DraggableFileItem({ item, depth = 0 }: { item: FileItem; depth?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<FileItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const isFolder = item.type === 'folder';

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: 'FILE',
    item: { name: item.name, path: item.path },
    canDrag: !isFolder,
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
        ref={!isFolder ? dragRef as unknown as React.Ref<HTMLDivElement> : undefined}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-muted cursor-pointer text-sm transition-colors',
          !isFolder && 'cursor-grab active:cursor-grabbing',
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
  const [userPath, setUserPath] = useState(() => {
    if (typeof window !== 'undefined') return localStorage.getItem('agentos_user_file_path') || '';
    return '';
  });
  const [userFiles, setUserFiles] = useState<FileItem[]>([]);
  const [agentFiles, setAgentFiles] = useState<FileItem[]>([]);
  const [editingPath, setEditingPath] = useState(false);
  const [pathInput, setPathInput] = useState(userPath);
  const [userError, setUserError] = useState('');

  const loadUserFiles = useCallback(async (path: string) => {
    if (!path.trim()) { setUserFiles([]); return; }
    try {
      const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent(path)}`);
      if (!res.ok) { setUserError('无法访问该路径'); setUserFiles([]); return; }
      const data = await res.json();
      setUserFiles(data.items || []);
      setUserError('');
    } catch {
      setUserError('加载失败');
      setUserFiles([]);
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
    if (userPath) loadUserFiles(userPath);
    loadAgentFiles();
  }, [userPath, loadUserFiles, loadAgentFiles]);

  const savePath = () => {
    const p = pathInput.trim();
    setUserPath(p);
    if (typeof window !== 'undefined') localStorage.setItem('agentos_user_file_path', p);
    setEditingPath(false);
    if (p) loadUserFiles(p);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 上半区：我的文件 */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex items-center justify-between px-3 py-2">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">我的文件</span>
          <button
            onClick={() => { setEditingPath(true); setPathInput(userPath); }}
            className="text-[10px] text-primary hover:underline"
          >
            {userPath ? '修改' : '选择'}
          </button>
        </div>
        {editingPath && (
          <div className="px-3 pb-2 flex gap-1">
            <input
              value={pathInput}
              onChange={e => setPathInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && savePath()}
              placeholder="输入文件夹路径..."
              className="flex-1 text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              autoFocus
            />
            <button onClick={savePath} className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground">确定</button>
          </div>
        )}
        {userError && <div className="text-[10px] text-destructive px-3 pb-1">{userError}</div>}
        <div className="space-y-0.5 px-1">
          {userFiles.map(f => <DraggableFileItem key={f.path} item={f} />)}
          {!userPath && !editingPath && (
            <div className="text-[10px] text-muted-foreground/50 px-3 py-4 text-center">
              点击"选择"指定文件夹路径
            </div>
          )}
        </div>
      </div>

      {/* 分隔线 */}
      <div className="border-t border-border mx-3" />

      {/* 下半区：Agent 工作区 */}
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

// ── 任务列表项 ──

function TaskGroupItem({
  group,
  currentSessionId,
  onSwitchSession,
  onNewSession,
}: {
  group: TaskGroup;
  currentSessionId: string | null;
  onSwitchSession: (sid: string) => void;
  onNewSession: (taskId: string) => void;
}) {
  const isSingle = group.sessions.length === 1;
  const [expanded, setExpanded] = useState(false);
  const isActive = group.sessions.some(s => s.session_id === currentSessionId);

  if (isSingle) {
    const s = group.sessions[0];
    return (
      <div
        onClick={() => onSwitchSession(s.session_id)}
        className={cn(
          'px-3 py-2.5 rounded-lg cursor-pointer transition-colors border text-sm',
          s.session_id === currentSessionId
            ? 'bg-primary/10 border-primary/30 text-foreground'
            : 'bg-transparent border-transparent hover:bg-muted',
        )}
      >
        <div className="font-medium truncate text-xs">{group.title}</div>
        <div className="text-[10px] text-muted-foreground mt-0.5">{timeLabel(s.last_active)}</div>
      </div>
    );
  }

  return (
    <div className={cn('rounded-lg border transition-colors', isActive ? 'border-primary/20' : 'border-transparent')}>
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 px-3 py-2.5 cursor-pointer hover:bg-muted rounded-lg transition-colors"
      >
        {expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        }
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate text-xs">{group.title}</div>
          <div className="text-[10px] text-muted-foreground">{group.sessions.length} 个会话 · {timeLabel(group.lastActive)}</div>
        </div>
        <button
          onClick={e => { e.stopPropagation(); onNewSession(group.taskId); }}
          className="p-1 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors opacity-0 group-hover:opacity-100"
          title="在此任务下新建会话"
        >
          <Plus className="w-3 h-3" />
        </button>
      </div>
      {expanded && (
        <div className="ml-4 space-y-0.5 pb-1">
          {group.sessions.map(s => {
            const agentId = getAgentId(s.meta);
            return (
              <div
                key={s.session_id}
                onClick={() => onSwitchSession(s.session_id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer transition-colors text-xs',
                  s.session_id === currentSessionId
                    ? 'bg-primary/10 text-foreground'
                    : 'hover:bg-muted text-muted-foreground',
                )}
              >
                <MessageSquare className="w-3 h-3 shrink-0" />
                <span className="truncate">{agentId}</span>
                <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{timeLabel(s.last_active)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── LeftNav ──

export function LeftNav() {
  const {
    taskGroups,
    currentSessionId,
    switchSession,
    createSession,
    startNewChat,
    refreshTaskGroups,
    loadingSessions,
  } = useChatSession();

  const handleNewTask = () => {
    startNewChat();
  };

  const handleNewSessionInTask = (taskId: string) => {
    createSession('default', taskId);
  };

  return (
    <nav className="w-56 border-r border-border bg-muted/20 flex flex-col shrink-0">
      <Tabs defaultValue="tasks" className="flex-1 flex flex-col">
        <TabsList className="w-full grid grid-cols-2 rounded-none border-b border-border bg-transparent p-0 h-auto">
          <TabsTrigger
            value="tasks"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            任务
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            文件区
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="flex-1 mt-0 overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 border-b">
            <button
              onClick={handleNewTask}
              className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> 新建任务
            </button>
            <button
              onClick={refreshTaskGroups}
              disabled={loadingSessions}
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', loadingSessions && 'animate-spin')} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {taskGroups.length === 0 && !loadingSessions && (
              <p className="text-xs text-muted-foreground/50 px-1 py-8 text-center">暂无任务记录</p>
            )}
            {taskGroups.map(group => (
              <TaskGroupItem
                key={group.taskId}
                group={group}
                currentSessionId={currentSessionId}
                onSwitchSession={switchSession}
                onNewSession={handleNewSessionInTask}
              />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="files" className="flex-1 mt-0 overflow-hidden">
          <FilePanel />
        </TabsContent>
      </Tabs>
    </nav>
  );
}
