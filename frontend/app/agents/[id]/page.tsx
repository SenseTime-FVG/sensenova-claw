'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Settings, Loader2, Save, Plus, FileText, Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
    fetch(`${API_BASE}/api/agents/${agentId}`)
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
      fetch(`${API_BASE}/api/agents`)
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
      const res = await fetch(`${API_BASE}/api/agents/${agentId}/config`, {
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
    fetch(`${API_BASE}/api/workspace/files`)
      .then(res => res.json())
      .then(data => setWsFiles(data))
      .catch(() => setWsFiles([]));
  }, []);

  useEffect(() => { if (activeTab === 'files') loadWsFiles(); }, [activeTab, loadWsFiles]);

  const loadFile = async (name: string) => {
    setSelectedFile(name); setFileLoading(true); setFileSaveMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/workspace/files/${name}`);
      const data = await res.json();
      setFileContent(data.content || '');
    } catch { setFileContent(''); }
    finally { setFileLoading(false); }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    setFileSaving(true); setFileSaveMsg('');
    try {
      await fetch(`${API_BASE}/api/workspace/files/${selectedFile}`, {
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
      const res = await fetch(`${API_BASE}/api/workspace/files/${name}`, { method: 'DELETE' });
      if (res.ok) { if (selectedFile === name) { setSelectedFile(null); setFileContent(''); } loadWsFiles(); }
    } catch { /* ignore */ }
  };

  const createFile = async () => {
    let fname = newFileName.trim();
    if (!fname) return;
    if (!fname.endsWith('.md')) fname += '.md';
    try {
      await fetch(`${API_BASE}/api/workspace/files/${fname}`, {
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
      await fetch(`${API_BASE}/api/agents/${agentId}/preferences`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tools: toolStates, skills: skillStates }),
      });
      setSaveMsg('已保存');
    } catch { setSaveMsg('保存失败'); }
    finally { setSaving(false); setTimeout(() => setSaveMsg(''), 2000); }
  };

  if (loading) {
    return <DashboardLayout><div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-[#858585]" size={32} /></div></DashboardLayout>;
  }
  if (!agent) {
    return <DashboardLayout><div className="flex items-center justify-center h-full text-[#858585]">Agent not found</div></DashboardLayout>;
  }

  const enabledToolCount = Object.values(toolStates).filter(Boolean).length;
  const enabledSkillCount = Object.values(skillStates).filter(Boolean).length;

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
            <div><span className="text-[#858585]">Status: </span><span className="text-green-400">{agent.status}</span></div>
            <div><span className="text-[#858585]">Provider: </span><span className="text-[#cccccc]">{agent.provider}</span></div>
            <div><span className="text-[#858585]">Model: </span><span className="text-[#cccccc]">{agent.model}</span></div>
            <div><span className="text-[#858585]">Sessions: </span><span className="text-[#cccccc]">{agent.sessionCount}</span></div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-[#252526] border-b border-[#2d2d30] px-4">
          <div className="flex gap-1">
            {(['config', 'files', 'tools', 'skills', 'sessions'] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm capitalize transition-colors ${activeTab === tab ? 'text-[#cccccc] border-b-2 border-[#007acc]' : 'text-[#858585] hover:text-[#cccccc]'}`}>
                {tab === 'files' ? 'Files' : tab}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {/* Config Tab — per-agent */}
          {activeTab === 'config' && (
            <div className="space-y-4 max-w-3xl">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#cccccc]">Agent 配置</h2>
                  <p className="text-xs text-[#858585] mt-0.5">修改此 Agent 的独立配置</p>
                </div>
                <div className="flex items-center gap-2">
                  {cfgSaveMsg && <span className={`text-xs ${cfgSaveMsg.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>{cfgSaveMsg}</span>}
                  <button onClick={saveAgentConfig} disabled={cfgSaving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                    {cfgSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                    保存配置
                  </button>
                </div>
              </div>

              <ConfigSection title="基本信息" desc="名称和描述" expanded={expandedSections.basic}
                onToggle={() => setExpandedSections(p => ({ ...p, basic: !p.basic }))}>
                <div className="grid grid-cols-2 gap-3">
                  <CfgInput label="名称" value={editName} onChange={setEditName} />
                  <CfgInput label="ID" value={agent.id} onChange={() => {}} />
                </div>
                <div className="mt-3">
                  <label className="text-[#858585] text-xs block mb-1">描述</label>
                  <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                    className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
                </div>
              </ConfigSection>

              <ConfigSection title="LLM 配置" desc="模型提供商和参数" expanded={expandedSections.llm}
                onToggle={() => setExpandedSections(p => ({ ...p, llm: !p.llm }))}>
                <div className="grid grid-cols-2 gap-3">
                  <CfgInput label="Provider" value={editProvider} onChange={setEditProvider} />
                  <CfgInput label="Model" value={editModel} onChange={setEditModel} />
                  <CfgInput label="Temperature" type="number" value={editTemp} onChange={setEditTemp} />
                  <CfgInput label="Max Tokens" type="number" value={editMaxTokens} onChange={setEditMaxTokens} />
                </div>
              </ConfigSection>

              <ConfigSection title="系统提示词" desc="Agent 角色设定" expanded={expandedSections.prompt}
                onToggle={() => setExpandedSections(p => ({ ...p, prompt: !p.prompt }))}>
                <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} rows={6}
                  className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-2 text-sm text-[#cccccc] font-mono resize-y focus:outline-none focus:border-[#007acc]"
                  spellCheck={false} placeholder="你是一个有用的AI助手..." />
              </ConfigSection>

              <ConfigSection title="委托配置" desc="Agent 间任务委托设置" expanded={expandedSections.delegation}
                onToggle={() => setExpandedSections(p => ({ ...p, delegation: !p.delegation }))}>
                <div className="mb-3">
                  <CfgInput label="最大委托深度" type="number" value={editMaxDepth} onChange={setEditMaxDepth} />
                </div>
                <div>
                  <label className="text-[#858585] text-xs block mb-2">可委托目标 (空 = 全部)</label>
                  <div className="space-y-1.5 max-h-48 overflow-auto">
                    {allAgents.filter(a => a.id !== agentId).map(a => (
                      <label key={a.id} className="flex items-center gap-2 text-sm text-[#cccccc] cursor-pointer hover:bg-[#2d2d30] px-2 py-1 rounded">
                        <input type="checkbox" checked={editDelegateTo.includes(a.id)}
                          onChange={e => {
                            if (e.target.checked) setEditDelegateTo(prev => [...prev, a.id]);
                            else setEditDelegateTo(prev => prev.filter(id => id !== a.id));
                          }}
                          className="accent-[#007acc]" />
                        <span>{a.name}</span>
                        <span className="text-xs text-[#858585]">({a.id})</span>
                      </label>
                    ))}
                    {allAgents.filter(a => a.id !== agentId).length === 0 && (
                      <p className="text-xs text-[#858585]">暂无其他 Agent</p>
                    )}
                  </div>
                </div>
              </ConfigSection>
            </div>
          )}

          {/* Files Tab */}
          {activeTab === 'files' && (
            <div className="flex gap-4 h-full">
              <div className="w-48 shrink-0 space-y-2">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-[#cccccc]">Workspace Files</h2>
                  <button onClick={() => setShowNewFile(!showNewFile)} className="p-1 hover:bg-[#2d2d30] rounded transition-colors" title="新建文件">
                    <Plus size={14} className="text-[#007acc]" />
                  </button>
                </div>
                {showNewFile && (
                  <div className="flex gap-1 mb-2">
                    <input type="text" value={newFileName} onChange={e => setNewFileName(e.target.value)} placeholder="文件名.md"
                      className="flex-1 bg-[#3c3c3c] border border-[#5a5a5a] rounded px-2 py-1 text-xs text-[#cccccc] focus:outline-none focus:border-[#007acc]"
                      onKeyDown={e => e.key === 'Enter' && createFile()} />
                    <button onClick={createFile} className="px-2 py-1 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb]">创建</button>
                  </div>
                )}
                {wsFiles.map(f => (
                  <div key={f.name} onClick={() => loadFile(f.name)}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-sm transition-colors group ${selectedFile === f.name ? 'bg-[#37373d] text-[#cccccc]' : 'text-[#858585] hover:bg-[#2d2d30]'}`}>
                    <FileText size={14} className="shrink-0" />
                    <span className="flex-1 truncate">{f.name}</span>
                    {!['AGENTS.md', 'USER.md'].includes(f.name) && (
                      <button onClick={e => { e.stopPropagation(); deleteFile(f.name); }} className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-[#3c3c3c] rounded">
                        <Trash2 size={12} className="text-red-400" />
                      </button>
                    )}
                  </div>
                ))}
                {wsFiles.length === 0 && <p className="text-xs text-[#858585]">暂无文件</p>}
              </div>
              <div className="flex-1 flex flex-col">
                {selectedFile ? (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-medium text-[#cccccc]">{selectedFile}</h3>
                      <div className="flex items-center gap-2">
                        {fileSaveMsg && <span className="text-xs text-green-400">{fileSaveMsg}</span>}
                        <button onClick={saveFile} disabled={fileSaving}
                          className="flex items-center gap-1 px-3 py-1 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                          {fileSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                          保存
                        </button>
                      </div>
                    </div>
                    {fileLoading ? (
                      <div className="flex items-center justify-center h-32"><Loader2 className="animate-spin text-[#858585]" size={24} /></div>
                    ) : (
                      <textarea value={fileContent} onChange={e => setFileContent(e.target.value)}
                        className="flex-1 w-full bg-[#1e1e1e] border border-[#2d2d30] rounded p-3 text-sm text-[#cccccc] font-mono resize-none focus:outline-none focus:border-[#007acc]"
                        spellCheck={false} />
                    )}
                  </>
                ) : (
                  <div className="flex items-center justify-center h-full text-[#858585] text-sm">选择一个文件进行编辑</div>
                )}
              </div>
            </div>
          )}

          {/* Tools Tab */}
          {activeTab === 'tools' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-[#cccccc]">Tools ({enabledToolCount}/{agent.toolsDetail?.length || 0} 已启用)</h2>
                <div className="flex items-center gap-2">
                  {saveMsg && <span className="text-xs text-green-400">{saveMsg}</span>}
                  <button onClick={savePreferences} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                    {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                    保存设置
                  </button>
                </div>
              </div>
              {(agent.toolsDetail || []).map((tool) => (
                <div key={tool.name} className="bg-[#252526] border border-[#2d2d30] rounded p-3 flex items-center justify-between hover:border-[#3e3e42] transition-colors">
                  <div className="flex items-center gap-3 flex-1">
                    <div className={`w-2 h-2 rounded-full ${toolStates[tool.name] ? 'bg-green-500' : 'bg-gray-500'}`} />
                    <div>
                      <span className="text-[#cccccc] text-sm">{tool.name}</span>
                      {tool.description && <p className="text-xs text-[#858585] mt-0.5">{tool.description}</p>}
                    </div>
                  </div>
                  <ToggleSwitch checked={toolStates[tool.name] ?? true} onChange={v => setToolStates(prev => ({ ...prev, [tool.name]: v }))} />
                </div>
              ))}
              {(!agent.toolsDetail || agent.toolsDetail.length === 0) && <p className="text-sm text-[#858585]">No tools registered</p>}
            </div>
          )}

          {/* Skills Tab */}
          {activeTab === 'skills' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-[#cccccc]">Skills ({enabledSkillCount}/{agent.skillsDetail?.length || 0} 已启用)</h2>
                <div className="flex items-center gap-2">
                  {saveMsg && <span className="text-xs text-green-400">{saveMsg}</span>}
                  <button onClick={savePreferences} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                    {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                    保存设置
                  </button>
                </div>
              </div>
              {(agent.skillsDetail || []).map((skill) => (
                <div key={skill.name} className="bg-[#252526] border border-[#2d2d30] rounded p-3 flex items-center justify-between hover:border-[#3e3e42] transition-colors">
                  <div className="flex items-center gap-3 flex-1">
                    <div className={`w-2 h-2 rounded-full ${skillStates[skill.name] ? 'bg-blue-500' : 'bg-gray-500'}`} />
                    <div>
                      <span className="text-[#cccccc] text-sm">{skill.name}</span>
                      {skill.description && <p className="text-xs text-[#858585] mt-0.5 line-clamp-2">{skill.description}</p>}
                    </div>
                  </div>
                  <ToggleSwitch checked={skillStates[skill.name] ?? true} onChange={v => setSkillStates(prev => ({ ...prev, [skill.name]: v }))} />
                </div>
              ))}
              {(!agent.skillsDetail || agent.skillsDetail.length === 0) && <p className="text-sm text-[#858585]">No skills loaded</p>}
            </div>
          )}

          {/* Sessions Tab */}
          {activeTab === 'sessions' && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-[#cccccc] mb-4">Sessions ({agent.sessions?.length || 0})</h2>
              {(agent.sessions || []).map((session) => (
                <Link key={session.id} href={`/sessions/${session.id}`}
                  className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#007acc] transition-colors block">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${session.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}`} />
                      <span className="text-sm text-[#cccccc] font-mono">{session.id}</span>
                    </div>
                    <span className="text-xs text-[#858585]">{session.channel}</span>
                  </div>
                </Link>
              ))}
              {(!agent.sessions || agent.sessions.length === 0) && <p className="text-sm text-[#858585]">No sessions</p>}
            </div>
          )}
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
    <div className="bg-[#252526] border border-[#2d2d30] rounded">
      <button onClick={onToggle} className="w-full flex items-center gap-2 px-4 py-3 hover:bg-[#2d2d30] transition-colors">
        {expanded ? <ChevronDown size={16} className="text-[#858585]" /> : <ChevronRight size={16} className="text-[#858585]" />}
        <div className="text-left">
          <span className="text-sm font-semibold text-[#cccccc]">{title}</span>
          <span className="text-xs text-[#858585] ml-2">{desc}</span>
        </div>
      </button>
      {expanded && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

function CfgInput({ label, value, onChange, type = 'text', fullWidth = false }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; fullWidth?: boolean;
}) {
  return (
    <div className={`space-y-1 ${fullWidth ? 'col-span-2' : ''}`}>
      <label className="text-[#858585] text-xs">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} step={type === 'number' ? 'any' : undefined}
        className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
    </div>
  );
}

function ToggleSwitch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="relative inline-flex items-center cursor-pointer">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="sr-only peer" />
      <div className="w-9 h-5 bg-[#3c3c3c] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#858585] after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[#0e639c] peer-checked:after:bg-white pointer-events-none" />
    </label>
  );
}
