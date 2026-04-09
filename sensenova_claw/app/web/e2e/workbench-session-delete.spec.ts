import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('工作台左侧删除含子会话的记录时应弹出作用域确认框', async ({ page }) => {
  const deleteCalls: string[] = [];
  const token = readCurrentToken();

  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/verify-token', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/custom-pages', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ pages: [] }),
    });
  });

  await page.route('**/api/config/llm-status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true }),
    });
  });

  await page.route('**/api/agents', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 'office-main', name: '办公主助手', description: '工作台主智能体' },
        { id: 'research-agent', name: '搜索调研助手', description: '子智能体' },
      ]),
    });
  });

  await page.route('**/api/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [
          {
            session_id: 'sess-root',
            created_at: 1710000000,
            last_active: 1710000300,
            meta: JSON.stringify({ title: '主任务会话', agent_id: 'office-main' }),
            status: 'idle',
            has_children: true,
          },
          {
            session_id: 'sess-child',
            created_at: 1710000100,
            last_active: 1710000200,
            meta: JSON.stringify({
              title: '[send_message] 子会话',
              agent_id: 'research-agent',
              parent_session_id: 'sess-root',
            }),
            status: 'idle',
            has_children: false,
          },
          {
            session_id: 'sess-leaf',
            created_at: 1710000200,
            last_active: 1710000100,
            meta: JSON.stringify({
              title: '普通会话',
              agent_id: 'office-main',
            }),
            status: 'idle',
            has_children: false,
          },
        ],
      }),
    });
  });

  await page.route('**/api/sessions/**', async (route) => {
    const request = route.request();
    if (request.method() === 'DELETE') {
      deleteCalls.push(request.url());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'deleted', session_id: request.url().includes('sess-root') ? 'sess-root' : 'sess-leaf' }),
      });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/cron/jobs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/cron/runs?limit=50', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [] }),
    });
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
      if (urlString.includes('localhost:8000/ws')) {
        return new FakeWebSocket(urlString);
      }
      return new NativeWebSocket(url, protocols);
    }

    Object.assign(MockWebSocket, {
      CONNECTING: FakeWebSocket.CONNECTING,
      OPEN: FakeWebSocket.OPEN,
      CLOSING: FakeWebSocket.CLOSING,
      CLOSED: FakeWebSocket.CLOSED,
    });

    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });

  await page.goto('/');

  await expect(page.getByText('主任务会话')).toBeVisible();
  await page.getByTestId('workbench-delete-session-sess-root').click({ force: true });
  await expect(page.getByTestId('workbench-session-delete-dialog')).toBeVisible();
  await expect(page.getByTestId('workbench-session-delete-dialog')).toContainText('存在子会话');
  await page.getByTestId('workbench-session-delete-descendants-confirm').click();

  await expect.poll(() => deleteCalls.at(-1) ?? '').toContain('scope=self_and_descendants');

  await expect(page.getByText('普通会话')).toBeVisible();
  await page.getByTestId('workbench-delete-session-sess-leaf').click({ force: true });
  await expect(page.getByTestId('workbench-session-delete-dialog')).toBeHidden();
  await page.getByTestId('workbench-delete-session-sess-leaf').click({ force: true });
  await expect.poll(() => deleteCalls.at(-1) ?? '').toContain('/api/sessions/sess-leaf');
  await expect.poll(() => deleteCalls.at(-1) ?? '').not.toContain('scope=self_and_descendants');
});
