'use client';

import { useState, useEffect } from 'react';
import { Loader2, Save, Plus, Trash2, ChevronDown, ChevronRight, Server, Cpu, Settings2, Workflow, RefreshCw, Wand2, HardDriveDownload, TerminalSquare } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface ProviderConfig {
  source_type: string;
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

interface ACPConfig {
  enabled: boolean;
  command: string;
  args: string[];
  env: Record<string, string>;
  startup_timeout_seconds: number;
  request_timeout_seconds: number;
}

interface MiniAppsConfig {
  default_builder: 'builtin' | 'acp';
  acp: ACPConfig;
}

interface ACPWizardInstaller {
  id: string;
  label: string;
  found: boolean;
  path: string;
  candidate: string;
}

interface ACPWizardComponent {
  id: string;
  label: string;
  found: boolean;
  path: string;
  candidate: string;
}

interface ACPWizardInstallStep {
  id: string;
  label: string;
  installed: boolean;
  available: boolean;
  selected_recipe_id: string;
  command_preview: string;
  note: string;
}

interface ACPWizardEnvHint {
  key: string;
  description: string;
  required: boolean;
}

interface ACPWizardRecommendedConfig {
  enabled: boolean;
  command: string;
  args: string[];
  env: Record<string, string>;
  startup_timeout_seconds: number;
  request_timeout_seconds: number;
  default_builder: 'builtin' | 'acp';
}

interface ACPWizardAgent {
  id: string;
  name: string;
  summary: string;
  homepage: string;
  platforms: string[];
  supported_on_current_platform: boolean;
  mode: 'native' | 'adapter' | 'bridge';
  ready: boolean;
  configured: boolean;
  components: ACPWizardComponent[];
  runtime: ACPWizardComponent;
  missing_components: string[];
  recommended_config: ACPWizardRecommendedConfig;
  install_steps: ACPWizardInstallStep[];
  env_hints: ACPWizardEnvHint[];
  notes: string[];
}

interface ACPWizardState {
  platform: {
    id: string;
    label: string;
    python: string;
  };
  installers: Record<string, ACPWizardInstaller>;
  agents: ACPWizardAgent[];
  current_config: ACPConfig;
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // LLM 配置
  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [models, setModels] = useState<Record<string, ModelConfig>>({});
  const [defaultModel, setDefaultModel] = useState('');
  const [miniappsConfig, setMiniappsConfig] = useState<MiniAppsConfig>(normalizeMiniAppsConfig({}));
  const [acpArgsText, setAcpArgsText] = useState('[]');
  const [acpEnvText, setAcpEnvText] = useState('{}');
  const [wizardState, setWizardState] = useState<ACPWizardState | null>(null);
  const [wizardLoading, setWizardLoading] = useState(true);
  const [installingAgentId, setInstallingAgentId] = useState('');

  // 展开状态
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    providers: true, models: true, general: true, miniapps: true,
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
    Promise.all([
      authFetch(`${API_BASE}/api/config/sections`).then(res => res.json()),
      authFetch(`${API_BASE}/api/config/acp/wizard`).then(res => res.json()).catch(() => null),
    ])
      .then(([data, wizard]) => {
        const llm = data?.llm || {};
        const p = normalizeProviders(llm.providers || {});
        // 过滤掉 mock provider
        const { mock, ...realProviders } = p;
        setProviders(realProviders);
        const m = llm.models || {};
        const { mock: mockModel, ...realModels } = m;
        setModels(realModels);
        setDefaultModel(llm.default_model || '');
        const nextMiniappsConfig = normalizeMiniAppsConfig(data?.miniapps || {});
        setMiniappsConfig(nextMiniappsConfig);
        setAcpArgsText(JSON.stringify(nextMiniappsConfig.acp.args || [], null, 2));
        setAcpEnvText(JSON.stringify(nextMiniappsConfig.acp.env || {}, null, 2));
        setWizardState(normalizeWizardState(wizard));
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
        setWizardLoading(false);
      });
  }, []);

  // 保存配置
  const saveConfig = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      let parsedArgs: string[];
      let parsedEnv: Record<string, string>;
      try {
        parsedArgs = parseJsonStringArray(acpArgsText);
        parsedEnv = parseJsonStringRecord(acpEnvText);
      } catch (error) {
        setSaveMsg(error instanceof Error ? error.message : 'ACP 配置格式错误');
        return;
      }

      // 重新组装完整的 llm section（包含 mock）
      const llm = {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          ...buildProviderPayloads(providers),
        },
        models: { mock: { provider: 'mock', model_id: 'mock-agent-v1' }, ...models },
        default_model: defaultModel,
      };
      const miniapps = {
        default_builder: miniappsConfig.default_builder,
        acp: {
          enabled: miniappsConfig.acp.enabled,
          command: miniappsConfig.acp.command.trim(),
          args: parsedArgs,
          env: parsedEnv,
          startup_timeout_seconds: miniappsConfig.acp.startup_timeout_seconds,
          request_timeout_seconds: miniappsConfig.acp.request_timeout_seconds,
        },
      };
      const res = await authFetch(`${API_BASE}/api/config/sections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm, miniapps }),
      });
      if (res.ok) {
        setSaveMsg('已保存');
        setMiniappsConfig(miniapps);
        setAcpArgsText(JSON.stringify(miniapps.acp.args, null, 2));
        setAcpEnvText(JSON.stringify(miniapps.acp.env, null, 2));
        void refreshWizard();
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

  const refreshWizard = async () => {
    setWizardLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/api/config/acp/wizard`);
      const data = await res.json();
      setWizardState(normalizeWizardState(data));
    } catch {
      setSaveMsg('ACP 向导刷新失败');
    } finally {
      setWizardLoading(false);
    }
  };

  const applyWizardConfig = (agent: ACPWizardAgent) => {
    const next = normalizeMiniAppsConfig({
      default_builder: agent.recommended_config.default_builder,
      acp: {
        enabled: agent.recommended_config.enabled,
        command: agent.recommended_config.command,
        args: agent.recommended_config.args,
        env: agent.recommended_config.env,
        startup_timeout_seconds: agent.recommended_config.startup_timeout_seconds,
        request_timeout_seconds: agent.recommended_config.request_timeout_seconds,
      },
    });
    setMiniappsConfig(next);
    setAcpArgsText(JSON.stringify(next.acp.args, null, 2));
    setAcpEnvText(JSON.stringify(next.acp.env, null, 2));
    setSaveMsg(`已应用 ${agent.name} 推荐配置，请保存`);
    setTimeout(() => setSaveMsg(''), 3000);
  };

  const installWizardAgent = async (agent: ACPWizardAgent) => {
    setInstallingAgentId(agent.id);
    setSaveMsg('');
    try {
      const res = await authFetch(`${API_BASE}/api/config/acp/wizard/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agent.id }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setSaveMsg(data?.detail || '安装失败');
        return;
      }
      setWizardState(normalizeWizardState(data?.wizard));
      setSaveMsg(`${agent.name} 安装完成`);
    } catch {
      setSaveMsg('安装失败');
    } finally {
      setInstallingAgentId('');
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
      [name]: { source_type: 'openai', api_key: '', api_key_meta: null, api_key_touched: true, base_url: '', timeout: 60, max_retries: 3 },
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
  const saveMsgIsSuccess = Boolean(saveMsg) && !/失败|错误/.test(saveMsg);

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
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">ACP Settings</h2>
          <div className="flex items-center gap-4">
            {saveMsg && (
              <span className={`text-sm font-semibold px-3 py-1.5 rounded-full border shadow-sm ${
                saveMsgIsSuccess
                  ? 'text-green-600 bg-green-500/10 border-green-500/20 dark:text-green-400'
                  : 'text-destructive bg-destructive/10 border-destructive/20'
              }`}>
                {saveMsg}
              </span>
            )}
            <button onClick={saveConfig} disabled={saving} data-testid="save-settings"
              className="flex items-center gap-2.5 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 disabled:opacity-50 shadow-lg shadow-primary/20 active:scale-95 transition-all">
              {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
              Save All
            </button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
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
          <Card className="shadow-lg border-border/60">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Mini-App Builder</CardTitle>
              <Workflow className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-black truncate">
                {miniappsConfig.acp.enabled ? 'ACP Enabled' : 'Builtin Only'}
              </div>
              <p className="text-sm font-medium text-muted-foreground mt-2">
                Default: {miniappsConfig.default_builder === 'acp' ? 'ACP' : 'Builtin'}
              </p>
            </CardContent>
          </Card>
        </div>

        <Card className="shadow-xl border-border/80 overflow-hidden">
          <CardHeader className="bg-muted/30 border-b p-8">
            <CardTitle className="text-2xl font-bold">ACP Configuration</CardTitle>
            <CardDescription className="text-base mt-2">Manage mini-app ACP builder configuration here. LLM defaults remain on the same page for convenience.</CardDescription>
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

              <Section title="Mini-App Builder" desc="ACP 与默认 builder 配置" icon={<Workflow size={18} />}
                expanded={expandedSections.miniapps} onToggle={() => setExpandedSections(p => ({ ...p, miniapps: !p.miniapps }))}>
                <div className="space-y-5">
                  <div className="rounded-2xl border border-border/70 bg-muted/20 p-5 space-y-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                          <TerminalSquare size={16} className="text-primary" />
                          ACP Wizard
                        </div>
                        <p className="text-xs leading-6 text-muted-foreground">
                          自动检测当前平台可用的 ACP agent / adapter，并生成对应的 `command`、`args` 与安装动作。
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-flex items-center rounded-full border border-border bg-background px-3 py-1 text-xs font-semibold text-muted-foreground"
                          data-testid="acp-wizard-platform"
                        >
                          当前平台: {wizardState?.platform?.label || 'Unknown'}
                        </span>
                        <button
                          type="button"
                          onClick={refreshWizard}
                          disabled={wizardLoading}
                          data-testid="acp-wizard-refresh"
                          className="inline-flex items-center gap-2 rounded-xl border border-input bg-background px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted/40 disabled:opacity-50"
                        >
                          {wizardLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                          刷新检测
                        </button>
                      </div>
                    </div>

                    {wizardLoading && !wizardState ? (
                      <div className="flex items-center gap-3 rounded-xl border border-dashed border-border/70 bg-background px-4 py-4 text-sm text-muted-foreground">
                        <Loader2 size={16} className="animate-spin text-primary" />
                        正在检测 ACP agent 与安装器...
                      </div>
                    ) : wizardState && wizardState.agents.length > 0 ? (
                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                        {wizardState.agents.map(agent => (
                          <div
                            key={agent.id}
                            className="rounded-2xl border border-border/60 bg-background p-4 shadow-sm space-y-4"
                            data-testid={`acp-wizard-card-${agent.id}`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-semibold text-foreground">{agent.name}</div>
                                  <span className="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                                    {renderAgentMode(agent.mode)}
                                  </span>
                                </div>
                                <p className="text-xs leading-6 text-muted-foreground">{agent.summary}</p>
                              </div>
                              <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${
                                agent.configured
                                  ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400'
                                  : agent.ready
                                    ? 'border-primary/30 bg-primary/10 text-primary'
                                    : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                              }`}>
                                {agent.configured ? '已配置' : agent.ready ? '可直接使用' : '缺少依赖'}
                              </span>
                            </div>

                            <div className="rounded-xl border border-border/60 bg-muted/20 p-3 space-y-2 text-xs text-muted-foreground">
                              <div>
                                <span className="font-semibold text-foreground/90">推荐命令</span>
                                <pre className="mt-1 overflow-auto rounded-lg bg-background px-3 py-2 font-mono text-[11px] text-foreground/80">{`${agent.recommended_config.command}${agent.recommended_config.args.length ? ` ${agent.recommended_config.args.join(' ')}` : ''}`}</pre>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {agent.components.map(component => (
                                  <span key={component.id} className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold ${
                                    component.found
                                      ? 'border-green-500/25 bg-green-500/10 text-green-700 dark:text-green-400'
                                      : 'border-border text-muted-foreground'
                                  }`}>
                                    {component.label}: {component.found ? '已检测' : '未检测'}
                                  </span>
                                ))}
                              </div>
                              {agent.env_hints.length > 0 && (
                                <div className="space-y-1">
                                  <div className="font-semibold text-foreground/90">常见环境变量</div>
                                  <div className="flex flex-wrap gap-2">
                                    {agent.env_hints.map(hint => (
                                      <span key={hint.key} className="inline-flex items-center rounded-full border border-border bg-background px-2 py-1 text-[10px] font-semibold text-muted-foreground">
                                        {hint.key}{hint.required ? ' *' : ''}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>

                            {agent.install_steps.length > 0 && (
                              <div className="space-y-2">
                                {agent.install_steps.map(step => (
                                  <div key={step.id} className="rounded-xl border border-border/50 px-3 py-2 text-xs text-muted-foreground">
                                    <div className="flex items-center justify-between gap-3">
                                      <span className="font-semibold text-foreground/90">{step.label}</span>
                                      <span>{step.installed ? '已安装' : step.available ? '可安装' : '当前环境不可安装'}</span>
                                    </div>
                                    {step.command_preview && (
                                      <pre className="mt-2 overflow-auto rounded-lg bg-muted/30 px-3 py-2 font-mono text-[11px] text-foreground/80">{step.command_preview}</pre>
                                    )}
                                    {step.note && <p className="mt-2 leading-5">{step.note}</p>}
                                  </div>
                                ))}
                              </div>
                            )}

                            {agent.notes.length > 0 && (
                              <div className="space-y-1 text-xs text-muted-foreground">
                                {agent.notes.map(note => (
                                  <p key={note} className="leading-6">{note}</p>
                                ))}
                              </div>
                            )}

                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => applyWizardConfig(agent)}
                                data-testid={`acp-wizard-apply-${agent.id}`}
                                className="inline-flex items-center gap-2 rounded-xl bg-primary px-3.5 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90"
                              >
                                <Wand2 size={14} />
                                应用推荐配置
                              </button>
                              <button
                                type="button"
                                onClick={() => installWizardAgent(agent)}
                                disabled={installingAgentId === agent.id || agent.install_steps.every(step => step.installed || !step.available)}
                                data-testid={`acp-wizard-install-${agent.id}`}
                                className="inline-flex items-center gap-2 rounded-xl border border-input bg-background px-3.5 py-2 text-xs font-bold text-foreground hover:bg-muted/40 disabled:opacity-50"
                              >
                                {installingAgentId === agent.id ? <Loader2 size={14} className="animate-spin" /> : <HardDriveDownload size={14} />}
                                安装缺失项
                              </button>
                              <a
                                href={agent.homepage}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-2 rounded-xl border border-border bg-muted/20 px-3.5 py-2 text-xs font-semibold text-muted-foreground hover:bg-muted/40"
                              >
                                官方文档
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-border/70 bg-background px-4 py-4 text-sm text-muted-foreground">
                        当前无法加载 ACP 向导数据，请稍后重试。
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-muted-foreground text-xs font-semibold">Default Builder</label>
                      <select
                        value={miniappsConfig.default_builder}
                        data-testid="miniapps-default-builder-select"
                        onChange={e => setMiniappsConfig(prev => ({
                          ...prev,
                          default_builder: (e.target.value === 'acp' ? 'acp' : 'builtin'),
                        }))}
                        className="w-full bg-background border border-input rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm appearance-none cursor-pointer"
                      >
                        <option value="builtin">builtin</option>
                        <option value="acp">acp</option>
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-muted-foreground text-xs font-semibold">ACP Enabled</label>
                      <label className="flex items-center gap-3 rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm">
                        <input
                          type="checkbox"
                          checked={miniappsConfig.acp.enabled}
                          data-testid="miniapps-acp-enabled"
                          onChange={e => setMiniappsConfig(prev => ({
                            ...prev,
                            acp: {
                              ...prev.acp,
                              enabled: e.target.checked,
                            },
                          }))}
                          className="h-4 w-4 rounded border-input text-primary focus:ring-primary/20"
                        />
                        <span>启用 ACP coding agent 构建链路</span>
                      </label>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FieldInput label="ACP Command" value={miniappsConfig.acp.command}
                      dataTestId="miniapps-acp-command-input"
                      onChange={v => setMiniappsConfig(prev => ({
                        ...prev,
                        acp: {
                          ...prev.acp,
                          command: v,
                        },
                      }))} />
                    <FieldInput label="Startup Timeout (s)" value={String(miniappsConfig.acp.startup_timeout_seconds)} type="number"
                      dataTestId="miniapps-acp-startup-timeout-input"
                      onChange={v => setMiniappsConfig(prev => ({
                        ...prev,
                        acp: {
                          ...prev.acp,
                          startup_timeout_seconds: parseInt(v, 10) || 20,
                        },
                      }))} />
                    <FieldInput label="Request Timeout (s)" value={String(miniappsConfig.acp.request_timeout_seconds)} type="number"
                      dataTestId="miniapps-acp-request-timeout-input"
                      onChange={v => setMiniappsConfig(prev => ({
                        ...prev,
                        acp: {
                          ...prev.acp,
                          request_timeout_seconds: parseInt(v, 10) || 180,
                        },
                      }))} />
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <FieldTextArea
                      label="ACP Args (JSON array)"
                      value={acpArgsText}
                      dataTestId="miniapps-acp-args-input"
                      placeholder={'[\n  "--stdio"\n]'}
                      onChange={setAcpArgsText}
                    />
                    <FieldTextArea
                      label="ACP Env (JSON object)"
                      value={acpEnvText}
                      dataTestId="miniapps-acp-env-input"
                      placeholder={'{\n  "OPENAI_API_KEY": "sk-..."\n}'}
                      onChange={setAcpEnvText}
                    />
                  </div>

                  <p className="text-xs text-muted-foreground leading-6">
                    `args` 需要填写 JSON 字符串数组，`env` 需要填写 JSON 对象。上面的 ACP Wizard 会根据当前平台生成推荐配置；这里仍保留手工编辑入口，方便你继续微调 command / args / env。
                  </p>
                  <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                    <div className="text-sm font-semibold text-foreground mb-2">常见 ACP 启动命令</div>
                    <div className="space-y-2 text-xs text-muted-foreground leading-6">
                      <pre className="rounded-xl bg-background px-3 py-3 font-mono text-[11px] overflow-auto text-foreground/80">{`Codex CLI      -> command: codex-acp,          args: []
Claude         -> command: claude-agent-acp,   args: []
Gemini CLI     -> command: gemini,             args: ["--experimental-acp"]
Kimi CLI       -> command: kimi,               args: ["acp"]
OpenCode       -> command: opencode,           args: ["acp"]
Codex Bridge   -> command: python3,            args: ["-m", "sensenova_claw.capabilities.miniapps.codex_acp_bridge"]`}</pre>
                      <p>如果某个 agent / adapter 还没装，优先直接使用上方 ACP Wizard 检测并安装；Wizard 会按当前平台给出更稳的命令路径。</p>
                    </div>
                  </div>
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

function FieldInput({ label, value, onChange, type = 'text', dataTestId }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; dataTestId?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-semibold">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} step={type === 'number' ? 'any' : undefined}
        data-testid={dataTestId}
        className="w-full bg-background border border-input rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm" />
    </div>
  );
}

function FieldTextArea({ label, value, onChange, placeholder, dataTestId }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  dataTestId?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-semibold">{label}</label>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={dataTestId}
        spellCheck={false}
        rows={6}
        className="w-full bg-background border border-input rounded-xl px-4 py-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all shadow-sm font-mono"
      />
    </div>
  );
}

function renderAgentMode(mode: ACPWizardAgent['mode']): string {
  switch (mode) {
    case 'native':
      return 'Native ACP';
    case 'bridge':
      return 'Bridge';
    default:
      return 'Adapter';
  }
}

function normalizeWizardState(input: any): ACPWizardState | null {
  if (!input || typeof input !== 'object') return null;
  const agents = Array.isArray(input.agents) ? input.agents : [];
  return {
    platform: {
      id: String(input.platform?.id || ''),
      label: String(input.platform?.label || ''),
      python: String(input.platform?.python || ''),
    },
    installers: Object.fromEntries(
      Object.entries(input.installers && typeof input.installers === 'object' ? input.installers : {}).map(([key, value]) => {
        const installer = value && typeof value === 'object' ? value as Record<string, unknown> : {};
        return [
          key,
          {
            id: String(installer.id || key),
            label: String(installer.label || key),
            found: Boolean(installer.found),
            path: String(installer.path || ''),
            candidate: String(installer.candidate || ''),
          },
        ];
      }),
    ),
    agents: agents.map((item: unknown): ACPWizardAgent => {
      const agent = item && typeof item === 'object' ? item as Record<string, unknown> : {};
      const runtime = agent.runtime && typeof agent.runtime === 'object' ? agent.runtime as Record<string, unknown> : {};
      const recommendedConfig = agent.recommended_config && typeof agent.recommended_config === 'object' ? agent.recommended_config as Record<string, unknown> : {};
      return {
        id: String(agent.id || ''),
        name: String(agent.name || ''),
        summary: String(agent.summary || ''),
        homepage: String(agent.homepage || ''),
        platforms: Array.isArray(agent.platforms) ? agent.platforms.map((platform: unknown) => String(platform)) : [],
        supported_on_current_platform: Boolean(agent.supported_on_current_platform),
        mode: agent.mode === 'native' || agent.mode === 'bridge' ? agent.mode : 'adapter',
        ready: Boolean(agent.ready),
        configured: Boolean(agent.configured),
        components: Array.isArray(agent.components)
          ? agent.components.map((component: any) => ({
              id: String(component?.id || ''),
              label: String(component?.label || ''),
              found: Boolean(component?.found),
              path: String(component?.path || ''),
              candidate: String(component?.candidate || ''),
            }))
          : [],
        runtime: {
          id: String(runtime.id || ''),
          label: String(runtime.label || ''),
          found: Boolean(runtime.found),
          path: String(runtime.path || ''),
          candidate: String(runtime.candidate || ''),
        },
        missing_components: Array.isArray(agent.missing_components)
          ? agent.missing_components.map((part: unknown) => String(part))
          : [],
        recommended_config: {
          enabled: Boolean(recommendedConfig.enabled),
          command: String(recommendedConfig.command || ''),
          args: Array.isArray(recommendedConfig.args) ? recommendedConfig.args.map((part: unknown) => String(part)) : [],
          env: Object.fromEntries(
            Object.entries(recommendedConfig.env && typeof recommendedConfig.env === 'object' ? recommendedConfig.env : {}).map(([key, value]) => [String(key), String(value)])
          ),
          startup_timeout_seconds: Number(recommendedConfig.startup_timeout_seconds || 20),
          request_timeout_seconds: Number(recommendedConfig.request_timeout_seconds || 180),
          default_builder: recommendedConfig.default_builder === 'acp' ? 'acp' : 'builtin',
        },
        install_steps: Array.isArray(agent.install_steps)
          ? agent.install_steps.map((step: any) => ({
              id: String(step?.id || ''),
              label: String(step?.label || ''),
              installed: Boolean(step?.installed),
              available: Boolean(step?.available),
              selected_recipe_id: String(step?.selected_recipe_id || ''),
              command_preview: String(step?.command_preview || ''),
              note: String(step?.note || ''),
            }))
          : [],
        env_hints: Array.isArray(agent.env_hints)
          ? agent.env_hints.map((hint: any) => ({
              key: String(hint?.key || ''),
              description: String(hint?.description || ''),
              required: Boolean(hint?.required),
            }))
          : [],
        notes: Array.isArray(agent.notes) ? agent.notes.map((note: unknown) => String(note)) : [],
      };
    }),
    current_config: normalizeMiniAppsConfig({ acp: input.current_config || {} }).acp,
  };
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
          source_type: String(provider.source_type || 'openai'),
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

function normalizeMiniAppsConfig(input: Record<string, any>): MiniAppsConfig {
  const miniapps = input && typeof input === 'object' ? input : {};
  const acp = miniapps.acp && typeof miniapps.acp === 'object' ? miniapps.acp : {};
  return {
    default_builder: miniapps.default_builder === 'acp' ? 'acp' : 'builtin',
    acp: {
      enabled: Boolean(acp.enabled),
      command: String(acp.command || ''),
      args: Array.isArray(acp.args) ? acp.args.map((item: unknown) => String(item)) : [],
      env: Object.fromEntries(
        Object.entries(acp.env && typeof acp.env === 'object' ? acp.env : {}).map(([key, value]) => [key, String(value)])
      ),
      startup_timeout_seconds: Number(acp.startup_timeout_seconds || 20),
      request_timeout_seconds: Number(acp.request_timeout_seconds || 180),
    },
  };
}

function parseJsonStringArray(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const parsed = JSON.parse(trimmed);
  if (!Array.isArray(parsed) || parsed.some(item => typeof item !== 'string')) {
    throw new Error('ACP args 必须是 JSON 字符串数组');
  }
  return parsed;
}

function parseJsonStringRecord(text: string): Record<string, string> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('ACP env 必须是 JSON 对象');
  }
  const entries = Object.entries(parsed).map(([key, value]) => {
    if (value !== null && typeof value === 'object') {
      throw new Error('ACP env 的值必须是字符串或基础类型');
    }
    return [key, value === undefined ? '' : String(value)];
  });
  return Object.fromEntries(entries);
}

function buildProviderPayloads(providers: Record<string, ProviderConfig>): Record<string, Record<string, unknown>> {
  return Object.fromEntries(
    Object.entries(providers).map(([name, provider]) => {
      const payload: Record<string, unknown> = {
        source_type: provider.source_type || 'openai',
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
