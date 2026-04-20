import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

const mockSessions = [
  {
    session_id: 'sess-alpha',
    created_at: 1710000000,
    last_active: 1710000100,
    meta: JSON.stringify({ title: '对话一', agent_id: 'office-main' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
  {
    session_id: 'sess-beta',
    created_at: 1710000200,
    last_active: 1710000300,
    meta: JSON.stringify({ title: '对话二', agent_id: 'office-main' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
];

const mockPptSessions = [
  {
    session_id: 'ppt-alpha',
    created_at: 1710000000,
    last_active: 1710000100,
    meta: JSON.stringify({ title: 'PPT 对话一', agent_id: 'ppt-agent' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
  {
    session_id: 'ppt-beta',
    created_at: 1710000200,
    last_active: 1710000300,
    meta: JSON.stringify({ title: 'PPT 对话二', agent_id: 'ppt-agent' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
];

const mockWorkbenchSessions = [
  {
    session_id: 'workbench-alpha',
    created_at: 1710000000,
    last_active: 1710000100,
    meta: JSON.stringify({ title: '工作台对话一', agent_id: 'office-main' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
  {
    session_id: 'workbench-beta',
    created_at: 1710000200,
    last_active: 1710000300,
    meta: JSON.stringify({ title: '工作台对话二', agent_id: 'office-main' }),
    status: 'idle',
    last_turn_status: 'completed',
  },
];

async function mockSharedApis(page: Page, sessions: typeof mockSessions) {
  await page.route('**/api/auth/status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/verify-token', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/me', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/config/llm-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true }),
    });
  });

  await page.route('**/api/custom-pages', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ pages: [] }),
    });
  });

  await page.route(/.*\/api\/todolist(?:\/.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/proactive/recommendations**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/cron/jobs', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/cron/runs*', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [] }),
    });
  });

  await page.route('**/api/skills', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/files/roots', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ roots: [] }),
    });
  });

  await page.route('**/api/agents*', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 'office-main', name: '办公主助手', description: '工作台主智能体' },
        { id: 'ppt-agent', name: 'PPT 助手', description: 'PPT 专用智能体' },
      ]),
    });
  });

  await page.route('**/api/sessions**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/api/sessions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions,
          page: 1,
          page_size: 50,
          total: sessions.length,
          active_total: 0,
          total_pages: 1,
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.route('**/api/sessions/*/events', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ events: [] }),
    });
  });

  await page.route('**/api/sessions/*/messages', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ messages: [] }),
    });
  });
}

async function installFakeWebSocket(page: Page, storeKey: string) {
  await page.addInitScript((key: string) => {
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
        }, 10);
        (window as Window & Record<string, unknown>)[key] = this;
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
      if (urlString.includes('/ws')) {
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
  }, storeKey);
}

test('聊天页切换会话时应保留各自输入框草稿', async ({ page }) => {
  const token = readCurrentToken();

  await mockSharedApis(page, mockSessions);
  await installFakeWebSocket(page, '__chatDraftIsolationWs');

  await page.goto(`/chat?token=${encodeURIComponent(token)}`);

  const sessionList = page.locator('#session-list');

  await sessionList.getByText('对话一').click();
  const input = page.getByTestId('chat-input');
  await expect(input).toBeEnabled();

  await input.fill('111');
  await expect(input).toHaveValue('111');

  await sessionList.getByText('对话二').click();
  await expect(input).toHaveValue('');

  await input.fill('222');
  await expect(input).toHaveValue('222');

  await sessionList.getByText('对话一').click();
  await expect(input).toHaveValue('111');

  await sessionList.getByText('对话二').click();
  await expect(input).toHaveValue('222');
});

test('PPT 页切换会话时应保留各自输入框草稿', async ({ page }) => {
  const token = readCurrentToken();

  await mockSharedApis(page, mockPptSessions);
  await installFakeWebSocket(page, '__pptDraftIsolationWs');

  await page.goto(`/ppt?token=${encodeURIComponent(token)}`);

  const input = page.getByTestId('chat-input');
  await expect(input).toBeEnabled();

  await page.getByText('PPT 对话一').click();
  await input.fill('111');
  await expect(input).toHaveValue('111');

  await page.getByText('PPT 对话二').click();
  await expect(input).toHaveValue('');

  await input.fill('222');
  await expect(input).toHaveValue('222');

  await page.getByText('PPT 对话一').click();
  await expect(input).toHaveValue('111');

  await page.getByText('PPT 对话二').click();
  await expect(input).toHaveValue('222');
});

test('工作台切换会话时应保留各自输入框草稿', async ({ page }) => {
  const token = readCurrentToken();

  await mockSharedApis(page, mockWorkbenchSessions);
  await installFakeWebSocket(page, '__workbenchDraftIsolationWs');

  await page.goto(`/?token=${encodeURIComponent(token)}`);

  const input = page.getByTestId('chat-input');
  await expect(input).toBeEnabled();

  await page.getByText('工作台对话一').click();
  await input.fill('111');
  await expect(input).toHaveValue('111');

  await page.getByText('工作台对话二').click();
  await expect(input).toHaveValue('');

  await input.fill('222');
  await expect(input).toHaveValue('222');

  await page.getByText('工作台对话一').click();
  await expect(input).toHaveValue('111');

  await page.getByText('工作台对话二').click();
  await expect(input).toHaveValue('222');
});
