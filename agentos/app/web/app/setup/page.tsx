"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authGet, authFetch, API_BASE } from '@/lib/authFetch';

// 步骤类型
type Step = 'category' | 'provider' | 'config' | 'model';

// 预设数据类型
interface ProviderPreset {
  key: string;
  name: string;
  base_url: string;
  models: { key: string; name: string; model_id: string }[];
}

interface CategoryPreset {
  key: string;        // 'openai_compatible' | 'anthropic' | 'gemini'
  name: string;
  llm_provider: string; // 提交时使用的 provider key（如 'openai', 'anthropic', 'gemini'）
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
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [selectedModelKey, setSelectedModelKey] = useState('');
  const [customModelId, setCustomModelId] = useState('');
  const [useCustomModel, setUseCustomModel] = useState(false);

  // 提交状态
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

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
    setBaseUrl('');
    setApiKey('');
    setSelectedModelKey('');
    setCustomModelId('');
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
    setBaseUrl(provider.base_url);
    setApiKey('');
    setSelectedModelKey(provider.models.length > 0 ? provider.models[0].key : '');
    setCustomModelId('');
    setUseCustomModel(false);
    setStep('config');
  };

  // 从 config 步骤前进到 model 步骤
  const handleConfigNext = () => {
    if (!apiKey.trim()) return;
    setStep('model');
  };

  // 提交配置
  const handleSubmit = async () => {
    if (!selectedCategory || !selectedProvider) return;

    const llmProvider = selectedCategory.key === 'openai_compatible'
      ? 'openai'
      : selectedCategory.llm_provider;

    let modelId: string;
    let modelKey: string;

    if (useCustomModel || selectedProvider.models.length === 0) {
      modelId = customModelId.trim();
      modelKey = modelId.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase() || 'custom_model';
    } else {
      const found = selectedProvider.models.find(m => m.key === selectedModelKey);
      modelId = found ? found.model_id : selectedModelKey;
      modelKey = selectedModelKey;
    }

    if (!modelId) return;

    setIsSubmitting(true);
    setSubmitError('');

    try {
      await authFetch(`${API_BASE}/api/config/sections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm: {
            providers: {
              [llmProvider]: {
                api_key: apiKey.trim(),
                base_url: baseUrl.trim(),
                timeout: 60,
                max_retries: 3,
              },
            },
            models: {
              [modelKey]: { provider: llmProvider, model_id: modelId },
            },
            default_model: modelKey,
          },
          agent: { model: modelKey },
        }),
      });

      router.push('/chat?agent=system-admin');
    } catch (e) {
      console.error('保存配置失败:', e);
      setSubmitError('保存配置失败，请稍后重试');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 跳过
  const handleSkip = () => {
    router.push('/chat');
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
      <div className="max-w-md w-full space-y-6 p-8 bg-white rounded-lg shadow-md">
        {/* 标题 */}
        <div>
          <h2 className="text-center text-3xl font-extrabold text-gray-900">
            AgentOS
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            配置 LLM 服务以开始使用
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
                  <span className="font-medium text-gray-800">{category.name}</span>
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
                  <span className="font-medium text-gray-800">{provider.name}</span>
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
          <div className="space-y-4">
            <button
              onClick={handleBack}
              className="text-sm text-blue-600 hover:text-blue-800 focus:outline-none"
            >
              ← 返回
            </button>
            <h3 className="text-lg font-medium text-gray-900">填写连接配置</h3>

            <div className="space-y-4">
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
                />
              </div>
            </div>

            <button
              onClick={handleConfigNext}
              disabled={!apiKey.trim()}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              下一步
            </button>
          </div>
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

            {selectedProvider.models.length > 0 && (
              <div className="space-y-2">
                {selectedProvider.models.map((model) => (
                  <label
                    key={model.key}
                    className={`flex items-center px-4 py-3 border rounded-md cursor-pointer transition-colors ${
                      !useCustomModel && selectedModelKey === model.key
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-300 hover:border-blue-300'
                    }`}
                  >
                    <input
                      type="radio"
                      name="model"
                      value={model.key}
                      checked={!useCustomModel && selectedModelKey === model.key}
                      onChange={() => {
                        setSelectedModelKey(model.key);
                        setUseCustomModel(false);
                      }}
                      className="mr-3 text-blue-600"
                    />
                    <span className="font-medium text-gray-800 text-sm">{model.name}</span>
                    <span className="ml-2 text-xs text-gray-400">{model.model_id}</span>
                  </label>
                ))}

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

            {/* 自定义模型输入框（无预设模型时始终显示） */}
            {(useCustomModel || selectedProvider.models.length === 0) && (
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
            )}

            {submitError && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
                {submitError}
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={
                isSubmitting ||
                (useCustomModel || selectedProvider.models.length === 0
                  ? !customModelId.trim()
                  : !selectedModelKey)
              }
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isSubmitting ? '保存中...' : '完成配置'}
            </button>
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

// 内置默认预设（当接口不可用时使用）
const DEFAULT_PRESETS: CategoryPreset[] = [
  {
    key: 'openai_compatible',
    name: 'OpenAI 兼容',
    llm_provider: 'openai',
    providers: [
      {
        key: 'openai',
        name: 'OpenAI',
        base_url: 'https://api.openai.com/v1',
        models: [
          { key: 'gpt_4o', name: 'GPT-4o', model_id: 'gpt-4o' },
          { key: 'gpt_4o_mini', name: 'GPT-4o Mini', model_id: 'gpt-4o-mini' },
          { key: 'gpt_4_turbo', name: 'GPT-4 Turbo', model_id: 'gpt-4-turbo' },
        ],
      },
      {
        key: 'qwen',
        name: '通义千问',
        base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        models: [
          { key: 'qwen_max', name: 'Qwen Max', model_id: 'qwen-max' },
          { key: 'qwen_plus', name: 'Qwen Plus', model_id: 'qwen-plus' },
          { key: 'qwen_turbo', name: 'Qwen Turbo', model_id: 'qwen-turbo' },
        ],
      },
      {
        key: 'deepseek',
        name: 'DeepSeek',
        base_url: 'https://api.deepseek.com/v1',
        models: [
          { key: 'deepseek_chat', name: 'DeepSeek Chat', model_id: 'deepseek-chat' },
          { key: 'deepseek_reasoner', name: 'DeepSeek Reasoner', model_id: 'deepseek-reasoner' },
        ],
      },
      {
        key: 'other',
        name: '其他',
        base_url: '',
        models: [],
      },
    ],
  },
  {
    key: 'anthropic',
    name: 'Anthropic (Claude)',
    llm_provider: 'anthropic',
    providers: [
      {
        key: 'anthropic',
        name: 'Anthropic',
        base_url: 'https://api.anthropic.com',
        models: [
          { key: 'claude_3_5_sonnet', name: 'Claude 3.5 Sonnet', model_id: 'claude-3-5-sonnet-20241022' },
          { key: 'claude_3_5_haiku', name: 'Claude 3.5 Haiku', model_id: 'claude-3-5-haiku-20241022' },
          { key: 'claude_3_opus', name: 'Claude 3 Opus', model_id: 'claude-3-opus-20240229' },
        ],
      },
    ],
  },
  {
    key: 'gemini',
    name: 'Google Gemini',
    llm_provider: 'gemini',
    providers: [
      {
        key: 'gemini',
        name: 'Google Gemini',
        base_url: 'https://generativelanguage.googleapis.com/v1beta',
        models: [
          { key: 'gemini_2_0_flash', name: 'Gemini 2.0 Flash', model_id: 'gemini-2.0-flash' },
          { key: 'gemini_1_5_pro', name: 'Gemini 1.5 Pro', model_id: 'gemini-1.5-pro' },
          { key: 'gemini_1_5_flash', name: 'Gemini 1.5 Flash', model_id: 'gemini-1.5-flash' },
        ],
      },
    ],
  },
];
