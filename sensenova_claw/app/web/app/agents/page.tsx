'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Plus, Search, Activity, MessageSquare, Loader2, X, Bot, Wrench, Trash2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useCustomPages } from '@/hooks/useCustomPages';

interface Agent {
  id: string;
  name: string;
  status: string;
  description: string;
  model: string;
  sessionCount: number;
  toolCount: number;
  skillCount: number;
  lastActive: string;
}

export default function OrchestrationPage() {
  const { refresh: refreshCustomPages } = useCustomPages();
  const [searchTerm, setSearchTerm] = useState('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null);

  const loadAgents = () => {
    setAgentsLoading(true);
    authFetch(`${API_BASE}/api/agents`)
      .then(res => res.json())
      .then(data => setAgents(data))
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false));
  };

  useEffect(() => { loadAgents(); }, []);

  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const requestDeleteAgent = (e: React.MouseEvent, agent: Agent) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteError('');
    setAgentToDelete(agent);
  };

  const deleteAgent = async () => {
    if (!agentToDelete) return;
    setDeletingAgentId(agentToDelete.id);
    setDeleteError('');
    try {
      const res = await authFetch(`${API_BASE}/api/agents/${agentToDelete.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setDeleteError(data.detail || '删除失败');
        return;
      }
      setAgentToDelete(null);
      await refreshCustomPages();
      loadAgents();
    } catch {
      setDeleteError('删除失败');
    } finally {
      setDeletingAgentId(null);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'default';
      case 'inactive': return 'secondary';
      case 'error': return 'destructive';
      default: return 'secondary';
    }
  };

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Dashboard</h2>
          <Button onClick={() => setShowCreateAgent(true)} size="lg" className="gap-2 rounded-xl px-8 font-bold shadow-lg shadow-primary/20">
            <Plus size={18} /> New Agent
          </Button>
        </div>

        <div className="flex flex-col md:flex-row gap-8 mt-10">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">Overview</p>
              <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                <Bot className="h-5 w-5" /> Agents
              </button>
              <Link
                href="/agents/analytics"
                className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Activity className="h-5 w-5" /> Analytics
              </Link>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 space-y-8">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Total Agents</CardTitle>
                  <Bot className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{agents.length}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Registered agent instances</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Total Sessions</CardTitle>
                  <MessageSquare className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{agents.reduce((acc, a) => acc + (a.sessionCount || 0), 0)}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Cumulative conversations</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Active Tools</CardTitle>
                  <Wrench className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{agents.reduce((acc, a) => acc + (a.toolCount || 0), 0)}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Enabled tool bindings</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">System Status</CardTitle>
                  <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black text-green-600 dark:text-green-500">Healthy</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">All services operational</p>
                </CardContent>
              </Card>
            </div>

            <Card className="shadow-xl border-border/80 overflow-hidden">
              <CardHeader className="bg-muted/30 border-b p-8">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                  <div>
                    <CardTitle className="text-2xl font-bold">Agent Registry</CardTitle>
                    <CardDescription className="text-base mt-2">
                      Manage and inspect all registered agent configurations.
                    </CardDescription>
                  </div>
                  <div className="relative w-full md:w-96">
                    <Search className="absolute left-4 top-4 h-5 w-5 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Search agents..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-12 py-7 text-base bg-background rounded-2xl shadow-inner border-border/60"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-8">
                {agentsLoading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-primary" size={48} />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest">Hydrating agent registry...</p>
                  </div>
                ) : filteredAgents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-24 border border-dashed rounded-2xl text-center text-muted-foreground bg-muted/5">
                    <Bot size={64} className="mb-4 opacity-20" />
                    <p className="text-lg font-bold uppercase tracking-widest opacity-40">{searchTerm ? 'No agents match your search' : 'No agents registered'}</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredAgents.map((agent) => (
                      <div key={agent.id} className="flex flex-col p-8 border border-border/60 rounded-2xl bg-card hover:bg-muted/30 transition-all shadow-sm group relative overflow-hidden h-full">
                        <div className={`absolute top-0 right-0 w-2 h-full ${agent.status === 'active' ? 'bg-green-500/40' : 'bg-muted-foreground/20'}`} />
                        <div className="flex items-center justify-between mb-3">
                          <Link href={`/agents/${agent.id}`} className="flex items-center gap-2 min-w-0">
                            <h3 className="text-xl font-bold text-foreground group-hover:text-primary transition-colors">{agent.name}</h3>
                            <Badge variant={getStatusColor(agent.status) as any} className={`text-[10px] font-black uppercase tracking-wider px-2.5 py-1 ${agent.status === 'active' ? 'bg-green-500 text-white shadow-sm' : ''}`}>
                              {agent.status}
                            </Badge>
                          </Link>
                          {agent.id !== 'default' && (
                            <button
                              className="shrink-0 p-1.5 rounded-lg text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all"
                              data-testid={`agent-delete-button-${agent.id}`}
                              aria-label={`删除 ${agent.name}`}
                              title={`删除 ${agent.name}`}
                              onClick={(e) => requestDeleteAgent(e, agent)}
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </div>
                        <Link href={`/agents/${agent.id}`} className="block">
                          <p className="text-base leading-relaxed text-muted-foreground line-clamp-2 min-h-[48px] mb-4">
                            {agent.description || "No description provided."}
                          </p>
                          <div className="mt-auto flex items-center justify-between pt-4 border-t border-border/40">
                            <div className="flex items-center gap-4 text-sm text-muted-foreground">
                              <span className="flex items-center gap-1.5" title="Sessions"><MessageSquare size={16}/> {agent.sessionCount || 0}</span>
                              <span className="flex items-center gap-1.5" title="Tools"><Wrench size={16}/> {agent.toolCount || 0}</span>
                            </div>
                            <span className="text-xs font-mono font-black uppercase bg-muted text-muted-foreground/60 px-2.5 py-1 rounded-lg tracking-wider">{agent.model}</span>
                          </div>
                        </Link>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Create Agent Modal */}
      {showCreateAgent && (
        <CreateAgentModal onClose={() => setShowCreateAgent(false)} onCreated={loadAgents} />
      )}

      <Dialog open={!!agentToDelete} onOpenChange={(open) => {
        if (!open) {
          setAgentToDelete(null);
          setDeleteError('');
        }
      }}>
        <DialogContent data-testid="agent-delete-dialog">
          <DialogHeader>
            <DialogTitle>确认删除 Agent</DialogTitle>
            <DialogDescription>
              {agentToDelete
                ? `确定要删除 Agent "${agentToDelete.name}" 吗？该操作会移除它的注册配置。`
                : ''}
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setAgentToDelete(null);
                setDeleteError('');
              }}
              disabled={!!deletingAgentId}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              data-testid="agent-delete-confirm"
              onClick={deleteAgent}
              disabled={!agentToDelete || !!deletingAgentId}
              className="gap-2"
            >
              {deletingAgentId && <Loader2 size={16} className="animate-spin" />}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
}

/* ===== Create Agent Modal ===== */

function CreateAgentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [formId, setFormId] = useState('');
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formModel, setFormModel] = useState('');
  const [formTemp, setFormTemp] = useState('0.2');
  const [formPrompt, setFormPrompt] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    authFetch(`${API_BASE}/api/config/sections`)
      .then(res => res.json())
      .then(data => {
        if (cancelled) return;
        const llm = data?.llm;
        const models = llm?.models && typeof llm.models === 'object'
          ? Object.keys(llm.models).filter(key => key !== 'mock')
          : [];
        const defaultModel = typeof llm?.default_model === 'string' ? llm.default_model : '';

        setAvailableModels(models);
        setFormModel(currentValue => {
          if (currentValue && models.includes(currentValue)) return currentValue;
          if (defaultModel && models.includes(defaultModel)) return defaultModel;
          return models[0] || '';
        });
      })
      .catch(() => {
        if (!cancelled) {
          setAvailableModels([]);
          setFormModel('');
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreate = async () => {
    if (!formId.trim() || !formName.trim()) {
      setError('ID 和名称为必填项');
      return;
    }
    setCreating(true);
    setError('');
    try {
      const res = await authFetch(`${API_BASE}/api/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: formId.trim(),
          name: formName.trim(),
          description: formDesc.trim(),
          model: formModel.trim() || undefined,
          temperature: parseFloat(formTemp) || 1.0,
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <Card className="w-full max-w-lg mx-4 max-h-[80vh] flex flex-col shadow-lg">
        <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border text-foreground">
          <CardTitle className="text-lg">创建新 Agent</CardTitle>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"><X size={16} /></button>
        </CardHeader>
        <CardContent className="p-4 space-y-4 overflow-auto flex-1 text-foreground">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">ID (唯一标识)</label>
              <Input value={formId} onChange={e => setFormId(e.target.value)} placeholder="research-agent" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">名称</label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="Research Agent" />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">描述</label>
            <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="负责搜索和研究的 Agent" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Model</label>
              <select
                value={formModel}
                onChange={e => setFormModel(e.target.value)}
                data-testid="agent-model-select"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <option value="">跟随系统默认模型</option>
                {availableModels.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
              {availableModels.length === 0 && (
                <p className="text-xs text-muted-foreground">当前未发现已配置模型，创建时将跟随系统默认模型。</p>
              )}
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Temperature</label>
              <Input type="number" step="any" value={formTemp} onChange={e => setFormTemp(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">System Prompt</label>
            <textarea value={formPrompt} onChange={e => setFormPrompt(e.target.value)} rows={4}
              placeholder="你是一个有用的AI助手..."
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              spellCheck={false} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-border bg-muted/30">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleCreate} disabled={creating} className="gap-2">
            {creating && <Loader2 size={16} className="animate-spin" />}
            创建
          </Button>
        </div>
      </Card>
    </div>
  );
}
