import { expect, test } from '@playwright/test';

test('工作台最近对话应显示深度 2 的 subagent 会话', async ({ page }) => {
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: 'test-token',
    url: 'http://localhost:3101',
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
        { id: 'write-agent', name: '写作助手', description: '子智能体' },
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
            meta: JSON.stringify({ title: '最新大模型新闻调研', agent_id: 'office-main' }),
            status: 'idle',
          },
          {
            session_id: 'sess-child',
            created_at: 1710000100,
            last_active: 1710000200,
            meta: JSON.stringify({
              title: '[send_message] 请调研新闻源',
              agent_id: 'research-agent',
              parent_session_id: 'sess-root',
            }),
            status: 'idle',
          },
          {
            session_id: 'sess-grandchild',
            created_at: 1710000150,
            last_active: 1710000180,
            meta: JSON.stringify({
              title: '[send_message] 请整理结论',
              agent_id: 'write-agent',
              parent_session_id: 'sess-child',
            }),
            status: 'idle',
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

  await expect(page.getByText('最新大模型新闻调研')).toBeVisible();
  await expect(page.getByText('[send_message] 请调研新闻源')).toBeVisible();
  await expect(page.getByText('[send_message] 请整理结论')).toBeVisible();
});
