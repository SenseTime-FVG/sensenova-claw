'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckCircle, ChevronDown, ChevronRight, Cpu, Eye, EyeOff, Loader2, Plus, RefreshCw, Save, Server, Trash2, X, XCircle, Zap } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface SecretValueStatus {
  configured: boolean;
  masked_value?: string | null;
  length?: number;
  source: string;
}

interface ProviderConfig {
  source_type: string;
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
  type?: string;  // "chat" | "embedding"
  timeout: number;
  max_tokens: number;
  max_output_tokens: number;
  dimensions?: number;  // embedding 模型向量维度
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
  defaultEmbeddingModel: string;
}

interface LlmMeta {
  explicit_provider_names?: string[];
}

interface ModelTestResult {
  success: boolean;
  message: string;
  detail?: string;
}

interface BulkModelTestState extends ModelTestResult {
  status: 'pending' | 'success' | 'failed';
}

const MAX_BULK_TEST_CONCURRENCY = 10;
const TEST_TOOLTIP_DELAY_MS = 1000;
const TEST_TOOLTIP_MESSAGE = '连接测试会消耗少量token';

const PROVIDER_SOURCE_TYPE_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'qwen', label: 'Qwen' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'glm', label: 'GLM' },
  { value: 'kimi', label: 'Kimi' },
  { value: 'step', label: 'Step' },
  { value: 'openai-compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic-compatible', label: 'Anthropic Compatible' },
  { value: 'gemini-compatible', label: 'Gemini Compatible' },
] as const;

function isSecretRefLike(value: string | null | undefined): boolean {
  return typeof value === 'string' && value.startsWith('${secret:') && value.endsWith('}');
}

