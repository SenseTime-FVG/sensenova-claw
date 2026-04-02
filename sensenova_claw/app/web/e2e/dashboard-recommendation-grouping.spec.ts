import { expect, test } from '@playwright/test';

test('不同 session 的下一问推荐应按来源会话分组展示', async ({ page }) => {
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: 'test-token',
    url: 'http://localhost:3000',
  }]);

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
        { id: 'office-main', name: 'Office Main', description: '工作台主智能体', model: 'office-v1' },
        { id: 'proactive-agent', name: 'Proactive Agent', description: '主动推荐智能体', model: 'proactive-v1' },
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
            session_id: 'sess_source_001',
            created_at: 1710000000,
            last_active: 1710000100,
            meta: JSON.stringify({ title: '市场分析对话', agent_id: 'office-main' }),
            status: 'idle',
            last_turn_status: 'completed',
            last_agent_response: '这是一段足够长的历史回复，用来模拟已完成会话。'.repeat(8),
          },
          {
            session_id: 'sess_source_002',
            created_at: 1710000200,
            last_active: 1710000300,
            meta: JSON.stringify({ title: '招聘沟通记录', agent_id: 'office-main' }),
            status: 'idle',
            last_turn_status: 'completed',
            last_agent_response: '这里放另一段足够长的历史回复，用来模拟第二个已完成会话。'.repeat(8),
          },
        ],
      }),
    });
  });

  await page.route('**/api/sessions/sess_source_001/events', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ events: [] }),
    });
  });

  await page.route('**/api/sessions/sess_source_002/events', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ events: [] }),
    });
  });

  await page.route('**/api/proactive/recommendations**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ recommendations: [] }),
    });
  });

  await page.route('**/api/cron/jobs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
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

          window.setTimeout(() => {
            this.onmessage?.(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'proactive_result',
                session_id: 'sess_source_001',
                payload: {
                  job_id: 'builtin-turn-end-recommendation',
                  job_name: '会话推荐',
                  session_id: 'sess_source_001',
                  source_session_id: 'sess_source_001',
                  recommendation_type: 'turn_end',
                  items: [
                    {
                      id: 'rec_1',
                      title: '继续追问竞品策略',
                      prompt: '请继续分析头部竞品最近两个季度的策略变化',
                      category: 'follow-up',
                    },
                  ],
                },
              }),
            }));
          }, 30);

          window.setTimeout(() => {
            this.onmessage?.(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'proactive_result',
                session_id: 'sess_source_002',
                payload: {
                  job_id: 'builtin-turn-end-recommendation',
                  job_name: '会话推荐',
                  session_id: 'sess_source_002',
                  source_session_id: 'sess_source_002',
                  recommendation_type: 'turn_end',
                  items: [
                    {
                      id: 'rec_2',
                      title: '总结候选人顾虑',
                      prompt: '请帮我总结候选人当前最在意的三个问题',
                      category: 'follow-up',
                    },
                  ],
                },
              }),
            }));
          }, 60);
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

  await expect(page.getByText('Connected')).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId('next-question-recommendations')).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId('next-question-recommendation-group')).toHaveCount(2);

  const marketGroup = page.getByTestId('next-question-recommendation-group').filter({ hasText: '市场分析对话' });
  await expect(marketGroup.getByTestId('next-question-recommendation-group-title')).toHaveText('市场分析对话');
  await expect(marketGroup).toContainText('请继续分析头部竞品最近两个季度的策略变化');

  const hiringGroup = page.getByTestId('next-question-recommendation-group').filter({ hasText: '招聘沟通记录' });
  await expect(hiringGroup.getByTestId('next-question-recommendation-group-title')).toHaveText('招聘沟通记录');
  await expect(hiringGroup).toContainText('请帮我总结候选人当前最在意的三个问题');
});
