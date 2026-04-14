import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('mcp 页面应支持 JSON 导入并保存 server 配置', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([
    {
      name: 'sensenova_claw_token',
      value: token,
      domain: 'localhost',
      path: '/',
    },
  ]);

  await page.addInitScript((currentToken) => {
    document.cookie = `sensenova_claw_token=${currentToken}; path=/`;
    localStorage.setItem('access_token', 'e2e-access-token');
    localStorage.setItem('refresh_token', 'e2e-refresh-token');

    const nativeFetch = window.fetch.bind(window);
    const state = {
      servers: [
        {
          name: 'docs-search',
          transport: 'sse',
          command: '',
          args: [],
          env: [],
          cwd: '',
          url: 'http://127.0.0.1:3100/sse',
          headers: [{ key: 'Authorization', value: 'Bearer ${DOCS_MCP_TOKEN}' }],
          timeout: 15,
        },
      ],
    };
    const putBodies: unknown[] = [];
    Object.assign(window, { __mcpPutBodies: putBodies });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/me')) {
        return new Response(JSON.stringify({
          user_id: 'u_e2e',
          username: 'e2e',
          email: null,
          is_active: true,
          is_admin: true,
          created_at: Date.now() / 1000,
          last_login: Date.now() / 1000,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/auth/status') || url.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['mock'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/mcp/servers') && method === 'GET') {
        return new Response(JSON.stringify(state), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/mcp/servers') && method === 'PUT') {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
        putBodies.push(body);
        state.servers = body.servers;
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  }, token);

  await page.goto('/mcp');

  await expect(page.getByRole('link', { name: 'MCP' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'MCP Registry' })).toBeVisible();
  await expect(page.getByText('docs-search')).toBeVisible();

  await page.getByRole('button', { name: 'Import JSON' }).click();
  await page.getByTestId('mcp-import-textarea').fill(`{
  "mcpServers": {
    "browsermcp": {
      "command": "npx",
      "args": ["@browsermcp/mcp@latest"]
    }
  }
}`);
  await page.getByRole('button', { name: 'Import' }).click();

  await expect(page.getByRole('heading', { name: 'browsermcp' })).toBeVisible();
  await expect(page.getByTestId('mcp-command-browsermcp')).toHaveValue('npx');

  await page.getByRole('button', { name: 'Save All' }).click();

  const bodies = await page.evaluate(() => (window as typeof window & { __mcpPutBodies?: unknown[] }).__mcpPutBodies || []);
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({
    servers: expect.arrayContaining([
      expect.objectContaining({
        name: 'browsermcp',
        transport: 'stdio',
        command: 'npx',
        args: ['@browsermcp/mcp@latest'],
      }),
    ]),
  });
});
