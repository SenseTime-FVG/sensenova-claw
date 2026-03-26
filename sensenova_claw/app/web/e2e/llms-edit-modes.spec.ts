import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('llms 页面应支持单项编辑与编辑所有配置', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: { source_type: 'openai', api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' }, base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_tokens: 128000, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    const providerPuts: unknown[] = [];
    const modelPuts: unknown[] = [];
    const defaultModelPuts: unknown[] = [];
    const sectionPuts: unknown[] = [];

    Object.assign(window, {
      __providerPuts: providerPuts,
      __modelPuts: modelPuts,
      __defaultModelPuts: defaultModelPuts,
      __sectionPuts: sectionPuts,
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/llm/providers/openai') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        providerPuts.push(body);
        (window as typeof window & { __providerPuts: unknown[] }).__providerPuts = providerPuts;
        state.llm.providers.openai = {
          ...state.llm.providers.openai,
          source_type: body.source_type,
          base_url: body.base_url,
          timeout: body.timeout,
          max_retries: body.max_retries,
          api_key: body.api_key ? { configured: true, masked_value: 'sk-••••real', source: 'secret' } : state.llm.providers.openai.api_key,
        };
        return new Response(JSON.stringify({ status: 'saved' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/llm/models/gpt-4o-mini') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        modelPuts.push(body);
        (window as typeof window & { __modelPuts: unknown[] }).__modelPuts = modelPuts;
        state.llm.models['gpt-4o-mini'] = body;
        return new Response(JSON.stringify({ status: 'saved' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/llm/default-model') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        defaultModelPuts.push(body);
        (window as typeof window & { __defaultModelPuts: unknown[] }).__defaultModelPuts = defaultModelPuts;
        state.llm.default_model = body.default_model ?? '';
        return new Response(JSON.stringify({ status: 'saved' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        sectionPuts.push(body);
        (window as typeof window & { __sectionPuts: unknown[] }).__sectionPuts = sectionPuts;
        return new Response(JSON.stringify({ status: 'saved' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');

  await expect(page.getByTestId('default-model-select')).toBeDisabled();
  await page.getByTestId('default-model-edit').click();
  await expect(page.getByTestId('default-model-select')).toBeEnabled();
  await page.getByTestId('default-model-select').selectOption('');
  await page.getByTestId('default-model-cancel').click();
  await expect(page.getByTestId('default-model-select')).toHaveValue('gpt-4o-mini');

  await page.getByTestId('default-model-edit').click();
  await page.getByTestId('default-model-select').selectOption('');
  await page.getByTestId('default-model-save').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __defaultModelPuts?: unknown[] }).__defaultModelPuts ?? []).length);
  }).toBe(1);
  await expect(page.getByTestId('default-model-select')).toHaveValue('');

  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toBeDisabled();
  await page.getByTestId('provider-edit-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toBeEditable();
  await page.getByTestId('provider-base-url-input-openai').fill('https://proxy.example.com/v1');
  await page.getByTestId('provider-cancel-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toHaveValue('https://api.openai.com/v1');

  await page.getByTestId('provider-edit-openai').click();
  await page.getByTestId('provider-source-type-select-openai').selectOption('openai-compatible');
  await page.getByTestId('provider-base-url-input-openai').fill('https://proxy.example.com/v1');
  await page.getByTestId('provider-save-openai').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __providerPuts?: unknown[] }).__providerPuts ?? []).length);
  }).toBe(1);

  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-body-openai')).toBeVisible();
  await expect(page.getByTestId('llm-model-id-input-gpt-4o-mini')).toBeDisabled();
  await page.getByTestId('llm-edit-gpt-4o-mini').click();
  await page.getByTestId('llm-model-id-input-gpt-4o-mini').fill('gpt-4.1-mini');
  await page.getByTestId('llm-save-gpt-4o-mini').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __modelPuts?: unknown[] }).__modelPuts ?? []).length);
  }).toBe(1);

  await page.getByTestId('edit-all-llm-config').click();
  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-body-openai')).toBeVisible();
  await expect(page.getByTestId('provider-base-url-input-openai')).toBeEditable();
  await expect(page.getByTestId('llm-model-id-input-gpt-4o-mini')).toBeEditable();
  await page.getByTestId('provider-base-url-input-openai').fill('https://global.example.com/v1');
  await page.getByTestId('cancel-edit-all-llm-config').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toHaveValue('https://proxy.example.com/v1');

  await page.getByTestId('edit-all-llm-config').click();
  await page.getByTestId('provider-base-url-input-openai').fill('https://global.example.com/v1');
  await page.getByTestId('save-all-llm-config').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __sectionPuts?: unknown[] }).__sectionPuts ?? []).length);
  }).toBe(1);
});

