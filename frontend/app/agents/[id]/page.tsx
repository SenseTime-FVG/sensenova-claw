'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Settings, Loader2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface AgentDetail {
  id: string;
  name: string;
  status: string;
  description: string;
  provider: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  sessionCount: number;
  toolCount: number;
  skillCount: number;
  tools: string[];
  skills: string[];
  sessions: { id: string; status: string; channel: string; messageCount: number }[];
}

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.id as string;
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'config' | 'tools' | 'skills' | 'sessions'>('config');

  useEffect(() => {
    fetch(`${API_BASE}/api/agents/${agentId}`)
      .then(res => res.json())
      .then(data => setAgent(data))
      .catch(() => setAgent(null))
      .finally(() => setLoading(false));
  }, [agentId]);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-full">
          <Loader2 className="animate-spin text-[#858585]" size={32} />
        </div>
      </DashboardLayout>
    );
  }

  if (!agent) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-full text-[#858585]">
          Agent not found
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center gap-4 mb-4">
            <Link href="/agents" className="p-2 hover:bg-[#2d2d30] rounded transition-colors">
              <ArrowLeft size={20} />
            </Link>
            <div className="flex-1">
              <h1 className="text-xl font-semibold text-[#cccccc]">{agent.name}</h1>
              <p className="text-sm text-[#858585] mt-1">{agent.description}</p>
            </div>
            <button className="p-2 hover:bg-[#2d2d30] rounded transition-colors" title="Configure">
              <Settings size={20} />
            </button>
          </div>
          <div className="flex gap-6 text-sm">
            <div>
              <span className="text-[#858585]">Status: </span>
              <span className="text-green-400">{agent.status}</span>
            </div>
            <div>
              <span className="text-[#858585]">Provider: </span>
              <span className="text-[#cccccc]">{agent.provider}</span>
            </div>
            <div>
              <span className="text-[#858585]">Model: </span>
              <span className="text-[#cccccc]">{agent.model}</span>
            </div>
            <div>
              <span className="text-[#858585]">Sessions: </span>
              <span className="text-[#cccccc]">{agent.sessionCount}</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-[#252526] border-b border-[#2d2d30] px-4">
          <div className="flex gap-1">
            {(['config', 'tools', 'skills', 'sessions'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm capitalize transition-colors ${
                  activeTab === tab
                    ? 'text-[#cccccc] border-b-2 border-[#007acc]'
                    : 'text-[#858585] hover:text-[#cccccc]'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 'config' && (
            <div className="space-y-4 max-w-2xl">
              <div className="bg-[#252526] border border-[#2d2d30] rounded p-4">
                <h2 className="text-sm font-semibold text-[#cccccc] mb-3">Agent Configuration</h2>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-[#858585]">Provider</span>
                    <span className="text-[#cccccc]">{agent.provider}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#858585]">Model</span>
                    <span className="text-[#cccccc]">{agent.model}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#858585]">Temperature</span>
                    <span className="text-[#cccccc]">{agent.temperature}</span>
                  </div>
                </div>
              </div>
              <div className="bg-[#252526] border border-[#2d2d30] rounded p-4">
                <h2 className="text-sm font-semibold text-[#cccccc] mb-3">System Prompt</h2>
                <pre className="text-xs text-[#858585] font-mono whitespace-pre-wrap bg-[#1e1e1e] p-3 rounded border border-[#2d2d30]">
                  {agent.systemPrompt || '(empty)'}
                </pre>
              </div>
            </div>
          )}

          {activeTab === 'tools' && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-[#cccccc] mb-4">
                Tools ({agent.tools.length})
              </h2>
              {agent.tools.map((toolName) => (
                <div
                  key={toolName}
                  className="bg-[#252526] border border-[#2d2d30] rounded p-3 flex items-center justify-between hover:border-[#3e3e42] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-green-500" />
                    <span className="text-[#cccccc] text-sm">{toolName}</span>
                  </div>
                  <span className="text-xs text-[#858585]">enabled</span>
                </div>
              ))}
              {agent.tools.length === 0 && (
                <p className="text-sm text-[#858585]">No tools registered</p>
              )}
            </div>
          )}

          {activeTab === 'skills' && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-[#cccccc] mb-4">
                Skills ({agent.skills.length})
              </h2>
              {agent.skills.map((skillName) => (
                <div
                  key={skillName}
                  className="bg-[#252526] border border-[#2d2d30] rounded p-3 flex items-center justify-between hover:border-[#3e3e42] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-blue-500" />
                    <span className="text-[#cccccc] text-sm">{skillName}</span>
                  </div>
                  <span className="text-xs text-[#858585]">loaded</span>
                </div>
              ))}
              {agent.skills.length === 0 && (
                <p className="text-sm text-[#858585]">No skills loaded</p>
              )}
            </div>
          )}

          {activeTab === 'sessions' && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-[#cccccc] mb-4">
                Sessions ({agent.sessions?.length || 0})
              </h2>
              {(agent.sessions || []).map((session) => (
                <Link
                  key={session.id}
                  href={`/sessions/${session.id}`}
                  className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#007acc] transition-colors block"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${session.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}`} />
                      <span className="text-sm text-[#cccccc] font-mono">{session.id}</span>
                    </div>
                    <span className="text-xs text-[#858585]">{session.channel}</span>
                  </div>
                </Link>
              ))}
              {(!agent.sessions || agent.sessions.length === 0) && (
                <p className="text-sm text-[#858585]">No sessions</p>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
