import { expect, test } from '@playwright/test';

type MockWindow = Window & {
  __mockWs?: {
    emit: (data: unknown) => void;
  };
  __mockWsSent?: string[];
  WebSocket: typeof globalThis.WebSocket;
};

function mockAuthAndWebSocket() {
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
    private listeners: Record<string, Array<(event: Event | MessageEvent) => void>> = {};

    constructor(url: string) {
      if (url.includes('/ws')) {
        (window as unknown as MockWindow).__mockWs = this;
        (window as unknown as MockWindow).__mockWsSent = this.sent;
      }
      window.setTimeout(() => {
        const event = new Event('open');
        this.onopen?.(event);
        (this.listeners.open || []).forEach((listener) => listener(event));
      }, 0);
    }

    send(data: string) {
      this.sent.push(data);
    }

    addEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] ??= [];
      this.listeners[type].push(listener);
    }

    removeEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener);
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.(new Event('close'));
      (this.listeners.close || []).forEach((listener) => listener(new Event('close')));
    }

    emit(data: unknown) {
      const event = { data: JSON.stringify(data) } as MessageEvent;
      this.onmessage?.(event);
      (this.listeners.message || []).forEach((listener) => listener(event));
    }
  }

  (window as unknown as MockWindow).WebSocket = MockWebSocket as unknown as typeof globalThis.WebSocket;
}

test.describe('chat markdown rendering（mock websocket）', () => {
  test.beforeEach(async ({ page }) => {
    await page.context().addCookies([
      {
        name: 'agentos_token',
        value: 'e2e-agentos-token',
        domain: '127.0.0.1',
        path: '/',
      },
      {
        name: 'agentos_token',
        value: 'e2e-agentos-token',
        domain: 'localhost',
        path: '/',
      },
    ]);

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

    await page.route('**/api/auth/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
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
    await page.waitForFunction(() => Boolean((window as unknown as MockWindow).__mockWs));

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

  test('chat 页面应把非流式 think 内容渲染为默认折叠的思考块', async ({ page }) => {
    await page.goto('/chat');
    await page.waitForFunction(() => Boolean((window as unknown as MockWindow).__mockWs));

    await page.evaluate(() => {
      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'session_created',
        session_id: 'sess_md_think_static',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });

      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'turn_completed',
        session_id: 'sess_md_think_static',
        payload: {
          final_response: '<think>先分析用户意图\\n再组织回答</think>你好！有什么我可以帮助你的吗？',
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('assistant-think-toggle')).toBeVisible();
    await expect(page.getByText('你好！有什么我可以帮助你的吗？')).toBeVisible();
    await expect(page.getByTestId('assistant-think-content')).toBeHidden();

    await page.getByTestId('assistant-think-toggle').click();
    await expect(page.getByTestId('assistant-think-content')).toContainText('先分析用户意图');
    await expect(page.getByTestId('assistant-think-content')).toContainText('再组织回答');
  });

  test('chat 页面应在 llm_result 阶段展开 think，turn_completed 后自动折叠', async ({ page }) => {
    await page.goto('/chat');
    await page.waitForFunction(() => Boolean((window as unknown as MockWindow).__mockWs));

    await page.evaluate(() => {
      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'session_created',
        session_id: 'sess_md_think_stream',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });

      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'llm_result',
        session_id: 'sess_md_think_stream',
        payload: {
          turn_id: 'turn_stream_1',
          content: '最终答案',
          reasoning_details: [
            { type: 'thinking', thinking: '先判断这是一个问候' },
            { type: 'thinking', thinking: '再给出友好回复' },
          ],
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('assistant-think-content')).toBeVisible();
    await expect(page.getByTestId('assistant-think-content')).toContainText('先判断这是一个问候');
    await expect(page.getByText('最终答案')).toBeVisible();

    await page.evaluate(() => {
      (window as unknown as MockWindow).__mockWs!.emit({
        type: 'turn_completed',
        session_id: 'sess_md_think_stream',
        payload: {
          turn_id: 'turn_stream_1',
          final_response: '<think>先判断这是一个问候\\n再给出友好回复</think>最终答案',
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('assistant-think-content')).toBeHidden();
    await expect(page.getByText('最终答案')).toBeVisible();
  });

  test('chat 页面 tool 消息应让字符串结果走 markdown、JSON 结果仍走 JSON 查看器', async ({ page }) => {
    await page.goto('/chat');
    await page.waitForFunction(() => Boolean((window as unknown as MockWindow).__mockWs));

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
