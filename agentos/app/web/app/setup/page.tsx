"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authGet, authFetch, API_BASE } from '@/lib/authFetch';

// 步骤类型
type Step = 'category' | 'provider' | 'config' | 'model';

// 预设数据类型（后端使用 label 字段，前端同时兼容 name/label）
interface ProviderPreset {
  key: string;
  label: string;
  base_url: string;
  models: { key: string; model_id: string }[];
}

interface CategoryPreset {
  key: string;        // 'openai_compatible' | 'anthropic' | 'gemini'
  label: string;
  providers: ProviderPreset[];
}

export default function SetupPage() {
  const router = useRouter();

  // 步骤状态
  const [step, setStep] = useState<Step>('category');

  // 预设数据
  const [presets, setPresets] = useState<CategoryPreset[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(true);

  // 用户选择
  const [selectedCategory, setSelectedCategory] = useState<CategoryPreset | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<ProviderPreset | null>(null);
  const [customProviderName, setCustomProviderName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [selectedModelKey, setSelectedModelKey] = useState('');
  const [customModelId, setCustomModelId] = useState('');
  const [customModelName, setCustomModelName] = useState('');
  const [useCustomModel, setUseCustomModel] = useState(false);
  const [multimodalInput, setMultimodalInput] = useState<string[]>([]);

  // 动态模型列表
  const [fetchedModels, setFetchedModels] = useState<{ id: string; owned_by: string }[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchModelsError, setFetchModelsError] = useState('');

  // 提交状态
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // 加载预设数据
  useEffect(() => {
    const fetchPresets = async () => {
      try {
        const data = await authGet<{ categories: CategoryPreset[] }>(`${API_BASE}/api/config/llm-presets`);
        setPresets(Array.isArray(data) ? data : data.categories ?? []);
      } catch (e) {
        console.error('加载 LLM 预设失败:', e);
        // 使用内置默认值，避免因接口不存在导致页面无法使用
        setPresets(DEFAULT_PRESETS);
      } finally {
        setPresetsLoading(false);
      }
    };
    fetchPresets();
  }, []);

  // 选择分类
  const handleSelectCategory = (category: CategoryPreset) => {
    setSelectedCategory(category);
    setSelectedProvider(null);
    setCustomProviderName('');
    setBaseUrl('');
    setApiKey('');
    setSelectedModelKey('');
    setCustomModelId('');
    setCustomModelName('');
    setUseCustomModel(false);

    if (category.providers.length === 1) {
      // 只有一个 provider，直接跳到配置步骤
      const prov = category.providers[0];
      setSelectedProvider(prov);
      setBaseUrl(prov.base_url);
      if (prov.models.length > 0) setSelectedModelKey(prov.models[0].key);
      setStep('config');
    } else {
      setStep('provider');
    }
  };

  // 选择具体 provider
  const handleSelectProvider = (provider: ProviderPreset) => {
    setSelectedProvider(provider);
    setCustomProviderName('');
    setBaseUrl(provider.base_url);
    setApiKey('');
    setSelectedModelKey(provider.models.length > 0 ? provider.models[0].key : '');
    setCustomModelId('');
    setCustomModelName('');
    setUseCustomModel(false);
    setMultimodalInput([]);
    setStep('config');
  };

  // 获取可用模型列表
  const fetchModelList = async () => {
    if (!apiKey.trim()) return;
    setFetchingModels(true);
    setFetchModelsError('');
    setFetchedModels([]);

    const listProvider = selectedProvider?.key === 'custom_openai'
      ? (customProviderName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_') || 'openai')
      : (selectedProvider?.key || (selectedCategory?.key === 'anthropic' ? 'anthropic' : 'openai'));

    try {
      const resp = await authFetch(`${API_BASE}/api/config/list-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKey.trim(),
          base_url: baseUrl.trim(),
          provider: listProvider,
        }),
      });
      const data = await resp.json();
      if (data.success && Array.isArray(data.models) && data.models.length > 0) {
        setFetchedModels(data.models);
        // 自动选中第一个模型
        setSelectedModelKey(data.models[0].id);
        setUseCustomModel(false);
      } else {
        setFetchModelsError(data.error || '未获取到可用模型');
        setUseCustomModel(true);
      }
    } catch {
      setFetchModelsError('获取模型列表失败，请手动输入');
      setUseCustomModel(true);
    } finally {
      setFetchingModels(false);
    }
  };

  // 从 config 步骤前进到 model 步骤
  const isCustomProvider = selectedProvider?.key === 'custom_openai';
  const needsCustomModelInput = useCustomModel || (!fetchingModels && fetchedModels.length === 0);
  const handleConfigNext = () => {
    if (!apiKey.trim()) return;
    if (isCustomProvider && !customProviderName.trim()) return;
    setStep('model');
    // 自动获取模型列表
    fetchModelList();
  };

  // 解析当前选择的 provider/model 信息
  const _resolveLLMConfig = () => {
    if (!selectedCategory || !selectedProvider) return null;

    // 使用实际选择的 provider key（如 minimax、qwen、deepseek），
    // 而非统一用 openai，确保 api_key 写入正确的 provider 配置
    const llmProvider = selectedProvider.key === 'custom_openai'
      ? (customProviderName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_') || 'openai')
      : selectedProvider.key;

    let modelId: string;
    let modelKey: string;

    if (useCustomModel || (fetchedModels.length === 0 && selectedProvider.models.length === 0)) {
      modelId = customModelId.trim();
      modelKey = modelId || 'custom_model';
    } else if (fetchedModels.length > 0) {
      modelId = selectedModelKey;
      modelKey = modelId;
    } else {
      const found = selectedProvider.models.find(m => m.key === selectedModelKey);
      modelId = found ? found.model_id : selectedModelKey;
      modelKey = modelId;
    }

    if (!modelId) return null;
    return { llmProvider, modelId, modelKey, multimodalInput };
  };

  // 测试 LLM 连接
  const handleTest = async () => {
    const cfg = _resolveLLMConfig();
    if (!cfg) return;

    setIsTesting(true);
    setTestResult(null);
    setSubmitError('');

    try {
      const resp = await authFetch(`${API_BASE}/api/config/test-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: cfg.llmProvider,
          api_key: apiKey.trim(),
          base_url: baseUrl.trim(),
          model_id: cfg.modelId,
        }),
      });
      const data = await resp.json();
      if (data.success) {
        setTestResult({ success: true, message: data.message || '连接成功' });
      } else {
        setTestResult({ success: false, message: data.error || '连接失败' });
      }
    } catch (e) {
      setTestResult({ success: false, message: '请求失败，请检查网络连接' });
    } finally {
      setIsTesting(false);
    }
  };

  // 保存配置并跳转
  const handleSubmit = async () => {
    const cfg = _resolveLLMConfig();
    if (!cfg) return;

    setIsSubmitting(true);
    setSubmitError('');

    try {
      await authFetch(`${API_BASE}/api/config/sections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm: {
            providers: {
              [cfg.llmProvider]: {
                api_key: apiKey.trim(),
                base_url: baseUrl.trim(),
                timeout: 60,
                max_retries: 3,
              },
            },
            models: {
              [cfg.modelKey]: {
                provider: cfg.llmProvider,
                model_id: cfg.modelId,
                ...(cfg.multimodalInput.length > 0 ? { multimodal_input: cfg.multimodalInput } : {}),
              },
            },
            default_model: cfg.modelKey,
          },
          agent: { model: cfg.modelKey },
        }),
      });

      // 标记已完成配置，避免 ProtectedRoute 再次跳回 setup
      sessionStorage.setItem('llm_just_configured', '1');
      router.push('/');
    } catch (e) {
      console.error('保存配置失败:', e);
      setSubmitError('保存配置失败，请稍后重试');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 跳过
  const handleSkip = () => {
    router.push('/');
  };

  // 返回上一步
  const handleBack = () => {
    if (step === 'provider') {
      setStep('category');
    } else if (step === 'config') {
      if (selectedCategory && selectedCategory.providers.length > 1) {
        setStep('provider');
      } else {
        setStep('category');
      }
    } else if (step === 'model') {
      setStep('config');
    }
  };

  if (presetsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-500">加载配置...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-xl w-full space-y-6 p-8 bg-white rounded-lg shadow-md">
        {/* 标题 */}
        <div>
          <h2 className="text-center text-3xl font-extrabold text-gray-900">
            AgentOS
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            配置第一个 LLM 服务后，即可使用运维 Agent 智能完成其余配置
          </p>
        </div>

        {/* 步骤：选择分类 */}
        {step === 'category' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-900">选择 LLM 服务商类型</h3>
            <div className="space-y-3">
              {presets.map((category) => (
                <button
                  key={category.key}
                  onClick={() => handleSelectCategory(category)}
                  className="w-full text-left px-4 py-3 border border-gray-300 rounded-md hover:border-blue-500 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                >
                  <span className="font-medium text-gray-800">{category.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 步骤：选择具体 provider */}
        {step === 'provider' && selectedCategory && (
          <div className="space-y-4">
            <button
              onClick={handleBack}
              className="text-sm text-blue-600 hover:text-blue-800 focus:outline-none"
            >
              ← 返回
            </button>
            <h3 className="text-lg font-medium text-gray-900">选择服务商</h3>
            <div className="space-y-3">
              {selectedCategory.providers.map((provider) => (
                <button
                  key={provider.key}
                  onClick={() => handleSelectProvider(provider)}
                  className="w-full text-left px-4 py-3 border border-gray-300 rounded-md hover:border-blue-500 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                >
                  <span className="font-medium text-gray-800">{provider.label}</span>
                  {provider.base_url && (
                    <span className="block text-xs text-gray-400 mt-0.5 truncate">{provider.base_url}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 步骤：填写配置 */}
        {step === 'config' && selectedProvider && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); handleConfigNext(); }}>
            <button
              type="button"
              onClick={handleBack}
              className="text-sm text-blue-600 hover:text-blue-800 focus:outline-none"
            >
              ← 返回
            </button>
            <h3 className="text-lg font-medium text-gray-900">填写连接配置</h3>

            <div className="space-y-4">
              {selectedProvider.key === 'custom_openai' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    服务商名称 <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={customProviderName}
                    onChange={(e) => setCustomProviderName(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    placeholder="例如: SiliconFlow、Groq"
                    autoFocus
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Base URL
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
                  placeholder="https://api.openai.com/v1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  API Key <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
                  placeholder="sk-..."
                  autoFocus
                  autoComplete="off"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={!apiKey.trim() || (isCustomProvider && !customProviderName.trim())}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              下一步
            </button>
          </form>
        )}

        {/* 步骤：选择模型 */}
        {step === 'model' && selectedProvider && (
          <div className="space-y-4">
            <button
              onClick={handleBack}
              className="text-sm text-blue-600 hover:text-blue-800 focus:outline-none"
            >
              ← 返回
            </button>
            <h3 className="text-lg font-medium text-gray-900">选择模型</h3>

            {/* 加载中 */}
            {fetchingModels && (
              <div className="flex items-center gap-2 px-4 py-3 text-sm text-gray-500">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                正在获取可用模型列表...
              </div>
            )}

            {/* 动态获取的模型列表 */}
            {!fetchingModels && fetchedModels.length > 0 && (
              <div className="space-y-2">
                <div className="max-h-64 overflow-y-auto space-y-2">
                  {fetchedModels.map((model) => (
                    <label
                      key={model.id}
                      className={`flex items-center px-4 py-3 border rounded-md cursor-pointer transition-colors ${
                        !useCustomModel && selectedModelKey === model.id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-300 hover:border-blue-300'
                      }`}
                    >
                      <input
                        type="radio"
                        name="model"
                        value={model.id}
                        checked={!useCustomModel && selectedModelKey === model.id}
                        onChange={() => {
                          setSelectedModelKey(model.id);
                          setUseCustomModel(false);
                        }}
                        className="mr-3 text-blue-600"
                      />
                      <span className="font-medium text-gray-800 text-sm">{model.id}</span>
                    </label>
                  ))}
                </div>

                {/* 自定义模型选项 */}
                <label
                  className={`flex items-center px-4 py-3 border rounded-md cursor-pointer transition-colors ${
                    useCustomModel
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-300 hover:border-blue-300'
                  }`}
                >
                  <input
                    type="radio"
                    name="model"
                    checked={useCustomModel}
                    onChange={() => setUseCustomModel(true)}
                    className="mr-3 text-blue-600"
                  />
                  <span className="font-medium text-gray-800 text-sm">自定义模型</span>
                </label>
              </div>
            )}

            {/* 获取失败提示 */}
            {!fetchingModels && fetchedModels.length === 0 && fetchModelsError && (
              <div className="px-4 py-3 rounded text-sm border bg-yellow-50 border-yellow-200 text-yellow-700">
                {fetchModelsError}，请手动输入模型 ID
                <button
                  onClick={fetchModelList}
                  className="ml-2 text-blue-600 hover:text-blue-800 underline"
                >
                  重试
                </button>
              </div>
            )}

            {/* 自定义模型输入框 */}
            {(useCustomModel || (!fetchingModels && fetchedModels.length === 0)) && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    模型 ID <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={customModelId}
                    onChange={(e) => setCustomModelId(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
                    placeholder="gpt-4o-mini"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    模型名称
                  </label>
                  <input
                    type="text"
                    value={customModelName}
                    onChange={(e) => setCustomModelName(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    placeholder="仅用于显示，留空则使用模型 ID"
                  />
                </div>
              </div>
            )}

            {/* 多模态输入 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                多模态输入
              </label>
              <div className="flex gap-2">
                {[
                  { key: 'image', label: '图像' },
                ].map((option) => {
                  const active = multimodalInput.includes(option.key);
                  return (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => {
                        setMultimodalInput(prev =>
                          active ? prev.filter(k => k !== option.key) : [...prev, option.key]
                        );
                      }}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                        active
                          ? 'bg-blue-100 border-blue-400 text-blue-700'
                          : 'bg-gray-100 border-gray-300 text-gray-500 hover:border-gray-400'
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
              <p className="mt-1 text-xs text-gray-400">选择该模型支持的输入类型</p>
            </div>

            {/* 测试结果 */}
            {testResult && (
              <div className={`px-4 py-3 rounded text-sm border ${
                testResult.success
                  ? 'bg-green-50 border-green-200 text-green-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}>
                {testResult.success ? '✓ ' : '✗ '}{testResult.message}
              </div>
            )}

            {submitError && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
                {submitError}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={handleTest}
                disabled={
                  isTesting || isSubmitting || fetchingModels ||
                  (needsCustomModelInput ? !customModelId.trim() : !selectedModelKey)
                }
                className="flex-1 flex justify-center py-2 px-4 border border-blue-600 rounded-md shadow-sm text-sm font-medium text-blue-600 bg-white hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:border-gray-300 disabled:text-gray-400 disabled:cursor-not-allowed"
              >
                {isTesting ? '测试中...' : '测试连接'}
              </button>
              <button
                onClick={handleSubmit}
                disabled={
                  isSubmitting || isTesting ||
                  (needsCustomModelInput ? !customModelId.trim() : !selectedModelKey)
                }
                className="flex-1 flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {isSubmitting ? '保存中...' : '完成配置'}
              </button>
            </div>
          </div>
        )}

        {/* 跳过按钮（始终显示） */}
        <div className="text-center pt-2">
          <button
            onClick={handleSkip}
            className="text-sm text-gray-500 hover:text-gray-700 focus:outline-none"
          >
            跳过，稍后配置
          </button>
        </div>
      </div>
    </div>
  );
}

// 内置默认预设（当接口不可用时使用，模型列表为空，统一走动态获取）
const DEFAULT_PRESETS: CategoryPreset[] = [
  {
    key: 'openai_compatible',
    label: 'OpenAI 兼容',
    providers: [
      { key: 'openai', label: 'OpenAI', base_url: 'https://api.openai.com/v1', models: [] },
      { key: 'qwen', label: '通义千问(Qwen)', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: [] },
      { key: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: [] },
      { key: 'custom_openai', label: '其他（自定义）', base_url: '', models: [] },
    ],
  },
  {
    key: 'anthropic',
    label: 'Anthropic (Claude)',
    providers: [
      { key: 'anthropic', label: 'Anthropic', base_url: 'https://api.anthropic.com', models: [] },
    ],
  },
  {
    key: 'gemini',
    label: 'Google Gemini',
    providers: [
      { key: 'gemini', label: 'Google Gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta', models: [] },
    ],
  },
];
