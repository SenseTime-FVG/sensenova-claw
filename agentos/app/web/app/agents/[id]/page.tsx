'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Settings, Loader2, Save, Plus, FileText, Trash2, ChevronDown, ChevronRight, Wrench, Bot } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface ToolDetail { name: string; description: string; enabled: boolean; }
interface SkillDetail { name: string; description: string; enabled: boolean; }
interface WorkspaceFile { name: string; size: number; editable: boolean; }
interface AgentSummary { id: string; name: string; }

interface AgentDetail {
  id: string;
  name: string;
  status: string;
  description: string;
  provider: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  maxTokens: number | null;
  sessionCount: number;
  toolCount: number;
  skillCount: number;
  tools: string[];
  skills: string[];
  toolsDetail: ToolDetail[];
  skillsDetail: SkillDetail[];
  canDelegateTo: string[];
  maxDelegationDepth: number;
  sessions: { id: string; status: string; channel: string; messageCount: number }[];
}

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.id as string;
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'config' | 'files' | 'tools' | 'skills' | 'sessions'>('config');

  // Tools / Skills 本地状态
  const [toolStates, setToolStates] = useState<Record<string, boolean>>({});
  const [skillStates, setSkillStates] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // Workspace 文件
  const [wsFiles, setWsFiles] = useState<WorkspaceFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);
  const [fileSaveMsg, setFileSaveMsg] = useState('');
  const [showNewFile, setShowNewFile] = useState(false);
  const [newFileName, setNewFileName] = useState('');

  // Per-agent config 编辑状态
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editProvider, setEditProvider] = useState('');
  const [editModel, setEditModel] = useState('');
  const [editTemp, setEditTemp] = useState('0.2');
  const [editMaxTokens, setEditMaxTokens] = useState('');
  const [editPrompt, setEditPrompt] = useState('');
  const [editDelegateTo, setEditDelegateTo] = useState<string[]>([]);
  const [editMaxDepth, setEditMaxDepth] = useState('3');
  const [allAgents, setAllAgents] = useState<AgentSummary[]>([]);
  const [cfgSaving, setCfgSaving] = useState(false);
  const [cfgSaveMsg, setCfgSaveMsg] = useState('');
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    basic: true, llm: true, prompt: false, delegation: false,
  });

  const loadAgent = useCallback(() => {
    authFetch(`${API_BASE}/api/agents/${agentId}`)
      .then(res => res.json())
      .then(data => {
        setAgent(data);
        // 初始化编辑状态
        setEditName(data.name || '');
        setEditDesc(data.description || '');
        setEditProvider(data.provider || '');
        setEditModel(data.model || '');
        setEditTemp(String(data.temperature ?? 0.2));
        setEditMaxTokens(data.maxTokens ? String(data.maxTokens) : '');
        setEditPrompt(data.systemPrompt || '');
        setEditDelegateTo(data.canDelegateTo || []);
        setEditMaxDepth(String(data.maxDelegationDepth ?? 3));
        // tools/skills 状态
        const ts: Record<string, boolean> = {};
        (data.toolsDetail || []).forEach((t: ToolDetail) => { ts[t.name] = t.enabled; });
        setToolStates(ts);
        const ss: Record<string, boolean> = {};
        (data.skillsDetail || []).forEach((s: SkillDetail) => { ss[s.name] = s.enabled; });
        setSkillStates(ss);
      })
      .catch(() => setAgent(null))
      .finally(() => setLoading(false));
  }, [agentId]);

  useEffect(() => { loadAgent(); }, [loadAgent]);

  // 加载所有 agent 列表（用于委托配置）
  useEffect(() => {
    if (activeTab === 'config') {
      authFetch(`${API_BASE}/api/agents`)
        .then(res => res.json())
        .then(data => setAllAgents(data.map((a: AgentSummary) => ({ id: a.id, name: a.name }))))
        .catch(() => setAllAgents([]));
    }
  }, [activeTab]);

  // 保存 per-agent config
  const saveAgentConfig = async () => {
    setCfgSaving(true);
    setCfgSaveMsg('');
    try {
      const body: Record<string, unknown> = {
        name: editName,
        description: editDesc,
        provider: editProvider || undefined,
        model: editModel || undefined,
        temperature: parseFloat(editTemp) || 0.2,
        systemPrompt: editPrompt,
        can_delegate_to: editDelegateTo,
        max_delegation_depth: parseInt(editMaxDepth) || 3,
      };
      if (editMaxTokens) body.max_tokens = parseInt(editMaxTokens) || undefined;
      const res = await authFetch(`${API_BASE}/api/agents/${agentId}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setCfgSaveMsg('已保存');
        loadAgent();
      } else {
        const err = await res.json().catch(() => ({}));
        setCfgSaveMsg(err.detail || '保存失败');
      }
    } catch {
      setCfgSaveMsg('保存失败');
    } finally {
      setCfgSaving(false);
      setTimeout(() => setCfgSaveMsg(''), 3000);
    }
  };

  // Workspace 文件操作
  const loadWsFiles = useCallback(() => {
    authFetch(`${API_BASE}/api/workspace/files`)
      .then(res => res.json())
      .then(data => setWsFiles(data))
      .catch(() => setWsFiles([]));
  }, []);

  useEffect(() => { if (activeTab === 'files') loadWsFiles(); }, [activeTab, loadWsFiles]);

  const loadFile = async (name: string) => {
    setSelectedFile(name); setFileLoading(true); setFileSaveMsg('');
    try {
      const res = await authFetch(`${API_BASE}/api/workspace/files/${name}`);
      const data = await res.json();
      setFileContent(data.content || '');
    } catch { setFileContent(''); }
    finally { setFileLoading(false); }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    setFileSaving(true); setFileSaveMsg('');
    try {
      await authFetch(`${API_BASE}/api/workspace/files/${selectedFile}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: fileContent }),
      });
      setFileSaveMsg('已保存'); loadWsFiles();
    } catch { setFileSaveMsg('保存失败'); }
    finally { setFileSaving(false); setTimeout(() => setFileSaveMsg(''), 2000); }
  };

  const deleteFile = async (name: string) => {
    if (!confirm(`确定要删除 ${name} 吗?`)) return;
    try {
      const res = await authFetch(`${API_BASE}/api/workspace/files/${name}`, { method: 'DELETE' });
      if (res.ok) { if (selectedFile === name) { setSelectedFile(null); setFileContent(''); } loadWsFiles(); }
    } catch { /* ignore */ }
  };

  const createFile = async () => {
    let fname = newFileName.trim();
    if (!fname) return;
    if (!fname.endsWith('.md')) fname += '.md';
    try {
      await authFetch(`${API_BASE}/api/workspace/files/${fname}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: `# ${fname.replace('.md', '')}\n\n` }),
      });
      setShowNewFile(false); setNewFileName(''); loadWsFiles(); loadFile(fname);
    } catch { /* ignore */ }
  };

  // 保存 tools/skills 偏好
  const savePreferences = async () => {
    setSaving(true); setSaveMsg('');
    try {
      await authFetch(`${API_BASE}/api/agents/${agentId}/preferences`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tools: toolStates, skills: skillStates }),
      });
      setSaveMsg('已保存');
    } catch { setSaveMsg('保存失败'); }
    finally { setSaving(false); setTimeout(() => setSaveMsg(''), 2000); }
  };

  if (loading) {
    return <DashboardLayout><div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground"><Loader2 className="animate-spin text-primary" size={40} /><p className="text-sm font-medium">Loading agent details...</p></div></DashboardLayout>;
  }
  if (!agent) {
    return <DashboardLayout><div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground"><Trash2 size={40} className="opacity-20" /><p className="text-lg font-medium">Agent not found</p></div></DashboardLayout>;
  }

  const enabledToolCount = Object.values(toolStates).filter(Boolean).length;
  const enabledSkillCount = Object.values(skillStates).filter(Boolean).length;

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col bg-background">
        {/* Header */}
        <div className="bg-card/50 backdrop-blur-sm border-b border-border p-6 sticky top-0 z-20 shadow-sm">
          <div className="flex items-center gap-6 mb-6">
            <Link href="/agents" className="p-2.5 hover:bg-muted rounded-full transition-all border border-transparent hover:border-border shadow-sm">
              <ArrowLeft size={22} />
            </Link>
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold text-foreground tracking-tight">{agent.name}</h1>
              <p className="text-base text-muted-foreground mt-1.5 line-clamp-1">{agent.description}</p>
            </div>
            <button className="p-2.5 hover:bg-muted rounded-full transition-all border border-transparent hover:border-border shadow-sm" title="Configure">
              <Settings size={22} className="text-muted-foreground" />
            </button>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm font-medium">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Status:</span>
              <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 capitalize bg-green-500/10 px-2.5 py-0.5 rounded-full border border-green-500/20 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                {agent.status}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Provider:</span>
              <span className="text-foreground bg-muted/60 px-2.5 py-0.5 rounded-full border border-border/50">{agent.provider}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Model:</span>
              <span className="text-foreground bg-muted/60 px-2.5 py-0.5 rounded-full border border-border/50">{agent.model}</span>
            </div>
            <div className="flex items-center gap-2 lg:ml-auto">
              <span className="text-muted-foreground">Sessions:</span>
              <span className="text-foreground font-bold text-base">{agent.sessionCount}</span>
            </div>
          </div>
        </div>

        {/* Tabs Bar */}
        <div className="bg-muted/30 border-b border-border px-8 overflow-x-auto no-scrollbar">
          <div className="flex gap-2">
            {(['config', 'files', 'tools', 'skills', 'sessions'] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`relative px-6 py-4 text-base font-semibold capitalize transition-all whitespace-nowrap ${
                  activeTab === tab 
                    ? 'text-primary' 
                    : 'text-muted-foreground hover:text-foreground'
                }`}>
                {tab === 'files' ? 'Workspace Files' : tab}
                {activeTab === tab && (
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-primary rounded-t-full shadow-[0_-2px_8px_rgba(59,130,246,0.3)]" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-auto p-8 lg:p-10">
          <div className="max-w-6xl mx-auto">
            {/* Config Tab */}
            {activeTab === 'config' && (
              <div className="space-y-8">
                <div className="flex items-center justify-between pb-2">
                  <div>
                    <h2 className="text-xl font-bold text-foreground tracking-tight">Agent Configuration</h2>
                    <p className="text-base text-muted-foreground mt-1">Modify independent settings for this tactical agent.</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {cfgSaveMsg && (
                      <span className={`text-sm font-semibold px-3 py-1.5 rounded-full border shadow-sm ${
                        cfgSaveMsg.includes('失败') 
                          ? 'text-destructive bg-destructive/10 border-destructive/20 shadow-destructive/5' 
                          : 'text-green-600 bg-green-500/10 border-green-500/20 shadow-green-500/5 dark:text-green-400'
                      }`}>
                        {cfgSaveMsg}
                      </span>
                    )}
                    <button onClick={saveAgentConfig} disabled={cfgSaving}
                      className="flex items-center gap-2.5 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-lg active:scale-95 transition-all">
                      {cfgSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                      Save Configuration
                    </button>
                  </div>
                </div>

                <div className="space-y-6">
                  <ConfigSection title="Identity" desc="Basic agent identity used for identification" expanded={expandedSections.basic}
                    onToggle={() => setExpandedSections(p => ({ ...p, basic: !p.basic }))}>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <CfgInput label="Name" value={editName} onChange={setEditName} />
                      <CfgInput label="Agent ID" value={agent.id} onChange={() => {}} readonly />
                    </div>
                    <div className="mt-6">
                      <label className="text-muted-foreground text-sm font-semibold block mb-2">Description</label>
                      <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                        className="w-full bg-background border border-input rounded-xl px-4 py-3 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm" />
                    </div>
                  </ConfigSection>

                  <ConfigSection title="LLM Backend" desc="Model provider and generation parameters" expanded={expandedSections.llm}
                    onToggle={() => setExpandedSections(p => ({ ...p, llm: !p.llm }))}>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <CfgInput label="Provider" value={editProvider} onChange={setEditProvider} />
                      <CfgInput label="Model" value={editModel} onChange={setEditModel} />
                      <CfgInput label="Temperature" type="number" value={editTemp} onChange={setEditTemp} />
                      <CfgInput label="Max Tokens" type="number" value={editMaxTokens} onChange={setEditMaxTokens} />
                    </div>
                  </ConfigSection>

                  <ConfigSection title="System Instructions" desc="Core behavioral prompts and mission definition" expanded={expandedSections.prompt}
                    onToggle={() => setExpandedSections(p => ({ ...p, prompt: !p.prompt }))}>
                    <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} rows={8}
                      className="w-full bg-background border border-input rounded-xl px-5 py-4 text-base text-foreground font-mono leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm bg-muted/5 selection:bg-primary/20"
                      spellCheck={false} placeholder="You are a helpful AI assistant specialized in..." />
                    <p className="mt-3 text-xs text-muted-foreground font-medium italic">Supports markdown and persona templates.</p>
                  </ConfigSection>

                  <ConfigSection title="Delegation Logic" desc="Rules for multi-agent cooperation and handoff" expanded={expandedSections.delegation}
                    onToggle={() => setExpandedSections(p => ({ ...p, delegation: !p.delegation }))}>
                    <div className="mb-6 max-w-sm">
                      <CfgInput label="Maximum Handoff Depth" type="number" value={editMaxDepth} onChange={setEditMaxDepth} />
                    </div>
                    <div>
                      <label className="text-muted-foreground text-sm font-bold block mb-4 uppercase tracking-wider">Authorized Delegate Targets (Leave empty for all)</label>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {allAgents.filter(a => a.id !== agentId).map(a => (
                          <label key={a.id} className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all cursor-pointer shadow-sm ${
                            editDelegateTo.includes(a.id) 
                              ? 'bg-primary/5 border-primary shadow-primary/5' 
                              : 'bg-card border-border hover:bg-muted/50 hover:border-muted-foreground/30'
                          }`}>
                            <input type="checkbox" checked={editDelegateTo.includes(a.id)}
                              onChange={e => {
                                if (e.target.checked) setEditDelegateTo(prev => [...prev, a.id]);
                                else setEditDelegateTo(prev => prev.filter(id => id !== a.id));
                              }}
                              className="w-5 h-5 rounded-md border-input bg-background accent-primary transition-all ring-offset-background focus:ring-2 focus:ring-ring" />
                            <div className="min-w-0">
                              <p className="text-sm font-bold truncate">{a.name}</p>
                              <p className="text-[10px] text-muted-foreground font-mono truncate">{a.id}</p>
                            </div>
                          </label>
                        ))}
                      </div>
                      {allAgents.filter(a => a.id !== agentId).length === 0 && (
                        <div className="text-center py-8 bg-muted/20 border border-dashed rounded-xl">
                          <p className="text-sm text-muted-foreground">No other active agents found in the system registry.</p>
                        </div>
                      )}
                    </div>
                  </ConfigSection>
                </div>
              </div>
            )}

            {/* Files Tab */}
            {activeTab === 'files' && (
              <div className="flex flex-col lg:flex-row gap-8 h-[calc(100vh-320px)]">
                <div className="w-full lg:w-72 shrink-0 flex flex-col gap-4">
                  <div className="flex items-center justify-between px-2">
                    <h2 className="text-lg font-bold text-foreground tracking-tight">File Explorer</h2>
                    <button onClick={() => setShowNewFile(!showNewFile)} className="p-2 hover:bg-primary/10 text-primary rounded-full transition-all border border-transparent hover:border-primary/20 shadow-sm" title="New file">
                      <Plus size={20} />
                    </button>
                  </div>
                  {showNewFile && (
                    <div className="flex gap-2 p-1 bg-muted/30 rounded-xl border border-border shadow-sm">
                      <input type="text" value={newFileName} onChange={e => setNewFileName(e.target.value)} placeholder="filename.md"
                        className="flex-1 bg-background border-none rounded-lg px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-primary/20 transition-all"
                        onKeyDown={e => e.key === 'Enter' && createFile()} autoFocus />
                      <button onClick={createFile} className="px-3 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-lg hover:bg-primary/90 shadow-sm">Add</button>
                    </div>
                  )}
                  <div className="flex-1 overflow-auto space-y-1.5 p-1 no-scrollbar">
                    {wsFiles.map(f => (
                      <div key={f.name} onClick={() => loadFile(f.name)}
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer text-sm font-semibold transition-all group border shadow-sm ${
                          selectedFile === f.name 
                            ? 'bg-primary border-transparent text-primary-foreground shadow-primary/20' 
                            : 'bg-card border-border text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                        }`}>
                        <FileText size={18} className={`shrink-0 ${selectedFile === f.name ? 'text-primary-foreground' : 'text-primary'}`} />
                        <span className="flex-1 truncate">{f.name}</span>
                        {!['AGENTS.md', 'USER.md'].includes(f.name) && (
                          <button onClick={e => { e.stopPropagation(); deleteFile(f.name); }} 
                            className={`opacity-0 group-hover:opacity-100 p-1.5 rounded-lg transition-all ${
                              selectedFile === f.name ? 'hover:bg-white/20 text-white/80' : 'hover:bg-destructive/10 text-destructive/40 hover:text-destructive'
                            }`}>
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    ))}
                    {wsFiles.length === 0 && (
                      <div className="text-center py-10 opacity-40">
                        <FileText size={40} className="mx-auto mb-2" />
                        <p className="text-xs font-medium">No files present</p>
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex-1 flex flex-col bg-card border border-border rounded-2xl overflow-hidden shadow-lg">
                  {selectedFile ? (
                    <>
                      <div className="flex items-center justify-between px-6 py-4 bg-muted/20 border-b border-border">
                        <div className="flex items-center gap-3">
                           <FileText size={20} className="text-primary" />
                           <h3 className="text-base font-bold text-foreground tracking-tight">{selectedFile}</h3>
                        </div>
                        <div className="flex items-center gap-4">
                          {fileSaveMsg && <span className="text-sm font-bold text-green-600 dark:text-green-400">{fileSaveMsg}</span>}
                          <button onClick={saveFile} disabled={fileSaving}
                            className="flex items-center gap-2 px-5 py-2 bg-primary text-primary-foreground font-bold text-sm rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-md active:scale-95 transition-all">
                            {fileSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                            Save File
                          </button>
                        </div>
                      </div>
                      <div className="flex-1 p-0 relative">
                        {fileLoading ? (
                          <div className="flex flex-col items-center justify-center h-full gap-3 bg-muted/10">
                            <Loader2 className="animate-spin text-primary" size={32} />
                            <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Hydrating editor...</p>
                          </div>
                        ) : (
                          <textarea value={fileContent} onChange={e => setFileContent(e.target.value)}
                            className="absolute inset-0 w-full h-full bg-transparent p-8 text-base text-foreground font-mono leading-relaxed resize-none focus:outline-none selection:bg-primary/20 dark:selection:bg-primary/40 no-scrollbar"
                            spellCheck={false} />
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-6 opacity-30">
                      <div className="p-8 bg-muted rounded-full">
                        <FileText size={64} />
                      </div>
                      <p className="text-lg font-bold uppercase tracking-widest">Select a file to inspect or edit</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tools Tab */}
            {activeTab === 'tools' && (
              <div className="space-y-8">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-foreground tracking-tight">Enabled Toolset</h2>
                    <p className="text-base text-muted-foreground mt-1">Configure which utilities this agent can invoke during runtime.</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {saveMsg && <span className="text-sm font-bold text-green-600 dark:text-green-400 bg-green-500/10 px-3 py-1 rounded-full border border-green-500/20">{saveMsg}</span>}
                    <button onClick={savePreferences} disabled={saving}
                      className="flex items-center gap-2.5 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-lg transition-all active:scale-95">
                      {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                      Save Preferences
                    </button>
                  </div>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(agent.toolsDetail || []).map((tool) => (
                    <div key={tool.name} className={`bg-card border rounded-2xl p-6 flex items-start gap-4 transition-all hover:shadow-md ${
                      toolStates[tool.name] ? 'border-primary/20' : 'border-border/60 opacity-80'
                    }`}>
                      <div className={`p-3 rounded-xl shrink-0 border ${
                        toolStates[tool.name] ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-muted border-border text-muted-foreground'
                      }`}>
                         <Wrench size={24} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-base font-bold text-foreground truncate">{tool.name}</span>
                          <ToggleSwitch checked={toolStates[tool.name] ?? true} onChange={v => setToolStates(prev => ({ ...prev, [tool.name]: v }))} />
                        </div>
                        {tool.description && <p className="text-sm text-muted-foreground leading-relaxed line-clamp-2">{tool.description}</p>}
                      </div>
                    </div>
                  ))}
                  {(!agent.toolsDetail || agent.toolsDetail.length === 0) && (
                    <div className="col-span-2 text-center py-20 bg-muted/10 border border-dashed rounded-2xl text-muted-foreground">
                      <p className="text-lg font-bold">No functional tools registered for this agent.</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Skills Tab */}
            {activeTab === 'skills' && (
              <div className="space-y-8">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-foreground tracking-tight">Operational Skills</h2>
                    <p className="text-base text-muted-foreground mt-1">High-level procedural capabilities granted to this agent.</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {saveMsg && <span className="text-sm font-bold text-green-600 dark:text-green-400 bg-green-500/10 px-3 py-1 rounded-full border border-green-500/20">{saveMsg}</span>}
                    <button onClick={savePreferences} disabled={saving}
                      className="flex items-center gap-2.5 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-lg transition-all active:scale-95">
                      {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                      Save Preferences
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(agent.skillsDetail || []).map((skill) => (
                    <div key={skill.name} className={`bg-card border rounded-2xl p-6 flex items-start gap-4 transition-all hover:shadow-md ${
                      skillStates[skill.name] ? 'border-primary/20' : 'border-border/60 opacity-80'
                    }`}>
                      <div className={`p-3 rounded-xl shrink-0 border ${
                        skillStates[skill.name] ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-muted border-border text-muted-foreground'
                      }`}>
                         <Bot size={24} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-base font-bold text-foreground truncate">{skill.name}</span>
                          <ToggleSwitch checked={skillStates[skill.name] ?? true} onChange={v => setSkillStates(prev => ({ ...prev, [skill.name]: v }))} />
                        </div>
                        {skill.description && <p className="text-sm text-muted-foreground leading-relaxed line-clamp-2">{skill.description}</p>}
                      </div>
                    </div>
                  ))}
                  {(!agent.skillsDetail || agent.skillsDetail.length === 0) && (
                    <div className="col-span-2 text-center py-20 bg-muted/10 border border-dashed rounded-2xl text-muted-foreground">
                      <p className="text-lg font-bold">No tactical skills loaded into this agent's brain.</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Sessions Tab */}
            {activeTab === 'sessions' && (
              <div className="space-y-8">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-foreground tracking-tight">Historical Sessions</h2>
                    <p className="text-base text-muted-foreground mt-1">Review past interaction logs where this agent was the primary actor.</p>
                  </div>
                  <div className="text-base font-bold text-muted-foreground bg-muted/50 px-4 py-2 rounded-full border border-border">
                    {agent.sessions?.length || 0} Total Sessions
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {(agent.sessions || []).map((session) => (
                    <Link key={session.id} href={`/sessions/${session.id}`}
                      className="group bg-card border border-border rounded-2xl p-5 hover:border-primary hover:shadow-lg transition-all shadow-sm">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-2.5 h-2.5 rounded-full shadow-sm ${session.status === 'active' ? 'bg-green-500 shadow-green-500/40' : 'bg-muted-foreground/40'}`} />
                          <span className="text-sm text-foreground font-mono font-bold tracking-tight">{session.id}</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest bg-muted px-2 py-1 rounded border border-border group-hover:bg-primary/5 group-hover:text-primary transition-colors">{session.channel || 'generic'}</span>
                      </div>
                      <div className="flex items-center justify-between">
                         <div className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-primary/40" />
                            {session.messageCount || 0} Messages
                         </div>
                         <ArrowLeft size={16} className="rotate-180 text-muted-foreground opacity-0 group-hover:opacity-100 transition-all transform group-hover:translate-x-1" />
                      </div>
                    </Link>
                  ))}
                  {(!agent.sessions || agent.sessions.length === 0) && (
                    <div className="col-span-2 text-center py-20 bg-muted/10 border border-dashed rounded-2xl text-muted-foreground">
                      <p className="text-lg font-bold">No historical data available for this agent.</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}

/* ===== 辅助组件 ===== */

function ConfigSection({ title, desc, expanded, onToggle, children }: {
  title: string; desc: string; expanded: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm shadow-black/5">
      <button onClick={onToggle} className="w-full flex items-center gap-4 px-6 py-5 hover:bg-muted/30 transition-all text-left group">
        <div className={`p-1.5 rounded-lg transition-all ${expanded ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground group-hover:bg-muted-foreground/10'}`}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </div>
        <div className="flex-1">
          <span className="text-base font-bold text-foreground tracking-tight">{title}</span>
          <p className="text-xs text-muted-foreground mt-0.5 font-medium">{desc}</p>
        </div>
      </button>
      {expanded && <div className="px-6 pb-6 pt-2 border-t border-border/40 space-y-2">{children}</div>}
    </div>
  );
}

function CfgInput({ label, value, onChange, type = 'text', fullWidth = false, readonly = false }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; fullWidth?: boolean; readonly?: boolean;
}) {
  return (
    <div className={`space-y-1.5 ${fullWidth ? 'col-span-2' : ''}`}>
      <label className="text-muted-foreground text-sm font-semibold">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} step={type === 'number' ? 'any' : undefined}
        readOnly={readonly}
        className={`w-full bg-background border border-input rounded-xl px-4 py-2.5 text-base text-foreground focus:outline-none transition-all shadow-sm ${
          readonly ? 'opacity-60 cursor-not-allowed bg-muted/30' : 'focus:ring-2 focus:ring-primary/20 focus:border-primary'
        }`} />
    </div>
  );
}
function ToggleSwitch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="relative inline-flex items-center cursor-pointer">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="sr-only peer" />
      <div className="w-10 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-[16px] peer-checked:after:border-white after:content-[''] after:absolute after:top-[4px] after:left-[4px] after:bg-muted-foreground/50 after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary peer-checked:after:bg-white shadow-inner active:after:w-5" />
    </label>
  );
}
