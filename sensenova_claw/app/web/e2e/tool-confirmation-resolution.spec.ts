import { expect, test } from '@playwright/test';

function installMockToolConfirmationApp() {
  const NativeWebSocket = window.WebSocket;
  const nativeFetch = window.fetch.bind(window);
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  const queuedMessages: unknown[] = [];
  const sentMessages: string[] = [];
  (window as any).__mockWsSent = sentMessages;
  (window as any).__mockWs = {
    emit(data: unknown) {
      queuedMessages.push(data);
    },
  };

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
    const { pathname } = new URL(url, window.location.origin);

    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

    if (pathname.endsWith('/api/auth/status') || pathname.endsWith('/api/auth/verify-token')) {
      return json({ authenticated: true });
    }
    if (pathname.endsWith('/api/config/llm-status')) {
      return json({ configured: true });
    }
    if (pathname.endsWith('/api/auth/me')) {
      return json({
        user_id: 'u_e2e',
        username: 'e2e',
        email: null,
        is_active: true,
        is_admin: true,
        created_at: Date.now() / 1000,
        last_login: Date.now() / 1000,
      });
    }
    if (pathname.endsWith('/api/sessions')) {
      return json({
        sessions: [
          {
            session_id: 'sess_e2e',
            created_at: Date.now() / 1000,
            last_active: Date.now() / 1000,
            status: 'active',
            meta: JSON.stringify({ title: 'E2E Session' }),
          },
        ],
      });
    }
    if (/\/api\/sessions\/[^/]+\/messages$/.test(pathname)) {
      return json({ messages: [] });
    }
    if (/\/api\/sessions\/[^/]+\/events$/.test(pathname)) {
      return json({ events: [] });
    }
    if (pathname.endsWith('/api/agents')) {
      return json([
        {
          id: 'default',
          name: 'Default Agent',
          description: '默认助手',
          status: 'active',
          model: 'mock',
        },
      ]);
    }
    if (pathname.endsWith('/api/config/required-check')) {
      return json({ missing: [] });
    }
    if (pathname.endsWith('/api/files/roots')) {
      return json({ roots: [] });
    }
    if (pathname.endsWith('/api/skills') || pathname.endsWith('/api/custom-pages')) {
      return json([]);
    }
    if (/\/api\/todolist\/[^/]+$/.test(pathname)) {
      return json({ date: pathname.split('/').pop(), items: [] });
    }

    return nativeFetch(input, init);
  };

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

    constructor(url: string | URL, protocols?: string | string[]) {
      const resolvedUrl = String(url);
      if (!resolvedUrl.includes('localhost:8000/ws')) {
        return new NativeWebSocket(url, protocols) as unknown as MockWebSocket;
      }

      (window as any).__mockWs = this;
      window.setTimeout(() => {
        this.onopen?.(new Event('open'));
        queuedMessages.splice(0).forEach((message) => this.emit(message));
      }, 0);
    }

    send(data: string) {
      sentMessages.push(data);
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.(new Event('close'));
    }

    emit(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  (window as Window & { WebSocket: typeof WebSocket }).WebSocket = MockWebSocket as unknown as typeof WebSocket;
}

test.beforeEach(async ({ page }) => {
  await page.context().addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'e2e-sensenova-claw-token',
      url: 'http://127.0.0.1:3000',
    },
    {
      name: 'sensenova_claw_token',
      value: 'e2e-sensenova-claw-token',
      url: 'http://localhost:3000',
    },
  ]);
  await page.addInitScript(installMockToolConfirmationApp);
});

