import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.agentos', 'token'), 'utf-8').trim();
}

test('切换 agent 后应在发送时才切到新 agent 的 session，而不是沿用默认 agent', async ({ page }) => {
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
          { id: 'minimax', name: 'MiniMax 助手', description: 'MiniMax 专用智能体', model: 'MiniMax-M2.7-highspeed' },
        ]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({
          sessions: [
            {
              session_id: 'sess_default_001',
              created_at: 1710000000,
              last_active: 1710000100,
              meta: JSON.stringify({ title: 'Default 历史会话', agent_id: 'default' }),
              status: 'idle',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions/sess_default_001/events')) {
        return new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions/sess_minimax_auto/events')) {
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
        const parsed = JSON.parse(data) as Record<string, unknown>;
        sentMessages.push(parsed);
        (window as typeof window & {
          __wsSentMessages?: Array<Record<string, unknown>>;
        }).__wsSentMessages = sentMessages;

        if (parsed.type === 'create_session') {
          const payload = (parsed.payload || {}) as { agent_id?: string };
          const sessionId = payload.agent_id === 'minimax' ? 'sess_minimax_auto' : 'sess_default_auto';
          setTimeout(() => {
            this.onmessage?.(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'session_created',
                session_id: sessionId,
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

  await page.getByText('Default 历史会话').click();
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
          (message.payload as { session_id?: string }).session_id === 'sess_default_001',
      );
    });
  }).toBe(true);

  await page.getByTestId('chat-agent-selector-button').click();
  await page.getByTestId('chat-agent-option-minimax').click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some(
        (message) =>
          message.type === 'create_session' &&
          typeof message.payload === 'object' &&
          message.payload !== null &&
          (message.payload as { agent_id?: string }).agent_id === 'minimax',
      );
    });
  }).toBe(false);

  await input.fill('请介绍一下你自己');
  await page.getByTestId('send-button').click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some(
        (message) =>
          message.type === 'create_session' &&
          typeof message.payload === 'object' &&
          message.payload !== null &&
          (message.payload as { agent_id?: string }).agent_id === 'minimax',
      );
    });
  }).toBe(true);

  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as typeof window & {
        __wsSentMessages?: Array<Record<string, unknown>>;
      }).__wsSentMessages ?? [];
      return sentMessages.some(
        (message) =>
          message.type === 'user_input' &&
          message.session_id === 'sess_minimax_auto' &&
          typeof message.payload === 'object' &&
          message.payload !== null &&
          (message.payload as { content?: string }).content === '请介绍一下你自己',
      );
    });
  }).toBe(true);
});
