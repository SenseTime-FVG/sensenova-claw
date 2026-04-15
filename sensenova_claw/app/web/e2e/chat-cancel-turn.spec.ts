import { expect, test } from '@playwright/test';

function mockAuthAndWebSocket() {
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');
  (window as Window & { __mockWsSent?: Array<Record<string, unknown>> }).__mockWsSent = [];

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

    constructor(_url: string) {
      (window as Window & { __mockWs?: MockWebSocket }).__mockWs = this;
      window.setTimeout(() => {
        this.onopen?.(new Event('open'));
      }, 0);
    }

    send(data: string) {
      try {
        const parsed = JSON.parse(data) as Record<string, unknown>;
        const sent = (window as Window & { __mockWsSent?: Array<Record<string, unknown>> }).__mockWsSent;
        sent?.push(parsed);
      } catch {
        // noop
      }
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

  (window as Window & typeof globalThis).WebSocket = MockWebSocket as unknown as typeof WebSocket;
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
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.addInitScript(mockAuthAndWebSocket);
});

test('cancelled turn ignores late llm deltas and unlocks input', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible({ timeout: 10000 });
  await expect(input).toBeEnabled();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'agent_thinking',
      session_id: 'sess_cancel',
      payload: {},
      timestamp: Date.now() / 1000,
    });
    (window as any).__mockWs.emit({
      type: 'llm_delta',
      session_id: 'sess_cancel',
      payload: {
        turn_id: 'turn_cancel',
        content_delta: 'a',
        content_snapshot: 'a',
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('stop-button')).toBeVisible();
  await expect(input).toBeDisabled();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'turn_cancelled',
      session_id: 'sess_cancel',
      payload: {
        turn_id: 'turn_cancel',
        reason: 'user_cancel',
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('stop-button')).toBeHidden();
  await expect(input).toBeEnabled();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'llm_delta',
      session_id: 'sess_cancel',
      payload: {
        turn_id: 'turn_cancel',
        content_delta: 'b',
        content_snapshot: 'ab',
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('stop-button')).toBeHidden();
  await expect(input).toBeEnabled();
});

test('首条消息创建会话时在首个 token 前也应显示停止按钮', async ({ page }) => {
  await page.route('**/api/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.route('**/api/cron/runs?limit=50', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [] }),
    });
  });

  await page.goto('/automation');

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible({ timeout: 10000 });
  await expect(input).toBeEnabled();

  await input.fill('第一条消息');
  await page.getByTestId('send-button').click();

  await expect(page.locator('.bubble.user').last()).toHaveText('第一条消息');
  await expect(page.getByTestId('stop-button')).toBeVisible();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'session_created',
      session_id: 'sess_first_turn',
      payload: {},
      timestamp: Date.now() / 1000,
    });
  });

  await expect(page.getByTestId('stop-button')).toBeVisible();
});

test('当前会话 ask_user 期间仍应允许终止，并立即进入终止中状态', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible({ timeout: 10000 });

  await input.fill('请开始研究');
  await page.getByTestId('send-button').click();
  await expect(page.getByTestId('stop-button')).toBeVisible();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'session_created',
      session_id: 'sess_question_stop',
      payload: {},
      timestamp: Date.now() / 1000,
    });
    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_question_stop',
      payload: {
        question_id: 'q_stop_1',
        question: '请选择部署环境',
        source_agent_id: 'research-agent',
        source_agent_name: 'Research Agent',
        options: ['staging', 'prod'],
        multi_select: false,
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  const stopButton = page.getByTestId('stop-button');
  await expect(stopButton).toBeVisible();
  await stopButton.click();

  await expect(stopButton).toBeDisabled();
  await expect(stopButton).toHaveAttribute('title', '终止中');

  const sentMessages = await page.evaluate(() => (window as any).__mockWsSent ?? []);
  expect(sentMessages.some((msg: Record<string, unknown>) => msg.type === 'cancel_turn' && msg.session_id === 'sess_question_stop')).toBeTruthy();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'turn_cancelled',
      session_id: 'sess_question_stop',
      payload: {
        turn_id: 'turn_question_stop',
        reason: 'user_cancel',
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(stopButton).toBeHidden();
});
