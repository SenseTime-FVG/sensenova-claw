'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Play, Save, Loader2, Plus, Trash2, ChevronDown, ChevronRight, X } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface WfNode {
  id: string;
  agent_id: string;
  input_template: string;
  description: string;
  timeout: number;
  retry: number;
  node_type: string;
}

interface WfEdge {
  from: string;
  to: string;
  condition?: string;
  label: string;
}

interface WfDetail {
  id: string;
  name: string;
  description: string;
  version: string;
  nodes: WfNode[];
  edges: WfEdge[];
  entry_node: string;
  exit_nodes: string[];
  max_iterations: number;
  timeout: number;
  enabled: boolean;
  created_at: number;
  updated_at: number;
}

interface NodeResult {
  node_id: string;
  status: string;
  output: string;
  error: string;
  started_at: number;
  completed_at: number;
  agent_id: string;
}

interface WfRun {
  run_id: string;
  workflow_id: string;
  status: string;
  input: string;
  output: string;
  node_results: Record<string, NodeResult>;
  iteration_count: number;
  started_at: number;
  completed_at: number;
  session_id: string;
}

interface AgentOption { id: string; name: string; }

export default function WorkflowDetailPage() {
  const params = useParams();
  const workflowId = params.id as string;
  const [wf, setWf] = useState<WfDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'editor' | 'graph' | 'runs'>('overview');
  const [agents, setAgents] = useState<AgentOption[]>([]);

  // 编辑状态（本地副本）
  const [editWf, setEditWf] = useState<WfDetail | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // 运行
  const [showRunModal, setShowRunModal] = useState(false);
  const [runs, setRuns] = useState<WfRun[]>([]);
  const [lastRun, setLastRun] = useState<WfRun | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  // 编辑器：新增节点/边
  const [showAddNode, setShowAddNode] = useState(false);
  const [showAddEdge, setShowAddEdge] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});

  const loadWorkflow = useCallback(() => {
    fetch(`${API_BASE}/api/workflows/${workflowId}`)
      .then(res => res.json())
      .then(data => { setWf(data); setEditWf(JSON.parse(JSON.stringify(data))); })
      .catch(() => setWf(null))
      .finally(() => setLoading(false));
  }, [workflowId]);

  useEffect(() => { loadWorkflow(); }, [loadWorkflow]);

  useEffect(() => {
    fetch(`${API_BASE}/api/agents`)
      .then(res => res.json())
      .then(data => setAgents(data.map((a: AgentOption) => ({ id: a.id, name: a.name }))))
      .catch(() => setAgents([]));
  }, []);

  const loadRuns = useCallback(() => {
    fetch(`${API_BASE}/api/workflows/runs/active`)
      .then(res => res.json())
      .then(data => setRuns(data.filter((r: WfRun) => r.workflow_id === workflowId)))
      .catch(() => setRuns([]));
  }, [workflowId]);

  useEffect(() => { if (activeTab === 'runs') loadRuns(); }, [activeTab, loadRuns]);

  // 保存整个 workflow
  const saveWorkflow = async () => {
    if (!editWf) return;
    setSaving(true); setSaveMsg('');
    try {
      const body = {
        id: editWf.id,
        name: editWf.name,
        description: editWf.description,
        version: editWf.version,
        nodes: editWf.nodes.map(n => ({
          id: n.id, agent_id: n.agent_id, input_template: n.input_template,
          description: n.description, timeout: n.timeout, retry: n.retry, node_type: n.node_type,
        })),
        edges: editWf.edges.map(e => ({
          from_node: e.from, to_node: e.to, condition: e.condition || undefined, label: e.label,
        })),
        entry_node: editWf.entry_node,
        exit_nodes: editWf.exit_nodes,
        max_iterations: editWf.max_iterations,
        timeout: editWf.timeout,
      };
      const res = await fetch(`${API_BASE}/api/workflows/${workflowId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) { setSaveMsg('已保存'); loadWorkflow(); }
      else { const err = await res.json().catch(() => ({})); setSaveMsg(err.detail || '保存失败'); }
    } catch { setSaveMsg('保存失败'); }
    finally { setSaving(false); setTimeout(() => setSaveMsg(''), 3000); }
  };

  // 编辑辅助
  const updateEditWf = (patch: Partial<WfDetail>) => {
    if (!editWf) return;
    setEditWf({ ...editWf, ...patch });
  };

  const updateNode = (idx: number, patch: Partial<WfNode>) => {
    if (!editWf) return;
    const nodes = [...editWf.nodes];
    nodes[idx] = { ...nodes[idx], ...patch };
    setEditWf({ ...editWf, nodes });
  };

  const removeNode = (idx: number) => {
    if (!editWf) return;
    const nodeId = editWf.nodes[idx].id;
    const nodes = editWf.nodes.filter((_, i) => i !== idx);
    const edges = editWf.edges.filter(e => e.from !== nodeId && e.to !== nodeId);
    setEditWf({ ...editWf, nodes, edges });
  };

  const removeEdge = (idx: number) => {
    if (!editWf) return;
    const edges = editWf.edges.filter((_, i) => i !== idx);
    setEditWf({ ...editWf, edges });
  };

  if (loading) {
    return <DashboardLayout><div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-[#858585]" size={32} /></div></DashboardLayout>;
  }
  if (!wf || !editWf) {
    return <DashboardLayout><div className="flex items-center justify-center h-full text-[#858585]">Workflow not found</div></DashboardLayout>;
  }

  const nodeIds = editWf.nodes.map(n => n.id);

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center gap-4 mb-4">
            <Link href="/workflows" className="p-2 hover:bg-[#2d2d30] rounded transition-colors"><ArrowLeft size={20} /></Link>
            <div className="flex-1">
              <h1 className="text-xl font-semibold text-[#cccccc]">{wf.name}</h1>
              <p className="text-sm text-[#858585] mt-1">{wf.description}</p>
            </div>
            <button onClick={() => setShowRunModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-[#0e639c] hover:bg-[#1177bb] rounded text-white text-sm transition-colors">
              <Play size={16} /> 运行
            </button>
          </div>
          <div className="flex gap-6 text-sm">
            <div><span className="text-[#858585]">版本: </span><span className="text-[#cccccc]">v{wf.version}</span></div>
            <div><span className="text-[#858585]">节点: </span><span className="text-[#cccccc]">{wf.nodes.length}</span></div>
            <div><span className="text-[#858585]">边: </span><span className="text-[#cccccc]">{wf.edges.length}</span></div>
            <div><span className="text-[#858585]">入口: </span><span className="text-[#cccccc]">{wf.entry_node || '自动'}</span></div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-[#252526] border-b border-[#2d2d30] px-4">
          <div className="flex gap-1">
            {(['overview', 'editor', 'graph', 'runs'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm transition-colors ${activeTab === tab ? 'text-[#cccccc] border-b-2 border-[#007acc]' : 'text-[#858585] hover:text-[#cccccc]'}`}>
                {tab === 'overview' ? '概览' : tab === 'editor' ? '编辑器' : tab === 'graph' ? 'DAG 图' : '运行记录'}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-4 max-w-3xl">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[#cccccc]">Workflow 配置</h2>
                <div className="flex items-center gap-2">
                  {saveMsg && <span className={`text-xs ${saveMsg.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>{saveMsg}</span>}
                  <button onClick={saveWorkflow} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                    {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存
                  </button>
                </div>
              </div>
              <CfgSection title="基本信息" defaultOpen>
                <div className="grid grid-cols-2 gap-3">
                  <CfgInput label="名称" value={editWf.name} onChange={v => updateEditWf({ name: v })} />
                  <CfgInput label="版本" value={editWf.version} onChange={v => updateEditWf({ version: v })} />
                </div>
                <div className="mt-3 space-y-1">
                  <label className="text-[#858585] text-xs">描述</label>
                  <input value={editWf.description} onChange={e => updateEditWf({ description: e.target.value })}
                    className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
                </div>
              </CfgSection>
              <CfgSection title="执行配置" defaultOpen>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-[#858585] text-xs">入口节点</label>
                    <select value={editWf.entry_node} onChange={e => updateEditWf({ entry_node: e.target.value })}
                      className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
                      <option value="">自动检测</option>
                      {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[#858585] text-xs">最大迭代次数</label>
                    <input type="number" value={editWf.max_iterations} onChange={e => updateEditWf({ max_iterations: parseInt(e.target.value) || 10 })}
                      className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
                  </div>
                  <CfgInput label="超时 (秒)" type="number" value={String(editWf.timeout)} onChange={v => updateEditWf({ timeout: parseFloat(v) || 1800 })} />
                </div>
                <div className="mt-3 space-y-1">
                  <label className="text-[#858585] text-xs">出口节点 (逗号分隔, 空=自动)</label>
                  <input value={editWf.exit_nodes.join(', ')} onChange={e => updateEditWf({ exit_nodes: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                    className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
                </div>
              </CfgSection>
            </div>
          )}

          {/* Editor Tab */}
          {activeTab === 'editor' && (
            <div className="space-y-6 max-w-4xl">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[#cccccc]">节点和边编辑</h2>
                <div className="flex items-center gap-2">
                  {saveMsg && <span className={`text-xs ${saveMsg.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>{saveMsg}</span>}
                  <button onClick={saveWorkflow} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb] disabled:opacity-50">
                    {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存
                  </button>
                </div>
              </div>

              {/* 节点 */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm text-[#cccccc] font-medium">节点 ({editWf.nodes.length})</h3>
                  <button onClick={() => setShowAddNode(true)}
                    className="flex items-center gap-1 px-3 py-1 bg-[#3c3c3c] text-[#cccccc] text-xs rounded hover:bg-[#4c4c4c] transition-colors">
                    <Plus size={12} /> 添加节点
                  </button>
                </div>

                {showAddNode && (
                  <AddNodeForm agents={agents} existingIds={nodeIds}
                    onAdd={node => { setEditWf({ ...editWf, nodes: [...editWf.nodes, node] }); setShowAddNode(false); }}
                    onCancel={() => setShowAddNode(false)} />
                )}

                <div className="space-y-2">
                  {editWf.nodes.map((node, idx) => (
                    <div key={node.id} className="bg-[#252526] border border-[#2d2d30] rounded">
                      <button onClick={() => setExpandedNodes(p => ({ ...p, [node.id]: !p[node.id] }))}
                        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-[#2d2d30] transition-colors text-left">
                        {expandedNodes[node.id] ? <ChevronDown size={14} className="text-[#858585]" /> : <ChevronRight size={14} className="text-[#858585]" />}
                        <span className="text-sm font-medium text-[#cccccc] flex-1">{node.id}</span>
                        <span className="text-xs text-[#858585]">{node.agent_id}</span>
                        <span className="text-xs bg-[#3c3c3c] text-[#858585] px-1.5 py-0.5 rounded">{node.node_type}</span>
                        <button onClick={e => { e.stopPropagation(); removeNode(idx); }} className="p-1 hover:bg-[#3c3c3c] rounded">
                          <Trash2 size={12} className="text-red-400" />
                        </button>
                      </button>
                      {expandedNodes[node.id] && (
                        <div className="px-3 pb-3 space-y-2">
                          <div className="grid grid-cols-3 gap-2">
                            <div className="space-y-1">
                              <label className="text-[#858585] text-xs">Agent</label>
                              <select value={node.agent_id} onChange={e => updateNode(idx, { agent_id: e.target.value })}
                                className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                              </select>
                            </div>
                            <CfgInput label="超时(秒)" type="number" value={String(node.timeout)} onChange={v => updateNode(idx, { timeout: parseFloat(v) || 300 })} />
                            <CfgInput label="重试次数" type="number" value={String(node.retry)} onChange={v => updateNode(idx, { retry: parseInt(v) || 0 })} />
                          </div>
                          <CfgInput label="描述" value={node.description} onChange={v => updateNode(idx, { description: v })} fullWidth />
                          <div className="space-y-1">
                            <label className="text-[#858585] text-xs">输入模板</label>
                            <textarea value={node.input_template} onChange={e => updateNode(idx, { input_template: e.target.value })} rows={3}
                              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-2 text-xs text-[#cccccc] font-mono resize-y focus:outline-none focus:border-[#007acc]"
                              placeholder="支持变量: {workflow.input}, {node_id.output}" spellCheck={false} />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  {editWf.nodes.length === 0 && <p className="text-xs text-[#858585] py-4 text-center">暂无节点，点击上方按钮添加</p>}
                </div>
              </div>

              {/* 边 */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm text-[#cccccc] font-medium">边 ({editWf.edges.length})</h3>
                  <button onClick={() => setShowAddEdge(true)}
                    className="flex items-center gap-1 px-3 py-1 bg-[#3c3c3c] text-[#cccccc] text-xs rounded hover:bg-[#4c4c4c] transition-colors">
                    <Plus size={12} /> 添加边
                  </button>
                </div>

                {showAddEdge && nodeIds.length >= 2 && (
                  <AddEdgeForm nodeIds={nodeIds}
                    onAdd={edge => { setEditWf({ ...editWf, edges: [...editWf.edges, edge] }); setShowAddEdge(false); }}
                    onCancel={() => setShowAddEdge(false)} />
                )}

                <div className="space-y-1">
                  {editWf.edges.map((edge, idx) => (
                    <div key={idx} className="bg-[#252526] border border-[#2d2d30] rounded px-3 py-2 flex items-center gap-3 text-sm">
                      <span className="text-[#4ec9b0] font-mono">{edge.from}</span>
                      <span className="text-[#858585]">&rarr;</span>
                      <span className="text-[#4ec9b0] font-mono">{edge.to}</span>
                      {edge.condition && <span className="text-xs text-[#858585] bg-[#3c3c3c] px-1.5 py-0.5 rounded">条件: {edge.condition}</span>}
                      {edge.label && <span className="text-xs text-[#858585]">{edge.label}</span>}
                      <span className="flex-1" />
                      <button onClick={() => removeEdge(idx)} className="p-1 hover:bg-[#3c3c3c] rounded">
                        <Trash2 size={12} className="text-red-400" />
                      </button>
                    </div>
                  ))}
                  {editWf.edges.length === 0 && <p className="text-xs text-[#858585] py-4 text-center">暂无边</p>}
                </div>
              </div>
            </div>
          )}

          {/* Graph Tab */}
          {activeTab === 'graph' && (
            <DAGVisualization nodes={editWf.nodes} edges={editWf.edges}
              entryNode={editWf.entry_node} exitNodes={editWf.exit_nodes}
              nodeResults={lastRun?.node_results} />
          )}

          {/* Runs Tab */}
          {activeTab === 'runs' && (
            <div className="space-y-3 max-w-4xl">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-[#cccccc]">运行记录</h2>
                <button onClick={loadRuns} className="text-xs text-[#007acc] hover:underline">刷新</button>
              </div>
              {lastRun && (
                <div className="bg-[#252526] border border-[#007acc] rounded p-4 mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-[#cccccc]">最近运行结果</span>
                    <StatusBadge status={lastRun.status} />
                  </div>
                  <p className="text-xs text-[#858585] mb-2">ID: {lastRun.run_id}</p>
                  {lastRun.output && (
                    <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded p-3 text-sm text-[#cccccc] max-h-48 overflow-auto whitespace-pre-wrap">
                      {lastRun.output}
                    </div>
                  )}
                  {Object.keys(lastRun.node_results).length > 0 && (
                    <div className="mt-3 space-y-1">
                      <p className="text-xs text-[#858585] mb-1">节点结果:</p>
                      {Object.values(lastRun.node_results).map(nr => (
                        <div key={nr.node_id} className="flex items-center gap-2 text-xs">
                          <StatusDot status={nr.status} />
                          <span className="text-[#cccccc] font-mono">{nr.node_id}</span>
                          <span className="text-[#858585]">({nr.agent_id})</span>
                          {nr.error && <span className="text-red-400">{nr.error}</span>}
                          {nr.output && <span className="text-[#858585] truncate max-w-xs">{nr.output.slice(0, 80)}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {runs.map(run => (
                <div key={run.run_id} className="bg-[#252526] border border-[#2d2d30] rounded">
                  <button onClick={() => setExpandedRun(expandedRun === run.run_id ? null : run.run_id)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[#2d2d30] transition-colors text-left">
                    <StatusDot status={run.status} />
                    <span className="text-sm text-[#cccccc] font-mono">{run.run_id}</span>
                    <StatusBadge status={run.status} />
                    <span className="flex-1" />
                    <span className="text-xs text-[#858585]">{new Date(run.started_at * 1000).toLocaleString()}</span>
                  </button>
                  {expandedRun === run.run_id && (
                    <div className="px-4 pb-3 space-y-2">
                      <p className="text-xs text-[#858585]">输入: {run.input.slice(0, 200)}</p>
                      {run.output && <p className="text-xs text-[#cccccc]">输出: {run.output.slice(0, 200)}</p>}
                      {Object.values(run.node_results).map(nr => (
                        <div key={nr.node_id} className="flex items-center gap-2 text-xs">
                          <StatusDot status={nr.status} />
                          <span className="text-[#cccccc] font-mono">{nr.node_id}</span>
                          <span className="text-[#858585]">{nr.agent_id}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {runs.length === 0 && !lastRun && <p className="text-sm text-[#858585] text-center py-8">暂无运行记录</p>}
            </div>
          )}
        </div>
      </div>

      {/* 运行弹窗 */}
      {showRunModal && (
        <RunWorkflowModal workflowId={workflowId}
          onClose={() => setShowRunModal(false)}
          onComplete={run => { setLastRun(run); setShowRunModal(false); setActiveTab('runs'); }} />
      )}
    </DashboardLayout>
  );
}

/* ===== DAG 可视化 ===== */

const NODE_W = 160, NODE_H = 56, LAYER_GAP = 200, NODE_GAP = 76, PAD = 40;

function DAGVisualization({ nodes, edges, entryNode, exitNodes, nodeResults }: {
  nodes: WfNode[]; edges: WfEdge[]; entryNode: string; exitNodes: string[]; nodeResults?: Record<string, NodeResult>;
}) {
  const layout = useMemo(() => {
    if (nodes.length === 0) return { positions: {}, width: 400, height: 200 };

    // 拓扑排序分层
    const adj: Record<string, string[]> = {};
    const inDeg: Record<string, number> = {};
    nodes.forEach(n => { adj[n.id] = []; inDeg[n.id] = 0; });
    edges.forEach(e => { adj[e.from]?.push(e.to); inDeg[e.to] = (inDeg[e.to] || 0) + 1; });

    const layers: string[][] = [];
    const layerOf: Record<string, number> = {};
    const queue = Object.keys(inDeg).filter(id => inDeg[id] === 0);
    // BFS 分层
    while (queue.length > 0) {
      const batch = [...queue];
      queue.length = 0;
      layers.push(batch);
      batch.forEach(id => { layerOf[id] = layers.length - 1; });
      batch.forEach(id => {
        (adj[id] || []).forEach(nb => {
          inDeg[nb]--;
          if (inDeg[nb] === 0) queue.push(nb);
        });
      });
    }
    // 处理没有入度的剩余节点（环中节点）
    const placed = new Set(Object.keys(layerOf));
    nodes.forEach(n => { if (!placed.has(n.id)) { layers.push([n.id]); layerOf[n.id] = layers.length - 1; } });

    const positions: Record<string, { x: number; y: number }> = {};
    layers.forEach((layer, li) => {
      layer.forEach((nodeId, ni) => {
        positions[nodeId] = {
          x: PAD + li * LAYER_GAP,
          y: PAD + ni * NODE_GAP,
        };
      });
    });

    const maxLayer = layers.length;
    const maxPerLayer = Math.max(...layers.map(l => l.length));
    return {
      positions,
      width: Math.max(400, PAD * 2 + maxLayer * LAYER_GAP),
      height: Math.max(200, PAD * 2 + maxPerLayer * NODE_GAP),
    };
  }, [nodes, edges]);

  if (nodes.length === 0) {
    return <div className="flex items-center justify-center h-64 text-[#858585]">暂无节点，请先在编辑器中添加</div>;
  }

  const getNodeBorder = (id: string) => {
    if (nodeResults?.[id]) {
      const s = nodeResults[id].status;
      if (s === 'completed') return '#4ec9b0';
      if (s === 'running') return '#007acc';
      if (s === 'failed') return '#f44747';
      if (s === 'skipped') return '#858585';
    }
    if (id === entryNode) return '#007acc';
    if (exitNodes.includes(id)) return '#4ec9b0';
    return '#2d2d30';
  };

  const getNodeFill = (id: string) => {
    if (nodeResults?.[id]) {
      const s = nodeResults[id].status;
      if (s === 'completed') return '#1a3a2a';
      if (s === 'running') return '#1a2a3a';
      if (s === 'failed') return '#3a1a1a';
    }
    return '#252526';
  };

  return (
    <div className="overflow-auto">
      <svg width={layout.width} height={layout.height} className="min-w-full">
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#858585" />
          </marker>
        </defs>
        {/* 边 */}
        {edges.map((edge, i) => {
          const from = layout.positions[edge.from];
          const to = layout.positions[edge.to];
          if (!from || !to) return null;
          const x1 = from.x + NODE_W;
          const y1 = from.y + NODE_H / 2;
          const x2 = to.x;
          const y2 = to.y + NODE_H / 2;
          const mx = (x1 + x2) / 2;
          return (
            <g key={i}>
              <path d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
                stroke="#858585" strokeWidth={1.5} fill="none" markerEnd="url(#arrowhead)" />
              {edge.label && (
                <text x={mx} y={Math.min(y1, y2) - 6} textAnchor="middle" fill="#858585" fontSize={10}>{edge.label}</text>
              )}
            </g>
          );
        })}
        {/* 节点 */}
        {nodes.map(node => {
          const pos = layout.positions[node.id];
          if (!pos) return null;
          return (
            <g key={node.id}>
              <rect x={pos.x} y={pos.y} width={NODE_W} height={NODE_H} rx={6}
                fill={getNodeFill(node.id)} stroke={getNodeBorder(node.id)} strokeWidth={2} />
              <text x={pos.x + NODE_W / 2} y={pos.y + 22} textAnchor="middle" fill="#cccccc" fontSize={12} fontWeight="bold">
                {node.id.length > 16 ? node.id.slice(0, 14) + '..' : node.id}
              </text>
              <text x={pos.x + NODE_W / 2} y={pos.y + 40} textAnchor="middle" fill="#858585" fontSize={10}>
                {node.agent_id}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ===== 运行弹窗 ===== */

function RunWorkflowModal({ workflowId, onClose, onComplete }: {
  workflowId: string; onClose: () => void; onComplete: (run: WfRun) => void;
}) {
  const [input, setInput] = useState('');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const handleRun = async () => {
    if (!input.trim()) { setError('请输入内容'); return; }
    setRunning(true); setError('');
    try {
      const res = await fetch(`${API_BASE}/api/workflows/${workflowId}/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: input.trim() }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); setError(d.detail || '运行失败'); return; }
      const run = await res.json();
      onComplete(run);
    } catch { setError('运行失败'); }
    finally { setRunning(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[#252526] border border-[#2d2d30] rounded-lg w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2d2d30]">
          <h2 className="text-sm font-semibold text-[#cccccc]">运行 Workflow</h2>
          <button onClick={onClose} className="p-1 hover:bg-[#3c3c3c] rounded"><X size={16} className="text-[#858585]" /></button>
        </div>
        <div className="p-4 space-y-3">
          <div className="space-y-1">
            <label className="text-[#858585] text-xs">输入内容</label>
            <textarea value={input} onChange={e => setInput(e.target.value)} rows={4}
              className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-2 text-sm text-[#cccccc] font-mono resize-y focus:outline-none focus:border-[#007acc]"
              placeholder="输入传递给工作流的文本..." spellCheck={false} />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#2d2d30]">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-[#858585] hover:text-[#cccccc] transition-colors">取消</button>
          <button onClick={handleRun} disabled={running}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-[#0e639c] text-white text-sm rounded hover:bg-[#1177bb] disabled:opacity-50">
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? '运行中...' : '运行'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ===== 添加节点表单 ===== */

function AddNodeForm({ agents, existingIds, onAdd, onCancel }: {
  agents: AgentOption[]; existingIds: string[];
  onAdd: (node: WfNode) => void; onCancel: () => void;
}) {
  const [id, setId] = useState('');
  const [agentId, setAgentId] = useState(agents[0]?.id || 'default');
  const [nodeType, setNodeType] = useState('agent');
  const [desc, setDesc] = useState('');
  const [error, setError] = useState('');

  const handleAdd = () => {
    if (!id.trim()) { setError('ID 不能为空'); return; }
    if (existingIds.includes(id.trim())) { setError('ID 已存在'); return; }
    onAdd({ id: id.trim(), agent_id: agentId, input_template: '', description: desc, timeout: 300, retry: 0, node_type: nodeType });
  };

  return (
    <div className="bg-[#1e1e1e] border border-[#007acc] rounded p-3 mb-3 space-y-2">
      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <label className="text-[#858585] text-xs">节点 ID</label>
          <input value={id} onChange={e => setId(e.target.value)} placeholder="node-1"
            className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
        </div>
        <div className="space-y-1">
          <label className="text-[#858585] text-xs">Agent</label>
          <select value={agentId} onChange={e => setAgentId(e.target.value)}
            className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[#858585] text-xs">类型</label>
          <select value={nodeType} onChange={e => setNodeType(e.target.value)}
            className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
            <option value="agent">agent</option>
            <option value="condition">condition</option>
            <option value="merge">merge</option>
          </select>
        </div>
      </div>
      <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="描述（可选）"
        className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="px-3 py-1 text-xs text-[#858585] hover:text-[#cccccc]">取消</button>
        <button onClick={handleAdd} className="px-3 py-1 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb]">添加</button>
      </div>
    </div>
  );
}

/* ===== 添加边表单 ===== */

function AddEdgeForm({ nodeIds, onAdd, onCancel }: {
  nodeIds: string[];
  onAdd: (edge: WfEdge) => void; onCancel: () => void;
}) {
  const [from, setFrom] = useState(nodeIds[0] || '');
  const [to, setTo] = useState(nodeIds[1] || nodeIds[0] || '');
  const [condition, setCondition] = useState('');
  const [label, setLabel] = useState('');

  return (
    <div className="bg-[#1e1e1e] border border-[#007acc] rounded p-3 mb-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <label className="text-[#858585] text-xs">起始节点</label>
          <select value={from} onChange={e => setFrom(e.target.value)}
            className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
            {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[#858585] text-xs">目标节点</label>
          <select value={to} onChange={e => setTo(e.target.value)}
            className="w-full bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]">
            {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input value={condition} onChange={e => setCondition(e.target.value)} placeholder="条件表达式（可选）"
          className="bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
        <input value={label} onChange={e => setLabel(e.target.value)} placeholder="标签（可选）"
          className="bg-[#252526] border border-[#2d2d30] rounded px-2 py-1 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="px-3 py-1 text-xs text-[#858585] hover:text-[#cccccc]">取消</button>
        <button onClick={() => { onAdd({ from, to, condition: condition || undefined, label }); }}
          className="px-3 py-1 bg-[#0e639c] text-white text-xs rounded hover:bg-[#1177bb]">添加</button>
      </div>
    </div>
  );
}

/* ===== 辅助组件 ===== */

function CfgSection({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(defaultOpen);
  return (
    <div className="bg-[#252526] border border-[#2d2d30] rounded">
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-2 px-4 py-3 hover:bg-[#2d2d30] transition-colors">
        {expanded ? <ChevronDown size={16} className="text-[#858585]" /> : <ChevronRight size={16} className="text-[#858585]" />}
        <span className="text-sm font-semibold text-[#cccccc]">{title}</span>
      </button>
      {expanded && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

function CfgInput({ label, value, onChange, type = 'text', fullWidth = false }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; fullWidth?: boolean;
}) {
  return (
    <div className={`space-y-1 ${fullWidth ? 'col-span-full' : ''}`}>
      <label className="text-[#858585] text-xs">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} step={type === 'number' ? 'any' : undefined}
        className="w-full bg-[#1e1e1e] border border-[#2d2d30] rounded px-3 py-1.5 text-sm text-[#cccccc] focus:outline-none focus:border-[#007acc]" />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: 'bg-green-900 text-green-300', running: 'bg-blue-900 text-blue-300',
    failed: 'bg-red-900 text-red-300', pending: 'bg-gray-800 text-gray-400',
  };
  return <span className={`text-xs px-2 py-0.5 rounded ${colors[status] || colors.pending}`}>{status}</span>;
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: 'bg-green-500', running: 'bg-blue-500', failed: 'bg-red-500',
    pending: 'bg-gray-500', skipped: 'bg-gray-500',
  };
  return <div className={`w-2 h-2 rounded-full ${colors[status] || colors.pending}`} />;
}
