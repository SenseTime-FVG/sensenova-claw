import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('agents 页面应显示删除按钮并在确认后调用删除接口', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const deleteCalls: string[] = [];

    const agents = [
      {
        id: 'default',
        name: 'Default Agent',
        status: 'active',
        description: '系统默认智能体',
        provider: 'openai',
        model: 'gpt-4o-mini',
        sessionCount: 1,
        toolCount: 3,
        skillCount: 0,
        lastActive: 'never',
      },
      {
        id: 'helper',
        name: 'Helper Agent',
        status: 'active',
        description: '可删除的测试智能体',
        provider: 'openai',
        model: 'gpt-4o-mini',
        sessionCount: 0,
        toolCount: 2,
        skillCount: 0,
        lastActive: 'never',
      },
    ];

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
        return new Response(JSON.stringify(agents), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/agents/helper') && method === 'DELETE') {
        deleteCalls.push(url);
        const idx = agents.findIndex((agent) => agent.id === 'helper');
        if (idx >= 0) {
          agents.splice(idx, 1);
        }
        (window as typeof window & { __deleteCalls?: string[] }).__deleteCalls = deleteCalls;
        return new Response(JSON.stringify({ status: 'deleted', agent_id: 'helper' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto('/agents');

  await expect(page.getByText('Helper Agent')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('agent-delete-button-helper')).toBeVisible();

  await page.getByTestId('agent-delete-button-helper').click();
  await expect(page.getByTestId('agent-delete-dialog')).toBeVisible();
  await expect(page.getByTestId('agent-delete-dialog')).toContainText('Helper Agent');
  await page.getByTestId('agent-delete-confirm').click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __deleteCalls?: string[] }).__deleteCalls ?? []).length);
  }).toBe(1);

  await expect(page.getByText('Helper Agent')).not.toBeVisible();
});