export default function LlmsPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [lastLoadedSnapshot, setLastLoadedSnapshot] = useState('');

  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [models, setModels] = useState<Record<string, ModelConfig>>({});
  const [defaultModel, setDefaultModel] = useState('');
  const [defaultEmbeddingModel, setDefaultEmbeddingModel] = useState('');

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
  const [editingDefaultModel, setEditingDefaultModel] = useState(false);
  const [editingDefaultEmbeddingModel, setEditingDefaultEmbeddingModel] = useState(false);
  const [providerDrafts, setProviderDrafts] = useState<Record<string, ProviderDraft>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, ModelDraft>>({});
  const [globalDraft, setGlobalDraft] = useState<GlobalDraft | null>(null);
  const [defaultModelDraft, setDefaultModelDraft] = useState('');
  const [defaultEmbeddingModelDraft, setDefaultEmbeddingModelDraft] = useState('');
  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ModelTestResult>>({});
  const [openTestErrorModel, setOpenTestErrorModel] = useState<string | null>(null);
  const [bulkTesting, setBulkTesting] = useState(false);
  const [bulkTestDialogOpen, setBulkTestDialogOpen] = useState(false);
  const [bulkTestResults, setBulkTestResults] = useState<Record<string, BulkModelTestState>>({});
  const [openBulkTestErrorModel, setOpenBulkTestErrorModel] = useState<string | null>(null);
  const [hasBulkTestResults, setHasBulkTestResults] = useState(false);
  const [hoveredTestModel, setHoveredTestModel] = useState<string | null>(null);
  const [visibleTestTooltipModel, setVisibleTestTooltipModel] = useState<string | null>(null);
  const [hoveringBulkTestButton, setHoveringBulkTestButton] = useState(false);
  const [showBulkTestTooltip, setShowBulkTestTooltip] = useState(false);

  const loadConfig = async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setRefreshing(true);
    }

    try {
      const res = await authFetch(`${API_BASE}/api/config/sections`);
      const data = await res.json();
        const llm = data?.llm || {};
        const normalizedProviders = normalizeProviders(llm.providers || {});
        const explicitProviderNames = normalizeExplicitProviderNames(llm._meta);
        const { mock, ...realProviders } = normalizedProviders;
        const visibleProviders = explicitProviderNames.length > 0
          ? Object.fromEntries(
            Object.entries(realProviders).filter(([name]) => explicitProviderNames.includes(name)),
          )
          : {};
        const rawModels = normalizeModels(llm.models || {});
        const { mock: _mockModel, ...realModels } = rawModels;
        const visibleModels = Object.fromEntries(
          Object.entries(realModels).filter(([, model]) => model.provider in visibleProviders),
        );
        const nextDefaultModel = llm.default_model && llm.default_model in visibleModels ? llm.default_model : '';
        const nextDefaultEmbeddingModel = llm.default_embedding_model && llm.default_embedding_model in visibleModels ? llm.default_embedding_model : '';
        setProviders(visibleProviders);
        setModels(visibleModels);
        setDefaultModel(nextDefaultModel);
        setDefaultEmbeddingModel(nextDefaultEmbeddingModel);
        setLastLoadedSnapshot(createConfigSnapshot({
          providers: cloneProvidersToDrafts(visibleProviders),
          models: cloneModelsToDrafts(visibleModels),
          defaultModel: nextDefaultModel,
          defaultEmbeddingModel: nextDefaultEmbeddingModel,
        }));
        setExpandedProviders(
          Object.fromEntries(Object.keys(visibleProviders).map((name) => [name, false])),
        );
        setEditingAll(false);
        setEditingProvider(null);
        setEditingModel(null);
        setEditingDefaultModel(false);
        setEditingDefaultEmbeddingModel(false);
        setProviderDrafts({});
        setModelDrafts({});
        setGlobalDraft(null);
        setDefaultModelDraft('');
        setDefaultEmbeddingModelDraft('');
        setOpenTestErrorModel(null);
        setBulkTesting(false);
        setBulkTestDialogOpen(false);
        setBulkTestResults({});
        setOpenBulkTestErrorModel(null);
        setHasBulkTestResults(false);
    } catch {
      setSaveMsg('读取配置失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadConfig({ silent: true });
  }, []);

  useEffect(() => {
    if (!openTestErrorModel) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        setOpenTestErrorModel(null);
        return;
      }
      if (target.closest('[data-llm-test-error-scope="true"]')) {
        return;
      }
      setOpenTestErrorModel(null);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [openTestErrorModel]);

  useEffect(() => {
    if (!hoveredTestModel) {
      setVisibleTestTooltipModel(null);
      return;
    }

    const timer = window.setTimeout(() => {
      setVisibleTestTooltipModel(hoveredTestModel);
    }, TEST_TOOLTIP_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [hoveredTestModel]);

  useEffect(() => {
    if (!hoveringBulkTestButton) {
      setShowBulkTestTooltip(false);
      return;
    }

    const timer = window.setTimeout(() => {
      setShowBulkTestTooltip(true);
    }, TEST_TOOLTIP_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [hoveringBulkTestButton]);

  const activeProviders = useMemo(() => {
    if (!editingAll || !globalDraft) return providers;
    return Object.fromEntries(Object.entries(globalDraft.providers).map(([key, draft]) => [
      key,
      {
        source_type: draft.source_type,
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
        type: draft.type,
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
        dimensions: draft.dimensions,
      },
    ]));
  }, [editingAll, globalDraft, models]);

  const providerNames = useMemo(() => Object.keys(activeProviders), [activeProviders]);
  const modelNames = useMemo(() => Object.keys(activeModels), [activeModels]);
  const chatModelNames = useMemo(() => modelNames.filter((name) => (activeModels[name]?.type || 'chat') === 'chat'), [activeModels, modelNames]);
  const embeddingModelNames = useMemo(() => modelNames.filter((name) => activeModels[name]?.type === 'embedding'), [activeModels, modelNames]);

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

  const currentSnapshot = useMemo(() => {
    if (editingAll && globalDraft) {
      return createConfigSnapshot({
        providers: globalDraft.providers,
        models: globalDraft.models,
        defaultModel: globalDraft.defaultModel,
        defaultEmbeddingModel: globalDraft.defaultEmbeddingModel,
      });
    }

    const currentProviderState = cloneProvidersToDrafts(providers);
    if (editingProvider && providerDrafts[editingProvider]) {
      const draft = providerDrafts[editingProvider];
      delete currentProviderState[editingProvider];
      currentProviderState[draft.name] = draft;
    }

    const currentModelState = cloneModelsToDrafts(models);
    if (editingModel && modelDrafts[editingModel]) {
      const draft = modelDrafts[editingModel];
      delete currentModelState[editingModel];
      currentModelState[draft.name] = draft;
    }

    return createConfigSnapshot({
      providers: currentProviderState,
      models: currentModelState,
      defaultModel: editingDefaultModel ? defaultModelDraft : defaultModel,
      defaultEmbeddingModel: editingDefaultEmbeddingModel ? defaultEmbeddingModelDraft : defaultEmbeddingModel,
    });
  }, [
    defaultEmbeddingModel,
    defaultEmbeddingModelDraft,
    defaultModel,
    defaultModelDraft,
    editingAll,
    editingDefaultEmbeddingModel,
    editingDefaultModel,
    editingModel,
    editingProvider,
    globalDraft,
    modelDrafts,
    models,
    providerDrafts,
    providers,
  ]);

  const hasUnsavedChanges = Boolean(lastLoadedSnapshot) && currentSnapshot !== lastLoadedSnapshot;

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
        source_type: 'openai',
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
        defaultEmbeddingModel: removedModels.includes(globalDraft.defaultEmbeddingModel) ? '' : globalDraft.defaultEmbeddingModel,
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
    if (!nextName) {
      setSaveMsg('LLM 名称不能为空');
      return;
    }
    if (modelSource[nextName]) {
      setSaveMsg(`LLM 名称已存在: ${nextName}`);
      return;
    }
    const nextModel: ModelDraft = {
        provider: providerName,
        model_id: '',
        type: 'chat',
        timeout: 60,
        max_tokens: 128000,
        max_output_tokens: 16384,
        dimensions: undefined,
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
      setEditingProvider(null);
      setEditingDefaultModel(false);
      setEditingModel(nextName);
      setModelDrafts((prev) => ({
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
        defaultEmbeddingModel: globalDraft.defaultEmbeddingModel === name ? '' : globalDraft.defaultEmbeddingModel,
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
    if (!editingAll && defaultEmbeddingModel === name) {
      setDefaultEmbeddingModel('');
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
        default_embedding_model: editingAll && globalDraft ? globalDraft.defaultEmbeddingModel : defaultEmbeddingModel,
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
    const payload = await res.json() as { path: string; value: string };
    if (isSecretRefLike(payload.value)) {
      throw new Error('Secret store 中保存的是占位符，请重新填写真实 API Key');
    }
    return payload;
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
      const len = currentProvider.api_key_meta.length || 6;
      return '*'.repeat(len);
    }
    return currentProvider.api_key;
  };

  const getResolvedModelForTesting = (modelName: string): {
    model: ModelConfig | ModelDraft;
    providerName: string;
    provider: ProviderConfig | ProviderDraft;
  } | null => {
    const model = editingAll && globalDraft
      ? activeModels[modelName]
      : editingModel === modelName
        ? getModelDraft(modelName)
        : activeModels[modelName];
    if (!model) return null;

    const providerName = model.provider;
    const provider = editingAll && globalDraft
      ? activeProviders[providerName]
      : editingProvider === providerName
        ? getProviderDraft(providerName)
        : activeProviders[providerName];
    if (!provider) return null;

    return { model, providerName, provider };
  };

  const resolveProviderApiKey = async (
    providerName: string,
    provider: ProviderConfig | ProviderDraft,
    apiKeyCache?: Map<string, string>,
  ) => {
    const cachedApiKey = apiKeyCache?.get(providerName);
    if (cachedApiKey) {
      return cachedApiKey;
    }

    let apiKey = provider.api_key;
    if (!apiKey && provider.api_key_meta?.configured) {
      const secret = await revealSecret(`llm.providers.${providerName}.api_key`);
      apiKey = secret.value || '';
    }
    if (apiKeyCache && apiKey) {
      apiKeyCache.set(providerName, apiKey);
    }
    return apiKey;
  };

  const runModelConnectivityTest = async (
    modelName: string,
    apiKeyCache?: Map<string, string>,
  ): Promise<ModelTestResult> => {
    const target = getResolvedModelForTesting(modelName);
    if (!target) {
      return { success: false, message: '连接失败', detail: '未找到对应的 llm 或 provider 配置' };
    }

    const { model, providerName, provider } = target;

    try {
      const apiKey = await resolveProviderApiKey(providerName, provider, apiKeyCache);
      if (isSecretRefLike(apiKey)) {
        return {
          success: false,
          message: '连接失败',
          detail: 'Secret store 中保存的是占位符，请重新填写真实 API Key',
        };
      }
      if (!apiKey) {
        return { success: false, message: '连接失败', detail: '未配置 API Key' };
      }

      const res = await authFetch(`${API_BASE}/api/config/test-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: provider.source_type || 'openai',
          api_key: apiKey,
          base_url: provider.base_url || '',
          model_id: model.model_id ?? '',
          max_tokens: model.max_tokens || 128000,
          max_output_tokens: model.max_output_tokens || 16384,
        }),
      });
      const data = await res.json();
      if (data.success) {
        return { success: true, message: data.message || '连接成功' };
      }

      const detail = typeof data.error === 'string' && data.error.trim() ? data.error : '测试失败';
      return { success: false, message: '连接失败', detail };
    } catch (error) {
      return {
        success: false,
        message: '连接失败',
        detail: error instanceof Error ? error.message : '测试失败',
      };
    }
  };

  const startEditProvider = (name: string) => {
    setEditingModel(null);
    setEditingDefaultModel(false);
    setDefaultModelDraft('');
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
      source_type: draft.source_type,
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
    setEditingDefaultModel(false);
    setDefaultModelDraft('');
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
        type: draft.type || 'chat',
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
        ...(draft.dimensions ? { dimensions: draft.dimensions } : {}),
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

  const startEditDefaultModel = () => {
    setEditingProvider(null);
    setEditingModel(null);
    setEditingDefaultEmbeddingModel(false);
    setEditingDefaultModel(true);
    setDefaultModelDraft(defaultModel);
  };

  const cancelEditDefaultModel = () => {
    setEditingDefaultModel(false);
    setDefaultModelDraft('');
  };

  const saveDefaultModel = async () => {
    setSaveMsg('');
    const res = await authFetch(`${API_BASE}/api/config/llm/default-model`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        default_model: defaultModelDraft,
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

  const startEditDefaultEmbeddingModel = () => {
    setEditingProvider(null);
    setEditingModel(null);
    setEditingDefaultModel(false);
    setEditingDefaultEmbeddingModel(true);
    setDefaultEmbeddingModelDraft(defaultEmbeddingModel);
  };

  const cancelEditDefaultEmbeddingModel = () => {
    setEditingDefaultEmbeddingModel(false);
    setDefaultEmbeddingModelDraft('');
  };

  const saveDefaultEmbeddingModel = async () => {
    setSaveMsg('');
    const res = await authFetch(`${API_BASE}/api/config/llm/default-embedding-model`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        default_embedding_model: defaultEmbeddingModelDraft,
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

  const testModel = async (modelName: string) => {
    if (!getResolvedModelForTesting(modelName)) return;
    setTestingModel(modelName);
    setOpenTestErrorModel(null);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[modelName];
      return next;
    });

    try {
      const result = await runModelConnectivityTest(modelName);
      setTestResults((prev) => ({ ...prev, [modelName]: result }));
    } finally {
      setTestingModel(null);
    }
  };

  const testAllModels = async () => {
    const allModelNames = providerNames.flatMap((providerName) => groupedModels[providerName] || []);
    if (allModelNames.length === 0) {
      setBulkTestResults({});
      setHasBulkTestResults(true);
      setBulkTestDialogOpen(true);
      return;
    }

    const initialResults = Object.fromEntries(
      allModelNames.map((modelName) => [
        modelName,
        {
          status: 'pending' as const,
          success: false,
          message: '连接中',
        },
      ]),
    );

    setBulkTesting(true);
    setHasBulkTestResults(true);
    setBulkTestDialogOpen(true);
    setOpenBulkTestErrorModel(null);
    setBulkTestResults(initialResults);

    const apiKeyCache = new Map<string, string>();
    let cursor = 0;
    const workerCount = Math.min(MAX_BULK_TEST_CONCURRENCY, allModelNames.length);

    try {
      await Promise.all(Array.from({ length: workerCount }, async () => {
        while (true) {
          const currentIndex = cursor;
          cursor += 1;
          if (currentIndex >= allModelNames.length) {
            return;
          }

          const modelName = allModelNames[currentIndex];
          const result = await runModelConnectivityTest(modelName, apiKeyCache);
          setBulkTestResults((prev) => ({
            ...prev,
            [modelName]: {
              ...result,
              status: result.success ? 'success' : 'failed',
            },
          }));
        }
      }));
    } finally {
      setBulkTesting(false);
    }
  };

  const startEditAll = () => {
    setEditingProvider(null);
    setEditingModel(null);
    setEditingDefaultModel(false);
    setEditingAll(true);
    setGlobalDraft({
      providers: cloneProvidersToDrafts(providers),
      models: cloneModelsToDrafts(models),
      defaultModel,
      defaultEmbeddingModel,
    });
  };

  const cancelEditAll = () => {
    setEditingAll(false);
    setGlobalDraft(null);
    setDefaultModelDraft('');
    setDefaultEmbeddingModelDraft('');
  };

  const refreshConfig = async () => {
    if (hasUnsavedChanges) {
      const confirmed = window.confirm('当前有未保存修改，刷新将丢弃这些更改。是否继续刷新？');
      if (!confirmed) {
        return;
      }
    }
    setSaveMsg('');
    await loadConfig();
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
              data-testid="refresh-llm-config"
              onClick={() => void refreshConfig()}
              disabled={loading || refreshing || saving}
              className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-bold text-foreground transition-all hover:bg-muted/40 disabled:opacity-50"
            >
              {refreshing ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
              刷新
            </button>
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
                disabled={Boolean(editingProvider || editingModel || editingDefaultModel || editingDefaultEmbeddingModel)}
                className="rounded-xl bg-primary px-6 py-2.5 text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 disabled:opacity-50"
              >
                编辑所有配置
              </button>
            )}
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <SummaryCard title="Providers" value={providerNames.length} desc="已配置 provider 数量" icon={<Server className="h-5 w-5 text-primary" />} />
          <SummaryCard title="LLMs" value={modelNames.length} desc="已配置 llm 数量" icon={<Cpu className="h-5 w-5 text-primary" />} />
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Default Model</CardTitle>
              {editingAll ? (
                <Save className="h-5 w-5 text-primary" />
              ) : editingDefaultModel ? (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="default-model-cancel"
                    onClick={cancelEditDefaultModel}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold text-foreground transition-all hover:bg-muted/40"
                  >
                    取消编辑
                  </button>
                  <button
                    type="button"
                    data-testid="default-model-save"
                    onClick={saveDefaultModel}
                    className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground transition-all hover:bg-primary/90"
                  >
                    保存
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  data-testid="default-model-edit"
                  onClick={startEditDefaultModel}
                  disabled={Boolean(editingProvider || editingModel || editingDefaultEmbeddingModel)}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold text-foreground transition-all hover:bg-muted/40 disabled:opacity-50"
                >
                  编辑
                </button>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <select
                data-testid="default-model-select"
                value={editingAll && globalDraft ? globalDraft.defaultModel : editingDefaultModel ? defaultModelDraft : defaultModel}
                onChange={(e) => {
                  if (editingAll && globalDraft) {
                    setGlobalDraft({ ...globalDraft, defaultModel: e.target.value });
                    return;
                  }
                  if (editingDefaultModel) {
                    setDefaultModelDraft(e.target.value);
                  }
                }}
                disabled={!editingAll && !editingDefaultModel}
                className="w-full cursor-pointer rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">未设置</option>
                {chatModelNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <p className="text-sm text-muted-foreground">默认模型用于 agent 未显式指定 model 的场景。</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Default Embedding</CardTitle>
              {editingAll ? (
                <Save className="h-5 w-5 text-primary" />
              ) : editingDefaultEmbeddingModel ? (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="default-embedding-model-cancel"
                    onClick={cancelEditDefaultEmbeddingModel}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold text-foreground transition-all hover:bg-muted/40"
                  >
                    取消编辑
                  </button>
                  <button
                    type="button"
                    data-testid="default-embedding-model-save"
                    onClick={saveDefaultEmbeddingModel}
                    className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground transition-all hover:bg-primary/90"
                  >
                    保存
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  data-testid="default-embedding-model-edit"
                  onClick={startEditDefaultEmbeddingModel}
                  disabled={Boolean(editingProvider || editingModel || editingDefaultModel)}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold text-foreground transition-all hover:bg-muted/40 disabled:opacity-50"
                >
                  编辑
                </button>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <select
                data-testid="default-embedding-model-select"
                value={editingAll && globalDraft ? globalDraft.defaultEmbeddingModel : editingDefaultEmbeddingModel ? defaultEmbeddingModelDraft : defaultEmbeddingModel}
                onChange={(e) => {
                  if (editingAll && globalDraft) {
                    setGlobalDraft({ ...globalDraft, defaultEmbeddingModel: e.target.value });
                    return;
                  }
                  if (editingDefaultEmbeddingModel) {
                    setDefaultEmbeddingModelDraft(e.target.value);
                  }
                }}
                disabled={!editingAll && !editingDefaultEmbeddingModel}
                className="w-full cursor-pointer rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">未设置</option>
                {embeddingModelNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <p className="text-sm text-muted-foreground">默认 embedding 模型用于记忆搜索的向量化。</p>
            </CardContent>
          </Card>
        </div>

        <Card className="overflow-hidden border-border/80 shadow-xl">
          <CardHeader className="border-b bg-muted/30 p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-2xl font-bold">Provider 列表</CardTitle>
                <CardDescription className="mt-2 text-base">每个 provider 下直接管理关联的 llm 配置。</CardDescription>
              </div>
              {hasBulkTestResults ? (
                <div className="flex flex-col items-stretch gap-2">
                  <div className="relative">
                    <button
                      type="button"
                      data-testid="retest-all-llms"
                      onClick={() => void testAllModels()}
                      onMouseEnter={() => setHoveringBulkTestButton(true)}
                      onMouseLeave={() => {
                        setHoveringBulkTestButton(false);
                        setShowBulkTestTooltip(false);
                      }}
                      onFocus={() => setHoveringBulkTestButton(true)}
                      onBlur={() => {
                        setHoveringBulkTestButton(false);
                        setShowBulkTestTooltip(false);
                      }}
                      disabled={bulkTesting || Boolean(editingProvider || editingModel || editingDefaultModel)}
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-amber-500/30 px-4 py-2 text-sm font-bold text-amber-600 transition-all hover:bg-amber-500/10 disabled:opacity-50 dark:text-amber-400"
                    >
                      {bulkTesting ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                      {bulkTesting ? '测试中...' : '重新测试全部'}
                    </button>
                    {showBulkTestTooltip ? (
                      <div
                        data-testid="bulk-llm-test-tooltip"
                        className="absolute bottom-full right-0 z-20 mb-2 whitespace-nowrap rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground shadow-lg"
                      >
                        {TEST_TOOLTIP_MESSAGE}
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    data-testid="show-all-llms-test-results"
                    onClick={() => setBulkTestDialogOpen(true)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2 text-sm font-bold text-foreground transition-all hover:bg-muted/40"
                  >
                    测试结果
                  </button>
                </div>
              ) : (
                <div className="relative">
                  <button
                    type="button"
                    data-testid="test-all-llms"
                    onClick={() => void testAllModels()}
                    onMouseEnter={() => setHoveringBulkTestButton(true)}
                    onMouseLeave={() => {
                      setHoveringBulkTestButton(false);
                      setShowBulkTestTooltip(false);
                    }}
                    onFocus={() => setHoveringBulkTestButton(true)}
                    onBlur={() => {
                      setHoveringBulkTestButton(false);
                      setShowBulkTestTooltip(false);
                    }}
                    disabled={bulkTesting || Boolean(editingProvider || editingModel || editingDefaultModel)}
                    className="inline-flex items-center gap-2 rounded-xl border border-amber-500/30 px-4 py-2 text-sm font-bold text-amber-600 transition-all hover:bg-amber-500/10 disabled:opacity-50 dark:text-amber-400"
                  >
                    {bulkTesting ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                    {bulkTesting ? '测试中...' : '测试全部'}
                  </button>
                  {showBulkTestTooltip ? (
                    <div
                      data-testid="bulk-llm-test-tooltip"
                      className="absolute bottom-full right-0 z-20 mb-2 whitespace-nowrap rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground shadow-lg"
                    >
                      {TEST_TOOLTIP_MESSAGE}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
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
                        <span className="rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 text-[11px] font-semibold text-primary">
                          {providers[providerName]?.source_type || 'openai'}
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
                      disabled={Boolean(editingModel || editingDefaultModel)}
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
                      <FieldSelect
                        label="Provider 来源"
                        value={getProviderDraft(providerName).source_type || 'openai'}
                        dataTestId={`provider-source-type-select-${providerName}`}
                        disabled={!isProviderEditable(providerName)}
                        options={PROVIDER_SOURCE_TYPE_OPTIONS.map((option) => ({
                          value: option.value,
                          label: option.label,
                        }))}
                        onChange={(value) => updateProviderField(providerName, 'source_type', value)}
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
                            className="grid gap-4 rounded-2xl border border-border bg-background p-4 md:grid-cols-[minmax(0,1fr)_auto]"
                          >
                            <div className="grid min-w-0 gap-4 md:grid-cols-2">
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
                              <FieldSelect
                                label="类型"
                                value={getModelDraft(modelName).type || 'chat'}
                                dataTestId={`llm-type-select-${modelName}`}
                                disabled={!isModelEditable(modelName)}
                                options={[
                                  { value: 'chat', label: 'Chat' },
                                  { value: 'embedding', label: 'Embedding' },
                                ]}
                                onChange={(value) => updateModelField(modelName, 'type', value)}
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
                              {(getModelDraft(modelName).type || 'chat') === 'chat' && (
                                <>
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
                                </>
                              )}
                              {getModelDraft(modelName).type === 'embedding' && (
                                <FieldInput
                                  label="向量维度"
                                  type="number"
                                  value={String(getModelDraft(modelName).dimensions || '')}
                                  placeholder="如: 1536"
                                  dataTestId={`llm-dimensions-input-${modelName}`}
                                  disabled={!isModelEditable(modelName)}
                                  onChange={(value) => updateModelField(modelName, 'dimensions', value ? parseInt(value, 10) : 0)}
                                />
                              )}
                            </div>
                            <div className="flex min-w-0 flex-col items-end gap-2">
                              <div className="flex flex-wrap items-center justify-end gap-2">
                                {editingAll ? null : editingModel === modelName ? (
                                  <>
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
                                  </>
                                ) : (
                                    <button
                                      type="button"
                                      data-testid={`llm-edit-${modelName}`}
                                      onClick={() => startEditModel(modelName)}
                                      disabled={Boolean(editingProvider || editingDefaultModel)}
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
                              <div className="flex w-full justify-end">
                                <div className="relative">
                                  <button
                                    type="button"
                                    data-testid={`llm-test-${modelName}`}
                                    onClick={() => void testModel(modelName)}
                                    onMouseEnter={() => setHoveredTestModel(modelName)}
                                    onMouseLeave={() => {
                                      setHoveredTestModel((prev) => (prev === modelName ? null : prev));
                                      setVisibleTestTooltipModel((prev) => (prev === modelName ? null : prev));
                                    }}
                                    onFocus={() => setHoveredTestModel(modelName)}
                                    onBlur={() => {
                                      setHoveredTestModel((prev) => (prev === modelName ? null : prev));
                                      setVisibleTestTooltipModel((prev) => (prev === modelName ? null : prev));
                                    }}
                                    disabled={testingModel === modelName}
                                    className="flex items-center gap-1.5 rounded-xl border border-amber-500/30 px-3 py-2 text-sm font-bold text-amber-600 transition-all hover:bg-amber-500/10 disabled:opacity-50 dark:text-amber-400"
                                  >
                                    {testingModel === modelName ? (
                                      <Loader2 size={16} className="animate-spin" />
                                    ) : (
                                      <Zap size={16} />
                                    )}
                                    测试
                                  </button>
                                  {visibleTestTooltipModel === modelName ? (
                                    <div
                                      data-testid={`llm-test-tooltip-${modelName}`}
                                      className="absolute bottom-full right-0 z-20 mb-2 whitespace-nowrap rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground shadow-lg"
                                    >
                                      {TEST_TOOLTIP_MESSAGE}
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                              {testResults[modelName] && (
                                <div className="relative flex justify-end self-end" data-llm-test-error-scope="true">
                                  {!testResults[modelName].success && openTestErrorModel === modelName && testResults[modelName].detail ? (
                                    <div
                                      data-testid={`llm-test-error-popover-${modelName}`}
                                      className="absolute bottom-full right-0 z-20 mb-2 w-[280px] max-w-[min(280px,calc(100vw-2rem))] rounded-xl border border-destructive/20 bg-background/95 p-3 text-left text-xs text-foreground shadow-2xl backdrop-blur"
                                    >
                                      <div className="mb-2 flex items-start justify-between gap-3">
                                        <div className="font-semibold text-destructive">错误信息</div>
                                        <button
                                          type="button"
                                          data-testid={`llm-test-error-popover-close-${modelName}`}
                                          onClick={() => setOpenTestErrorModel(null)}
                                          className="rounded-md p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                                        >
                                          <X size={14} />
                                        </button>
                                      </div>
                                      <div className="whitespace-pre-wrap break-words text-muted-foreground">
                                        {testResults[modelName].detail}
                                      </div>
                                    </div>
                                  ) : null}
                                  {testResults[modelName].success ? (
                                    <div
                                      data-testid={`llm-test-result-${modelName}`}
                                      className="inline-flex max-w-[220px] items-center justify-end gap-1.5 rounded-lg bg-green-500/10 px-3 py-1.5 text-right text-xs font-semibold text-green-600 dark:text-green-400"
                                    >
                                      <CheckCircle size={14} />
                                      {testResults[modelName].message}
                                    </div>
                                  ) : (
                                    <button
                                      type="button"
                                      data-testid={`llm-test-result-${modelName}`}
                                      onClick={() => setOpenTestErrorModel((prev) => (prev === modelName ? null : modelName))}
                                      className="inline-flex max-w-[220px] items-center justify-end gap-1.5 rounded-lg bg-destructive/10 px-3 py-1.5 text-right text-xs font-semibold text-destructive"
                                    >
                                      <XCircle size={14} />
                                      {testResults[modelName].message}
                                    </button>
                                  )}
                                </div>
                              )}
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

        <Dialog open={bulkTestDialogOpen} onOpenChange={setBulkTestDialogOpen}>
          <DialogContent data-testid="test-all-llms-dialog" className="z-[260] flex max-h-[85vh] flex-col overflow-hidden rounded-3xl p-0 sm:max-w-3xl">
            <DialogHeader className="border-b px-8 py-6">
              <DialogTitle className="text-2xl font-bold">批量测试 LLM 连接</DialogTitle>
              <DialogDescription className="text-base">
                按 provider 分组展示所有 llm 的连接进度与结果，失败项可点击查看错误详情。
              </DialogDescription>
            </DialogHeader>
            <div data-testid="test-all-llms-scroll-body" className="min-h-0 flex-1 space-y-6 overflow-y-auto px-8 py-6">
              {providerNames.map((providerName) => {
                const providerModels = groupedModels[providerName] || [];
                return (
                  <div key={providerName} className="space-y-3">
                    <div className="text-sm font-bold text-foreground">
                      {providerName}: {activeProviders[providerName]?.source_type || 'openai'}
                    </div>
                    {providerModels.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
                        当前 provider 暂无 llm
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {providerModels.map((modelName) => {
                          const result = bulkTestResults[modelName];
                          const isPending = result?.status === 'pending';
                          const isFailed = result?.status === 'failed';
                          return (
                            <div key={modelName} className="space-y-2">
                              <button
                                type="button"
                                data-testid={`test-all-llms-item-${modelName}`}
                                onClick={() => {
                                  if (!isFailed || !result?.detail) return;
                                  setOpenBulkTestErrorModel((prev) => (prev === modelName ? null : modelName));
                                }}
                                disabled={!isFailed || !result?.detail}
                                className={`flex w-full items-start gap-2 rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                                  isFailed ? 'hover:bg-destructive/5' : ''
                                } ${!isFailed ? 'cursor-default' : ''}`}
                              >
                                <span className="pt-0.5 text-muted-foreground">-</span>
                                <span className="min-w-0 flex-1 break-all text-foreground">{modelName}</span>
                                <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold ${
                                  isPending
                                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                                    : result?.success
                                      ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                                      : 'bg-destructive/10 text-destructive'
                                }`}>
                                  {isPending ? <Loader2 size={14} className="animate-spin" /> : result?.success ? <CheckCircle size={14} /> : <XCircle size={14} />}
                                  {isPending ? '连接中' : result?.message || '未开始'}
                                </span>
                              </button>
                              {isFailed && openBulkTestErrorModel === modelName && result?.detail ? (
                                <div
                                  data-testid={`test-all-llms-error-${modelName}`}
                                  className="ml-6 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-xs text-muted-foreground"
                                >
                                  {result.detail}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </DialogContent>
        </Dialog>
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
    <div className="min-w-0 space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground">{label}</label>
      <input
        type={type}
        value={value}
        data-testid={dataTestId}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
      />
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  dataTestId,
  disabled = false,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  dataTestId?: string;
  disabled?: boolean;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground">{label}</label>
      <select
        value={value}
        data-testid={dataTestId}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
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

function normalizeExplicitProviderNames(input: unknown): string[] {
  if (!input || typeof input !== 'object') return [];
  const meta = input as LlmMeta;
  if (!Array.isArray(meta.explicit_provider_names)) return [];
  return meta.explicit_provider_names.filter((name): name is string => typeof name === 'string');
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
          type: String(model.type || 'chat'),
          timeout: Number(model.timeout || 60),
          max_tokens: Number(model.max_tokens || 128000),
          max_output_tokens: Number(model.max_output_tokens || 16384),
          ...(model.dimensions ? { dimensions: Number(model.dimensions) } : {}),
        },
      ];
    }),
  );
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

function buildProviderPayloadsFromDrafts(providers: Record<string, ProviderDraft>): Record<string, Record<string, unknown>> {
  return buildProviderPayloads(
    Object.fromEntries(
      Object.entries(providers).map(([_, draft]) => [
        draft.name,
        {
          source_type: draft.source_type,
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
        type: draft.type || 'chat',
        timeout: draft.timeout,
        max_tokens: draft.max_tokens,
        max_output_tokens: draft.max_output_tokens,
        ...(draft.dimensions ? { dimensions: draft.dimensions } : {}),
      },
    ]),
  );
}

function createConfigSnapshot({
  providers,
  models,
  defaultModel,
  defaultEmbeddingModel,
}: {
  providers: Record<string, ProviderDraft>;
  models: Record<string, ModelDraft>;
  defaultModel: string;
  defaultEmbeddingModel: string;
}) {
  const providerPayloads = buildProviderPayloadsFromDrafts(providers);
  const modelPayloads = buildModelPayloadsFromDrafts(models);

  return JSON.stringify({
    providers: Object.fromEntries(
      Object.entries(providerPayloads).sort(([left], [right]) => left.localeCompare(right)),
    ),
    models: Object.fromEntries(
      Object.entries(modelPayloads).sort(([left], [right]) => left.localeCompare(right)),
    ),
    defaultModel,
    defaultEmbeddingModel,
  });
}
