import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('首连失败后应自动重连，无需刷新页面', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    let attempts = 0;
    const NativeWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/agents')) {
        return new Response(JSON.stringify([{ id: 'default', name: 'Default Agent', description: '默认智能体' }]), {
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

      constructor(public url: string) {
        attempts += 1;
        (window as typeof window & { __wsAttempts?: number }).__wsAttempts = attempts;

        setTimeout(() => {
          if (attempts === 1) {
            this.readyState = FakeWebSocket.CLOSED;
            this.onerror?.(new Event('error'));
            this.onclose?.(new CloseEvent('close'));
            return;
          }

          this.readyState = FakeWebSocket.OPEN;
          this.onopen?.(new Event('open'));
        }, 30);
      }

      send(_data: string) {}

      close() {
        this.readyState = FakeWebSocket.CLOSED;
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

  await page.goto('about:blank');
  await page.goto('/chat');

  await expect(page.getByText('Connected')).toBeVisible({ timeout: 8000 });
  await expect.poll(async () => {
    return page.evaluate(() => (window as typeof window & { __wsAttempts?: number }).__wsAttempts ?? 0);
  }).toBeGreaterThanOrEqual(2);
});

test('切换历史会话时应发送 load_session 重新绑定当前连接', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const sentMessages: Array<Record<string, unknown>> = [];
    const NativeWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/agents')) {
        return new Response(JSON.stringify([{ id: 'default', name: 'Default Agent', description: '默认智能体' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({
          sessions: [
            {
              session_id: 'session_rebind_001',
              created_at: 1710000000,
              last_active: 1710000100,
              meta: JSON.stringify({ title: '需要恢复绑定的会话' }),
              status: 'idle',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions/session_rebind_001/events')) {
        return new Response(JSON.stringify({ events: [] }), {
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

      send(data: string) {
        sentMessages.push(JSON.parse(data));
        (window as typeof window & { __wsSentMessages?: Array<Record<string, unknown>> }).__wsSentMessages = sentMessages;
      }

      close() {
        this.readyState = FakeWebSocket.CLOSED;
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

  await page.goto('about:blank');
  await page.goto('/chat');
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 5000 });
  await page.getByText('需要恢复绑定的会话').click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some(
        (message) =>
          message.type === 'load_session' &&
          typeof message.payload === 'object' &&
          message.payload !== null &&
          (message.payload as { session_id?: string }).session_id === 'session_rebind_001',
      );
    });
  }).toBe(true);
});
