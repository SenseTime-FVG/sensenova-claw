import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('sessions 页面支持右键重命名标题', async ({ page }) => {
  const token = readCurrentToken();

  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const patchCalls: Array<Record<string, unknown>> = [];
    const sessions = [
      {
        session_id: 'sess_manage_001',
        created_at: 1710000000,
        last_active: 1710003600,
        status: 'active',
        meta: JSON.stringify({ title: '管理页旧标题', agent_id: 'helper' }),
      },
    ];

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';
      const parsed = new URL(url, window.location.origin);

      if (parsed.pathname.includes('/api/auth/status') || parsed.pathname.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (parsed.pathname.endsWith('/api/sessions') && method === 'GET') {
        return new Response(JSON.stringify({
          sessions,
          page: 1,
          page_size: 50,
          total: sessions.length,
          total_pages: 1,
          active_total: 1,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (parsed.pathname.endsWith('/api/sessions/sess_manage_001') && method === 'PATCH') {
        const body = JSON.parse(String(init?.body ?? '{}'));
        patchCalls.push(body);
        sessions[0].meta = JSON.stringify({ title: body.title, agent_id: 'helper' });
        (window as typeof window & { __sessionRenamePatchCalls?: Array<Record<string, unknown>> }).__sessionRenamePatchCalls = patchCalls;
        return new Response(JSON.stringify({
          ok: true,
          session: {
            ...sessions[0],
            meta: { title: body.title, agent_id: 'helper' },
          },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (parsed.pathname.endsWith('/api/agents') && method === 'GET') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto(`/sessions?token=${encodeURIComponent(token)}`);

  await expect(page.getByText('管理页旧标题')).toBeVisible({ timeout: 10000 });
  await page.getByTestId('sessions-title-cell-sess_manage_001').click({ button: 'right' });
  await expect(page.getByTestId('sessions-context-menu')).toBeVisible();
  await page.getByTestId('sessions-context-menu-rename').click();
  await page.getByTestId('sessions-rename-input-sess_manage_001').fill('管理页新标题');
  await page.getByTestId('sessions-rename-input-sess_manage_001').press('Enter');

  await expect.poll(async () => (
    page.evaluate(() => ((window as typeof window & {
      __sessionRenamePatchCalls?: Array<Record<string, unknown>>;
    }).__sessionRenamePatchCalls ?? []).length)
  )).toBe(1);

  await expect(page.getByText('管理页新标题')).toBeVisible();
});
