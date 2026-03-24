import { expect, test } from '@playwright/test';

function installAskUserMockApp() {
  const NativeWebSocket = window.WebSocket;
  const nativeFetch = window.fetch.bind(window);
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';

  const queuedMessages: unknown[] = [];
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

    send(_data: string) {}

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
  await page.addInitScript(installAskUserMockApp);
});

test('ask_user 长选项在通知提示框内换行，不应横向溢出', async ({ page }) => {
  await page.goto('/chat?token=e2e-sensenova-claw-token');

  await page.evaluate(() => {
    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_long_option',
      payload: {
        question_id: 'q_long_option_1',
        question: '未检测到 MinerU API Token，你想走哪种渠道解析该文件？',
        options: [
          '官方免费快速模式：无需 token，但有 10MB / 20 页限制，且不含表格识别',
          'Token/API 完整模式：需要先创建 token（https://mineru.net/apiManage/token），支持更大文件、表格/公式识别和多格式导出',
        ],
        multi_select: false,
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  const toast = page.getByTestId('action-toast').filter({
    hasText: '未检测到 MinerU API Token，你想走哪种渠道解析该文件？',
  });
  const longOptionButton = page.getByTestId('action-toast-button').getByText(
    'Token/API 完整模式：需要先创建 token（https://mineru.net/apiManage/token），支持更大文件、表格/公式识别和多格式导出'
  );

  await expect(toast).toBeVisible({ timeout: 10000 });
  await expect(longOptionButton).toBeVisible();

  const toastBox = await toast.boundingBox();
  const buttonBox = await longOptionButton.boundingBox();
  expect(toastBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(toastBox!.x + toastBox!.width + 1);
});

test('ask_user 无选项时应在通知提示框显示输入框并提交回答', async ({ page }) => {
  await page.goto('/chat?token=e2e-sensenova-claw-token');

  await page.evaluate(() => {
    const sent: string[] = [];
    (window as any).__mockWsSent = sent;
    (window as any).__mockWs.send = (data: string) => {
      sent.push(data);
    };

    (window as any).__mockWs.emit({
      type: 'user_question_asked',
      session_id: 'sess_no_options',
      payload: {
        question_id: 'q_no_options_1',
        question: '请提供您的 MinerU API Token（可在 https://mineru.net/apiManage/token 获取）：',
        timeout: 300,
      },
      timestamp: Date.now() / 1000,
    });
  });

  const toast = page.getByTestId('action-toast').filter({
    hasText: '请提供您的 MinerU API Token（可在 https://mineru.net/apiManage/token 获取）：',
  });

  await expect(toast).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('action-toast-input')).toBeVisible();
  await expect(page.getByTestId('action-toast-submit')).toBeVisible();
  await expect(page.getByTestId('action-toast-button')).toHaveCount(0);

  await page.getByTestId('action-toast-input').fill('mineru-token-123');
  await page.getByTestId('action-toast-submit').click();

  const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
  const parsed = sent.map((item) => JSON.parse(item));
  expect(
    parsed.some(
      (msg) => msg.type === 'user_question_answered'
        && msg.payload?.question_id === 'q_no_options_1'
        && msg.payload?.answer === 'mineru-token-123'
        && msg.session_id === 'sess_no_options'
    )
  ).toBeTruthy();
});
