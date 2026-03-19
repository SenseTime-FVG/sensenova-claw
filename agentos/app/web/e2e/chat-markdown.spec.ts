import { expect, test } from '@playwright/test';

type MockWindow = Window & {
  __mockWs?: {
    emit: (data: unknown) => void;
  };
  __mockWsSent?: string[];
  WebSocket: typeof globalThis.WebSocket;
};

function mockAuthAndWebSocket() {
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  class MockWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;

    public readyState = MockWebSocket.OPEN;
    public onopen: ((event: Event) => void) | null = null;
    public onclose: ((event: Event) => void) | null = null;
    public onerror: ((event: Event) => void) | null = null;
    public onmessage: ((event: MessageEvent) => void) | null = null;
    public sent: string[] = [];

    constructor(_url: string) {
      (window as unknown as MockWindow).__mockWs = this;
      (window as unknown as MockWindow).__mockWsSent = this.sent;
      window.setTimeout(() => {
        this.onopen?.(new Event('open'));
      }, 0);
    }

    send(data: string) {
      this.sent.push(data);
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.(new Event('close'));
    }

    emit(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  (window as unknown as MockWindow).WebSocket = MockWebSocket as unknown as typeof globalThis.WebSocket;
}

test.describe('chat markdown rendering（mock websocket）', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'u_markdown',
          username: 'markdown-e2e',
          email: null,
          is_active: true,
          is_admin: true,
          created_at: Date.now() / 1000,
          last_login: Date.now() / 1000,
        }),
      });
    });

    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'default', name: 'Default Agent', description: '默认智能体' },
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
              session_id: 'sess_md_history',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: 'Markdown History Session' }),
            },
          ],
        }),
      });
    });

    await page.route('**/api/sessions/*/events', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ events: [] }),
      });
    });

    await page.route('**/api/sessions/*/messages', async (route) => {
      const url = route.request().url();
      const body = url.includes('/api/sessions/sess_md_history/messages')
        ? {
            messages: [
              {
                role: 'assistant',
                content: [
                  '# 历史摘要',
                  '',
                  '| 字段 | 值 |',
                  '| --- | --- |',
                  '| alpha | 1 |',
                  '',
                  '- [x] archived',
                  '<span data-testid="session-evil-html">evil</span>',
                ].join('\n'),
              },
            ],
          }
        : { messages: [] };

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await page.addInitScript(mockAuthAndWebSocket);
  });

  test('chat 页面应把 assistant markdown 渲染为语义化节点', async ({ page }) => {
    await page.goto('/chat');

    await page.evaluate(() => {
      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'session_created',
        session_id: 'sess_md_chat',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });

      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'turn_completed',
        session_id: 'sess_md_chat',
        payload: {
          final_response: [
            '# 今日摘要',
            '',
            '- **重点**',
            '- `inline-code`',
            '',
            '```python',
            'print("hello")',
            '```',
            '',
            '| 列 | 值 |',
            '| --- | --- |',
            '| A | 1 |',
            '',
            '- [x] done',
            '<span data-testid="evil-html">evil</span>',
          ].join('\n'),
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByRole('heading', { level: 1, name: '今日摘要' })).toBeVisible();
    await expect(page.locator('strong')).toContainText('重点');
    await expect(page.locator('pre code')).toContainText('print("hello")');
    await expect(page.locator('table')).toBeVisible();
    await expect(page.locator('input[type="checkbox"]')).toBeChecked();
    await expect(page.getByTestId('evil-html')).toHaveCount(0);
  });

  test('chat 页面 tool 消息应让字符串结果走 markdown、JSON 结果仍走 JSON 查看器', async ({ page }) => {
    await page.goto('/chat');

    await page.evaluate(() => {
      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'session_created',
        session_id: 'sess_md_tool',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });

      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'tool_result',
        session_id: 'sess_md_tool',
        payload: {
          tool_name: 'render_report',
          result: '## 查询条件\n\n- 关键词: AI',
        },
        timestamp: Date.now() / 1000,
      });

      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'tool_result',
        session_id: 'sess_md_tool',
        payload: {
          tool_name: 'search_web',
          result: {
            total: 2,
            items: [{ title: 'A' }],
          },
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByRole('heading', { level: 2, name: '查询条件' })).toBeVisible();
    await expect(page.locator('.json-viewer')).toContainText('"total": 2');
  });

  test('session 详情页也应渲染 markdown 且忽略原始 html', async ({ page }) => {
    await page.goto('/sessions/sess_md_history');

    await expect(page.getByRole('heading', { level: 1, name: '历史摘要' })).toBeVisible();
    await expect(page.locator('table')).toBeVisible();
    await expect(page.locator('input[type="checkbox"]')).toBeChecked();
    await expect(page.getByTestId('session-evil-html')).toHaveCount(0);
  });
});
