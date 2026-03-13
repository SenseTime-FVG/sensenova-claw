'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, Search, Activity, MessageSquare, Loader2, Trash2, X, Network, Bot, ChevronRight } from 'lucide-react';
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

interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  version: string;
  nodeCount: number;
  edgeCount: number;
  enabled: boolean;
  createdAt: number;
  updatedAt: number;
}

export default function OrchestrationPage() {
  const router = useRouter();
  const [searchTerm, setSearchTerm] = useState('');

  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [showCreateAgent, setShowCreateAgent] = useState(false);

  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(true);
  const [showCreateWorkflow, setShowCreateWorkflow] = useState(false);

  const loadAgents = () => {
    setAgentsLoading(true);
    fetch(`${API_BASE}/api/agents`)
      .then(res => res.json())
      .then(data => setAgents(data))
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false));
  };

  const loadWorkflows = () => {
    setWorkflowsLoading(true);
    fetch(`${API_BASE}/api/workflows`)
      .then(res => res.json())
      .then(data => setWorkflows(data))
      .catch(() => setWorkflows([]))
      .finally(() => setWorkflowsLoading(false));
  };

  useEffect(() => { loadAgents(); loadWorkflows(); }, []);

  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredWorkflows = workflows.filter(w =>
    w.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    w.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const deleteAgent = async (e: React.MouseEvent, agentId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`确定要删除 Agent "${agentId}" 吗？`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/agents/${agentId}`, { method: 'DELETE' });
      if (res.ok) loadAgents();
    } catch { /* ignore */ }
  };

  const deleteWorkflow = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`确定要删除 Workflow "${id}" 吗？`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/workflows/${id}`, { method: 'DELETE' });
      if (res.ok) loadWorkflows();
    } catch { /* ignore */ }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'inactive': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const loading = agentsLoading || workflowsLoading;

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-semibold text-[#cccccc]">编排中心</h1>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCreateAgent(true)}
                className="flex items-center gap-2 px-4 py-2 bg-[#0e639c] hover:bg-[#1177bb] rounded text-white text-sm transition-colors"
              >
                <Plus size={16} />
                New Agent
              </button>
              <button
                onClick={() => setShowCreateWorkflow(true)}
                className="flex items-center gap-2 px-4 py-2 bg-[#3c3c3c] hover:bg-[#4c4c4c] rounded text-[#cccccc] text-sm transition-colors border border-[#5a5a5a]"
              >
                <Plus size={16} />
                New Workflow
              </button>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
            <input
              type="text"
              placeholder="搜索 Agents 或 Workflows..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-10 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : (
            <>
              {/* Agents 区块 */}
              <section>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Bot size={18} className="text-[#007acc]" />
                    <h2 className="text-sm font-semibold text-[#cccccc]">
                      Agents
                    </h2>
                    <span className="text-xs text-[#858585] bg-[#3c3c3c] px-2 py-0.5 rounded-full">
                      {filteredAgents.length}
                    </span>
                  </div>
                </div>

                {filteredAgents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-[#858585]">
                    <Bot size={36} className="mb-2 opacity-50" />
                    <p className="text-sm">{searchTerm ? '没有匹配的 Agent' : '暂无 Agent，点击上方按钮创建'}</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredAgents.map((agent) => (
                      <Link
                        key={agent.id}
                        href={`/agents/${agent.id}`}
                        className="bg-[#252526] border border-[#2d2d30] rounded-lg p-4 hover:border-[#007acc] transition-colors block group"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`} />
                            <h3 className="font-semibold text-[#cccccc] text-sm">{agent.name}</h3>
                          </div>
                          <div className="flex items-center gap-1">
                            {agent.id !== 'default' && (
                              <button
                                onClick={(e) => deleteAgent(e, agent.id)}
                                className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-[#3c3c3c] transition-all"
                                title="删除 Agent"
                              >
                                <Trash2 size={13} className="text-red-400" />
                              </button>
                            )}
                            <ChevronRight size={14} className="text-[#858585] opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                        </div>

                        <p className="text-xs text-[#858585] mb-2 line-clamp-2">{agent.description}</p>
                        {agent.provider && (
                          <div className="text-xs text-[#007acc] mb-2">
                            {agent.provider} / {agent.model}
                          </div>
                        )}

                        <div className="flex items-center gap-3 text-xs text-[#858585]">
                          <div className="flex items-center gap-1">
                            <MessageSquare size={11} />
                            <span>{agent.sessionCount} sessions</span>
                          </div>
                          <span>{agent.toolCount} tools</span>
                          <span>{agent.skillCount} skills</span>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              {/* 分隔线 */}
              <div className="border-t border-[#2d2d30]" />

              {/* Workflows 区块 */}
              <section>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Network size={18} className="text-[#4ec9b0]" />
                    <h2 className="text-sm font-semibold text-[#cccccc]">
                      Workflows
                    </h2>
                    <span className="text-xs text-[#858585] bg-[#3c3c3c] px-2 py-0.5 rounded-full">
                      {filteredWorkflows.length}
                    </span>
                  </div>
                </div>

                {filteredWorkflows.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-[#858585]">
                    <Network size={36} className="mb-2 opacity-50" />
                    <p className="text-sm">{searchTerm ? '没有匹配的 Workflow' : '暂无 Workflow，点击上方按钮创建'}</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredWorkflows.map((wf) => (
                      <Link
                        key={wf.id}
                        href={`/workflows/${wf.id}`}
                        className="bg-[#252526] border border-[#2d2d30] rounded-lg p-4 hover:border-[#4ec9b0] transition-colors block group"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${wf.enabled ? 'bg-green-500' : 'bg-gray-500'}`} />
                            <h3 className="font-semibold text-[#cccccc] text-sm">{wf.name}</h3>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={(e) => deleteWorkflow(e, wf.id)}
                              className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-[#3c3c3c] transition-all"
                              title="删除 Workflow"
                            >
                              <Trash2 size={13} className="text-red-400" />
                            </button>
                            <span className="text-xs bg-[#3c3c3c] text-[#858585] px-1.5 py-0.5 rounded">v{wf.version}</span>
                          </div>
                        </div>

                        <p className="text-xs text-[#858585] mb-2 line-clamp-2">{wf.description || '无描述'}</p>

                        <div className="flex items-center gap-3 text-xs text-[#858585]">
                          <span>{wf.nodeCount} 节点</span>
                          <span>{wf.edgeCount} 边</span>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>

      {/* Create Agent Modal */}
      {showCreateAgent && (
        <CreateAgentModal onClose={() => setShowCreateAgent(false)} onCreated={loadAgents} />
      )}

      {/* Create Workflow Modal */}
      {showCreateWorkflow && (
        <CreateWorkflowModal
          onClose={() => setShowCreateWorkflow(false)}
          onCreated={(id) => { router.push(`/workflows/${id}`); }}
        />
      )}
    </DashboardLayout>
  );
}

/* ===== Create Agent Modal ===== */

function CreateAgentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [formId, setFormId] = useState('');
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formProvider, setFormProvider] = useState('openai');
  const [formModel, setFormModel] = useState('gpt-4o-mini');
  const [formTemp, setFormTemp] = useState('0.2');
  const [formPrompt, setFormPrompt] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!formId.trim() || !formName.trim()) {
      setError('ID 和名称为必填项');
      return;
    }
    setCreating(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: formId.trim(),
          name: formName.trim(),
          description: formDesc.trim(),
          provider: formProvider.trim() || undefined,
          model: formModel.trim() || undefined,
          temperature: parseFloat(formTemp) || 0.2,
          system_prompt: formPrompt,
        }),
      });
      if (res.status === 409) {
        setError('ID 已存在');
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || '创建失败');
        return;
      }
      onCreated();
      onClose();
    } catch {
      setError('创建失败');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[#252526] border border-[#2d2d30] rounded-lg w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2d2d30]">
          <h2 className="text-sm font-semibold text-[#cccccc]">创建新 Agent</h2>
          <button onClick={onClose} className="p-1 hover:bg-[#3c3c3c] rounded"><X size={16} className="text-[#858585]" /></button>
        </div>
        <div className="p-4 space-y-3 overflow-auto flex-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">ID (唯一标识)</label>
              <input value={formId} onChange={e => setFormId(e.target.value)} placeholder="research-agent"
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">名称</label>
              <input value={formName} onChange={e => setFormName(e.target.value)} placeholder="Research Agent"
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[#858585] text-xs">描述</label>
            <input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="负责搜索和研究的 Agent"
              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">Provider</label>
              <input value={formProvider} onChange={e => setFormProvider(e.target.value)}
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">Model</label>
              <input value={formModel} onChange={e => setFormModel(e.target.value)}
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">Temperature</label>
              <input type="number" step="any" value={formTemp} onChange={e => setFormTemp(e.target.value)}
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[#858585] text-xs">System Prompt</label>
            <textarea value={formPrompt} onChange={e => setFormPrompt(e.target.value)} rows={3}
              placeholder="你是一个有用的AI助手..."
              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-2 text-sm text-[#cccccc] font-mono resize-y focus:outline-none focus:border-[#007acc]"
              spellCheck={false} />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#2d2d30]">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-[#858585] hover:text-[#cccccc] transition-colors">取消</button>
          <button onClick={handleCreate} disabled={creating}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-[#0e639c] text-white text-sm rounded hover:bg-[#1177bb] disabled:opacity-50">
            {creating && <Loader2 size={14} className="animate-spin" />}
            创建
          </button>
        </div>
      </div>
    </div>
  );
}

/* ===== Create Workflow Modal ===== */

function CreateWorkflowModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [formId, setFormId] = useState('');
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formVersion, setFormVersion] = useState('1.0');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!formId.trim() || !formName.trim()) {
      setError('ID 和名称为必填项');
      return;
    }
    setCreating(true); setError('');
    try {
      const res = await fetch(`${API_BASE}/api/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: formId.trim(),
          name: formName.trim(),
          description: formDesc.trim(),
          version: formVersion.trim() || '1.0',
          nodes: [],
          edges: [],
        }),
      });
      if (res.status === 409) { setError('ID 已存在'); return; }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || '创建失败');
        return;
      }
      onCreated(formId.trim());
    } catch { setError('创建失败'); }
    finally { setCreating(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[#252526] border border-[#2d2d30] rounded-lg w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2d2d30]">
          <h2 className="text-sm font-semibold text-[#cccccc]">创建新 Workflow</h2>
          <button onClick={onClose} className="p-1 hover:bg-[#3c3c3c] rounded"><X size={16} className="text-[#858585]" /></button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">ID (唯一标识)</label>
              <input value={formId} onChange={e => setFormId(e.target.value)} placeholder="my-workflow"
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
            <div className="space-y-1">
              <label className="text-[#858585] text-xs">名称</label>
              <input value={formName} onChange={e => setFormName(e.target.value)} placeholder="我的工作流"
                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[#858585] text-xs">描述</label>
            <input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="工作流描述"
              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
          </div>
          <div className="space-y-1">
            <label className="text-[#858585] text-xs">版本</label>
            <input value={formVersion} onChange={e => setFormVersion(e.target.value)}
              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#2d2d30]">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-[#858585] hover:text-[#cccccc] transition-colors">取消</button>
          <button onClick={handleCreate} disabled={creating}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-[#0e639c] text-white text-sm rounded hover:bg-[#1177bb] disabled:opacity-50">
            {creating && <Loader2 size={14} className="animate-spin" />}
            创建
          </button>
        </div>
      </div>
    </div>
  );
}