test('chat 页面审批通知应等待 tool_confirmation_resolved 后才收口', async ({ page }) => {
  await page.goto('/chat?token=e2e-sensenova-claw-token');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_confirmation_requested',
      session_id: 'sess_confirm_chat',
      payload: {
        tool_call_id: 'tc_confirm_chat',
        tool_name: 'bash_command',
        risk_level: 'high',
        arguments: { command: 'ls -la' },
        timeout: 60,
        timeout_action: 'approve',
        requested_at_ms: Date.now(),
      },
      timestamp: Date.now() / 1000,
    });
  });

  const toast = page.getByTestId('action-toast').filter({ hasText: '需要授权' });
  await expect(toast).toBeVisible({ timeout: 10000 });

  await toast.getByTestId('action-toast-button').getByText('批准').click();
  await expect(toast).toContainText('等待服务端确认', { timeout: 10000 });

  const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
  const parsed = sent.map((item) => JSON.parse(item));
  expect(
    parsed.some(
      (msg) => msg.type === 'tool_confirmation_response'
        && msg.payload?.tool_call_id === 'tc_confirm_chat'
        && msg.payload?.approved === true
        && msg.session_id === 'sess_confirm_chat',
    ),
  ).toBeTruthy();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_result',
      session_id: 'sess_confirm_chat',
      payload: {
        tool_call_id: 'tc_confirm_chat',
        tool_name: 'bash_command',
        success: true,
        result: { stdout: 'ok' },
      },
      timestamp: Date.now() / 1000,
    });
  });
  await expect(toast).toBeVisible({ timeout: 10000 });

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_confirmation_resolved',
      session_id: 'sess_confirm_chat',
      payload: {
        tool_call_id: 'tc_confirm_chat',
        tool_name: 'bash_command',
        approved: true,
        status: 'approved',
        reason: 'user_approved',
        resolved_by: 'user',
        resolved_at_ms: Date.now(),
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(toast).not.toBeVisible({ timeout: 10000 });
});

test('chat 页面待处理 action-toast 应在 60 秒后自动消失但保留通知卡片', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-03-25T10:00:00Z') });
  await page.goto('/chat?token=e2e-sensenova-claw-token');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_confirmation_requested',
      session_id: 'sess_confirm_idle',
      payload: {
        tool_call_id: 'tc_confirm_idle',
        tool_name: 'bash_command',
        risk_level: 'high',
        arguments: { command: 'rm -rf /tmp/demo' },
        timeout: 60,
        timeout_action: 'approve',
        requested_at_ms: Date.now(),
      },
      timestamp: Date.now() / 1000,
    });
  });

  const toast = page.getByTestId('action-toast').filter({ hasText: '需要授权' });
  await expect(toast).toBeVisible({ timeout: 10000 });

  await page.clock.fastForward('00:59');
  await expect(toast).toBeVisible();

  await page.clock.fastForward('00:01');
  await expect(toast).not.toBeVisible({ timeout: 10000 });

  await page.locator('button[title*="通知"]').click();
  await expect(page.getByText('通知中心')).toBeVisible();
  await expect(page.getByText('工具 "bash_command" 需要你的确认才能执行')).toBeVisible();
});

test('session 页面确认弹窗超时后应等待 resolved 事件再关闭', async ({ page }) => {
  await page.goto('/sessions/sess_e2e');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_confirmation_requested',
      session_id: 'sess_e2e',
      payload: {
        tool_call_id: 'tc_session_timeout',
        tool_name: 'bash_command',
        risk_level: 'high',
        arguments: { command: 'sleep 10' },
        timeout: 1,
        timeout_action: 'approve',
        requested_at_ms: Date.now() - 2000,
      },
      timestamp: Date.now() / 1000,
    });
  });

  const dialog = page.getByTestId('tool-confirmation-dialog');
  await expect(dialog).toBeVisible({ timeout: 10000 });
  await expect(dialog).toContainText('等待服务端确认超时处理结果', { timeout: 10000 });
  await expect(page.getByTestId('tool-confirm-approve')).toBeDisabled();
  await expect(page.getByTestId('tool-confirm-reject')).toBeDisabled();

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'tool_confirmation_resolved',
      session_id: 'sess_e2e',
      payload: {
        tool_call_id: 'tc_session_timeout',
        tool_name: 'bash_command',
        approved: true,
        status: 'approved',
        reason: 'timeout_approved',
        resolved_by: 'timeout',
        resolved_at_ms: Date.now(),
      },
      timestamp: Date.now() / 1000,
    });
  });

  await expect(dialog).not.toBeVisible({ timeout: 10000 });
});