test('llms 页面只显示用户显式配置过的 provider', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: { source_type: 'openai', api_key: '', base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
          anthropic: { source_type: 'anthropic', api_key: '', base_url: 'https://api.anthropic.com', timeout: 60, max_retries: 3 },
          deepseek: { source_type: 'deepseek', api_key: { configured: true, masked_value: 'sk-••••deep', source: 'config' }, base_url: 'https://api.deepseek.com', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'deepseek-chat': { provider: 'deepseek', model_id: 'deepseek-chat', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'deepseek-chat',
        _meta: {
          explicit_provider_names: ['deepseek'],
        },
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['deepseek'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');

  await expect(page.getByTestId('provider-card-deepseek')).toBeVisible();
  await expect(page.getByTestId('provider-card-openai')).toHaveCount(0);
  await expect(page.getByTestId('provider-card-anthropic')).toHaveCount(0);
  await expect(page.getByTestId('llm-card-deepseek-chat')).toHaveCount(0);

  await page.getByTestId('provider-toggle-deepseek').click();
  await expect(page.getByTestId('llm-card-deepseek-chat')).toBeVisible();
});

test('llms 页面新增 provider 后应支持单项编辑并保存', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: { source_type: 'openai', api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' }, base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    const providerPuts: Array<{ url: string; body: Record<string, unknown> }> = [];

    Object.assign(window, {
      __providerPuts: providerPuts,
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm/providers/') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        providerPuts.push({ url, body });
        (window as typeof window & { __providerPuts: Array<{ url: string; body: Record<string, unknown> }> }).__providerPuts = providerPuts;
        return new Response(JSON.stringify({ status: 'saved' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');

  await page.getByTestId('add-provider-button').click();
  await page.getByTestId('new-provider-name-input').fill('deepseek');
  await page.getByTestId('confirm-add-provider-button').click();
  await expect(page.getByTestId('provider-card-deepseek')).toBeVisible();
  await expect(page.getByTestId('provider-body-deepseek')).toBeVisible();
  await expect(page.getByTestId('provider-base-url-input-deepseek')).toBeDisabled();

  await page.getByTestId('provider-edit-deepseek').click();
  await page.getByTestId('provider-source-type-select-deepseek').selectOption('deepseek');
  await expect(page.getByTestId('provider-base-url-input-deepseek')).toBeEditable();
  await page.getByTestId('provider-base-url-input-deepseek').fill('https://api.deepseek.com/v1');
  await page.getByTestId('provider-save-deepseek').click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __providerPuts?: Array<{ url: string; body: Record<string, unknown> }>;
    }).__providerPuts ?? []).length);
  }).toBe(1);

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __providerPuts?: Array<{ url: string; body: Record<string, unknown> }>;
    }).__providerPuts ?? [])[0]);
  }).toEqual({
    url: 'http://localhost:8000/api/config/llm/providers/deepseek',
    body: {
      name: 'deepseek',
      source_type: 'deepseek',
      base_url: 'https://api.deepseek.com/v1',
      timeout: 60,
      max_retries: 3,
      api_key: '',
    },
  });
});

