'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Filter, MessageSquare, Loader2, Plus, X, Bot, Trash2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { authFetch, API_BASE } from '@/lib/authFetch';

interface Session {
  session_id: string;
  created_at: number;
  last_active: number;
  status: string;
  meta: string;
  channel?: string;
  message_count?: number;
}

interface AgentOption { id: string; name: string; description: string; }
type SelectionMode = 'manual' | 'page' | 'filtered_all';

function formatTime(ts: number): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString();
}

function timeAgo(ts: number): string {
  if (!ts) return '-';
  const delta = Date.now() / 1000 - ts;
  if (delta < 60) return `${Math.floor(delta)}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function parseTitle(meta: string): string {
  try {
    const obj = JSON.parse(meta);
    return obj.title || obj.name || '-';
  } catch {
    return '-';
  }
}

function parseMeta(meta: string): Record<string, unknown> {
  try { return JSON.parse(meta); } catch { return {}; }
}

export default function SessionsPage() {
  const router = useRouter();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewChat, setShowNewChat] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [selectionEnabled, setSelectionEnabled] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('manual');
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkDeleteError, setBulkDeleteError] = useState('');
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const loadSessions = () => {
    setLoading(true);
    authFetch(`${API_BASE}/api/sessions`)
      .then(res => res.json())
      .then(data => setSessions(data.sessions || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSessions();
  }, []);

  const filteredSessions = sessions.filter((s) => {
    const title = parseTitle(s.meta);
    const matchesSearch = title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.session_id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || s.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getTargetLabel = (meta: string) => {
    const m = parseMeta(meta);
    if (m.agent_id && m.agent_id !== 'default') return { type: 'agent', id: m.agent_id as string };
    return null;
  };

  const requestDeleteSession = (event: React.MouseEvent, session: Session) => {
    event.preventDefault();
    event.stopPropagation();
    setDeleteError('');
    setSessionToDelete(session);
  };

  const deleteSession = async () => {
    if (!sessionToDelete) return;
    setDeletingSessionId(sessionToDelete.session_id);
    setDeleteError('');
    try {
      const res = await authFetch(`${API_BASE}/api/sessions/${sessionToDelete.session_id}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setDeleteError(data.detail || '删除失败');
        return;
      }
      setSessionToDelete(null);
      loadSessions();
    } catch {
      setDeleteError('删除失败');
    } finally {
      setDeletingSessionId(null);
    }
  };

  const exitSelectionMode = () => {
    setSelectionEnabled(false);
    setSelectedSessionIds([]);
    setSelectionMode('manual');
    setShowBulkDeleteConfirm(false);
    setBulkDeleteError('');
  };

  const toggleSelectionMode = () => {
    if (selectionEnabled) {
      exitSelectionMode();
      return;
    }
    setSelectionEnabled(true);
    setSelectedSessionIds([]);
    setSelectionMode('manual');
    setBulkDeleteError('');
  };

  const toggleSessionSelected = (sessionId: string, checked: boolean) => {
    setSelectionMode('manual');
    setSelectedSessionIds((prev) => {
      if (checked) return Array.from(new Set([...prev, sessionId]));
      return prev.filter((id) => id !== sessionId);
    });
  };

  const selectCurrentPage = () => {
    setSelectionMode('page');
    setSelectedSessionIds(filteredSessions.map((session) => session.session_id));
    setBulkDeleteError('');
  };

  const selectFilteredAll = () => {
    setSelectionMode('filtered_all');
    setSelectedSessionIds([]);
    setBulkDeleteError('');
  };

  const clearSelection = () => {
    setSelectionMode('manual');
    setSelectedSessionIds([]);
    setBulkDeleteError('');
  };

  const openBulkDeleteConfirm = () => {
    if (selectionMode !== 'filtered_all' && selectedSessionIds.length === 0) return;
    setBulkDeleteError('');
    setShowBulkDeleteConfirm(true);
  };

  const bulkDeleteSessions = async () => {
    setBulkDeleting(true);
    setBulkDeleteError('');
    try {
      const body = selectionMode === 'filtered_all'
        ? { filter: { search_term: searchTerm, status: statusFilter } }
        : { session_ids: selectedSessionIds };
      const res = await authFetch(`${API_BASE}/api/sessions/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setBulkDeleteError(data.detail || '批量删除失败');
        return;
      }
      setShowBulkDeleteConfirm(false);
      exitSelectionMode();
      loadSessions();
    } catch {
      setBulkDeleteError('批量删除失败');
    } finally {
      setBulkDeleting(false);
    }
  };

  const allVisibleSelected = filteredSessions.length > 0
    && filteredSessions.every((session) => selectedSessionIds.includes(session.session_id));

  const selectionSummary = selectionMode === 'filtered_all'
    ? '已选中当前筛选的所有结果'
    : selectionMode === 'page'
      ? `已选中当前页面 ${selectedSessionIds.length} 个会话`
      : `已手动选中 ${selectedSessionIds.length} 个会话`;

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Sessions History</h2>
          <div className="flex items-center gap-3">
            <Button
              data-testid="sessions-selection-toggle"
              onClick={toggleSelectionMode}
              variant={selectionEnabled ? 'secondary' : 'outline'}
              size="lg"
              className={`rounded-xl px-6 font-bold ${selectionEnabled ? 'ring-2 ring-primary/20' : ''}`}
            >
              选择
            </Button>
            <Button onClick={() => setShowNewChat(true)} size="lg" className="rounded-xl px-8 font-bold gap-2 shadow-lg shadow-primary/20">
              <Plus size={20} /> New Conversation
            </Button>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-8 mt-10">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">Workspace</p>
              <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                <MessageSquare className="h-5 w-5" /> Recent History
              </button>
              <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent text-muted-foreground hover:bg-muted hover:text-foreground opacity-60">
                <span className="h-5 w-5 bg-muted rounded-full flex items-center justify-center text-[10px]">★</span> Bookmarked
              </button>
              <div className="h-px bg-border/40 my-4 mx-4" />
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">Filters</p>
              <div className="px-4 py-2 space-y-4">
                 <div className="space-y-2">
                    <label className="text-xs font-bold text-muted-foreground">Status</label>
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      className="w-full h-11 rounded-xl border border-input bg-background/50 px-4 py-1 text-sm font-medium shadow-sm transition-all focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="all">All Status</option>
                      <option value="active">Active Only</option>
                      <option value="closed">Completed</option>
                    </select>
                 </div>
              </div>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 space-y-8">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Historical Load</CardTitle>
                  <MessageSquare className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{sessions.length}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Total tracked sessions</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Active Stream</CardTitle>
                  <div className="relative">
                    <span className="absolute -top-1 -right-1 flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                    </span>
                    <Bot className="h-5 w-5 text-green-500" />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black text-green-600 dark:text-green-500">{sessions.filter(s => s.status === 'active').length}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Currently running processes</p>
                </CardContent>
              </Card>
            </div>

            <Card className="shadow-xl border-border/80 overflow-hidden">
              <CardHeader className="bg-muted/30 border-b p-8">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                  <div>
                    <CardTitle className="text-2xl font-bold">Session Explorer</CardTitle>
                    <CardDescription className="text-base mt-2">
                      Review and resume recent past conversations.
                    </CardDescription>
                  </div>
                  <div className="relative w-full md:w-96">
                    <Search className="absolute left-4 top-4 h-5 w-5 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Search session ID or title..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-12 py-7 text-base bg-background rounded-2xl shadow-inner border-border/60"
                    />
                  </div>
                </div>
                {selectionEnabled && (
                  <div data-testid="sessions-bulk-bar" className="mt-6 flex flex-col gap-3 rounded-2xl border border-border/70 bg-background/80 p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <p data-testid="sessions-selected-summary" className="text-sm font-semibold text-foreground">
                        {selectionSummary}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button data-testid="sessions-select-page" variant="outline" size="sm" onClick={selectCurrentPage}>
                          全选当前页面
                        </Button>
                        <Button data-testid="sessions-select-filtered-all" variant="outline" size="sm" onClick={selectFilteredAll}>
                          全选当前筛选的所有结果
                        </Button>
                        <Button variant="ghost" size="sm" onClick={clearSelection}>
                          清空选择
                        </Button>
                        <Button
                          data-testid="sessions-bulk-delete"
                          variant="destructive"
                          size="sm"
                          onClick={openBulkDeleteConfirm}
                          disabled={selectionMode !== 'filtered_all' && selectedSessionIds.length === 0}
                        >
                          删除选中
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-primary" size={48} />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest">Hydrating session logs...</p>
                  </div>
                ) : filteredSessions.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-24 text-muted-foreground border-t border-dashed bg-muted/5">
                    <div className="p-10 bg-muted/20 rounded-full mb-6 italic opacity-20">
                      <MessageSquare size={80} />
                    </div>
                    <p className="text-xl font-bold uppercase tracking-widest opacity-40">No historical sessions found</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader className="bg-muted/50 border-b-2">
                        <TableRow className="hover:bg-transparent">
                          {selectionEnabled && (
                            <TableHead className="pl-8 py-5 text-center">
                              <input
                                type="checkbox"
                                checked={allVisibleSelected}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    selectCurrentPage();
                                  } else {
                                    clearSelection();
                                  }
                                }}
                                aria-label="全选当前页面"
                              />
                            </TableHead>
                          )}
                          <TableHead className="pl-10 py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Status</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Identity</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Session Title</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Primary Actor</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Timestamp</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground text-center">Actions</TableHead>
                          <TableHead className="pr-10 py-5 text-xs font-black uppercase tracking-widest text-muted-foreground text-right">Liveness</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredSessions.map((session) => {
                          const target = getTargetLabel(session.meta);
                          return (
                            <TableRow 
                              key={session.session_id} 
                              onClick={() => router.push(`/sessions/${session.session_id}`)} 
                              className="group cursor-pointer hover:bg-muted/40 transition-all border-b border-border/40"
                            >
                              {selectionEnabled && (
                                <TableCell className="pl-8 py-6 text-center">
                                  <input
                                    data-testid={`session-select-${session.session_id}`}
                                    type="checkbox"
                                    checked={selectionMode !== 'filtered_all' && selectedSessionIds.includes(session.session_id)}
                                    onClick={(event) => event.stopPropagation()}
                                    onChange={(event) => toggleSessionSelected(session.session_id, event.target.checked)}
                                    aria-label={`选择会话 ${parseTitle(session.meta)}`}
                                  />
                                </TableCell>
                              )}
                              <TableCell className="pl-10 py-6">
                                <Badge variant={session.status === 'active' ? 'default' : 'secondary'} className={`capitalize font-bold text-[10px] px-3 py-1 shadow-sm ${session.status === 'active' ? 'bg-primary shadow-primary/20' : ''}`}>
                                  {session.status || 'active'}
                                </Badge>
                              </TableCell>
                              <TableCell className="font-mono text-sm text-foreground/70 font-bold">{session.session_id.slice(0, 8)}...</TableCell>
                              <TableCell className="font-bold text-lg text-foreground group-hover:text-primary transition-colors">{parseTitle(session.meta)}</TableCell>
                              <TableCell>
                                {target ? (
                                  <Badge variant="outline" className="gap-2 bg-primary/5 text-primary text-xs px-3 py-1.5 font-bold border-primary/20 rounded-lg">
                                    <Bot size={14} />
                                    {target.id}
                                  </Badge>
                                ) : (
                                  <span className="text-sm text-muted-foreground/60 italic font-medium">system-default</span>
                                )}
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground font-medium">{formatTime(session.created_at)}</TableCell>
                              <TableCell className="py-6 text-center">
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  className="text-muted-foreground hover:text-destructive"
                                  data-testid={`session-delete-button-${session.session_id}`}
                                  aria-label={`删除会话 ${parseTitle(session.meta)}`}
                                  title={`删除会话 ${parseTitle(session.meta)}`}
                                  onClick={(event) => requestDeleteSession(event, session)}
                                >
                                  <Trash2 size={16} />
                                </Button>
                              </TableCell>
                              <TableCell className="pr-10 py-6 text-sm text-muted-foreground font-black text-right group-hover:text-foreground transition-colors uppercase tracking-tighter">{timeAgo(session.last_active)}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {showNewChat && (
        <NewChatModal onClose={() => setShowNewChat(false)} />
      )}

      <Dialog open={!!sessionToDelete} onOpenChange={(open) => {
        if (!open) {
          setSessionToDelete(null);
          setDeleteError('');
        }
      }}>
        <DialogContent data-testid="session-delete-dialog">
          <DialogHeader>
            <DialogTitle>确认删除会话</DialogTitle>
            <DialogDescription>
              {sessionToDelete
                ? `确定要删除会话 "${parseTitle(sessionToDelete.meta)}" 吗？如果该会话仍在运行，将被强制终止并删除对应的 session 文件。`
                : ''}
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setSessionToDelete(null);
                setDeleteError('');
              }}
              disabled={!!deletingSessionId}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              data-testid="session-delete-confirm"
              onClick={deleteSession}
              disabled={!sessionToDelete || !!deletingSessionId}
              className="gap-2"
            >
              {deletingSessionId && <Loader2 size={16} className="animate-spin" />}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showBulkDeleteConfirm} onOpenChange={(open) => {
        setShowBulkDeleteConfirm(open);
        if (!open) setBulkDeleteError('');
      }}>
        <DialogContent data-testid="session-bulk-delete-dialog">
          <DialogHeader>
            <DialogTitle>确认批量删除会话</DialogTitle>
            <DialogDescription>
              {selectionMode === 'filtered_all'
                ? '确定删除所有符合当前筛选条件的会话吗？这会按当前搜索词和状态筛选条件匹配后端全部命中结果。'
                : `确定删除选中的 ${selectedSessionIds.length} 个会话吗？如果其中仍有会话在运行，将被强制终止并删除对应的 session 文件。`}
            </DialogDescription>
          </DialogHeader>
          {bulkDeleteError && <p className="text-sm text-destructive">{bulkDeleteError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBulkDeleteConfirm(false)} disabled={bulkDeleting}>
              取消
            </Button>
            <Button
              data-testid="session-bulk-delete-confirm"
              variant="destructive"
              onClick={bulkDeleteSessions}
              disabled={bulkDeleting}
              className="gap-2"
            >
              {bulkDeleting && <Loader2 size={16} className="animate-spin" />}
              删除选中
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
}

/* ===== New Chat Modal ===== */

function NewChatModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    authFetch(`${API_BASE}/api/agents`).then(r => r.json()).catch(() => []).then(a => {
      setAgents(a);
    }).finally(() => setLoading(false));
  }, []);

  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.id.toLowerCase().includes(search.toLowerCase())
  );

  const selectAgent = (agentId: string) => {
    router.push(`/chat?agent=${encodeURIComponent(agentId)}`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <Card className="w-full max-w-lg mx-4 max-h-[70vh] flex flex-col shadow-lg">
        <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border">
          <CardTitle className="text-lg">新建会话</CardTitle>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded text-muted-foreground"><X size={16} /></button>
        </CardHeader>

        <div className="p-4 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索 Agent..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
        </div>

        <CardContent className="flex-1 overflow-auto p-4 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="animate-spin text-muted-foreground" size={24} />
            </div>
          ) : (
            filteredAgents.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-8">暂无 Agent</div>
            ) : (
              filteredAgents.map(a => (
                <button
                  key={a.id}
                  onClick={() => selectAgent(a.id)}
                  className="w-full text-left bg-background border border-border rounded-lg p-3 hover:border-primary/50 transition-colors group flex flex-col gap-1"
                >
                  <div className="flex items-center gap-2">
                    <Bot size={14} className="text-primary" />
                    <span className="text-sm font-semibold">{a.name}</span>
                    <span className="text-[10px] text-muted-foreground font-mono">{a.id}</span>
                  </div>
                  {a.description && (
                    <p className="text-xs text-muted-foreground line-clamp-1 ml-5">{a.description}</p>
                  )}
                </button>
              ))
            )
          )}
        </CardContent>

        <div className="px-4 py-3 border-t border-border bg-muted/30">
          <button
            onClick={() => router.push('/chat')}
            className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors py-1.5"
          >
            或直接使用默认 Agent 开始对话 →
          </button>
        </div>
      </Card>
    </div>
  );
}
