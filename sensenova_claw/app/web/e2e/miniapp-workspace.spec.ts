import { expect, test, type Page } from '@playwright/test';

type WorkspacePhase = 'running' | 'ready';

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
        return new (NativeWebSocket as any)(url, protocols);
      }

      window.setTimeout(() => {
        const event = new Event('open');
        (this as any).onopen?.(event);
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

async function addAuthCookies(page: Page) {
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
}

function jsonResponse(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  };
}

function buildPagePayload(phase: WorkspacePhase, now: number, startTs: number, lastInteractionSessionId: string) {
  const common = {
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
    preview_mode: 'server',
    server_entry_file_path: 'miniapp-research-hub-agent/miniapps/research-hub/server.py',
    server_start_command: '/usr/bin/python3',
    server_start_args: ['server.py'],
    background_refresh_policy: 'optional_cron',
    entry_file_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/index.html',
    bridge_script_path: 'miniapp-research-hub-agent/miniapps/research-hub/app/sensenova-claw-bridge.js',
    preserved_license_files: [],
    last_interaction_session_id: lastInteractionSessionId,
    workspace_root: 'miniapp-research-hub-agent/miniapps/research-hub',
    app_dir: 'miniapp-research-hub-agent/miniapps/research-hub/app',
    updated_at: now,
  };

  if (phase === 'running') {
    return {
      ...common,
      builder_type: 'acp',
      generation_prompt: 'Build a research workspace',
      build_status: 'running',
      build_summary: '正在生成 mini-app...',
      latest_run_id: 'run_live',
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
            { ts: startTs + 100, level: 'info', message: '开始生成 mini-app' },
            { ts: startTs + 200, level: 'info', message: 'ACP agent_thought_chunk: Inspect' },
            { ts: startTs + 300, level: 'info', message: 'ACP agent_thought_chunk: files' },
            { ts: startTs + 350, level: 'info', message: 'ACP tool_call [in_progress]: Edit app.js' },
            { ts: startTs + 400, level: 'info', message: 'ACP agent_message_chunk: Building' },
            { ts: startTs + 500, level: 'info', message: 'ACP agent_message_chunk: workspace' },
          ],
        },
      ],
    };
  }

  return {
    ...common,
    builder_type: 'builtin',
    generation_prompt: '做一个自带 server 的通用工作区，只在最后兜底时把动作分发给 Agent',
    build_status: 'ready',
    build_summary: 'workspace 已生成并接入独立 Web server，可直接预览；普通问答不会默认触发刷新',
    latest_run_id: 'run_1',
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
          { ts: now, level: 'info', message: '使用内置模板: generic-workspace-server' },
        ],
      },
    ],
  };
}

