import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

function installMockChatApp() {
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  const sentMessages: Array<Record<string, unknown>> = [];
  const NativeWebSocket = window.WebSocket;

  class MockWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;

    public readyState = MockWebSocket.CONNECTING;
    public onopen: ((event: Event) => void) | null = null;
    public onclose: ((event: Event) => void) | null = null;
    public onerror: ((event: Event) => void) | null = null;
    public onmessage: ((event: MessageEvent) => void) | null = null;

    constructor(_url: string) {
      (window as Window & { __mockWsSentMessages?: Array<Record<string, unknown>> }).__mockWsSentMessages = sentMessages;
      window.setTimeout(() => {
        this.readyState = MockWebSocket.OPEN;
        this.onopen?.(new Event('open'));
      }, 0);
    }

    send(data: string) {
      const parsed = JSON.parse(data) as Record<string, unknown>;
      sentMessages.push(parsed);
      (window as Window & { __mockWsSentMessages?: Array<Record<string, unknown>> }).__mockWsSentMessages = sentMessages;

      if (parsed.type === 'create_session') {
        const agentId = typeof parsed.payload === 'object' && parsed.payload
          ? String((parsed.payload as { agent_id?: string }).agent_id || 'default')
          : 'default';
        window.setTimeout(() => {
          this.onmessage?.(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'session_created',
              session_id: `sess_${agentId}_auto`,
              payload: {},
            }),
          }));
        }, 10);
      }
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.(new Event('close'));
    }

    addEventListener() {}

    removeEventListener() {}
  }

  function PatchedWebSocket(url: string | URL, protocols?: string | string[]) {
    const urlString = String(url);
    if (urlString.includes('localhost:8000/ws')) {
      return new MockWebSocket(urlString);
    }
    return new NativeWebSocket(url, protocols);
  }

  Object.assign(PatchedWebSocket, {
    CONNECTING: MockWebSocket.CONNECTING,
    OPEN: MockWebSocket.OPEN,
    CLOSING: MockWebSocket.CLOSING,
    CLOSED: MockWebSocket.CLOSED,
  });

  Object.defineProperty(window, 'WebSocket', {
    configurable: true,
    writable: true,
    value: PatchedWebSocket,
  });
}

async function expectNoUserInputSent(page: Parameters<typeof test>[0]['page']) {
  await expect.poll(async () => {
    return page.evaluate(() => {
      const sentMessages = (window as Window & {
        __mockWsSentMessages?: Array<Record<string, unknown>>;
      }).__mockWsSentMessages ?? [];
      return sentMessages.some((message) => message.type === 'user_input');
    });
  }).toBe(false);
}

async function expectUserInputSent(page: Parameters<typeof test>[0]['page'], sessionId: string, content: string) {
  await expect.poll(async () => {
    return page.evaluate(
      ({ expectedSessionId, expectedContent }) => {
        const sentMessages = (window as Window & {
          __mockWsSentMessages?: Array<Record<string, unknown>>;
        }).__mockWsSentMessages ?? [];
        return sentMessages.some(
          (message) =>
            message.type === 'user_input'
            && message.session_id === expectedSessionId
            && typeof message.payload === 'object'
            && message.payload !== null
            && (message.payload as { content?: string }).content === expectedContent,
        );
      },
      { expectedSessionId: sessionId, expectedContent: content },
    );
  }).toBe(true);
}

test.describe('聊天输入框 IME 回车保护', () => {
  test.beforeEach(async ({ page }) => {
    const token = readCurrentToken();
    await page.context().addCookies([{
      name: 'sensenova_claw_token',
      value: token,
      domain: 'localhost',
      path: '/',
    }]);

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'u_e2e',
          username: 'e2e',
          email: null,
          is_active: true,
          is_admin: true,
          created_at: Date.now() / 1000,
          last_login: Date.now() / 1000,
        }),
      });
    });

    await page.route('**/api/auth/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
      });
    });

    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'default', name: 'Default Agent', description: '默认智能体', model: 'mock-model' },
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
              session_id: 'sess_existing',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '现有会话', agent_id: 'default' }),
            },
          ],
        }),
      });
    });

    await page.route('**/api/sessions/*/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ messages: [] }),
      });
    });

    await page.route('**/api/sessions/*/events', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ events: [] }),
      });
    });

    await page.addInitScript(installMockChatApp);
  });

  test('工作台当前会话在拼音组合输入时按 Enter 不应发送，结束组合后仍可发送', async ({ page }) => {
    await page.goto('/');

    await page.getByText('现有会话').click();

    const input = page.getByTestId('chat-input');
    await expect(input).toBeVisible({ timeout: 5000 });
    await input.fill('pinyin');

    await input.dispatchEvent('compositionstart');
    await input.press('Enter');

    await expect(input).toHaveValue(/pinyin/);
    await expectNoUserInputSent(page);

    await input.dispatchEvent('compositionend');
    await input.press('Enter');

    await expectUserInputSent(page, 'sess_existing', 'pinyin');
  });

  test('/sessions/[id] 在拼音组合输入时按 Enter 不应发送，结束组合后仍可发送', async ({ page }) => {
    await page.goto('/sessions/sess_existing');

    const input = page.getByTestId('chat-input');
    await expect(input).toBeVisible({ timeout: 5000 });
    await input.fill('pinyin');

    await input.dispatchEvent('compositionstart');
    await input.press('Enter');

    await expect(input).toHaveValue(/pinyin/);
    await expectNoUserInputSent(page);

    await input.dispatchEvent('compositionend');
    await input.press('Enter');

    await expectUserInputSent(page, 'sess_existing', 'pinyin');
  });
});
