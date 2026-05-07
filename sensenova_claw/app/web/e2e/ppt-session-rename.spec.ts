import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('PPT 页面会话支持右键重命名', async ({ page }) => {
  const token = readCurrentToken();
  let title = 'PPT 旧标题';
  const patchCalls: string[] = [];

  await page.context().addCookies([{ name: 'sensenova_claw_token', value: token, domain: 'localhost', path: '/' }]);

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true }) });
  });
  await page.route('**/api/auth/verify-token', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true }) });
  });
  await page.route('**/api/agents', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 'ppt-agent', name: 'PPT 助手', description: 'ppt', status: 'active', model: 'mock' }]),
    });
  });
  await page.route('**/api/files/roots', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ roots: [] }) });
  });
  await page.route('**/api/sessions**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname === '/api/sessions') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [
            {
              session_id: 'sess_ppt_001',
              created_at: 1710000000,
              last_active: 1710000300,
              meta: JSON.stringify({ title, agent_id: 'ppt-agent' }),
              status: 'active',
              has_children: false,
            },
          ],
          total: 1,
          total_pages: 1,
          active_total: 1,
          page: 1,
          page_size: 1,
        }),
      });
      return;
    }
    if (request.method() === 'PATCH' && url.pathname === '/api/sessions/sess_ppt_001') {
      const body = request.postDataJSON() as { title: string };
      title = body.title;
      patchCalls.push(title);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          session: {
            session_id: 'sess_ppt_001',
            created_at: 1710000000,
            last_active: 1710000300,
            meta: { title, agent_id: 'ppt-agent' },
            status: 'active',
            has_children: false,
          },
        }),
      });
      return;
    }
    await route.fallback();
  });

  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket;
    class FakeWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      readyState = FakeWebSocket.CONNECTING;
      onopen: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {
        window.setTimeout(() => {
          this.readyState = FakeWebSocket.OPEN;
          this.onopen?.(new Event('open'));
        }, 20);
      }
      send(_data: string) {}
      close() {
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.(new CloseEvent('close'));
      }
      addEventListener() {}
      removeEventListener() {}
    }
    function MockWebSocket(url: string | URL, protocols?: string | string[]) {
      const urlString = String(url);
      if (urlString.includes('/ws')) return new FakeWebSocket(urlString);
      return new NativeWebSocket(url, protocols);
    }
    Object.assign(MockWebSocket, FakeWebSocket);
    Object.defineProperty(window, 'WebSocket', { configurable: true, writable: true, value: MockWebSocket });
  });

  await page.goto(`/ppt?token=${encodeURIComponent(token)}`);

  await expect(page.getByText('PPT 旧标题')).toBeVisible();
  await page.getByTestId('ppt-session-item-sess_ppt_001').click({ button: 'right' });
  await expect(page.getByTestId('ppt-session-context-menu')).toBeVisible();
  await page.getByTestId('ppt-session-context-menu-rename').click();
  await page.getByTestId('ppt-rename-input-sess_ppt_001').fill('PPT 新标题');
  await page.getByTestId('ppt-rename-input-sess_ppt_001').press('Enter');

  await expect.poll(() => patchCalls.at(-1) ?? '').toBe('PPT 新标题');
  await expect(page.getByText('PPT 新标题')).toBeVisible();
});
