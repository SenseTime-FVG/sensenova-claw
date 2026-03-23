import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.agentos', 'token'), 'utf-8').trim();
}

test('工作台最近对话 + 号应只切回新的空白对话窗口，不立即创建 session', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'agentos_token',
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
        return new Response(JSON.stringify([
          { id: 'default', name: 'Default Agent', description: '默认智能体', model: 'gemini-default' },
          { id: 'office-main', name: 'Office Main', description: '工作台主智能体', model: 'office-v1' },
        ]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({
          sessions: [
            {
              session_id: 'sess_office_001',
              created_at: 1710000000,
              last_active: 1710000100,
              meta: JSON.stringify({ title: '旧会话', agent_id: 'office-main' }),
              status: 'idle',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions/sess_office_001/events')) {
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
        (window as typeof window & {
          __wsSentMessages?: Array<Record<string, unknown>>;
        }).__wsSentMessages = sentMessages;
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
  await page.goto('/');
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 5000 });

  await page.getByText('旧会话').click();
  await expect(page.getByText('Session:')).toBeVisible({ timeout: 5000 });

  await page.getByTestId('recent-chats-new-button').click();

  await expect(page.getByText('你想做什么？')).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 5000 });
  await expect(page.getByText('Session:')).toHaveCount(0);
  await expect(page.getByTestId('recent-chats-agent-dialog')).toHaveCount(0);

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some((message) => message.type === 'create_session');
    });
  }).toBe(false);
});
