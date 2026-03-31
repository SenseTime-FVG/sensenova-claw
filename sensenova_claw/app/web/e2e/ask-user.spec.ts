import { expect, test, type Page } from '@playwright/test';

const E2E_TOKEN = 'e2e-sensenova-claw-token';

async function loginForAskUserTests(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Token').fill(E2E_TOKEN);
  await page.getByRole('button', { name: '验证 Token' }).click();
  await page.evaluate(() => {
    sessionStorage.setItem('auth_just_verified', '1');
  });
}

async function gotoChatPage(page: Page) {
  await loginForAskUserTests(page);
  await page.goto('/chat');
}

async function gotoWorkbenchPage(page: Page) {
  await loginForAskUserTests(page);
  await page.goto('/');
}

async function gotoPptPage(page: Page) {
  await loginForAskUserTests(page);
  await page.goto('/ppt');
}

async function gotoSessionPage(page: Page, sessionId: string) {
  await loginForAskUserTests(page);
  await page.goto(`/sessions/${sessionId}`);
}

async function waitForMockWebSocketReady(page: Page) {
  await page.waitForFunction(() => {
    const ws = (window as {
      __mockWs?: {
        send?: unknown;
        onmessage?: unknown;
      };
    }).__mockWs;
    return typeof ws?.send === 'function' && typeof ws?.onmessage === 'function';
  });
}

