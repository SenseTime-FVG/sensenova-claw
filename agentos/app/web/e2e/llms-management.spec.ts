import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.agentos', 'token'), 'utf-8').trim();
}

test('llms 页面应支持按 provider 管理 llm 配置并保存', async ({ page }) => {
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
          anthropic: { api_key: '', base_url: 'https://api.anthropic.com', timeout: 45, max_retries: 2 },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini', timeout: 60, max_output_tokens: 8192 },
          'claude-3-5-haiku': { provider: 'anthropic', model_id: 'claude-3-5-haiku-latest', timeout: 45, max_output_tokens: 4096 },
        },
        default_model: 'gpt-4o-mini',
      },
    };

    const putBodies: unknown[] = [];
    let secretRevealCalls = 0;

    Object.assign(window, {
      __llmPutBodies: putBodies,
      __llmSections: state,
      __secretRevealCalls: secretRevealCalls,
    });

    window.confirm = () => true;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai', 'anthropic'] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify((window as typeof window & { __llmSections: typeof state }).__llmSections), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/config/sections') && method === 'PUT') {
        const bodyText = typeof init?.body === 'string' ? init.body : '{}';
        const body = JSON.parse(bodyText);
        putBodies.push(body);
        (window as typeof window & { __llmPutBodies: unknown[] }).__llmPutBodies = putBodies;
        return new Response(JSON.stringify({ status: 'saved' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/secret') && method === 'GET') {
        secretRevealCalls += 1;
        (window as typeof window & { __secretRevealCalls: number }).__secretRevealCalls = secretRevealCalls;
        const parsed = new URL(url);
        if (parsed.searchParams.get('path') === 'llm.providers.openai.api_key') {
          return new Response(JSON.stringify({ path: 'llm.providers.openai.api_key', value: 'sk-real-openai-key' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ detail: 'Not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto('/llms');

  await expect(page.getByRole('link', { name: 'LLMs' })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole('heading', { name: 'LLM 配置' })).toBeVisible();
  await expect(page.getByTestId('provider-card-openai')).toBeVisible();
  await expect(page.getByTestId('provider-card-anthropic')).toBeVisible();
  await expect(page.getByTestId('provider-body-openai')).not.toBeVisible();
  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-body-openai')).toBeVisible();
  await expect(page.getByTestId('llm-card-gpt-4o-mini')).toBeVisible();
  await expect(page.getByTestId('provider-api-key-input-openai')).toHaveValue('******');
  await page.getByTestId('provider-api-key-toggle-openai').click();
  await expect(page.getByTestId('provider-api-key-input-openai')).toHaveValue('sk-real-openai-key');

  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-body-openai')).not.toBeVisible();
  await page.getByTestId('provider-toggle-openai').click();
  await expect(page.getByTestId('provider-body-openai')).toBeVisible();
  await expect.poll(async () => {
    return page.evaluate(() => (window as typeof window & { __secretRevealCalls?: number }).__secretRevealCalls ?? 0);
  }).toBe(1);

  await page.getByTestId('provider-name-input-openai').fill('openai-compatible');
  await page.getByTestId('provider-base-url-input-openai-compatible').fill('https://proxy.example.com/v1');
  await page.getByTestId('provider-timeout-input-openai-compatible').fill('90');

  await page.getByTestId('add-llm-button-openai-compatible').click();
  await page.getByTestId('new-llm-name-input-openai-compatible').fill('gpt-4.1');
  await page.getByTestId('confirm-add-llm-button-openai-compatible').click();

  await page.getByTestId('llm-name-input-gpt-4.1').fill('gpt-4.1-mini');
  await page.getByTestId('llm-model-id-input-gpt-4.1-mini').fill('gpt-4.1-mini');
  await page.getByTestId('llm-max-output-tokens-input-gpt-4.1-mini').fill('16384');

  await page.getByTestId('provider-toggle-anthropic').click();
  await expect(page.getByTestId('provider-body-anthropic')).toBeVisible();
  await page.getByTestId('delete-llm-button-claude-3-5-haiku').click();

  await page.getByTestId('add-provider-button').click();
  await page.getByTestId('new-provider-name-input').fill('deepseek');
  await page.getByTestId('confirm-add-provider-button').click();
  await page.getByTestId('provider-base-url-input-deepseek').fill('https://api.deepseek.com');
  await page.getByTestId('add-llm-button-deepseek').click();
  await page.getByTestId('new-llm-name-input-deepseek').fill('deepseek-chat');
  await page.getByTestId('confirm-add-llm-button-deepseek').click();
  await page.getByTestId('default-model-select').selectOption('deepseek-chat');

  await page.getByTestId('delete-provider-button-anthropic').click();

  await page.getByTestId('save-llm-config').click();
  await expect(page.getByText('已保存')).toBeVisible();

  const lastBody = await page.evaluate(() => {
    const bodies = (window as typeof window & { __llmPutBodies?: unknown[] }).__llmPutBodies ?? [];
    return bodies[bodies.length - 1];
  });

  expect(lastBody).toEqual({
    llm: {
      providers: {
        'openai-compatible': {
          base_url: 'https://proxy.example.com/v1',
          timeout: 90,
          max_retries: 3,
        },
        deepseek: {
          api_key: '',
          base_url: 'https://api.deepseek.com',
          timeout: 60,
          max_retries: 3,
        },
      },
      models: {
        'gpt-4o-mini': {
          provider: 'openai-compatible',
          model_id: 'gpt-4o-mini',
          timeout: 60,
          max_output_tokens: 8192,
        },
        'gpt-4.1-mini': {
          provider: 'openai-compatible',
          model_id: 'gpt-4.1-mini',
          timeout: 60,
          max_output_tokens: 16384,
        },
        'deepseek-chat': {
          provider: 'deepseek',
          model_id: '',
          timeout: 60,
          max_output_tokens: 8192,
        },
      },
      default_model: 'deepseek-chat',
    },
  });
});
