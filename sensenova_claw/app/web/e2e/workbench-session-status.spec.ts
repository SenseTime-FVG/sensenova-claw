import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('工作台会话列表应根据 last_turn_status 显示运行状态灯', async ({ page }) => {
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
            session_id: 'sess-running',
            created_at: 1710000000,
            last_active: 1710000300,
            meta: JSON.stringify({ title: '运行中会话', agent_id: 'office-main' }),
            status: 'idle',
            last_turn_status: 'started',
          },
          {
            session_id: 'sess-finished',
            created_at: 1710000100,
            last_active: 1710000200,
            meta: JSON.stringify({ title: '已结束会话', agent_id: 'office-main' }),
            status: 'idle',
            last_turn_status: 'completed',
          },
          {
            session_id: 'sess-child',
            created_at: 1710000150,
            last_active: 1710000180,
            meta: JSON.stringify({
              title: '[send_message] 子会话',
              agent_id: 'research-agent',
              parent_session_id: 'sess-running',
            }),
            status: 'idle',
            last_turn_status: 'error',
          },
        ],
      }),
    });
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

  await expect(page.getByText('运行中会话')).toBeVisible();
  await expect(page.getByTestId('workbench-session-status-sess-running')).toHaveAttribute('data-status', 'running');
  await expect(page.getByTestId('workbench-session-status-sess-finished')).toHaveAttribute('data-status', 'idle');
  await expect(page.getByTestId('workbench-session-status-sess-child')).toHaveAttribute('data-status', 'idle');
});

test('工作台会话列表应在实时事件到达时更新状态灯', async ({ page }) => {
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
            session_id: 'sess-live',
            created_at: 1710000000,
            last_active: 1710000300,
            meta: JSON.stringify({ title: '实时状态会话', agent_id: 'office-main' }),
            status: 'idle',
            last_turn_status: 'completed',
          },
        ],
      }),
    });
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
          (window as Window & { __workbenchMockWs?: FakeWebSocket }).__workbenchMockWs = this;
        }, 20);
      }

      send(_data: string) {}
      close() {
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.(new CloseEvent('close'));
      }
      addEventListener() {}
      removeEventListener() {}
      emit(data: unknown) {
        this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
      }
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

  await expect(page.getByTestId('workbench-session-status-sess-live')).toHaveAttribute('data-status', 'idle');

  await page.evaluate(() => {
    (window as Window & { __workbenchMockWs?: { emit: (data: unknown) => void } }).__workbenchMockWs?.emit({
      type: 'tool_execution',
      session_id: 'sess-live',
      payload: { tool_call_id: 'call-live', tool_name: 'send_message', status: 'running', arguments: {} },
    });
  });

  await expect(page.getByTestId('workbench-session-status-sess-live')).toHaveAttribute('data-status', 'running');

  await page.evaluate(() => {
    (window as Window & { __workbenchMockWs?: { emit: (data: unknown) => void } }).__workbenchMockWs?.emit({
      type: 'turn_completed',
      session_id: 'sess-live',
      payload: { turn_id: 'turn-live', final_response: 'done' },
    });
  });

  await expect(page.getByTestId('workbench-session-status-sess-live')).toHaveAttribute('data-status', 'idle');
});
