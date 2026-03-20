'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Cpu, Loader2, Plus, Save, Server, Trash2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface SecretValueStatus {
  configured: boolean;
  masked_value?: string | null;
  source: string;
}

interface ProviderConfig {
  api_key: string;
  api_key_meta?: SecretValueStatus | null;
  api_key_touched?: boolean;
  base_url: string;
  timeout: number;
  max_retries: number;
}

interface ModelConfig {
  provider: string;
  model_id: string;
  timeout: number;
  max_output_tokens: number;
}

export default function LlmsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [models, setModels] = useState<Record<string, ModelConfig>>({});
  const [defaultModel, setDefaultModel] = useState('');

  const [showNewProvider, setShowNewProvider] = useState(false);
  const [newProviderName, setNewProviderName] = useState('');
  const [newModelDrafts, setNewModelDrafts] = useState<Record<string, string>>({});
  const [openNewModelForms, setOpenNewModelForms] = useState<Record<string, boolean>>({});
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({});

  useEffect(() => {
    authFetch(`${API_BASE}/api/config/sections`)
      .then((res) => res.json())
      .then((data) => {
        const llm = data?.llm || {};
        const normalizedProviders = normalizeProviders(llm.providers || {});
        const { mock, ...realProviders } = normalizedProviders;
        const rawModels = normalizeModels(llm.models || {});
        const { mock: _mockModel, ...realModels } = rawModels;
        setProviders(realProviders);
        setModels(realModels);
        setDefaultModel(llm.default_model || '');
        setExpandedProviders(
          Object.fromEntries(Object.keys(realProviders).map((name) => [name, true])),
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const providerNames = useMemo(() => Object.keys(providers), [providers]);
  const modelNames = useMemo(() => Object.keys(models), [models]);

  const groupedModels = useMemo(() => {
    return providerNames.reduce<Record<string, string[]>>((acc, providerName) => {
      acc[providerName] = modelNames.filter((modelName) => models[modelName]?.provider === providerName);
      return acc;
    }, {});
  }, [modelNames, models, providerNames]);

  const updateProviderField = (name: string, field: keyof ProviderConfig, value: string | number) => {
    setProviders((prev) => ({
      ...prev,
      [name]: {
        ...prev[name],
        [field]: value,
        ...(field === 'api_key' ? { api_key_touched: true } : {}),
      },
    }));
  };

  const renameProvider = (oldName: string, nextNameRaw: string) => {
    const nextName = nextNameRaw.trim().toLowerCase();
    if (!nextName || nextName === oldName || providers[nextName]) {
      return;
    }

    setProviders((prev) => {
      const next = { ...prev };
      const provider = next[oldName];
      delete next[oldName];
      next[nextName] = provider;
      return next;
    });

    setModels((prev) => Object.fromEntries(
      Object.entries(prev).map(([modelName, model]) => [
        modelName,
        model.provider === oldName ? { ...model, provider: nextName } : model,
      ]),
    ));

    setOpenNewModelForms((prev) => {
      const next = { ...prev };
      if (oldName in next) {
        next[nextName] = next[oldName];
        delete next[oldName];
      }
      return next;
    });

    setNewModelDrafts((prev) => {
      const next = { ...prev };
      if (oldName in next) {
        next[nextName] = next[oldName];
        delete next[oldName];
      }
      return next;
    });
    setExpandedProviders((prev) => {
      const next = { ...prev };
      if (oldName in next) {
        next[nextName] = next[oldName];
        delete next[oldName];
      }
      return next;
    });
  };

  const addProvider = () => {
    const name = newProviderName.trim().toLowerCase();
    if (!name || providers[name]) {
      return;
    }
    setProviders((prev) => ({
      ...prev,
      [name]: {
        api_key: '',
        api_key_meta: null,
        api_key_touched: true,
        base_url: '',
        timeout: 60,
        max_retries: 3,
      },
    }));
    setShowNewProvider(false);
    setNewProviderName('');
    setExpandedProviders((prev) => ({ ...prev, [name]: true }));
  };

  const removeProvider = (name: string) => {
    if (!confirm(`确定删除 provider "${name}" 吗？其下关联的 llm 也会一并删除。`)) {
      return;
    }

    const removedModels = groupedModels[name] || [];
    setProviders((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    setModels((prev) => {
      const next = { ...prev };
      removedModels.forEach((modelName) => {
        delete next[modelName];
      });
      return next;
    });
    setExpandedProviders((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (removedModels.includes(defaultModel)) {
      setDefaultModel('');
    }
  };

  const updateModelField = (name: string, field: keyof ModelConfig, value: string | number) => {
    setModels((prev) => ({
      ...prev,
      [name]: {
        ...prev[name],
        [field]: value,
      },
    }));
  };

  const renameModel = (oldName: string, nextNameRaw: string) => {
    const nextName = nextNameRaw.trim();
    if (!nextName || nextName === oldName || models[nextName]) {
      return;
    }

    setModels((prev) => {
      const next = { ...prev };
      const model = next[oldName];
      delete next[oldName];
      next[nextName] = model;
      return next;
    });

    if (defaultModel === oldName) {
      setDefaultModel(nextName);
    }
  };

  const addModel = (providerName: string) => {
    const nextName = (newModelDrafts[providerName] || '').trim();
    if (!nextName || models[nextName]) {
      return;
    }

    setModels((prev) => ({
      ...prev,
      [nextName]: {
        provider: providerName,
        model_id: '',
        timeout: 60,
        max_output_tokens: 8192,
      },
    }));
    setNewModelDrafts((prev) => ({ ...prev, [providerName]: '' }));
    setOpenNewModelForms((prev) => ({ ...prev, [providerName]: false }));
  };

  const removeModel = (name: string) => {
    if (!confirm(`确定删除 llm "${name}" 吗？`)) {
      return;
    }
    setModels((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (defaultModel === name) {
      setDefaultModel('');
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      const llm = {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          ...buildProviderPayloads(providers),
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          ...models,
        },
        default_model: defaultModel,
      };
      const res = await authFetch(`${API_BASE}/api/config/sections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setSaveMsg(err.detail || '保存失败');
        return;
      }
      setSaveMsg('已保存');
    } catch {
      setSaveMsg('保存失败');
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(''), 3000);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
          <Loader2 className="animate-spin text-primary" size={48} />
          <p className="text-sm font-bold uppercase tracking-widest">Loading llm config...</p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-4xl font-extrabold tracking-tight text-foreground/90">LLM 配置</h1>
            <p className="text-sm text-muted-foreground">按 provider 管理 llm，支持 provider 与 llm 的增删改。</p>
          </div>
          <div className="flex items-center gap-4">
            {saveMsg && (
              <span className={`rounded-full border px-3 py-1.5 text-sm font-semibold shadow-sm ${
                saveMsg.includes('失败')
                  ? 'border-destructive/20 bg-destructive/10 text-destructive'
                  : 'border-green-500/20 bg-green-500/10 text-green-600 dark:text-green-400'
              }`}>
                {saveMsg}
              </span>
            )}
            <button
              type="button"
              data-testid="save-llm-config"
              onClick={saveConfig}
              disabled={saving}
              className="flex items-center gap-2.5 rounded-xl bg-primary px-6 py-2.5 font-bold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
              保存
            </button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <SummaryCard title="Providers" value={providerNames.length} desc="已配置 provider 数量" icon={<Server className="h-5 w-5 text-primary" />} />
          <SummaryCard title="LLMs" value={modelNames.length} desc="已配置 llm 数量" icon={<Cpu className="h-5 w-5 text-primary" />} />
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Default Model</CardTitle>
              <Save className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent className="space-y-3">
              <select
                data-testid="default-model-select"
                value={defaultModel}
                onChange={(e) => setDefaultModel(e.target.value)}
                className="w-full cursor-pointer rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">未设置</option>
                {modelNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <p className="text-sm text-muted-foreground">默认模型用于 agent 未显式指定 model 的场景。</p>
            </CardContent>
          </Card>
        </div>

        <Card className="overflow-hidden border-border/80 shadow-xl">
          <CardHeader className="border-b bg-muted/30 p-8">
            <CardTitle className="text-2xl font-bold">Provider 列表</CardTitle>
            <CardDescription className="mt-2 text-base">每个 provider 下直接管理关联的 llm 配置。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 p-8">
            {providerNames.map((providerName) => (
              <div
                key={providerName}
                data-testid={`provider-card-${providerName}`}
                className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm shadow-black/5"
              >
                <div className="flex items-center gap-3 border-b border-border/60 px-6 py-4">
                  <button
                    type="button"
                    data-testid={`provider-toggle-${providerName}`}
                    onClick={() => setExpandedProviders((prev) => ({ ...prev, [providerName]: !prev[providerName] }))}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left transition-colors hover:text-primary"
                  >
                    {expandedProviders[providerName] ? (
                      <ChevronDown className="h-4 w-4 text-primary" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <span className="truncate text-base font-bold text-foreground">{providerName}</span>
                        <span className="rounded-full border border-border/60 px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
                          {(groupedModels[providerName] || []).length} 个 llm
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {providers[providerName]?.base_url || '未配置 Base URL'}
                      </p>
                    </div>
                  </button>
                  <button
                    type="button"
                    data-testid={`delete-provider-button-${providerName}`}
                    onClick={() => removeProvider(providerName)}
                    className="rounded-xl border border-destructive/20 px-3 py-2 text-destructive transition-colors hover:bg-destructive/10"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {expandedProviders[providerName] && (
                  <div data-testid={`provider-body-${providerName}`} className="space-y-6 p-6">
                    <div className="grid gap-4 md:grid-cols-2">
                      <FieldInput
                        label="Provider 名称"
                        value={providerName}
                        dataTestId={`provider-name-input-${providerName}`}
                        onChange={(value) => renameProvider(providerName, value)}
                      />
                      <FieldInput
                        label="API Key"
                        type="password"
                        value={providers[providerName]?.api_key || ''}
                        dataTestId={`provider-api-key-input-${providerName}`}
                        placeholder={providers[providerName]?.api_key_meta?.configured ? (providers[providerName]?.api_key_meta?.masked_value || 'Configured') : ''}
                        onChange={(value) => updateProviderField(providerName, 'api_key', value)}
                      />
                      <FieldInput
                        label="Base URL"
                        value={providers[providerName]?.base_url || ''}
                        dataTestId={`provider-base-url-input-${providerName}`}
                        onChange={(value) => updateProviderField(providerName, 'base_url', value)}
                      />
                      <FieldInput
                        label="Timeout (s)"
                        type="number"
                        value={String(providers[providerName]?.timeout || 60)}
                        dataTestId={`provider-timeout-input-${providerName}`}
                        onChange={(value) => updateProviderField(providerName, 'timeout', parseInt(value, 10) || 60)}
                      />
                      <FieldInput
                        label="Max Retries"
                        type="number"
                        value={String(providers[providerName]?.max_retries || 3)}
                        dataTestId={`provider-max-retries-input-${providerName}`}
                        onChange={(value) => updateProviderField(providerName, 'max_retries', parseInt(value, 10) || 3)}
                      />
                    </div>

                    <div className="space-y-4 rounded-2xl border border-border/60 bg-muted/20 p-5">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <h2 className="text-lg font-bold text-foreground">LLM 列表</h2>
                          <p className="text-sm text-muted-foreground">当前 provider 下的 llm 会在保存时自动归属到该 provider。</p>
                        </div>
                        <button
                          type="button"
                          data-testid={`add-llm-button-${providerName}`}
                          onClick={() => setOpenNewModelForms((prev) => ({ ...prev, [providerName]: !prev[providerName] }))}
                          className="flex items-center gap-2 rounded-xl border border-primary/30 px-4 py-2 text-sm font-semibold text-primary transition-all hover:bg-primary/5"
                        >
                          <Plus size={16} />
                          添加 llm
                        </button>
                      </div>

                      {openNewModelForms[providerName] && (
                        <div className="flex flex-col gap-3 rounded-xl border border-dashed border-primary/30 bg-background p-4 md:flex-row">
                          <input
                            type="text"
                            value={newModelDrafts[providerName] || ''}
                            data-testid={`new-llm-name-input-${providerName}`}
                            onChange={(e) => setNewModelDrafts((prev) => ({ ...prev, [providerName]: e.target.value }))}
                            placeholder="llm 名称，例如 gpt-4.1-mini"
                            className="flex-1 rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                          />
                          <button
                            type="button"
                            data-testid={`confirm-add-llm-button-${providerName}`}
                            onClick={() => addModel(providerName)}
                            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground transition-all hover:bg-primary/90"
                          >
                            添加
                          </button>
                        </div>
                      )}

                      <div className="space-y-4">
                        {(groupedModels[providerName] || []).map((modelName) => (
                          <div
                            key={modelName}
                            data-testid={`llm-card-${modelName}`}
                            className="grid gap-4 rounded-2xl border border-border bg-background p-4 md:grid-cols-[1fr_1fr_140px]"
                          >
                            <div className="grid gap-4 md:col-span-2 md:grid-cols-2">
                              <FieldInput
                                label="LLM 名称"
                                value={modelName}
                                dataTestId={`llm-name-input-${modelName}`}
                                onChange={(value) => renameModel(modelName, value)}
                              />
                              <FieldInput
                                label="Model ID"
                                value={models[modelName]?.model_id || ''}
                                dataTestId={`llm-model-id-input-${modelName}`}
                                onChange={(value) => updateModelField(modelName, 'model_id', value)}
                              />
                              <FieldInput
                                label="Timeout (s)"
                                type="number"
                                value={String(models[modelName]?.timeout || 60)}
                                dataTestId={`llm-timeout-input-${modelName}`}
                                onChange={(value) => updateModelField(modelName, 'timeout', parseInt(value, 10) || 60)}
                              />
                              <FieldInput
                                label="Max Output Tokens"
                                type="number"
                                value={String(models[modelName]?.max_output_tokens || 8192)}
                                dataTestId={`llm-max-output-tokens-input-${modelName}`}
                                onChange={(value) => updateModelField(modelName, 'max_output_tokens', parseInt(value, 10) || 8192)}
                              />
                            </div>
                            <div className="flex items-start justify-end md:justify-center">
                              <button
                                type="button"
                                data-testid={`delete-llm-button-${modelName}`}
                                onClick={() => removeModel(modelName)}
                                className="rounded-xl border border-destructive/20 px-3 py-2 text-destructive transition-colors hover:bg-destructive/10"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </div>
                        ))}

                        {(groupedModels[providerName] || []).length === 0 && (
                          <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                            当前 provider 还没有 llm，点击“添加 llm”开始配置。
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {showNewProvider ? (
              <div className="flex flex-col gap-3 rounded-2xl border border-dashed border-primary/30 bg-muted/20 p-5 md:flex-row">
                <input
                  type="text"
                  value={newProviderName}
                  data-testid="new-provider-name-input"
                  onChange={(e) => setNewProviderName(e.target.value)}
                  placeholder="provider 名称，例如 deepseek"
                  className="flex-1 rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                <button
                  type="button"
                  data-testid="confirm-add-provider-button"
                  onClick={addProvider}
                  className="rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground transition-all hover:bg-primary/90"
                >
                  添加 provider
                </button>
              </div>
            ) : (
              <button
                type="button"
                data-testid="add-provider-button"
                onClick={() => setShowNewProvider(true)}
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-primary/30 px-4 py-4 text-sm font-semibold text-primary transition-all hover:bg-primary/5"
              >
                <Plus size={16} />
                添加 provider
              </button>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}

function SummaryCard({
  title,
  value,
  desc,
  icon,
}: {
  title: string;
  value: number;
  desc: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className="border-border/60 shadow-lg">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-4xl font-black">{value}</div>
        <p className="mt-2 text-sm font-medium text-muted-foreground">{desc}</p>
      </CardContent>
    </Card>
  );
}

function FieldInput({
  label,
  value,
  onChange,
  type = 'text',
  dataTestId,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  dataTestId?: string;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground">{label}</label>
      <input
        type={type}
        value={value}
        data-testid={dataTestId}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
      />
    </div>
  );
}

function normalizeProviders(input: Record<string, unknown>): Record<string, ProviderConfig> {
  return Object.fromEntries(
    Object.entries(input).map(([name, value]) => {
      const provider = value && typeof value === 'object' ? value as Record<string, unknown> : {};
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

function normalizeModels(input: Record<string, unknown>): Record<string, ModelConfig> {
  return Object.fromEntries(
    Object.entries(input).map(([name, value]) => {
      const model = value && typeof value === 'object' ? value as Record<string, unknown> : {};
      return [
        name,
        {
          provider: String(model.provider || ''),
          model_id: String(model.model_id || ''),
          timeout: Number(model.timeout || 60),
          max_output_tokens: Number(model.max_output_tokens || 8192),
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
