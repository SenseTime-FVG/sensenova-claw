import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.agentos', 'token'), 'utf-8').trim();
}

test('llms 页面应支持单项编辑与编辑所有配置', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'agentos_token',
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
          openai: { api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' }, base_url: 'https://api.openai.com/v1', timeout: 60, max_retries: 3 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    const providerPuts: unknown[] = [];
    const modelPuts: unknown[] = [];
    const sectionPuts: unknown[] = [];

    Object.assign(window, {
      __providerPuts: providerPuts,
      __modelPuts: modelPuts,
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

  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toBeDisabled();
  await page.getByTestId('provider-edit-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toBeEditable();
  await page.getByTestId('provider-base-url-input-openai').fill('https://proxy.example.com/v1');
  await page.getByTestId('provider-cancel-openai').click();
  await expect(page.getByTestId('provider-base-url-input-openai')).toHaveValue('https://api.openai.com/v1');

  await page.getByTestId('provider-edit-openai').click();
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
