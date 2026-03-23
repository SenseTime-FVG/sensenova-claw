'use client';

import { useState, useEffect } from 'react';
import { Loader2, Save, Plus, Trash2, ChevronDown, ChevronRight, Server, Cpu, Settings2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface ProviderConfig {
  api_key: string;
  api_key_meta?: SecretValueStatus | null;
  api_key_touched?: boolean;
  base_url: string;
  timeout: number;
  max_retries: number;
}

interface SecretValueStatus {
  configured: boolean;
  masked_value?: string | null;
  source: string;
}

interface ModelConfig {
  provider: string;
  model_id: string;
  timeout: number;
  max_tokens: number;
  max_output_tokens: number;
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // LLM 配置
  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [models, setModels] = useState<Record<string, ModelConfig>>({});
  const [defaultModel, setDefaultModel] = useState('');

  // 展开状态
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    providers: true, models: true, general: true,
  });
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({});
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});

  // 新建表单
  const [showNewProvider, setShowNewProvider] = useState(false);
  const [newProviderName, setNewProviderName] = useState('');
  const [showNewModel, setShowNewModel] = useState(false);
  const [newModelName, setNewModelName] = useState('');

  // 加载配置
  useEffect(() => {
    authFetch(`${API_BASE}/api/config/sections`)
      .then(res => res.json())
      .then(data => {
        const llm = data?.llm || {};
        const p = normalizeProviders(llm.providers || {});
        // 过滤掉 mock provider
        const { mock, ...realProviders } = p;
        setProviders(realProviders);
        const m = llm.models || {};
        const { mock: mockModel, ...realModels } = m;
        setModels(realModels);
        setDefaultModel(llm.default_model || '');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // 保存配置
  const saveConfig = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      // 重新组装完整的 llm section（包含 mock）
      const llm = {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          ...buildProviderPayloads(providers),
        },
        models: { mock: { provider: 'mock', model_id: 'mock-agent-v1' }, ...models },
        default_model: defaultModel,
      };
      const res = await authFetch(`${API_BASE}/api/config/sections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm }),
      });
      if (res.ok) {
        setSaveMsg('已保存');
      } else {
        const err = await res.json().catch(() => ({}));
        setSaveMsg(err.detail || '保存失败');
      }
    } catch {
      setSaveMsg('保存失败');
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(''), 3000);
    }
  };

  // Provider 操作
  const updateProvider = (name: string, field: keyof ProviderConfig, value: string | number) => {
    setProviders(prev => ({
      ...prev,
      [name]: {
        ...prev[name],
        [field]: value,
        ...(field === 'api_key' ? { api_key_touched: true } : {}),
      },
    }));
  };

  const removeProvider = (name: string) => {
    if (!confirm(`确定删除 provider "${name}" 吗？关联的模型配置不会自动删除。`)) return;
    setProviders(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const addProvider = () => {
    const name = newProviderName.trim().toLowerCase();
    if (!name || providers[name]) return;
    setProviders(prev => ({
      ...prev,
      [name]: { api_key: '', api_key_meta: null, api_key_touched: true, base_url: '', timeout: 60, max_retries: 3 },
    }));
    setExpandedProviders(prev => ({ ...prev, [name]: true }));
    setNewProviderName('');
    setShowNewProvider(false);
  };

  // Model 操作
  const updateModel = (name: string, field: keyof ModelConfig, value: string | number) => {
    setModels(prev => ({
      ...prev,
      [name]: { ...prev[name], [field]: value },
    }));
  };

  const removeModel = (name: string) => {
    if (!confirm(`确定删除模型 "${name}" 吗？`)) return;
    setModels(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (defaultModel === name) setDefaultModel('');
  };

  const addModel = () => {
    const name = newModelName.trim();
    if (!name || models[name]) return;
    const firstProvider = Object.keys(providers)[0] || '';
    setModels(prev => ({
      ...prev,
      [name]: { provider: firstProvider, model_id: '', timeout: 60, max_tokens: 128000, max_output_tokens: 16384 },
    }));
    setExpandedModels(prev => ({ ...prev, [name]: true }));
    setNewModelName('');
    setShowNewModel(false);
  };

  const providerNames = Object.keys(providers);
  const modelNames = Object.keys(models);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
          <Loader2 className="animate-spin text-primary" size={48} />
          <p className="text-sm font-bold uppercase tracking-widest">Loading settings...</p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">LLM Settings</h2>
          <div className="flex items-center gap-4">
            {saveMsg && (
              <span className={`text-sm font-semibold px-3 py-1.5 rounded-full border shadow-sm ${
                saveMsg.includes('失败')
                  ? 'text-destructive bg-destructive/10 border-destructive/20'
                  : 'text-green-600 bg-green-500/10 border-green-500/20 dark:text-green-400'
              }`}>
                {saveMsg}
              </span>
            )}
            <button onClick={saveConfig} disabled={saving}
              className="flex items-center gap-2.5 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-lg shadow-primary/20 active:scale-95 transition-all">
              {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
              Save All
            </button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card className="shadow-lg border-border/60">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Providers</CardTitle>
              <Server className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{providerNames.length}</div>
              <p className="text-sm font-medium text-muted-foreground mt-2">Configured LLM backends</p>
            </CardContent>
          </Card>
          <Card className="shadow-lg border-border/60">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Models</CardTitle>
              <Cpu className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{modelNames.length}</div>
              <p className="text-sm font-medium text-muted-foreground mt-2">Registered model profiles</p>
            </CardContent>
          </Card>
          <Card className="shadow-lg border-border/60">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Default Model</CardTitle>
              <Settings2 className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-black truncate">{defaultModel || 'Not set'}</div>
              <p className="text-sm font-medium text-muted-foreground mt-2">Fallback when unspecified</p>
            </CardContent>
          </Card>
        </div>

        <Card className="shadow-xl border-border/80 overflow-hidden">
          <CardHeader className="bg-muted/30 border-b p-8">
            <CardTitle className="text-2xl font-bold">Configuration</CardTitle>
            <CardDescription className="text-base mt-2">Manage LLM providers, models, and default configuration.</CardDescription>
          </CardHeader>
          <CardContent className="p-8">
            <div className="space-y-8">
              <Section title="General" desc="Global LLM defaults" icon={<Settings2 size={18} />}
                expanded={expandedSections.general} onToggle={() => setExpandedSections(p => ({ ...p, general: !p.general }))}>
                <div className="max-w-md">
                  <label className="text-muted-foreground text-sm font-semibold block mb-2">Default Model</label>
                  <select value={defaultModel} onChange={e => setDefaultModel(e.target.value)}
                    className="w-full bg-background border border-input rounded-xl px-4 py-2.5 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm appearance-none cursor-pointer">
                    {modelNames.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <p className="mt-2 text-xs text-muted-foreground">Used when an agent does not specify a model.</p>
                </div>
              </Section>

              <Section title="Providers" desc={`${providerNames.length} configured`} icon={<Server size={18} />}
                expanded={expandedSections.providers} onToggle={() => setExpandedSections(p => ({ ...p, providers: !p.providers }))}>
                <div className="space-y-4">
                  {providerNames.map(name => (
                    <div key={name} className="bg-background border border-border rounded-xl overflow-hidden">
                      <button onClick={() => setExpandedProviders(p => ({ ...p, [name]: !p[name] }))}
                        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-muted/30 transition-all text-left group">
                        <div className={`p-1 rounded-lg transition-all ${expandedProviders[name] ? 'text-primary' : 'text-muted-foreground'}`}>
                          {expandedProviders[name] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </div>
                        <span className="text-sm font-bold text-foreground flex-1">{name}</span>
                        <span className="text-xs text-muted-foreground font-mono">
                          {providerSecretSummary(providers[name])}
                        </span>
                        <button onClick={e => { e.stopPropagation(); removeProvider(name); }}
                          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-destructive/10 text-destructive/40 hover:text-destructive transition-all">
                          <Trash2 size={14} />
                        </button>
                      </button>
                      {expandedProviders[name] && (
                        <div className="px-5 pb-5 pt-2 border-t border-border/40">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <FieldInput label="API Key" value={providers[name]?.api_key || ''} type="password"
                              onChange={v => updateProvider(name, 'api_key', v)} />
                            <FieldInput label="Base URL" value={providers[name]?.base_url || ''}
                              onChange={v => updateProvider(name, 'base_url', v)} />
                            <FieldInput label="Timeout (s)" value={String(providers[name]?.timeout || 60)} type="number"
                              onChange={v => updateProvider(name, 'timeout', parseInt(v) || 60)} />
                            <FieldInput label="Max Retries" value={String(providers[name]?.max_retries || 3)} type="number"
                              onChange={v => updateProvider(name, 'max_retries', parseInt(v) || 3)} />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  {showNewProvider ? (
                    <div className="flex gap-2 p-1 bg-muted/30 rounded-xl border border-border shadow-sm">
                      <input type="text" value={newProviderName} onChange={e => setNewProviderName(e.target.value)}
                        placeholder="provider name (e.g. openai)"
                        className="flex-1 bg-background border-none rounded-lg px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-primary/20 transition-all"
                        onKeyDown={e => e.key === 'Enter' && addProvider()} autoFocus />
                      <button onClick={addProvider} className="px-3 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-lg hover:bg-primary/90 shadow-sm">Add</button>
                      <button onClick={() => { setShowNewProvider(false); setNewProviderName(''); }}
                        className="px-3 py-2 text-xs font-bold rounded-lg hover:bg-muted text-muted-foreground">Cancel</button>
                    </div>
                  ) : (
                    <button onClick={() => setShowNewProvider(true)}
                      className="flex items-center gap-2 px-4 py-3 text-sm font-semibold text-primary hover:bg-primary/5 rounded-xl border border-dashed border-primary/30 transition-all w-full justify-center">
                      <Plus size={16} />
                      Add Provider
                    </button>
                  )}
                </div>
              </Section>

              <Section title="Models" desc={`${modelNames.length} configured`} icon={<Cpu size={18} />}
                expanded={expandedSections.models} onToggle={() => setExpandedSections(p => ({ ...p, models: !p.models }))}>
                <div className="space-y-4">
                  {modelNames.map(name => (
                    <div key={name} className="bg-background border border-border rounded-xl overflow-hidden">
                      <button onClick={() => setExpandedModels(p => ({ ...p, [name]: !p[name] }))}
                        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-muted/30 transition-all text-left group">
                        <div className={`p-1 rounded-lg transition-all ${expandedModels[name] ? 'text-primary' : 'text-muted-foreground'}`}>
                          {expandedModels[name] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </div>
                        <span className="text-sm font-bold text-foreground flex-1">{name}</span>
                        <span className="text-xs text-muted-foreground font-mono">{models[name]?.provider} / {models[name]?.model_id}</span>
                        {defaultModel === name && (
                          <span className="text-[10px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">DEFAULT</span>
                        )}
                        <button onClick={e => { e.stopPropagation(); removeModel(name); }}
                          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-destructive/10 text-destructive/40 hover:text-destructive transition-all">
                          <Trash2 size={14} />
                        </button>
                      </button>
                      {expandedModels[name] && (
                        <div className="px-5 pb-5 pt-2 border-t border-border/40">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-muted-foreground text-xs font-semibold">Provider</label>
                              <select value={models[name]?.provider || ''} onChange={e => updateModel(name, 'provider', e.target.value)}
                                className="w-full bg-background border border-input rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm appearance-none cursor-pointer">
                                {providerNames.map(p => (
                                  <option key={p} value={p}>{p}</option>
                                ))}
                              </select>
                            </div>
                            <FieldInput label="Model ID" value={models[name]?.model_id || ''}
                              onChange={v => updateModel(name, 'model_id', v)} />
                            <FieldInput label="Timeout (s)" value={String(models[name]?.timeout || 60)} type="number"
                              onChange={v => updateModel(name, 'timeout', parseInt(v) || 60)} />
                            <FieldInput label="Max Tokens" value={String(models[name]?.max_tokens || 128000)} type="number"
                              onChange={v => updateModel(name, 'max_tokens', parseInt(v) || 128000)} />
                            <FieldInput label="Max Output Tokens" value={String(models[name]?.max_output_tokens || 16384)} type="number"
                              onChange={v => updateModel(name, 'max_output_tokens', parseInt(v) || 16384)} />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  {showNewModel ? (
                    <div className="flex gap-2 p-1 bg-muted/30 rounded-xl border border-border shadow-sm">
                      <input type="text" value={newModelName} onChange={e => setNewModelName(e.target.value)}
                        placeholder="model key (e.g. deepseek-chat)"
                        className="flex-1 bg-background border-none rounded-lg px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-primary/20 transition-all"
                        onKeyDown={e => e.key === 'Enter' && addModel()} autoFocus />
                      <button onClick={addModel} className="px-3 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-lg hover:bg-primary/90 shadow-sm">Add</button>
                      <button onClick={() => { setShowNewModel(false); setNewModelName(''); }}
                        className="px-3 py-2 text-xs font-bold rounded-lg hover:bg-muted text-muted-foreground">Cancel</button>
                    </div>
                  ) : (
                    <button onClick={() => setShowNewModel(true)}
                      className="flex items-center gap-2 px-4 py-3 text-sm font-semibold text-primary hover:bg-primary/5 rounded-xl border border-dashed border-primary/30 transition-all w-full justify-center">
                      <Plus size={16} />
                      Add Model
                    </button>
                  )}
                </div>
              </Section>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}

/* ===== Helper Components ===== */

function Section({ title, desc, icon, expanded, onToggle, children }: {
  title: string; desc: string; icon: React.ReactNode; expanded: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm shadow-black/5">
      <button onClick={onToggle} className="w-full flex items-center gap-4 px-6 py-5 hover:bg-muted/30 transition-all text-left group">
        <div className={`p-1.5 rounded-lg transition-all ${expanded ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground group-hover:bg-muted-foreground/10'}`}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </div>
        <div className="flex items-center gap-3 flex-1">
          <div className="text-muted-foreground">{icon}</div>
          <div>
            <span className="text-base font-bold text-foreground tracking-tight">{title}</span>
            <p className="text-xs text-muted-foreground mt-0.5 font-medium">{desc}</p>
          </div>
        </div>
      </button>
      {expanded && <div className="px-6 pb-6 pt-2 border-t border-border/40">{children}</div>}
    </div>
  );
}

function FieldInput({ label, value, onChange, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; type?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-semibold">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} step={type === 'number' ? 'any' : undefined}
        className="w-full bg-background border border-input rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm" />
    </div>
  );
}

function normalizeProviders(input: Record<string, any>): Record<string, ProviderConfig> {
  return Object.fromEntries(
    Object.entries(input).map(([name, value]) => {
      const provider = value && typeof value === 'object' ? value : {};
      const apiKeyValue = provider.api_key;
      const hasMeta = apiKeyValue && typeof apiKeyValue === 'object' && 'configured' in apiKeyValue;
      return [
        name,
        {
          api_key: hasMeta ? '' : String(apiKeyValue || ''),
          api_key_meta: hasMeta ? apiKeyValue as SecretValueStatus : null,
          api_key_touched: false,
          base_url: String(provider.base_url || ''),
          timeout: Number(provider.timeout || 60),
          max_retries: Number(provider.max_retries || 3),
        },
      ];
    }),
  );
}

function buildProviderPayloads(providers: Record<string, ProviderConfig>): Record<string, Record<string, unknown>> {
  return Object.fromEntries(
    Object.entries(providers).map(([name, provider]) => {
      const payload: Record<string, unknown> = {
        base_url: provider.base_url,
        timeout: provider.timeout,
        max_retries: provider.max_retries,
      };
      if (provider.api_key_touched) {
        payload.api_key = provider.api_key;
      } else if (!provider.api_key_meta?.configured) {
        payload.api_key = provider.api_key;
      }
      return [name, payload];
    }),
  );
}

function providerSecretSummary(provider?: ProviderConfig): string {
  if (!provider) return 'No key';
  if (provider.api_key) return maskApiKey(provider.api_key);
  if (provider.api_key_meta?.configured) return provider.api_key_meta.masked_value || 'Configured';
  return 'No key';
}

function maskApiKey(key: string): string {
  if (!key || key.startsWith('${')) return key;
  if (key.length <= 8) return '••••••••';
  return key.slice(0, 4) + '••••••••' + key.slice(-4);
}