async function setupMiniAppWorkspace(page: Page, phase: WorkspacePhase) {
  let lastInteractionSessionId = '';
  let pageDetailRequestCount = 0;
  const actionBodies: Record<string, unknown>[] = [];
  const startTs = Date.now();

  await addAuthCookies(page);

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill(jsonResponse({
      user_id: 'u_e2e',
      username: 'e2e',
      email: null,
      is_active: true,
      is_admin: true,
      created_at: Date.now() / 1000,
      last_login: Date.now() / 1000,
    }));
  });

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill(jsonResponse({ authenticated: true }));
  });

  await page.route('**/api/auth/verify-token', async (route) => {
    await route.fulfill(jsonResponse({ authenticated: true }));
  });

  await page.route('**/api/config/llm-status', async (route) => {
    await route.fulfill(jsonResponse({ configured: true }));
  });

  await page.route('**/api/agents*', async (route) => {
    await route.fulfill(jsonResponse([
      {
        id: 'miniapp-research-hub-agent',
        name: 'Research Hub Agent',
        description: '通用工作区专属 Agent',
      },
    ]));
  });

  await page.route('**/api/skills', async (route) => {
    await route.fulfill(jsonResponse([]));
  });

  await page.route('**/api/files/roots', async (route) => {
    await route.fulfill(jsonResponse({ roots: [] }));
  });

  await page.route('**/api/files?path=*', async (route) => {
    await route.fulfill(jsonResponse({ items: [] }));
  });

  await page.route('**/api/custom-pages', async (route) => {
    const url = route.request().url();
    if (!url.endsWith('/api/custom-pages')) {
      await route.fallback();
      return;
    }
    await route.fulfill(jsonResponse({
      pages: [
        {
          id: 'page_research_hub',
          slug: 'research-hub',
          name: 'Research Hub',
          icon: 'BookOpen',
        },
      ],
    }));
  });

  await page.route('**/api/todolist/**', async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split('/').filter(Boolean);
    const dateStr = parts[parts.length - 1] || '2026-03-25';
    await route.fulfill(jsonResponse({ date: dateStr, items: [] }));
  });

  await page.route('**/api/custom-pages/research-hub', async (route) => {
    pageDetailRequestCount += 1;
    const now = Date.now();
    await route.fulfill(jsonResponse(buildPagePayload(phase, now, startTs, lastInteractionSessionId)));
  });

  await page.route('**/api/custom-pages/research-hub/actions', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}');
    actionBodies.push(body);

    if (body.target === 'agent') {
      lastInteractionSessionId = 'sess_miniapp';
      await route.fulfill(jsonResponse({
        ok: true,
        target: 'agent',
        session_id: 'sess_miniapp',
        turn_id: 'turn_from_preview',
        refresh_mode: body.refresh_mode || 'none',
        should_refresh_workspace: body.refresh_mode === 'immediate',
      }));
      return;
    }

    await route.fulfill(jsonResponse({
      ok: true,
      target: 'server',
      session_id: '',
      turn_id: '',
      refresh_mode: body.refresh_mode || 'none',
      should_refresh_workspace: body.refresh_mode === 'immediate',
    }));
  });

  await page.route('**/api/sessions', async (route) => {
    await route.fulfill(jsonResponse({ sessions: [] }));
  });

  await page.route('**/api/sessions/sess_miniapp/events', async (route) => {
    await route.fulfill(jsonResponse({ events: [] }));
  });

  await page.route('**/api/cron/runs*', async (route) => {
    await route.fulfill(jsonResponse({ runs: [] }));
  });

  await page.route('**/api/custom-pages/research-hub/preview**', async (route) => {
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
            <button id="refresh-action">refresh action</button>
            <script>
              window.parent.postMessage({
                source: 'sensenova-claw-miniapp',
                slug: 'research-hub',
                kind: 'config',
                meta: {
                  defaultTarget: 'server',
                  routes: {
                    task_card_selected: 'local',
                    save_workspace_snapshot: 'server',
                    request_page_refine: 'agent',
                    request_workspace_rebuild: 'agent',
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
                  meta: { refreshMode: 'none' },
                }, '*');
              });

              document.getElementById('agent-action').addEventListener('click', () => {
                window.parent.postMessage({
                  source: 'sensenova-claw-miniapp',
                  slug: 'research-hub',
                  kind: 'interaction',
                  action: 'request_page_refine',
                  payload: { request: 'please refine the page layout' },
                  meta: { refreshMode: 'none' },
                }, '*');
              });

              document.getElementById('refresh-action').addEventListener('click', () => {
                window.parent.postMessage({
                  source: 'sensenova-claw-miniapp',
                  slug: 'research-hub',
                  kind: 'interaction',
                  action: 'request_workspace_rebuild',
                  payload: { reason: 'schema changed' },
                  meta: { refreshMode: 'immediate' },
                }, '*');
              });
            </script>
          </body>
        </html>
      `,
    });
  });

  await page.addInitScript(mockAuthAndWebSocket);

  return {
    actionBodies,
    getPageDetailRequestCount: () => pageDetailRequestCount,
  };
}

async function openWorkspace(page: Page) {
  await page.goto('/features/research-hub', { waitUntil: 'domcontentloaded' }).catch((error: Error) => {
    if (!String(error).includes('ERR_ABORTED')) {
      throw error;
    }
  });
  await expect.poll(() => page.url()).toContain('/features/research-hub');
}

test('mini-app 工作区在构建中时应展示 builder 消息流', async ({ page }) => {
  await setupMiniAppWorkspace(page, 'running');
  await openWorkspace(page);

  await expect(page.getByTestId('workspace-floating-tabs')).toBeVisible();
  await expect(page.getByTestId('workspace-overview-panel')).toBeVisible();
  await expect(page.getByTestId('workspace-chat-fab')).toBeVisible();

  await page.getByTestId('workspace-chat-fab').click();
  await expect(page.getByTestId('workspace-chat-floating-panel')).toBeVisible();
  await expect(page.getByText('正在转发当前构建任务的 builder 消息...')).toBeVisible();
  await expect(page.getByText('Research Hub 构建消息流')).toBeVisible();
  await expect(page.getByText('Build a research workspace')).toBeVisible();
  await expect(page.getByText(/Building\s*workspace/)).toBeVisible();
  await expect(page.getByTestId('build-tool-card')).toContainText('Edit app.js');
  await expect(page.getByTestId('build-tool-status')).toContainText('运行中');
});

test('mini-app 工作区在 ready 后应按 local/server/agent/immediate 分流动作', async ({ page }) => {
  const harness = await setupMiniAppWorkspace(page, 'ready');
  await openWorkspace(page);

  await expect(page.getByTestId('workspace-floating-tabs')).toBeVisible();
  await expect(page.getByTestId('workspace-overview-panel')).toBeVisible();
  await expect(page.getByTestId('miniapp-preview')).toBeVisible();

  const detailRequestsBeforeActions = harness.getPageDetailRequestCount();
  const preview = page.frameLocator('[data-testid="miniapp-preview"]');

  await preview.getByRole('button', { name: 'local action' }).click();
  await expect(page.getByText('本地动作')).toBeVisible();
  await expect(page.getByText('task_card_selected [refresh=none] -> {"title":"Alpha"}')).toBeVisible();
  await page.waitForTimeout(200);
  expect(harness.actionBodies).toHaveLength(0);

  await preview.getByRole('button', { name: 'server action' }).click();
  await expect.poll(() => harness.actionBodies.length).toBe(1);
  expect(harness.actionBodies[0]).toMatchObject({
    target: 'server',
    action: 'save_workspace_snapshot',
    payload: { cards: 3, summary: 'save current workspace state' },
    refresh_mode: 'none',
  });
  await expect(page.getByText('服务动作')).toBeVisible();
  await page.waitForTimeout(200);
  expect(harness.getPageDetailRequestCount()).toBe(detailRequestsBeforeActions);

  await preview.getByRole('button', { name: 'agent action' }).click();
  await expect.poll(() => harness.actionBodies.length).toBe(2);
  expect(harness.actionBodies[1]).toMatchObject({
    target: 'agent',
    action: 'request_page_refine',
    payload: { request: 'please refine the page layout' },
    refresh_mode: 'none',
  });
  await expect(page.getByText('Agent 动作')).toBeVisible();
  await expect(page.getByTestId('workspace-chat-floating-panel')).toBeVisible();
  await page.waitForTimeout(200);
  expect(harness.getPageDetailRequestCount()).toBe(detailRequestsBeforeActions);

  await preview.getByRole('button', { name: 'refresh action' }).click();
  await expect.poll(() => harness.actionBodies.length).toBe(3);
  expect(harness.actionBodies[2]).toMatchObject({
    target: 'agent',
    action: 'request_workspace_rebuild',
    payload: { reason: 'schema changed' },
    refresh_mode: 'immediate',
  });
  await expect.poll(() => harness.getPageDetailRequestCount()).toBe(detailRequestsBeforeActions + 1);
});
