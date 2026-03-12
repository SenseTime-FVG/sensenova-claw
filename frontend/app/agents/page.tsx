'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Plus, Search, Activity, MessageSquare, Loader2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Agent {
  id: string;
  name: string;
  status: string;
  description: string;
  provider: string;
  model: string;
  sessionCount: number;
  toolCount: number;
  skillCount: number;
  lastActive: string;
}

export default function AgentsPage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/agents`)
      .then(res => res.json())
      .then(data => setAgents(data))
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  }, []);

  const filteredAgents = agents.filter((agent) =>
    agent.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'inactive': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-semibold text-[#cccccc]">Agents</h1>
            <button className="flex items-center gap-2 px-4 py-2 bg-[#0e639c] hover:bg-[#1177bb] rounded text-white text-sm transition-colors">
              <Plus size={16} />
              New Agent
            </button>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
            <input
              type="text"
              placeholder="Search agents..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-10 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
            />
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredAgents.map((agent) => (
                <Link
                  key={agent.id}
                  href={`/agents/${agent.id}`}
                  className="bg-[#252526] border border-[#2d2d30] rounded p-4 hover:border-[#007acc] transition-colors block"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`} />
                      <h3 className="font-semibold text-[#cccccc]">{agent.name}</h3>
                    </div>
                    <Activity size={16} className="text-[#858585]" />
                  </div>

                  <p className="text-sm text-[#858585] mb-2 line-clamp-2">{agent.description}</p>
                  {agent.provider && (
                    <div className="text-xs text-[#007acc] mb-3">
                      {agent.provider} / {agent.model}
                    </div>
                  )}

                  <div className="flex items-center gap-4 text-xs text-[#858585]">
                    <div className="flex items-center gap-1">
                      <MessageSquare size={12} />
                      <span>{agent.sessionCount} sessions</span>
                    </div>
                    <span>{agent.toolCount} tools</span>
                    <span>{agent.skillCount} skills</span>
                  </div>

                  <div className="mt-3 pt-3 border-t border-[#2d2d30] text-xs text-[#858585]">
                    Last active: {agent.lastActive}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
