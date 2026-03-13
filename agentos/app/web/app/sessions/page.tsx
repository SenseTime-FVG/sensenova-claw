'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Filter, MessageSquare, Loader2, Plus, X, Bot } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

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
      <div className="h-full flex flex-col">
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-semibold text-[#cccccc]">Sessions</h1>
            <button
              onClick={() => setShowNewChat(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] transition-colors"
            >
              <Plus size={14} />
              New Chat
            </button>
          </div>
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={14} />
              <input
                type="text"
                placeholder="Search sessions..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-9 py-1.5 text-xs text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
              />
            </div>
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={14} />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-[#3c3c3c] border border-[#5a5a5a] rounded pl-9 pr-3 py-1.5 text-xs text-[#cccccc] focus:outline-none focus:border-[#007acc] cursor-pointer"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </div>
          <div className="flex gap-6 mt-4 text-sm">
            <div>
              <span className="text-[#858585]">Total: </span>
              <span className="text-[#cccccc]">{sessions.length}</span>
            </div>
            <div>
              <span className="text-[#858585]">Active: </span>
              <span className="text-green-400">{sessions.filter(s => s.status === 'active').length}</span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[#858585] text-sm">
              No sessions found
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-[#252526] border-b border-[#2d2d30] sticky top-0">
                <tr>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Status</th>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Session ID</th>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Title</th>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Target</th>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Created</th>
                  <th className="text-left p-4 font-semibold text-[#cccccc]">Last Active</th>
                </tr>
              </thead>
              <tbody>
                {filteredSessions.map((session) => {
                  const target = getTargetLabel(session.meta);
                  return (
                    <tr key={session.session_id} onClick={() => router.push(`/sessions/${session.session_id}`)} className="border-b border-[#2d2d30] hover:bg-[#2a2d2e] transition-colors cursor-pointer">
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${session.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}`} />
                          <span className="text-[#cccccc] capitalize">{session.status || 'active'}</span>
                        </div>
                      </td>
                      <td className="p-4 text-[#858585] font-mono text-xs">{session.session_id}</td>
                      <td className="p-4 text-[#cccccc]">{parseTitle(session.meta)}</td>
                      <td className="p-4">
                        {target ? (
                          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-[#007acc]/15 text-[#007acc]">
                            <Bot size={10} />
                            {target.id}
                          </span>
                        ) : (
                          <span className="text-xs text-[#585858]">default</span>
                        )}
                      </td>
                      <td className="p-4 text-[#858585] text-xs">{formatTime(session.created_at)}</td>
                      <td className="p-4 text-[#858585] text-xs">{timeAgo(session.last_active)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[#252526] border border-[#2d2d30] rounded-lg w-full max-w-lg mx-4 max-h-[70vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2d2d30]">
          <h2 className="text-sm font-semibold text-[#cccccc]">新建会话</h2>
          <button onClick={onClose} className="p-1 hover:bg-[#3c3c3c] rounded">
            <X size={16} className="text-[#858585]" />
          </button>
        </div>

        {/* 标题 */}
        <div className="flex border-b border-[#2d2d30]">
          <div className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs text-[#cccccc] border-b-2 border-[#007acc]">
            <Bot size={14} />
            选择 Agent
          </div>
        </div>

        {/* 搜索 */}
        <div className="px-4 pt-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={13} />
            <input
              type="text"
              placeholder="搜索 Agent..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-9 py-1.5 text-xs text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
            />
          </div>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-auto p-4 space-y-1.5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="animate-spin text-[#858585]" size={24} />
            </div>
          ) : (
            filteredAgents.length === 0 ? (
              <div className="text-center text-[#858585] text-xs py-8">暂无 Agent</div>
            ) : (
              filteredAgents.map(a => (
                <button
                  key={a.id}
                  onClick={() => selectAgent(a.id)}
                  className="w-full text-left bg-[#1e1e1e] border border-[#2d2d30] rounded-lg p-3 hover:border-[#007acc] transition-colors group"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Bot size={14} className="text-[#007acc]" />
                    <span className="text-sm font-medium text-[#cccccc]">{a.name}</span>
                    <span className="text-[10px] text-[#585858] font-mono">{a.id}</span>
                  </div>
                  {a.description && (
                    <p className="text-xs text-[#858585] line-clamp-1 ml-5">{a.description}</p>
                  )}
                </button>
              ))
            )
          )}
        </div>

        {/* 底部：快速开始 */}
        <div className="px-4 py-3 border-t border-[#2d2d30]">
          <button
            onClick={() => router.push('/chat')}
            className="w-full text-center text-xs text-[#858585] hover:text-[#cccccc] transition-colors py-1.5"
          >
            或直接使用默认 Agent 开始对话 →
          </button>
        </div>
      </div>
    </div>
  );
}