function mockAuthAndWebSocket() {
  // 登录态：避免被 ProtectedRoute 重定向到 /login
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');
  const NativeWebSocket = window.WebSocket;
  const sharedSent = ((window as any).__mockWsSent as string[] | undefined) ?? [];
  (window as any).__mockWsSent = sharedSent;

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
    public sent: string[] = sharedSent;

    constructor(_url: string) {
      (window as any).__mockWs = this;
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

  function WrappedWebSocket(url: string | URL, protocols?: string | string[]) {
    const urlString = String(url);
    if (urlString.includes('localhost:8000/ws')) {
      return new MockWebSocket(urlString);
    }
    return new NativeWebSocket(url, protocols);
  }

  Object.assign(WrappedWebSocket, {
    CONNECTING: MockWebSocket.CONNECTING,
    OPEN: MockWebSocket.OPEN,
    CLOSING: MockWebSocket.CLOSING,
    CLOSED: MockWebSocket.CLOSED,
  });

  Object.defineProperty(window, 'WebSocket', {
    configurable: true,
    writable: true,
    value: WrappedWebSocket,
  });
}

test.describe('ask_user UI（mock websocket）', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.addCookies([
      {
        name: 'sensenova_claw_token',
        value: E2E_TOKEN,
        domain: '127.0.0.1',
        path: '/',
      },
      {
        name: 'sensenova_claw_token',
        value: E2E_TOKEN,
        domain: 'localhost',
        path: '/',
      },
    ]);

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

    await page.route('**/api/auth/verify-token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
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
          {
            id: 'default',
            name: 'Default Agent',
            description: '默认智能体',
            status: 'active',
            model: 'mock',
          },
        ]),
      });
    });

    await page.route('**/api/custom-pages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ pages: [] }),
      });
    });

    await page.route('**/api/files/roots', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ roots: [] }),
      });
    });

    await page.route('**/api/todolist/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
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

    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/auth/verify-token')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ authenticated: true }),
        });
        return;
      }

      if (url.includes('/api/auth/status')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ authenticated: true }),
        });
        return;
      }

      if (url.includes('/api/config/llm-status')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ configured: true }),
        });
        return;
      }

      if (url.endsWith('/api/sessions')) {
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
        return;
      }

      if (url.includes('/api/sessions/') && url.endsWith('/messages')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ messages: [] }),
        });
        return;
      }

      if (url.includes('/api/agents')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'default',
              name: 'Default Agent',
              description: '默认智能体',
              status: 'active',
              model: 'mock',
            },
          ]),
        });
        return;
      }

      if (url.includes('/api/custom-pages')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ pages: [] }),
        });
        return;
      }

      if (url.includes('/api/files/roots')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ roots: [] }),
        });
        return;
      }

      if (url.includes('/api/todolist/')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });

    await page.addInitScript(mockAuthAndWebSocket);
  });

  test('ask_user 问题应显示弹窗', async ({ page }) => {
    await gotoChatPage(page);

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

  test('ask_user 工具卡片内应显示内嵌回复框并可提交', async ({ page }) => {
    await gotoChatPage(page);
    await page.getByTestId('session-list').getByText('E2E Session').click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'tool_execution',
        session_id: 'sess_e2e',
        payload: {
          tool_call_id: 'tc_inline_1',
          tool_name: 'ask_user',
          arguments: {
            question: '请选择部署环境',
          },
        },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_inline_1',
          question: '请选择部署环境',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    const inlineCard = page.getByTestId('inline-ask-user-q_inline_1');
    await expect(inlineCard).toBeVisible({ timeout: 10000 });
    await expect(inlineCard).toContainText('请选择部署环境');
    await expect(inlineCard).toContainText('dev');
    await expect(inlineCard).toContainText('prod');
    await inlineCard.getByTestId('ask-user-shared-custom-input').fill('staging');
    await inlineCard.getByTestId('ask-user-shared-confirm').click();
    await expect(inlineCard.getByText('已提交回复，等待服务端确认最终结果。')).toBeVisible({ timeout: 10000 });

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_inline_1'
          && msg.payload?.answer === 'staging'
          && msg.session_id === 'sess_e2e'
      )
    ).toBeTruthy();
  });

  test('chat 页面切换会话后再切回，应从历史 events 恢复 ask_user 内联卡片', async ({ page }) => {
    const sessionEvents: Record<string, Record<string, unknown>[]> = {
      sess_e2e: [
        {
          event_type: 'tool.call_requested',
          session_id: 'sess_e2e',
          payload_json: JSON.stringify({
            tool_call_id: 'tc_history_ask_user_1',
            tool_name: 'ask_user',
            arguments: {
              question: '请确认部署环境',
            },
          }),
        },
        {
          event_type: 'user.question_asked',
          session_id: 'sess_e2e',
          payload_json: JSON.stringify({
            question_id: 'q_history_ask_user_1',
            question: '请确认部署环境',
            options: ['dev', 'prod'],
            multi_select: false,
          }),
        },
      ],
      sess_other: [],
    };

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
            {
              session_id: 'sess_other',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: 'Other Session' }),
            },
          ],
        }),
      });
    });

    await page.route('**/api/sessions/*/events', async (route) => {
      const url = route.request().url();
      const match = url.match(/\/api\/sessions\/([^/]+)\/events/);
      const sessionId = match?.[1] || '';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ events: sessionEvents[sessionId] || [] }),
      });
    });

    await gotoChatPage(page);

    await page.getByTestId('session-list').getByText('E2E Session').click();
    await expect(page.getByTestId('inline-ask-user-q_history_ask_user_1')).toBeVisible({ timeout: 10000 });

    await page.getByTestId('session-list').getByText('Other Session').click();
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });

    await page.getByTestId('session-list').getByText('E2E Session').click();
    await expect(page.getByTestId('inline-ask-user-q_history_ask_user_1')).toBeVisible({ timeout: 10000 });
  });

  test('chat 页面可在当前会话接收其他 session 的 ask_user，并按来源 session 提交回答', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'session_created',
        session_id: 'sess_a',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_b',
        payload: {
          question_id: 'q_e2e_2',
          question: '请补充你的部署环境',
          source_agent_id: 'research',
          source_agent_name: 'Research Agent',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('ask-user-source-agent')).toHaveText('Research Agent');
    await expect(page.getByTestId('ask-user-source-session')).toHaveText('sess_b');
    await expect(page.getByText('提示：Enter 确认，Shift+Enter 换行')).toBeVisible();
    await expect(page.getByTestId('chat-input')).toBeDisabled();
    await page.getByTestId('ask-user-custom-input').fill('staging');
    await page.getByTestId('ask-user-confirm').click();
    await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible();

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_e2e_2'
          && msg.session_id === 'sess_b'
      )
    ).toBeTruthy();
  });

  test('ppt 页面通过主输入框回复 ask_user 后，应恢复正常发送按钮', async ({ page }) => {
    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'default',
            name: 'Default Agent',
            description: '默认智能体',
            status: 'active',
            model: 'mock',
          },
          {
            id: 'ppt-agent',
            name: 'PPT Agent',
            description: 'PPT 智能体',
            status: 'active',
            model: 'mock',
          },
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
              session_id: 'sess_ppt_old',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: 'PPT 会话', agent_id: 'ppt-agent' }),
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

    await gotoPptPage(page);
    await waitForMockWebSocketReady(page);

    await expect(page.getByText('PPT 会话')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });
    await page.getByText('PPT 会话').click();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_ppt_old',
        payload: {
          question_id: 'q_ppt_old_1',
          question: '请确认旧会话中的审批信息',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByTestId('chat-input').fill('这是旧问题的回复');

    const beforeSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();

    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeSendCount);

    const delta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeSendCount);

    expect(delta.some((msg: any) => msg.type === 'user_question_answered')).toBeTruthy();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_answered_event',
        session_id: 'sess_ppt_old',
        payload: {
          question_id: 'q_ppt_old_1',
          answer: '这是旧问题的回复',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await page.getByTestId('chat-input').fill('帮我生成一份关于行业趋势的 PPT');
    await expect(page.getByTestId('send-button')).toBeEnabled({ timeout: 10000 });

    const beforeNormalSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeNormalSendCount);

    const normalDelta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeNormalSendCount);

    expect(normalDelta.some((msg: any) => msg.type === 'user_input')).toBeTruthy();
  });

  test('ppt 页面新建对话后，后续消息不应落到上一会话的 ask_user 下', async ({ page }) => {
    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'default',
            name: 'Default Agent',
            description: '默认智能体',
            status: 'active',
            model: 'mock',
          },
          {
            id: 'ppt-agent',
            name: 'PPT Agent',
            description: 'PPT 智能体',
            status: 'active',
            model: 'mock',
          },
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
              session_id: 'sess_ppt_waiting',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '待回答会话', agent_id: 'ppt-agent' }),
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

    await gotoPptPage(page);
    await waitForMockWebSocketReady(page);

    await page.getByText('待回答会话').click();
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_ppt_waiting',
        payload: {
          question_id: 'q_ppt_waiting_1',
          question: '这是旧会话里的 ask_user',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByTestId('ppt-new-chat-button').evaluate((node) => {
      (node as HTMLButtonElement).click();
    });
    await page.getByTestId('chat-input').fill('这是新对话里的正常消息');

    const beforeSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeSendCount);

    const delta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeSendCount);

    expect(delta.some((msg: any) => msg.type === 'user_question_answered')).toBeFalsy();
    expect(delta.some((msg: any) => {
      if (msg.type === 'create_session') {
        return msg.payload?.agent_id === 'ppt-agent';
      }
      if (msg.type === 'user_input') {
        return msg.payload?.content === '这是新对话里的正常消息';
      }
      return false;
    })).toBeTruthy();
  });

  test('ppt 页面切换到另一会话后，主输入首条消息不应被旧会话 ask_user 吃掉', async ({ page }) => {
    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'default', name: 'Default Agent', description: '默认智能体', status: 'active', model: 'mock' },
          { id: 'ppt-agent', name: 'PPT Agent', description: 'PPT 智能体', status: 'active', model: 'mock' },
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
              session_id: 'sess_ppt_1',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: 'PPT 会话 1', agent_id: 'ppt-agent' }),
            },
            {
              session_id: 'sess_ppt_2',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000 - 10,
              status: 'active',
              meta: JSON.stringify({ title: 'PPT 会话 2', agent_id: 'ppt-agent' }),
            },
          ],
        }),
      });
    });

    await page.route('**/api/sessions/*/events', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ events: [] }) });
    });

    await gotoPptPage(page);
    await waitForMockWebSocketReady(page);
    await page.getByText('PPT 会话 1').click();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_ppt_1',
        payload: {
          question_id: 'q_ppt_cross_1',
          question: '这是会话1里的 ask_user',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByText('PPT 会话 2').click();
    await page.getByTestId('chat-input').fill('这是会话2里的正常消息');

    const beforeSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeSendCount);

    const delta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeSendCount);

    expect(delta.some((msg: any) => msg.type === 'user_question_answered')).toBeFalsy();
    expect(delta.some((msg: any) => msg.type === 'user_input'
      && msg.session_id === 'sess_ppt_2'
      && msg.payload?.content === '这是会话2里的正常消息')).toBeTruthy();
  });

  test('工作台首页通过主输入框回复 ask_user 后，应恢复正常发送按钮', async ({ page }) => {
    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'office-main',
            name: 'Office Main',
            description: '工作台主智能体',
            status: 'active',
            model: 'mock',
          },
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
              session_id: 'sess_workbench_old',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '工作台会话', agent_id: 'office-main' }),
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

    await gotoWorkbenchPage(page);
    await waitForMockWebSocketReady(page);

    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });
    await page.getByText('工作台会话').click();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_workbench_old',
        payload: {
          question_id: 'q_workbench_main_1',
          question: '请确认工作台中的目标环境',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await page.waitForTimeout(200);
    await page.getByTestId('chat-input').fill('工作台里的问答回复');

    const beforeAnswerSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeAnswerSendCount);

    const answerDelta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeAnswerSendCount);

    expect(answerDelta.some((msg: any) => msg.type === 'user_question_answered')).toBeTruthy();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_answered_event',
        session_id: 'sess_workbench_old',
        payload: {
          question_id: 'q_workbench_main_1',
          answer: '工作台里的问答回复',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await page.getByTestId('chat-input').fill('继续发送正常工作台消息');
    await expect(page.getByTestId('send-button')).toBeEnabled({ timeout: 10000 });

    const beforeNormalSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeNormalSendCount);

    const normalDelta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeNormalSendCount);

    expect(normalDelta.some((msg: any) => msg.type === 'user_input')).toBeTruthy();
  });

  test('工作台首页切换到另一会话后，主输入首条消息不应被旧会话 ask_user 吃掉', async ({ page }) => {
    await page.route('**/api/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'office-main', name: 'Office Main', description: '工作台主智能体', status: 'active', model: 'mock' },
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
              session_id: 'sess_workbench_1',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '工作台会话 1', agent_id: 'office-main' }),
            },
            {
              session_id: 'sess_workbench_2',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000 - 10,
              status: 'active',
              meta: JSON.stringify({ title: '工作台会话 2', agent_id: 'office-main' }),
            },
          ],
        }),
      });
    });

    await page.route('**/api/sessions/*/events', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ events: [] }) });
    });

    await gotoWorkbenchPage(page);
    await waitForMockWebSocketReady(page);
    await page.getByText('工作台会话 1').click();

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_workbench_1',
        payload: {
          question_id: 'q_workbench_cross_1',
          question: '这是会话1里的 ask_user',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByText('工作台会话 2').click();
    await page.getByTestId('chat-input').fill('这是会话2里的正常消息');

    const beforeSendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeSendCount);

    const delta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeSendCount);

    expect(delta.some((msg: any) => msg.type === 'user_question_answered')).toBeFalsy();
    expect(delta.some((msg: any) => msg.type === 'user_input'
      && msg.session_id === 'sess_workbench_2'
      && msg.payload?.content === '这是会话2里的正常消息')).toBeTruthy();
  });

  test('chat 页面主输入框首条输入可直接作为 ask_user 回复，随后恢复普通 user_input', async ({ page }) => {
    await gotoChatPage(page);
    await page.getByTestId('session-list').getByText('E2E Session').click();
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_chat_main_1',
          question: '请补充部署环境',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await page.waitForTimeout(200);
    const chatInput = page.getByTestId('chat-input');
    await expect(chatInput).toBeEditable();
    await chatInput.fill('staging');
    await chatInput.press('Enter');

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_answered_event',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_chat_main_1',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await chatInput.fill('继续正常聊天');
    await page.getByTestId('send-button').click();

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_chat_main_1'
          && msg.payload?.answer === 'staging'
          && msg.session_id === 'sess_e2e'
      )
    ).toBeTruthy();
    expect(
      parsed.some(
        (msg) => msg.type === 'user_input'
          && msg.session_id === 'sess_e2e'
          && msg.payload?.content === '继续正常聊天'
      )
    ).toBeTruthy();
  });

  test('chat 页面切换到另一会话后，主输入首条消息不应被旧会话 ask_user 吃掉', async ({ page }) => {
    await page.route('**/api/sessions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [
            {
              session_id: 'sess_chat_1',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '聊天会话 1', agent_id: 'default' }),
            },
            {
              session_id: 'sess_chat_2',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000 - 10,
              status: 'active',
              meta: JSON.stringify({ title: '聊天会话 2', agent_id: 'default' }),
            },
          ],
        }),
      });
    });

    await gotoChatPage(page);
    await waitForMockWebSocketReady(page);
    await page.getByTestId('session-list').getByText('聊天会话 1').click();
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_chat_1',
        payload: {
          question_id: 'q_chat_cross_1',
          question: '这是会话1里的 ask_user',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByTestId('session-list').getByText('聊天会话 2').click();
    const chatInput = page.getByTestId('chat-input');
    await chatInput.fill('这是会话2里的正常消息');
    await page.getByTestId('send-button').click();

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_chat_cross_1'
      )
    ).toBeFalsy();
    expect(
      parsed.some(
        (msg) => msg.type === 'user_input'
          && msg.session_id === 'sess_chat_2'
          && msg.payload?.content === '这是会话2里的正常消息'
      )
    ).toBeTruthy();
  });

  test('chat 页面切到会话2完成一轮后，切回会话1仍可用主输入回答原 ask_user', async ({ page }) => {
    await page.route('**/api/sessions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [
            {
              session_id: 'sess_chat_restore_1',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000,
              status: 'active',
              meta: JSON.stringify({ title: '恢复会话 1', agent_id: 'default' }),
            },
            {
              session_id: 'sess_chat_restore_2',
              created_at: Date.now() / 1000,
              last_active: Date.now() / 1000 - 10,
              status: 'active',
              meta: JSON.stringify({ title: '恢复会话 2', agent_id: 'default' }),
            },
          ],
        }),
      });
    });

    await gotoChatPage(page);
    await waitForMockWebSocketReady(page);

    await page.getByTestId('session-list').getByText('恢复会话 1').click();
    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_chat_restore_1',
        payload: {
          question_id: 'q_chat_restore_1',
          question: '这是会话1里待恢复的 ask_user',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByTestId('session-list').getByText('恢复会话 2').click();
    await page.getByTestId('chat-input').fill('这是会话2里的普通消息');
    const beforeSession2SendCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeSession2SendCount);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'turn_completed',
        session_id: 'sess_chat_restore_2',
        payload: {
          turn_id: 'turn_restore_2',
          final_response: '会话2已完成',
        },
        timestamp: Date.now() / 1000,
      });
    });
    await page.waitForTimeout(200);

    await page.getByTestId('session-list').getByText('恢复会话 1').click();
    const chatInput = page.getByTestId('chat-input');
    await chatInput.fill('这是切回会话1后的回答');
    const beforeAnswerCount = await page.evaluate(() => ((window as any).__mockWsSent as string[]).length);
    await page.getByTestId('send-button').click();
    await page.waitForFunction((count) => ((window as any).__mockWsSent as string[]).length > count, beforeAnswerCount);

    const delta = await page.evaluate((count) => {
      return ((window as any).__mockWsSent as string[]).slice(count).map((item) => JSON.parse(item));
    }, beforeAnswerCount);

    expect(delta.some((msg: any) =>
      msg.type === 'user_question_answered'
      && msg.session_id === 'sess_chat_restore_1'
      && msg.payload?.question_id === 'q_chat_restore_1'
      && msg.payload?.answer === '这是切回会话1后的回答'
    )).toBeTruthy();
  });

  test('ask_user 弹窗 textarea 按 Enter 可直接确认提交', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_enter_1',
        payload: {
          question_id: 'q_enter_submit_1',
          question: '请输入环境',
          source_agent_id: 'research',
          source_agent_name: 'Research Agent',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await page.getByTestId('ask-user-custom-input').fill('staging');
    await page.getByTestId('ask-user-custom-input').press('Enter');
    await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible({ timeout: 10000 });

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_enter_submit_1'
          && msg.payload?.answer === 'staging'
          && msg.session_id === 'sess_enter_1'
      )
    ).toBeTruthy();
  });

  test('ask_user 弹窗 textarea 按 Shift+Enter 仅换行不提交', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_shift_1',
        payload: {
          question_id: 'q_shift_newline_1',
          question: '请输入多行说明',
          source_agent_id: 'research',
          source_agent_name: 'Research Agent',
          options: ['A', 'B'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    const customInput = page.getByTestId('ask-user-custom-input');
    await customInput.fill('line1');
    await customInput.press('Shift+Enter');
    await customInput.type('line2');
    await expect(customInput).toHaveValue('line1\nline2');
    await expect(page.getByTestId('ask-user-dialog')).toBeVisible();

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_shift_newline_1'
      )
    ).toBeFalsy();
  });

  test('chat 页面多个 ask_user 按 FIFO 依次弹出', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'session_created',
        session_id: 'sess_a',
        payload: { created_at: Date.now() / 1000 },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_b',
        payload: {
          question_id: 'q_fifo_1',
          question: '第一个问题',
          options: ['A', 'B'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_c',
        payload: {
          question_id: 'q_fifo_2',
          question: '第二个问题',
          options: ['X', 'Y'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('第一个问题')).toBeVisible();
    await page.getByTestId('ask-user-option-0').click();
    await page.getByTestId('ask-user-confirm').click();

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('第二个问题')).toBeVisible();
  });

  test('chat 页面可处理 tool_confirmation_requested 并回传批准结果', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'tool_confirmation_requested',
        session_id: 'sess_confirm_1',
        payload: {
          tool_call_id: 'tc_confirm_1',
          tool_name: 'bash_command',
          risk_level: 'high',
          arguments: { command: 'ls -la' },
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('tool-confirmation-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('tool-confirm-name')).toHaveText('bash_command');
    await expect(page.getByTestId('tool-confirm-risk')).toHaveText('high');
    await expect(page.getByTestId('tool-confirm-source-session')).toHaveText('sess_confirm_1');
    await page.getByTestId('tool-confirm-approve').click();
    await expect(page.getByTestId('tool-confirmation-dialog')).not.toBeVisible({ timeout: 10000 });

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'tool_confirmation_response'
          && msg.payload?.tool_call_id === 'tc_confirm_1'
          && msg.payload?.approved === true
          && msg.session_id === 'sess_confirm_1'
      )
    ).toBeTruthy();
  });

  test('chat 页面审批与问答混合事件应按 FIFO 顺序处理', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'tool_confirmation_requested',
        session_id: 'sess_mix_a',
        payload: {
          tool_call_id: 'tc_mix_1',
          tool_name: 'bash_command',
          risk_level: 'high',
          arguments: { command: 'rm -rf /tmp/demo' },
        },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_mix_b',
        payload: {
          question_id: 'q_mix_2',
          question: '请确认目标环境',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('tool-confirmation-dialog')).toBeVisible({ timeout: 10000 });
    await page.getByTestId('tool-confirm-reject').click();
    await expect(page.getByTestId('tool-confirmation-dialog')).not.toBeVisible({ timeout: 10000 });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('请确认目标环境')).toBeVisible();
  });

  test('chat 页面交互超时后应自动关闭当前弹窗', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'tool_confirmation_requested',
        session_id: 'sess_timeout_1',
        payload: {
          tool_call_id: 'tc_timeout_1',
          tool_name: 'bash_command',
          risk_level: 'high',
          arguments: { command: 'sleep 10' },
          timeout: 1,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('tool-confirmation-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('tool-confirmation-dialog')).not.toBeVisible({ timeout: 10000 });
    await expect(page.getByText('工具审批已超时，系统将按后端策略拒绝。')).toBeVisible({ timeout: 10000 });
  });

  test('收到 user_question_answered_event 后应关闭对应问题弹窗', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_b',
        payload: {
          question_id: 'q_sync_close',
          question: '等待同步关闭',
          options: ['yes', 'no'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_answered_event',
        session_id: 'sess_b',
        payload: {
          question_id: 'q_sync_close',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible({ timeout: 10000 });
  });

  test('chat 页面错误文案应优先回落到 error_type', async ({ page }) => {
    await gotoChatPage(page);

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'error',
        session_id: 'sess_e2e',
        payload: {
          error_type: 'TimeoutError',
          message: '',
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByText('Error: TimeoutError')).toBeVisible({ timeout: 10000 });
  });

  test('chat 页面应忽略非当前 session 的完成事件，避免误关闭 ask_user 弹窗', async ({ page }) => {
    await gotoChatPage(page);

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
          question_id: 'q_e2e_keep',
          question: '请选择环境',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'turn_completed',
        session_id: 'sess_other',
        payload: { final_response: 'other session done' },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
  });

  test('session 页面可处理 ask_user', async ({ page }) => {
    await gotoSessionPage(page, 'sess_e2e');
    await waitForMockWebSocketReady(page);

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

  test('session 页面 ask_user 工具卡片内应显示内嵌回复框并可提交', async ({ page }) => {
    await gotoSessionPage(page, 'sess_e2e');
    await waitForMockWebSocketReady(page);

    await page.evaluate(() => {
      ((window as any).__mockWsSent as string[]).length = 0;

      (window as any).__mockWs.emit({
        type: 'tool_execution',
        session_id: 'sess_e2e',
        payload: {
          tool_call_id: 'tc_session_inline_1',
          tool_name: 'ask_user',
          arguments: {
            question: '请选择会话环境',
          },
        },
        timestamp: Date.now() / 1000,
      });
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_session_inline_1',
          question: '请选择会话环境',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    const inlineCard = page.getByTestId('inline-ask-user-q_session_inline_1');
    await expect(inlineCard).toBeVisible({ timeout: 10000 });
    await inlineCard.getByTestId('ask-user-shared-custom-input').fill('staging');
    await inlineCard.getByTestId('ask-user-shared-confirm').click();
    await expect(inlineCard.getByText('已提交回复，等待服务端确认最终结果。')).toBeVisible({ timeout: 10000 });

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_session_inline_1'
          && msg.payload?.answer === 'staging'
          && msg.session_id === 'sess_e2e'
      )
    ).toBeTruthy();
  });

  test('session 页面可接收其他 session 的 ask_user，并按来源 session 提交回答', async ({ page }) => {
    await gotoSessionPage(page, 'sess_e2e');

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_child',
        payload: {
          question_id: 'q_session_cross_1',
          question: '请确认目标环境',
          options: ['dev', 'prod'],
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('ask-user-source-session')).toHaveText('sess_child');
    await page.getByTestId('ask-user-custom-input').fill('prod');
    await page.getByTestId('ask-user-confirm').click();
    await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible({ timeout: 10000 });

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_session_cross_1'
          && msg.session_id === 'sess_child'
      )
    ).toBeTruthy();
  });

  test('session 页面主输入框首条输入可直接作为 ask_user 回复，随后恢复普通 user_input', async ({ page }) => {
    await gotoSessionPage(page, 'sess_e2e');
    await waitForMockWebSocketReady(page);
    await expect(page.getByTestId('current-session-id')).toHaveText('sess_e2e');

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_asked',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_session_main_1',
          question: '请确认目标环境',
          options: null,
          multi_select: false,
          timeout: 300,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await page.waitForTimeout(200);
    const chatInput = page.getByTestId('chat-input');
    await expect(chatInput).toBeEditable();
    await chatInput.fill('prod');
    await chatInput.press('Enter');

    await page.evaluate(() => {
      (window as any).__mockWs.emit({
        type: 'user_question_answered_event',
        session_id: 'sess_e2e',
        payload: {
          question_id: 'q_session_main_1',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    });

    await chatInput.fill('后续普通消息');
    await page.getByTestId('send-button').click();

    const sent = await page.evaluate(() => (window as any).__mockWsSent as string[]);
    const parsed = sent.map((item) => JSON.parse(item));
    expect(
      parsed.some(
        (msg) => msg.type === 'user_question_answered'
          && msg.payload?.question_id === 'q_session_main_1'
          && msg.payload?.answer === 'prod'
          && msg.session_id === 'sess_e2e'
      )
    ).toBeTruthy();
    expect(
      parsed.some(
        (msg) => msg.type === 'user_input'
          && msg.session_id === 'sess_e2e'
          && msg.payload?.content === '后续普通消息'
      )
    ).toBeTruthy();
  });
});

test.describe('真实 API ask_user 回归', () => {
  test.skip(process.env.ENABLE_REAL_API_E2E !== '1', '设置 ENABLE_REAL_API_E2E=1 后执行真实 API 回归');

  test('真实 API ask_user 回归', async ({ page }) => {
    await gotoChatPage(page);
    await expect(page.getByText('已连接')).toBeVisible({ timeout: 30000 });

    await page.getByTestId('chat-input').fill(
      process.env.ASK_USER_REAL_QUERY || '请先调用 ask_user 工具向我提一个确认问题，然后根据我的回答给出最终建议。'
    );
    await page.getByTestId('send-button').click();

    await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 120000 });
    await page.getByTestId('ask-user-custom-input').fill('生产环境，优先稳定');
    await page.getByTestId('ask-user-confirm').click();
    await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible({ timeout: 30000 });

    await expect(page.locator('.text-\\[13px\\].text-\\[\\#cccccc\\]').last()).not.toHaveText(/^$/, { timeout: 120000 });
  });
});
