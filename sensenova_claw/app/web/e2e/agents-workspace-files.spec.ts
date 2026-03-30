import { expect, test } from '@playwright/test';

function mockAgentWorkspacePage() {
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  const nativeFetch = window.fetch.bind(window);
  const workspaceCalls: Array<{ method: string; url: string; body?: string }> = [];

  const agentDetail = {
    id: 'researcher',
    name: 'Research Agent',
    status: 'active',
    description: '负责研究任务的测试 Agent',
    model: 'gpt-4o-mini',
    systemPrompt: 'You are a research assistant.',
    temperature: 0.2,
    maxTokens: 4096,
    sessionCount: 1,
    toolCount: 1,
    skillCount: 0,
    tools: ['serper_search'],
    skills: [],
    toolsDetail: [{ name: 'serper_search', description: 'Search the web', enabled: true }],
    skillsDetail: [],
    canDelegateTo: [],
    maxDelegationDepth: 3,
    sessions: [],
  };

  const workspaceFiles = [
    { name: 'AGENTS.md', size: 32, editable: true },
    { name: 'PLAN.md', size: 64, editable: true },
  ];
  const fileContents: Record<string, string> = {
    'AGENTS.md': '# Research Agent\n\nGlobal instructions',
    'PLAN.md': '# Research Plan\n\nInitial plan',
  };

  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
    const method = init?.method?.toUpperCase() ?? 'GET';
    const parsed = new URL(url, window.location.origin);
    const pathname = parsed.pathname;
    const agentId = parsed.searchParams.get('agent_id');

    if (pathname.endsWith('/api/auth/status') || pathname.endsWith('/api/auth/verify-token')) {
      return json({ authenticated: true });
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
    if (pathname.endsWith('/api/config/llm-status')) {
      return json({ configured: true });
    }
    if (pathname.endsWith('/api/custom-pages')) {
      return json([]);
    }
    if (pathname.endsWith('/api/agents/researcher') && method === 'GET') {
      return json(agentDetail);
    }
    if (pathname.endsWith('/api/agents') && method === 'GET') {
      return json([{ id: 'researcher', name: 'Research Agent' }]);
    }
    if (pathname.endsWith('/api/config/sections') && method === 'GET') {
      return json({ llm: { models: { 'gpt-4o-mini': {}, 'gpt-5': {} } } });
    }
    if (pathname.endsWith('/api/workspace/files') && agentId === 'researcher' && method === 'GET') {
      workspaceCalls.push({ method, url: parsed.toString() });
      (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls = workspaceCalls;
      return json(workspaceFiles);
    }
    if (pathname.endsWith('/api/workspace/files/PLAN.md') && agentId === 'researcher' && method === 'GET') {
      workspaceCalls.push({ method, url: parsed.toString() });
      (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls = workspaceCalls;
      return json({ name: 'PLAN.md', content: fileContents['PLAN.md'] });
    }
    if (pathname.endsWith('/api/workspace/files/PLAN.md') && agentId === 'researcher' && method === 'PUT') {
      workspaceCalls.push({ method, url: parsed.toString(), body: typeof init?.body === 'string' ? init.body : undefined });
      (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls = workspaceCalls;
      fileContents['PLAN.md'] = typeof init?.body === 'string' ? JSON.parse(init.body).content : fileContents['PLAN.md'];
      return json({ name: 'PLAN.md', size: fileContents['PLAN.md'].length, status: 'saved' });
    }
    if (pathname.endsWith('/api/workspace/files/notes.md') && agentId === 'researcher' && method === 'PUT') {
      workspaceCalls.push({ method, url: parsed.toString(), body: typeof init?.body === 'string' ? init.body : undefined });
      (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls = workspaceCalls;
      fileContents['notes.md'] = typeof init?.body === 'string' ? JSON.parse(init.body).content : '# notes';
      workspaceFiles.push({ name: 'notes.md', size: fileContents['notes.md'].length, editable: true });
      return json({ name: 'notes.md', size: fileContents['notes.md'].length, status: 'saved' });
    }
    if (pathname.endsWith('/api/workspace/files/notes.md') && agentId === 'researcher' && method === 'GET') {
      workspaceCalls.push({ method, url: parsed.toString() });
      (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls = workspaceCalls;
      return json({ name: 'notes.md', content: fileContents['notes.md'] });
    }

    return nativeFetch(input, init);
  };

  window.confirm = () => true;

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

    constructor(_url: string | URL, _protocols?: string | string[]) {
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

test('agent 详情页的 Workspace Files 请求应携带 agent_id', async ({ page }) => {
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

  await page.addInitScript(mockAgentWorkspacePage);
  await page.goto('/agents/researcher?token=e2e-sensenova-claw-token');

  await expect(page.getByText('Research Agent')).toBeVisible();
  await page.getByRole('button', { name: 'Workspace Files' }).click();

  await expect(page.getByText('PLAN.md')).toBeVisible();
  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __workspaceCalls?: Array<{ method: string; url: string }> }).__workspaceCalls ?? [];
      return calls.some((call) => call.method === 'GET' && call.url.includes('/api/workspace/files?agent_id=researcher'));
    });
  }).toBe(true);

  await page.getByText('PLAN.md').click();
  await expect(page.locator('textarea')).toHaveValue(/Initial plan/);
  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __workspaceCalls?: Array<{ method: string; url: string }> }).__workspaceCalls ?? [];
      return calls.some((call) => call.method === 'GET' && call.url.includes('/api/workspace/files/PLAN.md?agent_id=researcher'));
    });
  }).toBe(true);

  await page.locator('textarea').fill('# Research Plan\n\nUpdated plan');
  await page.getByRole('button', { name: 'Save File' }).click();
  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __workspaceCalls?: Array<{ method: string; url: string; body?: string }> }).__workspaceCalls ?? [];
      return calls.some((call) =>
        call.method === 'PUT'
          && call.url.includes('/api/workspace/files/PLAN.md?agent_id=researcher')
          && call.body?.includes('Updated plan'),
      );
    });
  }).toBe(true);

  await page.getByTitle('New file').click();
  await page.getByPlaceholder('filename.md').fill('notes');
  await page.getByRole('button', { name: 'Add' }).click();
  await expect(page.getByText('notes.md')).toBeVisible();
  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __workspaceCalls?: Array<{ method: string; url: string }> }).__workspaceCalls ?? [];
      return calls.some((call) => call.method === 'PUT' && call.url.includes('/api/workspace/files/notes.md?agent_id=researcher'));
    });
  }).toBe(true);
});