test('llms 页面单项编辑时测试按钮应读取草稿并位于编辑按钮下方，结果区域不侵入编辑按钮左侧', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    const testRequests: Array<Record<string, unknown>> = [];

    Object.assign(window, {
      __llmTestRequests: testRequests,
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/config/test-llm') && method === 'POST') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        testRequests.push(body);
        (window as typeof window & { __llmTestRequests: Array<Record<string, unknown>> }).__llmTestRequests = testRequests;
        return new Response(JSON.stringify({ success: true, message: '连接成功' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.setViewportSize({ width: 1361, height: 900 });
  await page.getByTestId('provider-toggle-openai').click();
  await page.getByTestId('llm-edit-gpt-4o-mini').click();
  await page.getByTestId('llm-model-id-input-gpt-4o-mini').fill('gpt-4.1-mini-draft');
  await page.getByTestId('llm-max-tokens-input-gpt-4o-mini').fill('4096');
  await page.getByTestId('llm-max-output-tokens-input-gpt-4o-mini').fill('1024');
  await page.getByTestId('llm-test-gpt-4o-mini').click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __llmTestRequests?: Array<Record<string, unknown>>;
    }).__llmTestRequests ?? []).length);
  }).toBe(1);

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __llmTestRequests?: Array<Record<string, unknown>>;
    }).__llmTestRequests ?? [])[0]);
  }).toEqual({
    provider: 'openai',
    api_key: 'sk-openai-real',
    base_url: 'https://api.openai.com/v1',
    model_id: 'gpt-4.1-mini-draft',
    max_tokens: 4096,
    max_output_tokens: 1024,
  });

  const modelIdInput = page.getByTestId('llm-model-id-input-gpt-4o-mini');
  const testButton = page.getByTestId('llm-test-gpt-4o-mini');
  const saveButton = page.getByTestId('llm-save-gpt-4o-mini');
  const testResult = page.getByTestId('llm-test-result-gpt-4o-mini');
  const inputBox = await modelIdInput.boundingBox();
  const buttonBox = await testButton.boundingBox();
  const saveBox = await saveButton.boundingBox();
  const resultBox = await testResult.boundingBox();

  expect(inputBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(saveBox).not.toBeNull();
  expect(resultBox).not.toBeNull();
  expect(inputBox!.x + inputBox!.width).toBeLessThanOrEqual(buttonBox!.x);
  expect(buttonBox!.y).toBeGreaterThan(saveBox!.y + saveBox!.height);
  expect(resultBox!.x).toBeGreaterThanOrEqual(saveBox!.x);
});

test('llms 页面测试按钮悬停 3 秒后应显示 token 消耗提示', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_tokens: 128000, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.setViewportSize({ width: 1361, height: 900 });
  await page.getByTestId('provider-toggle-openai').click();
  const testButton = page.getByTestId('llm-test-gpt-4o-mini');
  await testButton.hover();
  await page.waitForTimeout(3100);

  await expect(page.getByTestId('llm-test-tooltip-gpt-4o-mini')).toHaveText('连接测试会消耗少量token');
});

test('llms 页面测试全部按钮悬停 1 秒后应显示 token 消耗提示', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_tokens: 128000, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.setViewportSize({ width: 1361, height: 900 });
  const testAllButton = page.getByTestId('test-all-llms');
  await testAllButton.hover();
  await page.waitForTimeout(1100);

  await expect(page.getByTestId('bulk-llm-test-tooltip')).toHaveText('连接测试会消耗少量token');
});

