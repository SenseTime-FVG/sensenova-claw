import { expect, test } from '@playwright/test';

function mockAuthAndWebSocket() {
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
  const NativeWebSocket = window.WebSocket;

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
    private listeners: Record<string, Array<(event: Event | MessageEvent) => void>> = {};

    constructor(url: string | URL, protocols?: string | string[]) {
      const resolvedUrl = String(url);
      if (!resolvedUrl.includes('localhost:8000/ws')) {
        return new NativeWebSocket(url, protocols);
      }

      window.setTimeout(() => {
        const event = new Event('open');
        this.onopen?.(event);
        (this.listeners.open || []).forEach((listener) => listener(event));
      }, 0);
    }

    send(_data: string) {}

    addEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] ??= [];
      this.listeners[type].push(listener);
    }

    removeEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener);
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      const event = new Event('close');
      this.onclose?.(event);
      (this.listeners.close || []).forEach((listener) => listener(event));
    }
  }

  (window as Window & { WebSocket: typeof WebSocket }).WebSocket = MockWebSocket as unknown as typeof WebSocket;
}

test('mini-app 工作区应在构建期转发 builder 消息并按 local/server/agent 分流页面动作', async ({ page }) => {
  let lastInteractionSessionId = '';
  let workspacePhase: 'running' | 'ready' = 'running';
  const actionBodies: Record<string, unknown>[] = [];
  const startTs = Date.now();

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
          id: 'miniapp-research-hub-agent',
          name: 'Research Hub Agent',
          description: '通用工作区专属 Agent',
        },
      ]),
    });
  });

  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/files/roots', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ roots: [] }),
    });
  });

  await page.route('**/api/files?path=*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/custom-pages', async (route) => {
    const url = route.request().url();
    if (!url.endsWith('/api/custom-pages')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        pages: [
          {
            id: 'page_research_hub',
            slug: 'research-hub',
            name: 'Research Hub',
            icon: 'BookOpen',
          },
        ],
      }),
    });
  });

  await page.route('**/api/custom-pages/research-hub', async (route) => {
    const now = Date.now();
    const runningPayload = {
      id: 'page_research_hub',
      slug: 'research-hub',
      name: 'Research Hub',
      description: '通用研究任务工作区',
      icon: 'BookOpen',
      type: 'miniapp',
      agent_id: 'miniapp-research-hub-agent',
      base_agent_id: 'default',
      create_dedicated_agent: true,
      workspace_mode: 'scratch',
      builder_type: 'acp',
      generation_prompt: 'Build a research workspace',
      entry_file_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/index.html',
      bridge_script_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/sensenova-claw-bridge.js',
      preserved_license_files: [],
      build_status: 'running',
      build_summary: '正在生成 mini-app...',
      latest_run_id: 'run_live',
      last_interaction_session_id: '',
      workspace_root: 'miniapp-research-hub-agent/miniapps/research-hub',
      app_dir: 'miniapp-research-hub-agent/miniapps/research-hub/app',
      updated_at: now,
      templates: [],
      runs: [
        {
          id: 'run_live',
          builder_type: 'acp',
          status: 'running',
          prompt: 'Build a research workspace',
          started_at_ms: startTs,
          ended_at_ms: null,
          logs: [
            {
              ts: startTs + 100,
              level: 'info',
              message: '开始生成 mini-app',
            },
            {
              ts: startTs + 200,
              level: 'info',
              message: 'ACP agent_thought_chunk: Inspect',
            },
            {
              ts: startTs + 300,
              level: 'info',
              message: 'ACP agent_thought_chunk: files',
            },
            {
              ts: startTs + 350,
              level: 'info',
              message: 'ACP tool_call [in_progress]: Edit app.js',
            },
            {
              ts: startTs + 400,
              level: 'info',
              message: 'ACP agent_message_chunk: Building',
            },
            {
              ts: startTs + 500,
              level: 'info',
              message: 'ACP agent_message_chunk: workspace',
            },
          ],
        },
      ],
    };

    const readyPayload = {
      id: 'page_research_hub',
      slug: 'research-hub',
      name: 'Research Hub',
      description: '通用研究任务工作区',
      icon: 'BookOpen',
      type: 'miniapp',
      agent_id: 'miniapp-research-hub-agent',
      base_agent_id: 'default',
      create_dedicated_agent: true,
      workspace_mode: 'scratch',
      builder_type: 'builtin',
      generation_prompt: '做一个通用工作区，只在必要时把动作分发给 Agent',
      entry_file_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/index.html',
      bridge_script_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/sensenova-claw-bridge.js',
      preserved_license_files: [],
      build_status: 'ready',
      build_summary: 'mini-app 已生成，可直接预览并继续让 Agent 迭代',
      latest_run_id: 'run_1',
      last_interaction_session_id: lastInteractionSessionId,
      workspace_root: 'miniapp-research-hub-agent/miniapps/research-hub',
      app_dir: 'miniapp-research-hub-agent/miniapps/research-hub/app',
      updated_at: now,
      templates: [
        { title: '整理资料', desc: '先收敛输入材料' },
      ],
      runs: [
        {
          id: 'run_1',
          builder_type: 'builtin',
          status: 'completed',
          prompt: '做一个通用工作区，只在必要时把动作分发给 Agent',
          started_at_ms: now - 1000,
          ended_at_ms: now,
          logs: [
            {
              ts: now,
              level: 'info',
              message: '使用内置模板: generic-workspace',
            },
          ],
        },
      ],
    };

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(workspacePhase === 'running' ? runningPayload : readyPayload),
    });
  });

  await page.route('**/api/custom-pages/research-hub/actions', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}');
    actionBodies.push(body);
    if (body.target === 'agent') {
      lastInteractionSessionId = 'sess_miniapp';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          target: 'agent',
          session_id: 'sess_miniapp',
          turn_id: 'turn_from_preview',
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        target: 'server',
        session_id: '',
        turn_id: '',
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

  await page.route('**/api/sessions/sess_miniapp/events', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ events: [] }),
    });
  });

  await page.route('**/api/cron/runs*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [] }),
    });
  });

  await page.route('**/api/files/workdir/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: `
        <!doctype html>
        <html lang="zh-CN">
          <body style="font-family: sans-serif; padding: 16px;">
            <h1>Research Hub Preview</h1>
            <button id="local-action">local action</button>
            <button id="server-action">server action</button>
            <button id="agent-action">agent action</button>
            <script>
              window.parent.postMessage({
                source: 'sensenova-claw-miniapp',
                slug: 'research-hub',
                kind: 'config',
                meta: {
                  defaultTarget: 'agent',
                  routes: {
                    task_card_selected: 'local',
                    save_workspace_snapshot: 'server',
                    request_page_refine: 'agent',
                  },
                },
              }, '*');

              document.getElementById('local-action').addEventListener('click', () => {
                window.parent.postMessage({
                  source: 'sensenova-claw-miniapp',
                  slug: 'research-hub',
                  kind: 'interaction',
                  action: 'task_card_selected',
                  payload: { title: 'Alpha' },
                }, '*');
              });

              document.getElementById('server-action').addEventListener('click', () => {
                window.parent.postMessage({
                  source: 'sensenova-claw-miniapp',
                  slug: 'research-hub',
                  kind: 'interaction',
                  action: 'save_workspace_snapshot',
                  payload: { cards: 3, summary: 'save current workspace state' },
                }, '*');
              });

              document.getElementById('agent-action').addEventListener('click', () => {
                window.parent.postMessage({
                  source: 'sensenova-claw-miniapp',
                  slug: 'research-hub',
                  kind: 'interaction',
                  action: 'request_page_refine',
                  payload: { request: 'please refine the page layout' },
                }, '*');
              });
            </script>
          </body>
        </html>
      `,
    });
  });

  await page.addInitScript(mockAuthAndWebSocket);

  await page.goto('/login');
  await page.getByLabel('Token').fill('e2e-sensenova-claw-token');
  await page.getByRole('button', { name: '验证 Token' }).click();
  await page.goto('/features/research-hub');

  await expect(page.getByTestId('workspace-floating-tabs')).toBeVisible();
  await expect(page.getByTestId('workspace-overview-panel')).toBeVisible();
  await expect(page.getByTestId('workspace-chat-fab')).toBeVisible();
  await page.getByTestId('workspace-tab-workspace').click();
  await expect(page.getByTestId('workspace-overview-panel')).toBeHidden();
  await page.getByTestId('workspace-tab-workspace').click();
  await expect(page.getByTestId('workspace-overview-panel')).toBeVisible();

  await page.getByTestId('workspace-tab-runs').click();
  await expect(page.getByTestId('workspace-runs-panel')).toBeVisible();
  await page.getByTestId('workspace-tab-runs').click();
  await expect(page.getByTestId('workspace-runs-panel')).toBeHidden();
  await page.getByTestId('workspace-tab-runs').click();
  await expect(page.getByTestId('workspace-runs-panel')).toBeVisible();

  await page.getByTestId('workspace-tab-details').click();
  await expect(page.getByTestId('workspace-details-panel')).toBeVisible();
  await page.getByTestId('workspace-tab-details').click();
  await expect(page.getByTestId('workspace-details-panel')).toBeHidden();
  await page.getByTestId('workspace-tab-details').click();
  await expect(page.getByTestId('workspace-details-panel')).toBeVisible();

  await page.getByTestId('workspace-tab-workspace').click();
  await expect(page.getByTestId('workspace-overview-panel')).toBeVisible();

  await page.getByTestId('workspace-chat-fab').click();
  await expect(page.getByTestId('workspace-chat-floating-panel')).toBeVisible();
  await expect(page.getByText('正在转发当前构建任务的 builder 消息...')).toBeVisible();
  await expect(page.getByText('Research Hub 构建消息流')).toBeVisible();
  await expect(page.getByText('Build a research workspace')).toBeVisible();
  await expect(page.getByText(/Building\s*workspace/)).toBeVisible();
  await expect(page.getByTestId('build-tool-card')).toContainText('Edit app.js');
  await expect(page.getByTestId('build-tool-status')).toContainText('运行中');

  await page.getByTestId('assistant-think-toggle').first().click();
  await expect(page.getByTestId('assistant-think-content').first()).toContainText(/Inspect\s*files/);
  await page.getByLabel('固定聊天窗口').click();
  await expect(page.getByTestId('workspace-chat-pinned')).toBeVisible();

  workspacePhase = 'ready';
  await page.getByRole('button', { name: '刷新' }).click();

  await expect(page.getByRole('heading', { name: 'Research Hub Agent' })).toBeVisible();
  await expect(page.getByTestId('miniapp-preview')).toBeVisible();

  const preview = page.frameLocator('[data-testid="miniapp-preview"]');
  await preview.getByRole('button', { name: 'local action' }).click();
  await expect(page.getByText('本地动作')).toBeVisible();
  await expect(page.getByText('task_card_selected -> {"title":"Alpha"}')).toBeVisible();
  await page.waitForTimeout(200);
  expect(actionBodies).toHaveLength(0);

  await preview.getByRole('button', { name: 'server action' }).click();
  await expect.poll(() => actionBodies.length).toBe(1);
  expect(actionBodies[0]).toMatchObject({
    target: 'server',
    action: 'save_workspace_snapshot',
    payload: { cards: 3, summary: 'save current workspace state' },
  });
  await expect(page.getByText('服务动作')).toBeVisible();

  await preview.getByRole('button', { name: 'agent action' }).click();
  await expect.poll(() => actionBodies.length).toBe(2);
  expect(actionBodies[1]).toMatchObject({
    target: 'agent',
    action: 'request_page_refine',
    payload: { request: 'please refine the page layout' },
  });
  await expect(page.getByText('Agent 动作')).toBeVisible();
  await expect(page.getByText('sess_miniapp').first()).toBeVisible();
});
