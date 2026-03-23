import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.agentos', 'token'), 'utf-8').trim();
}

test('agents 创建弹窗应提供模型下拉并提交选中模型', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'agentos_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const createCalls: unknown[] = [];

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/agents') && method === 'GET') {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify({
          llm: {
            models: {
              mock: { provider: 'mock', model_id: 'mock-agent-v1' },
              'gpt-4o-mini': { provider: 'openai', model_id: 'gpt-4o-mini' },
              'claude-3-5-haiku': { provider: 'anthropic', model_id: 'claude-3-5-haiku-latest' },
            },
            default_model: 'claude-3-5-haiku',
          },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/agents') && method === 'POST') {
        const bodyText = typeof init?.body === 'string' ? init.body : '{}';
        const body = JSON.parse(bodyText);
        createCalls.push(body);
        (window as typeof window & { __createCalls?: unknown[] }).__createCalls = createCalls;
        return new Response(JSON.stringify({ id: body.id, name: body.name }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto('/agents');

  await page.getByRole('button', { name: /new agent/i }).click();

  const modelSelect = page.getByTestId('agent-model-select');
  await expect(modelSelect).toBeVisible();
  await expect(modelSelect).toHaveValue('claude-3-5-haiku');

  await modelSelect.selectOption('gpt-4o-mini');
  await page.getByPlaceholder('research-agent').fill('research-agent');
  await page.getByPlaceholder('Research Agent').fill('Research Agent');
  await page.getByRole('button', { name: '创建' }).click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __createCalls?: unknown[] }).__createCalls ?? []).length);
  }).toBe(1);

  const createBody = await page.evaluate(() => {
    return (window as typeof window & { __createCalls?: unknown[] }).__createCalls?.[0];
  });

  expect(createBody).toMatchObject({
    id: 'research-agent',
    name: 'Research Agent',
    model: 'gpt-4o-mini',
  });
});
