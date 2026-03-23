'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Cpu, Eye, EyeOff, Loader2, Plus, Save, Server, Trash2 } from 'lucide-react';
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
  max_tokens: number;
  max_output_tokens: number;
}

interface ProviderDraft extends ProviderConfig {
  name: string;
}

interface ModelDraft extends ModelConfig {
  name: string;
}

interface GlobalDraft {
  providers: Record<string, ProviderDraft>;
  models: Record<string, ModelDraft>;
  defaultModel: string;
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
  const [apiKeyVisibility, setApiKeyVisibility] = useState<Record<string, boolean>>({});
  const [apiKeyLoading, setApiKeyLoading] = useState<Record<string, boolean>>({});
  const [editingAll, setEditingAll] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [editingModel, setEditingModel] = useState<string | null>(null);
  const [providerDrafts, setProviderDrafts] = useState<Record<string, ProviderDraft>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, ModelDraft>>({});
  const [globalDraft, setGlobalDraft] = useState<GlobalDraft | null>(null);

  const loadConfig = () => {
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
          Object.fromEntries(Object.keys(realProviders).map((name) => [name, false])),
        );
        setEditingAll(false);
        setEditingProvider(null);
        setEditingModel(null);
        setProviderDrafts({});
        setModelDrafts({});
        setGlobalDraft(null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const activeProviders = useMemo(() => {
    if (!editingAll || !globalDraft) return providers;
    return Object.fromEntries(Object.entries(globalDraft.providers).map(([key, draft]) => [
      key,
      {
        api_key: draft.api_key,
        api_key_meta: draft.api_key_meta,
        api_key_touched: draft.api_key_touched,
        base_url: draft.base_url,
        timeout: draft.timeout,
        max_retries: draft.max_retries,
      },
    ]));
  }, [editingAll, globalDraft, providers]);

  const activeModels = useMemo(() => {
    if (!editingAll || !globalDraft) return models;
    return Object.fromEntries(Object.entries(globalDraft.models).map(([key, draft]) => [
      key,
      {
        provider: draft.provider,
        model_id: draft.model_id,
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
      },
    ]));
  }, [editingAll, globalDraft, models]);

  const providerNames = useMemo(() => Object.keys(activeProviders), [activeProviders]);
  const modelNames = useMemo(() => Object.keys(activeModels), [activeModels]);

  const groupedModels = useMemo(() => {
    return providerNames.reduce<Record<string, string[]>>((acc, providerName) => {
      acc[providerName] = modelNames.filter((modelName) => activeModels[modelName]?.provider === providerName);
      return acc;
    }, {});
  }, [activeModels, modelNames, providerNames]);

  const cloneProvidersToDrafts = (source: Record<string, ProviderConfig>): Record<string, ProviderDraft> => (
    Object.fromEntries(Object.entries(source).map(([name, provider]) => [
      name,
      { ...provider, name },
    ]))
  );

  const cloneModelsToDrafts = (source: Record<string, ModelConfig>): Record<string, ModelDraft> => (
    Object.fromEntries(Object.entries(source).map(([name, model]) => [
      name,
      { ...model, name },
    ]))
  );

  const isProviderEditable = (name: string) => editingAll || editingProvider === name;
  const isModelEditable = (name: string) => editingAll || editingModel === name;

  const getProviderDraft = (name: string): ProviderDraft => {
    if (editingAll && globalDraft) return globalDraft.providers[name];
    return providerDrafts[name] || { ...providers[name], name };
  };

  const getModelDraft = (name: string): ModelDraft => {
    if (editingAll && globalDraft) return globalDraft.models[name];
    return modelDrafts[name] || { ...models[name], name };
  };

  const updateProviderField = (name: string, field: keyof ProviderConfig, value: string | number) => {
    if (editingAll && globalDraft) {
      setGlobalDraft({
        ...globalDraft,
        providers: {
          ...globalDraft.providers,
          [name]: {
            ...globalDraft.providers[name],
            [field]: value,
            ...(field === 'api_key' ? { api_key_touched: true } : {}),
          },
        },
      });
      return;
    }
    setProviderDrafts((prev) => ({
      ...prev,
      [name]: {
        ...(prev[name] || { ...providers[name], name }),
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
    const providerSource = editingAll && globalDraft ? globalDraft.providers : cloneProvidersToDrafts(providers);
    if (!name || providerSource[name]) {
      return;
    }
    const nextProvider: ProviderDraft = {
        api_key: '',
        api_key_meta: null,
        api_key_touched: true,
        base_url: '',
        timeout: 60,
        max_retries: 3,
        name,
      };
    if (editingAll && globalDraft) {
      setGlobalDraft({
        ...globalDraft,
        providers: {
          ...globalDraft.providers,
          [name]: nextProvider,
        },
      });
    } else {
      setProviders((prev) => ({
        ...prev,
        [name]: nextProvider,
      }));
    }
    setShowNewProvider(false);
    setNewProviderName('');
    setExpandedProviders((prev) => ({ ...prev, [name]: true }));
  };

  const removeProvider = (name: string) => {
    if (!confirm(`确定删除 provider "${name}" 吗？其下关联的 llm 也会一并删除。`)) {
      return;
    }

    const removedModels = groupedModels[name] || [];
    if (editingAll && globalDraft) {
      const nextProviders = { ...globalDraft.providers };
      delete nextProviders[name];
      const nextModels = { ...globalDraft.models };
      removedModels.forEach((modelName) => {
        delete nextModels[modelName];
      });
      setGlobalDraft({
        ...globalDraft,
        providers: nextProviders,
        models: nextModels,
        defaultModel: removedModels.includes(globalDraft.defaultModel) ? '' : globalDraft.defaultModel,
      });
    } else {
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
    }
    setExpandedProviders((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (!editingAll && removedModels.includes(defaultModel)) {
      setDefaultModel('');
    }
  };

  const updateModelField = (name: string, field: keyof ModelConfig, value: string | number) => {
    if (editingAll && globalDraft) {
      setGlobalDraft({
        ...globalDraft,
        models: {
          ...globalDraft.models,
          [name]: {
            ...globalDraft.models[name],
            [field]: value,
          },
        },
      });
      return;
    }
    setModelDrafts((prev) => ({
      ...prev,
      [name]: {
        ...(prev[name] || { ...models[name], name }),
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
    const modelSource = editingAll && globalDraft ? globalDraft.models : cloneModelsToDrafts(models);
    if (!nextName || modelSource[nextName]) {
      return;
    }
    const nextModel: ModelDraft = {
        provider: providerName,
        model_id: '',
        timeout: 60,
        max_tokens: 128000,
        max_output_tokens: 16384,
        name: nextName,
      };
    if (editingAll && globalDraft) {
      setGlobalDraft({
        ...globalDraft,
        models: {
          ...globalDraft.models,
          [nextName]: nextModel,
        },
      });
    } else {
      setModels((prev) => ({
        ...prev,
        [nextName]: nextModel,
      }));
    }
    setNewModelDrafts((prev) => ({ ...prev, [providerName]: '' }));
    setOpenNewModelForms((prev) => ({ ...prev, [providerName]: false }));
  };

  const removeModel = (name: string) => {
    if (!confirm(`确定删除 llm "${name}" 吗？`)) {
      return;
    }
    if (editingAll && globalDraft) {
      const nextModels = { ...globalDraft.models };
      delete nextModels[name];
      setGlobalDraft({
        ...globalDraft,
        models: nextModels,
        defaultModel: globalDraft.defaultModel === name ? '' : globalDraft.defaultModel,
      });
    } else {
      setModels((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
    if (!editingAll && defaultModel === name) {
      setDefaultModel('');
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      const sourceProviders = editingAll && globalDraft ? globalDraft.providers : cloneProvidersToDrafts(providers);
      const sourceModels = editingAll && globalDraft ? globalDraft.models : cloneModelsToDrafts(models);
      const llm = {
        providers: buildProviderPayloadsFromDrafts(sourceProviders),
        models: buildModelPayloadsFromDrafts(sourceModels),
        default_model: editingAll && globalDraft ? globalDraft.defaultModel : defaultModel,
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
      loadConfig();
    } catch {
      setSaveMsg('保存失败');
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(''), 3000);
    }
  };

  const revealSecret = async (path: string) => {
    const res = await authFetch(`${API_BASE}/api/config/secret?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '读取 secret 失败');
    }
    return res.json() as Promise<{ path: string; value: string }>;
  };

  const toggleProviderApiKey = async (providerName: string) => {
    if (apiKeyVisibility[providerName]) {
      setApiKeyVisibility((prev) => ({ ...prev, [providerName]: false }));
      return;
    }

    const provider = providers[providerName];
    const needReveal = provider?.api_key_meta?.configured && !provider.api_key && !provider.api_key_touched;
    if (!needReveal) {
      setApiKeyVisibility((prev) => ({ ...prev, [providerName]: true }));
      return;
    }

    try {
      setApiKeyLoading((prev) => ({ ...prev, [providerName]: true }));
      const secret = await revealSecret(`llm.providers.${providerName}.api_key`);
      if (editingAll && globalDraft) {
        setGlobalDraft({
          ...globalDraft,
          providers: {
            ...globalDraft.providers,
            [providerName]: {
              ...globalDraft.providers[providerName],
              api_key: secret.value || '',
              api_key_touched: false,
            },
          },
        });
      } else if (editingProvider === providerName) {
        setProviderDrafts((prev) => ({
          ...prev,
          [providerName]: {
            ...(prev[providerName] || { ...providers[providerName], name: providerName }),
            api_key: secret.value || '',
            api_key_touched: false,
          },
        }));
      } else {
        setProviders((prev) => ({
          ...prev,
          [providerName]: {
            ...prev[providerName],
            api_key: secret.value || '',
            api_key_touched: false,
          },
        }));
      }
      setApiKeyVisibility((prev) => ({ ...prev, [providerName]: true }));
    } catch (error) {
      setSaveMsg(error instanceof Error ? error.message : '读取 secret 失败');
    } finally {
      setApiKeyLoading((prev) => ({ ...prev, [providerName]: false }));
    }
  };

  const providerApiKeyValue = (providerName: string) => {
    const provider = providers[providerName];
    const currentProvider = editingAll && globalDraft ? globalDraft.providers[providerName] : editingProvider === providerName ? getProviderDraft(providerName) : provider;
    if (!currentProvider) {
      return '';
    }
    if (currentProvider.api_key_touched) {
      return currentProvider.api_key;
    }
    if (apiKeyVisibility[providerName]) {
      return currentProvider.api_key;
    }
    if (currentProvider.api_key_meta?.configured) {
      return '******';
    }
    return currentProvider.api_key;
  };

  const startEditProvider = (name: string) => {
    setEditingModel(null);
    setEditingProvider(name);
    setProviderDrafts((prev) => ({
      ...prev,
      [name]: { ...providers[name], name },
    }));
  };

  const cancelEditProvider = (name: string) => {
    setEditingProvider((prev) => (prev === name ? null : prev));
    setProviderDrafts((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const saveProvider = async (name: string) => {
    const draft = getProviderDraft(name);
    setSaveMsg('');
    const payload: Record<string, unknown> = {
      name: draft.name,
      base_url: draft.base_url,
      timeout: draft.timeout,
      max_retries: draft.max_retries,
    };
    if (draft.api_key_touched) {
      payload.api_key = draft.api_key;
    }
    const res = await authFetch(`${API_BASE}/api/config/llm/providers/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setSaveMsg(err.detail || '保存失败');
      return;
    }
    setSaveMsg('已保存');
    loadConfig();
  };

  const startEditModel = (name: string) => {
    setEditingProvider(null);
    setEditingModel(name);
    setModelDrafts((prev) => ({
      ...prev,
      [name]: { ...models[name], name },
    }));
  };

  const cancelEditModel = (name: string) => {
    setEditingModel((prev) => (prev === name ? null : prev));
    setModelDrafts((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const saveModel = async (name: string) => {
    const draft = getModelDraft(name);
    setSaveMsg('');
    const res = await authFetch(`${API_BASE}/api/config/llm/models/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: draft.name,
        provider: draft.provider,
        model_id: draft.model_id,
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setSaveMsg(err.detail || '保存失败');
      return;
    }
    setSaveMsg('已保存');
    loadConfig();
  };

  const startEditAll = () => {
    setEditingProvider(null);
    setEditingModel(null);
    setEditingAll(true);
    setGlobalDraft({
      providers: cloneProvidersToDrafts(providers),
      models: cloneModelsToDrafts(models),
      defaultModel,
    });
  };

  const cancelEditAll = () => {
    setEditingAll(false);
    setGlobalDraft(null);
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
            {editingAll ? (
              <>
                <button
                  type="button"
                  data-testid="cancel-edit-all-llm-config"
                  onClick={cancelEditAll}
                  className="rounded-xl border border-border px-4 py-2.5 text-sm font-bold text-foreground transition-all hover:bg-muted/40"
                >
                  取消编辑所有
                </button>
                <button
                  type="button"
                  data-testid="save-all-llm-config"
                  onClick={saveConfig}
                  disabled={saving}
                  className="flex items-center gap-2.5 rounded-xl bg-primary px-6 py-2.5 font-bold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 disabled:opacity-50"
                >
                  {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                  保存所有
                </button>
              </>
            ) : (
              <button
                type="button"
                data-testid="edit-all-llm-config"
                onClick={startEditAll}
                disabled={Boolean(editingProvider || editingModel)}
                className="rounded-xl bg-primary px-6 py-2.5 text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 disabled:opacity-50"
              >
                编辑所有配置
              </button>
            )}
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
                value={editingAll && globalDraft ? globalDraft.defaultModel : defaultModel}
                onChange={(e) => {
                  if (!editingAll || !globalDraft) return;
                  setGlobalDraft({ ...globalDraft, defaultModel: e.target.value });
                }}
                disabled={!editingAll}
                className="w-full cursor-pointer rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
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
                  {editingAll ? null : editingProvider === providerName ? (
                    <>
                      <button
                        type="button"
                        data-testid={`provider-cancel-${providerName}`}
                        onClick={() => cancelEditProvider(providerName)}
                        className="rounded-xl border border-border px-3 py-2 text-sm font-bold text-foreground transition-all hover:bg-muted/40"
                      >
                        取消编辑
                      </button>
                      <button
                        type="button"
                        data-testid={`provider-save-${providerName}`}
                        onClick={() => void saveProvider(providerName)}
                        className="rounded-xl bg-primary px-3 py-2 text-sm font-bold text-primary-foreground transition-all hover:bg-primary/90"
                      >
                        保存
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      data-testid={`provider-edit-${providerName}`}
                      onClick={() => startEditProvider(providerName)}
                      disabled={Boolean(editingModel)}
                      className="rounded-xl border border-border px-3 py-2 text-sm font-bold text-foreground transition-all hover:bg-muted/40 disabled:opacity-50"
                    >
                      编辑
                    </button>
                  )}
                </div>

                {expandedProviders[providerName] && (
                  <div data-testid={`provider-body-${providerName}`} className="space-y-6 p-6">
                    <div className="grid gap-4 md:grid-cols-2">
                      <FieldInput
                        label="Provider 名称"
                        value={getProviderDraft(providerName).name}
                        dataTestId={`provider-name-input-${providerName}`}
                        disabled={!isProviderEditable(providerName)}
                        onChange={(value) => {
                          if (editingAll && globalDraft) {
                            setGlobalDraft({
                              ...globalDraft,
                              providers: {
                                ...globalDraft.providers,
                                [providerName]: { ...globalDraft.providers[providerName], name: value },
                              },
                            });
                            return;
                          }
                          setProviderDrafts((prev) => ({
                            ...prev,
                            [providerName]: { ...(prev[providerName] || { ...providers[providerName], name: providerName }), name: value },
                          }));
                        }}
                      />
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-muted-foreground">API Key</label>
                        <div className="flex gap-2">
                          <input
                            type={apiKeyVisibility[providerName] ? 'text' : 'password'}
                            value={providerApiKeyValue(providerName)}
                            data-testid={`provider-api-key-input-${providerName}`}
                            onChange={(e) => updateProviderField(providerName, 'api_key', e.target.value)}
                            disabled={!isProviderEditable(providerName)}
                            className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                          />
                          <button
                            type="button"
                            data-testid={`provider-api-key-toggle-${providerName}`}
                            onClick={() => void toggleProviderApiKey(providerName)}
                            className="flex h-10 w-10 items-center justify-center rounded-xl border border-input bg-background text-muted-foreground transition-colors hover:text-foreground"
                          >
                            {apiKeyLoading[providerName] ? (
                              <Loader2 size={16} className="animate-spin" />
                            ) : apiKeyVisibility[providerName] ? (
                              <EyeOff size={16} />
                            ) : (
                              <Eye size={16} />
                            )}
                          </button>
                        </div>
                      </div>
                      <FieldInput
                        label="Base URL"
                        value={getProviderDraft(providerName).base_url || ''}
                        dataTestId={`provider-base-url-input-${providerName}`}
                        disabled={!isProviderEditable(providerName)}
                        onChange={(value) => updateProviderField(providerName, 'base_url', value)}
                      />
                      <FieldInput
                        label="Timeout (s)"
                        type="number"
                        value={String(getProviderDraft(providerName).timeout || 60)}
                        dataTestId={`provider-timeout-input-${providerName}`}
                        disabled={!isProviderEditable(providerName)}
                        onChange={(value) => updateProviderField(providerName, 'timeout', parseInt(value, 10) || 60)}
                      />
                      <FieldInput
                        label="Max Retries"
                        type="number"
                        value={String(getProviderDraft(providerName).max_retries || 3)}
                        dataTestId={`provider-max-retries-input-${providerName}`}
                        disabled={!isProviderEditable(providerName)}
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
                                value={getModelDraft(modelName).name}
                                dataTestId={`llm-name-input-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                onChange={(value) => {
                                  if (editingAll && globalDraft) {
                                    setGlobalDraft({
                                      ...globalDraft,
                                      models: {
                                        ...globalDraft.models,
                                        [modelName]: { ...globalDraft.models[modelName], name: value },
                                      },
                                    });
                                    return;
                                  }
                                  setModelDrafts((prev) => ({
                                    ...prev,
                                    [modelName]: { ...(prev[modelName] || { ...models[modelName], name: modelName }), name: value },
                                  }));
                                }}
                              />
                              <FieldInput
                                label="Model ID"
                                value={getModelDraft(modelName).model_id || ''}
                                dataTestId={`llm-model-id-input-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                onChange={(value) => updateModelField(modelName, 'model_id', value)}
                              />
                              <FieldInput
                                label="Timeout (s)"
                                type="number"
                                value={String(getModelDraft(modelName).timeout || 60)}
                                dataTestId={`llm-timeout-input-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                onChange={(value) => updateModelField(modelName, 'timeout', parseInt(value, 10) || 60)}
                              />
                              <FieldInput
                                label="Max Tokens"
                                type="number"
                                value={String(getModelDraft(modelName).max_tokens || 128000)}
                                dataTestId={`llm-max-tokens-input-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                onChange={(value) => updateModelField(modelName, 'max_tokens', parseInt(value, 10) || 128000)}
                              />
                              <FieldInput
                                label="Max Output Tokens"
                                type="number"
                                value={String(getModelDraft(modelName).max_output_tokens || 16384)}
                                dataTestId={`llm-max-output-tokens-input-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                onChange={(value) => updateModelField(modelName, 'max_output_tokens', parseInt(value, 10) || 16384)}
                              />
                            </div>
                            <div className="flex items-start justify-end md:justify-center">
                              {editingAll ? null : editingModel === modelName ? (
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    data-testid={`llm-cancel-${modelName}`}
                                    onClick={() => cancelEditModel(modelName)}
                                    className="rounded-xl border border-border px-3 py-2 text-sm font-bold text-foreground transition-all hover:bg-muted/40"
                                  >
                                    取消编辑
                                  </button>
                                  <button
                                    type="button"
                                    data-testid={`llm-save-${modelName}`}
                                    onClick={() => void saveModel(modelName)}
                                    className="rounded-xl bg-primary px-3 py-2 text-sm font-bold text-primary-foreground transition-all hover:bg-primary/90"
                                  >
                                    保存
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  data-testid={`llm-edit-${modelName}`}
                                  onClick={() => startEditModel(modelName)}
                                  disabled={Boolean(editingProvider)}
                                  className="rounded-xl border border-border px-3 py-2 text-sm font-bold text-foreground transition-all hover:bg-muted/40 disabled:opacity-50"
                                >
                                  编辑
                                </button>
                              )}
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
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  dataTestId?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground">{label}</label>
      <input
        type={type}
        value={value}
        data-testid={dataTestId}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
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
          max_tokens: Number(model.max_tokens || 128000),
          max_output_tokens: Number(model.max_output_tokens || 16384),
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

function buildProviderPayloadsFromDrafts(providers: Record<string, ProviderDraft>): Record<string, Record<string, unknown>> {
  return buildProviderPayloads(
    Object.fromEntries(
      Object.entries(providers).map(([_, draft]) => [
        draft.name,
        {
          api_key: draft.api_key,
          api_key_meta: draft.api_key_meta,
          api_key_touched: draft.api_key_touched,
          base_url: draft.base_url,
          timeout: draft.timeout,
          max_retries: draft.max_retries,
        },
      ]),
    ),
  );
}

function buildModelPayloadsFromDrafts(models: Record<string, ModelDraft>): Record<string, ModelConfig> {
  return Object.fromEntries(
    Object.entries(models).map(([_, draft]) => [
      draft.name,
      {
        provider: draft.provider,
        model_id: draft.model_id,
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
      },
    ]),
  );
}
