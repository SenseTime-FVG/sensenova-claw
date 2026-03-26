import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('切换语言后应立即刷新界面文案并在刷新后保留', async ({ page }) => {
  const token = readCurrentToken();

  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript((currentToken) => {
    document.cookie = `sensenova_claw_token=${currentToken}; path=/`;

    const nativeFetch = window.fetch.bind(window);
    const NativeWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/agents')) {
        return new Response(JSON.stringify([
          { id: 'default', name: 'Default Agent', description: '默认智能体', model: 'mock-model' },
        ]), {
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

      if (url.includes('/api/proactive/recommendations')) {
        return new Response(JSON.stringify({ recommendations: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };

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
        setTimeout(() => {
          this.readyState = FakeWebSocket.OPEN;
          this.onopen?.(new Event('open'));
        }, 20);
      }

      send() {}

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
  }, token);

  await page.goto('about:blank');
  try {
    await page.goto('/chat', { waitUntil: 'commit' });
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes('ERR_ABORTED')) {
      throw error;
    }
  }

  await expect(page.getByPlaceholder('搜索...')).toBeVisible({ timeout: 30000 });

  await page.getByTestId('user-dropdown-trigger').click();
  await expect(page.getByTestId('locale-option-en-US')).toBeVisible();
  await page.getByTestId('locale-option-en-US').click();

  await expect(page.getByPlaceholder('Search...')).toBeVisible();

  await page.getByTestId('user-dropdown-trigger').click();
  await expect(page.getByText('Settings')).toBeVisible();

  await page.reload();

  await expect(page.getByPlaceholder('Search...')).toBeVisible();
});
