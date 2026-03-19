'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Plus, Search, Activity, MessageSquare, Loader2, Trash2, X, Bot, ChevronRight, Wrench } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { authFetch, API_BASE } from '@/lib/authFetch';

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

export default function OrchestrationPage() {
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
      <div className="flex-1 space-y-4 p-8 pt-6">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
          <div className="flex items-center space-x-2">
            <Button onClick={() => setShowCreateAgent(true)} className="gap-2">
              <Plus size={16} /> New Agent
            </Button>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-6 mt-6">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-48 lg:w-56 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-1">
              <span className="bg-muted hover:bg-muted text-primary font-medium justify-start w-full text-sm px-4 py-2 rounded-md transition-colors cursor-default">
                Overview
              </span>
              <span className="hover:bg-muted text-muted-foreground hover:text-foreground justify-start w-full text-sm px-4 py-2 rounded-md transition-colors cursor-not-allowed opacity-50">
                Analytics
              </span>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 space-y-6">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total Agents</CardTitle>
                  <Bot className="h-5 w-5 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{agents.length}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total Sessions</CardTitle>
                  <MessageSquare className="h-5 w-5 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{agents.reduce((acc, a) => acc + (a.sessionCount || 0), 0)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Active Tools</CardTitle>
                  <Wrench className="h-5 w-5 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{agents.reduce((acc, a) => acc + (a.toolCount || 0), 0)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">System Status</CardTitle>
                  <Activity className="h-5 w-5 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-green-500">Healthy</div>
                </CardContent>
              </Card>
            </div>

            <div className="flex items-center justify-between mt-6 mb-4">
              <div className="relative w-80">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search Agents..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 bg-background h-10 text-sm"
                />
              </div>
            </div>

            {agentsLoading ? (
            <div className="flex items-center justify-center h-64 border rounded-xl bg-card">
              <Loader2 className="animate-spin text-muted-foreground" size={32} />
            </div>
            ) : filteredAgents.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-muted-foreground border border-dashed border-border rounded-xl bg-card">
                <Bot size={48} className="mb-4 opacity-20" />
                <p className="text-base">{searchTerm ? 'No agents match your search.' : 'No agents found. Click "New Agent" to get started.'}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredAgents.map((agent) => (
                    <Card key={agent.id} className="hover:border-primary/50 transition-colors h-full flex flex-col group shadow-sm">
                      <CardHeader className="p-6 pb-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3 min-w-0">
                            <CardTitle className="text-xl flex items-center gap-2 truncate">
                              {agent.name}
                            </CardTitle>
                            <Badge variant={getStatusColor(agent.status) as any} className="text-xs px-2.5 py-0.5 shrink-0">
                              {agent.status}
                            </Badge>
                          </div>
                          {agent.id !== 'default' && (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="shrink-0 text-muted-foreground hover:text-destructive"
                              data-testid={`agent-delete-button-${agent.id}`}
                              aria-label={`删除 ${agent.name}`}
                              title={`删除 ${agent.name}`}
                              onClick={(e) => requestDeleteAgent(e, agent)}
                            >
                              <Trash2 size={16} />
                            </Button>
                          )}
                        </div>
                        <Link href={`/agents/${agent.id}`} className="block">
                          <CardDescription className="line-clamp-2 min-h-[44px] pt-1.5 text-sm leading-relaxed cursor-pointer">
                            {agent.description || "No description provided."}
                          </CardDescription>
                        </Link>
                      </CardHeader>
                      <CardContent className="mt-auto p-6 pt-0">
                        <Link href={`/agents/${agent.id}`} className="block">
                        <div className="flex items-center justify-between text-sm text-muted-foreground border-t border-border pt-4 cursor-pointer">
                           <div className="flex items-center gap-4">
                             <span className="flex items-center gap-1.5" title="Sessions"><MessageSquare size={16}/> {agent.sessionCount || 0}</span>
                             <span className="flex items-center gap-1.5" title="Tools"><Wrench size={16}/> {agent.toolCount || 0}</span>
                           </div>
                           <div className="flex items-center gap-2">
                             <span className="text-xs font-mono uppercase bg-muted text-muted-foreground px-2.5 py-1 rounded-md tracking-wider">{agent.model}</span>
                           </div>
                        </div>
                        </Link>
                      </CardContent>
                    </Card>
                ))}
              </div>
            )}
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
      const res = await authFetch(`${API_BASE}/api/agents`, {
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
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Provider</label>
              <Input value={formProvider} onChange={e => setFormProvider(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Model</label>
              <Input value={formModel} onChange={e => setFormModel(e.target.value)} />
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
