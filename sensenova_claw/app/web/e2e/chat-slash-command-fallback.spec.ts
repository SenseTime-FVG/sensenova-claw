import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

test('未匹配的 / 命令应作为普通消息发送', async ({ page }) => {
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

      if (url.endsWith('/api/skills')) {
        return new Response(JSON.stringify([
          { name: 'brainstorming', description: '头脑风暴', enabled: true },
        ]), {
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

      if (url.includes('/skill-invoke')) {
        return new Response(JSON.stringify({ detail: '不应该触发 skill-invoke' }), {
          status: 500,
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
        const parsed = JSON.parse(data) as Record<string, unknown>;
        sentMessages.push(parsed);
        (window as typeof window & {
          __wsSentMessages?: Array<Record<string, unknown>>;
        }).__wsSentMessages = sentMessages;

        if (parsed.type === 'create_session') {
          setTimeout(() => {
            this.onmessage?.(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'session_created',
                session_id: 'sess_slash_fallback',
                payload: {},
              }),
            }));
          }, 10);
        }
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

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible({ timeout: 5000 });

  const prompt = '/does-not-exist 帮我做个总结';
  await input.fill(prompt);
  await page.getByTestId('send-button').click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some((message) => message.type === 'create_session');
    });
  }).toBe(true);

  await expect.poll(async () => {
    return page.evaluate((expectedPrompt) => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some(
        (message) =>
          message.type === 'user_input' &&
          message.session_id === 'sess_slash_fallback' &&
          typeof message.payload === 'object' &&
          message.payload !== null &&
          (message.payload as { content?: string }).content === expectedPrompt,
      );
    }, prompt);
  }).toBe(true);
});
