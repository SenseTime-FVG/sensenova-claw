import { expect, test } from '@playwright/test';

function mockAuthAndWebSocket() {
  // 登录态：避免被 ProtectedRoute 重定向到 /login
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
      (window as any).__mockWs = this;
      (window as any).__mockWsSent = this.sent;
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
      const payload = JSON.stringify(data);
      this.onmessage?.({ data: payload } as MessageEvent);
    }
  }

  (window as any).WebSocket = MockWebSocket;
}

test.beforeEach(async ({ page }) => {
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

  await page.route('**/api/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [
          {
            session_id: 'sess_e2e',
            created_at: Date.now() / 1000,
            last_active: Date.now() / 1000,
            status: 'active',
            meta: JSON.stringify({ title: 'E2E Session' }),
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

  await page.addInitScript(mockAuthAndWebSocket);
});

test('ask_user 问题应显示弹窗', async ({ page }) => {
  await page.goto('/chat');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_e2e',
      payload: {
        question_id: 'q_e2e_1',
        question: '请选择部署环境',
        options: ['dev', 'prod'],
        multi_select: false,
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
});

test('chat 页面可提交 ask_user 回答', async ({ page }) => {
  await page.goto('/chat');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'session_created',
      session_id: 'sess_e2e',
      payload: { created_at: Date.now() / 1000 },
      timestamp: Date.now() / 1000,
    });
    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_e2e',
      payload: {
        question_id: 'q_e2e_2',
        question: '请补充你的部署环境',
        options: ['dev', 'prod'],
        multi_select: false,
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('chat-input')).toBeDisabled();
  await page.getByTestId('ask-user-custom-input').fill('staging');
  await page.getByTestId('ask-user-confirm').click();
  await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible();

  const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
  const parsed = sent.map((item) => JSON.parse(item));
  expect(parsed.some((msg) => msg.type === 'user_question_answered' && msg.payload?.question_id === 'q_e2e_2')).toBeTruthy();
});

test('session 页面可处理 ask_user', async ({ page }) => {
  await page.goto('/sessions/sess_e2e');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_e2e',
      payload: {
        question_id: 'q_e2e_3',
        question: '请选择功能',
        options: ['日志', '监控'],
        multi_select: true,
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('current-session-id')).toHaveText('sess_e2e');
});
