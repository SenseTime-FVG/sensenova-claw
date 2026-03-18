'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Filter, MessageSquare, Loader2, Plus, X, Bot } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

  useEffect(() => {
    fetch(`${API_BASE}/api/sessions`)
      .then(res => res.json())
      .then(data => setSessions(data.sessions || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
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

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Sessions History</h2>
          <Button onClick={() => setShowNewChat(true)} size="lg" className="rounded-xl px-8 font-bold gap-2 shadow-lg shadow-primary/20">
            <Plus size={20} /> New Conversation
          </Button>
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
                          <TableHead className="pl-10 py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Status</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Identity</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Session Title</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Primary Actor</TableHead>
                          <TableHead className="py-5 text-xs font-black uppercase tracking-widest text-muted-foreground">Timestamp</TableHead>
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
    fetch(`${API_BASE}/api/agents`).then(r => r.json()).catch(() => []).then(a => {
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