test('llms 页面测试失败时应先显示连接失败状态框，点击后再展示错误浮层，并支持关闭', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/config/test-llm') && method === 'POST') {
        return new Response(JSON.stringify({
          success: false,
          error: 'Error code: 401 - {"error":{"code":"401","message":"You are not authorized to access this resource."}}',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('provider-toggle-openai').click();
  await page.getByTestId('llm-test-gpt-4o-mini').click();

  const failedBadge = page.getByTestId('llm-test-result-gpt-4o-mini');
  const failedPopover = page.getByTestId('llm-test-error-popover-gpt-4o-mini');

  await expect(failedBadge).toContainText('连接失败');
  await expect(page.getByText('You are not authorized to access this resource.')).toHaveCount(0);
  await expect(failedPopover).toHaveCount(0);

  await failedBadge.click();

  await expect(failedPopover).toBeVisible();
  await expect(failedPopover).toContainText('You are not authorized to access this resource.');

  await page.getByTestId('llm-test-error-popover-close-gpt-4o-mini').click();
  await expect(failedPopover).toHaveCount(0);

  await failedBadge.click();
  await expect(failedPopover).toBeVisible();
  await page.mouse.click(20, 20);
  await expect(failedPopover).toHaveCount(0);
});

test('llms 页面应支持测试全部，并以最大并发 10 在浮层中展示进度和失败详情', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const llmModels = Object.fromEntries(
      Array.from({ length: 12 }, (_, index) => [
        `openai-model-${index + 1}`,
        { provider: 'openai', model_id: `gpt-4.1-mini-${index + 1}`, timeout: 60, max_output_tokens: 8192 },
      ]),
    );

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••openai', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
          anthropic: {
            source_type: 'anthropic',
            api_key: { configured: true, masked_value: 'sk-••••anthropic', source: 'config' },
            base_url: 'https://api.anthropic.com',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          ...llmModels,
          'claude-3-5-haiku': { provider: 'anthropic', model_id: 'claude-3-5-haiku-20241022', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'openai-model-1',
        _meta: {
          explicit_provider_names: ['openai', 'anthropic'],
        },
      },
    };

    const pendingResolvers = new Map<string, () => void>();
    let activeRequests = 0;
    let maxActiveRequests = 0;
    const startedModels: string[] = [];

    Object.assign(window, {
      __bulkTestState: {
        activeRequests: 0,
        maxActiveRequests: 0,
        startedModels,
      },
      __releaseBulkTest(modelName: string) {
        pendingResolvers.get(modelName)?.();
      },
      __releaseAllBulkTests() {
        Array.from(pendingResolvers.values()).forEach((release) => release());
      },
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai', 'anthropic'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.anthropic.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.anthropic.api_key', value: 'sk-anthropic-real' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/test-llm') && method === 'POST') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        const modelId = String(body.model_id ?? '');
        const modelName = Object.entries(state.llm.models).find(([, model]) => model.model_id === modelId)?.[0] ?? modelId;

        activeRequests += 1;
        maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
        startedModels.push(modelName);
        Object.assign(window, {
          __bulkTestState: {
            activeRequests,
            maxActiveRequests,
            startedModels,
          },
        });

        await new Promise<void>((resolve) => {
          pendingResolvers.set(modelName, () => {
            pendingResolvers.delete(modelName);
            resolve();
          });
        });

        activeRequests -= 1;
        Object.assign(window, {
          __bulkTestState: {
            activeRequests,
            maxActiveRequests,
            startedModels,
          },
        });

        if (modelName === 'claude-3-5-haiku') {
          return new Response(JSON.stringify({
            success: false,
            error: 'Error code: 401 - invalid anthropic api key',
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }

        return new Response(JSON.stringify({ success: true, message: '连接成功' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await expect(page.getByTestId('test-all-llms')).toBeVisible();

  await page.getByTestId('test-all-llms').click();

  const bulkDialog = page.getByTestId('test-all-llms-dialog');
  await expect(bulkDialog).toBeVisible();
  await expect(bulkDialog).toContainText('openai: openai');
  await expect(bulkDialog).toContainText('anthropic: anthropic');
  await expect(page.getByTestId('test-all-llms-item-openai-model-1')).toContainText('连接中');

  await expect.poll(async () => page.evaluate(() => {
    return (window as typeof window & {
      __bulkTestState?: { maxActiveRequests: number; startedModels: string[] };
    }).__bulkTestState?.startedModels.length ?? 0;
  })).toBe(10);

  await expect.poll(async () => page.evaluate(() => {
    return (window as typeof window & {
      __bulkTestState?: { maxActiveRequests: number };
    }).__bulkTestState?.maxActiveRequests ?? 0;
  })).toBe(10);

  await page.evaluate(() => {
    (window as typeof window & { __releaseAllBulkTests?: () => void }).__releaseAllBulkTests?.();
  });

  await expect.poll(async () => page.evaluate(() => {
    return (window as typeof window & {
      __bulkTestState?: { startedModels: string[] };
    }).__bulkTestState?.startedModels.length ?? 0;
  })).toBe(13);

  await page.evaluate(() => {
    (window as typeof window & { __releaseAllBulkTests?: () => void }).__releaseAllBulkTests?.();
  });

  await expect(page.getByTestId('test-all-llms-item-openai-model-1')).toContainText('连接成功');
  await expect(page.getByTestId('test-all-llms-item-claude-3-5-haiku')).toContainText('连接失败');
  await expect(page.getByTestId('test-all-llms-error-claude-3-5-haiku')).toHaveCount(0);
  await expect(page.getByTestId('test-all-llms')).toHaveCount(0);
  await expect(page.getByTestId('retest-all-llms')).toBeVisible();
  await expect(page.getByTestId('show-all-llms-test-results')).toBeVisible();

  await page.getByTestId('test-all-llms-item-claude-3-5-haiku').click();
  await expect(page.getByTestId('test-all-llms-error-claude-3-5-haiku')).toContainText('invalid anthropic api key');
  await page.keyboard.press('Escape');
  await expect(bulkDialog).toBeHidden();

  await page.getByTestId('show-all-llms-test-results').click();
  await expect(bulkDialog).toBeVisible();
  await expect(page.getByTestId('test-all-llms-item-claude-3-5-haiku')).toContainText('连接失败');
});

test('llms 页面批量测试浮窗层级应高于顶部导航栏', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••openai', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
        _meta: {
          explicit_provider_names: ['openai'],
        },
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/test-llm') && method === 'POST') {
        return new Response(JSON.stringify({ success: true, message: '连接成功' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('test-all-llms').click();
  await expect(page.getByTestId('test-all-llms-dialog')).toBeVisible();

  const zIndex = await page.evaluate(() => {
    const header = document.querySelector('header');
    const dialog = document.querySelector('[data-testid="test-all-llms-dialog"]');
    return {
      header: header ? Number.parseInt(window.getComputedStyle(header).zIndex || '0', 10) : 0,
      dialog: dialog ? Number.parseInt(window.getComputedStyle(dialog).zIndex || '0', 10) : 0,
    };
  });

  expect(zIndex.dialog).toBeGreaterThan(zIndex.header);
});

test('llms 页面批量测试浮窗应由外层裁切圆角，滚动条位于内容区内部', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const llmModels = Object.fromEntries(
      Array.from({ length: 18 }, (_, index) => [
        `openai-model-${index + 1}`,
        { provider: 'openai', model_id: `gpt-4.1-mini-${index + 1}`, timeout: 60, max_output_tokens: 8192 },
      ]),
    );

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••openai', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          ...llmModels,
        },
        default_model: 'openai-model-1',
        _meta: {
          explicit_provider_names: ['openai'],
        },
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-openai-real' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/test-llm') && method === 'POST') {
        return new Response(JSON.stringify({ success: true, message: '连接成功' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('test-all-llms').click();
  await expect(page.getByTestId('test-all-llms-dialog')).toBeVisible();

  const overflow = await page.evaluate(() => {
    const dialog = document.querySelector('[data-testid="test-all-llms-dialog"]');
    const body = document.querySelector('[data-testid="test-all-llms-scroll-body"]');
    return {
      dialogOverflowY: dialog ? window.getComputedStyle(dialog).overflowY : '',
      dialogOverflowX: dialog ? window.getComputedStyle(dialog).overflowX : '',
      bodyOverflowY: body ? window.getComputedStyle(body).overflowY : '',
    };
  });

  expect(overflow.dialogOverflowY).toBe('hidden');
  expect(overflow.dialogOverflowX).toBe('hidden');
  expect(overflow.bodyOverflowY).toBe('auto');
});

test('llms 页面当 secret reveal 返回占位符时不应显示占位符 API Key', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            source_type: 'openai',
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'secret' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/secret?path=llm.providers.openai.api_key') && method === 'GET') {
        return new Response(JSON.stringify({
          path: 'llm.providers.openai.api_key',
          value: '${secret:sensenova_claw/llm.providers.openai.api_key}',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('provider-toggle-openai').click();
  await page.getByTestId('provider-api-key-toggle-openai').click();

  await expect(page.getByText('Secret store 中保存的是占位符，请重新填写真实 API Key')).toBeVisible();
  await expect(page.getByTestId('provider-api-key-input-openai')).not.toHaveValue('${secret:sensenova_claw/llm.providers.openai.api_key}');
});

test('llms 页面普通模式新增 llm 后应立即进入编辑态', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: { source_type: 'openai', api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' }, base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('provider-toggle-openai').click();
  await page.getByTestId('add-llm-button-openai').click();
  await page.getByTestId('new-llm-name-input-openai').fill('gpt-4.1-mini');
  await page.getByTestId('confirm-add-llm-button-openai').click();

  await expect(page.getByTestId('llm-card-gpt-4.1-mini')).toBeVisible();
  await expect(page.getByTestId('llm-model-id-input-gpt-4.1-mini')).toBeEditable();
  await expect(page.getByTestId('llm-save-gpt-4.1-mini')).toBeVisible();
});

test('llms 页面新增重复 llm 名称时应给出提示', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { source_type: 'mock', api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: { source_type: 'openai', api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' }, base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
          test: { source_type: 'openai-compatible', api_key: '', base_url: 'https://proxy.example.com/v1', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-5.4': { provider: 'openai', model_id: 'gpt-5.4', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-5.4',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai', 'test'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/llms');
  await page.getByTestId('provider-toggle-test').click();
  await page.getByTestId('add-llm-button-test').click();
  await page.getByTestId('new-llm-name-input-test').fill('gpt-5.4');
  await page.getByTestId('confirm-add-llm-button-test').click();

  await expect(page.getByText('LLM 名称已存在: gpt-5.4')).toBeVisible();
});
