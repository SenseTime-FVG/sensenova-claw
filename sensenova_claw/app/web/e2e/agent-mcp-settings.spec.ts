import { expect, test } from '@playwright/test';

function mockAgentMcpPage() {
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  const nativeFetch = window.fetch.bind(window);
  const configCalls: Array<{ method: string; url: string; body?: string }> = [];

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
    mcpServerCount: 2,
    mcpToolCount: 3,
    tools: ['serper_search'],
    skills: [],
    mcpServers: ['docs-search', 'browser'],
    mcpTools: ['docs-search/search_docs', 'docs-search/fetch_page', 'browser/click'],
    toolsDetail: [{ name: 'serper_search', description: 'Search the web', enabled: true }],
    skillsDetail: [],
    mcpServersDetail: [
      { name: 'docs-search', transport: 'stdio', enabled: true, toolCount: 2 },
      { name: 'browser', transport: 'streamable-http', enabled: true, toolCount: 1 },
    ],
    mcpToolsDetail: [
      { name: 'docs-search/search_docs', serverName: 'docs-search', toolName: 'search_docs', safeName: 'mcp__docs_search__search_docs', description: '搜索文档', enabled: true },
      { name: 'docs-search/fetch_page', serverName: 'docs-search', toolName: 'fetch_page', safeName: 'mcp__docs_search__fetch_page', description: '抓取页面', enabled: true },
      { name: 'browser/click', serverName: 'browser', toolName: 'click', safeName: 'mcp__browser__click', description: '点击页面元素', enabled: true },
    ],
    canDelegateTo: [],
    maxDelegationDepth: 3,
    sessions: [],
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
    const pathname = new URL(url, window.location.origin).pathname;

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
    if (pathname.endsWith('/api/agents/researcher/config') && method === 'PUT') {
      configCalls.push({ method, url, body: typeof init?.body === 'string' ? init.body : undefined });
      Object.assign(window, { __agentConfigCalls: configCalls });
      return json(agentDetail);
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
    constructor(_url: string | URL, _protocols?: string | string[]) {
      window.setTimeout(() => this.onopen?.(new Event('open')), 0);
    }
    send(_data: string) {}
    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.(new Event('close'));
    }
    addEventListener() {}
    removeEventListener() {}
  }

  (window as Window & { WebSocket: typeof WebSocket }).WebSocket = MockWebSocket as unknown as typeof WebSocket;
}

test('agent 详情页应支持按 server/tool 配置 MCP 开关', async ({ page }) => {
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

  await page.addInitScript(mockAgentMcpPage);
  await page.goto('/agents/researcher?token=e2e-sensenova-claw-token');

  await page.getByRole('button', { name: 'mcp' }).click();
  await expect(page.getByText('MCP Servers & Tools')).toBeVisible();

  await page.getByTestId('mcp-server-toggle-browser').click();
  await page.getByTestId('mcp-server-expand-docs-search').click();
  await page.getByTestId('mcp-tool-toggle-docs-search-fetch_page').click();
  await page.getByRole('button', { name: 'Save Preferences' }).click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __agentConfigCalls?: Array<{ body?: string }> }).__agentConfigCalls ?? [];
      return calls.length;
    });
  }).toBe(1);

  const payload = await page.evaluate(() => {
    const calls = (window as Window & { __agentConfigCalls?: Array<{ body?: string }> }).__agentConfigCalls ?? [];
    return calls[0]?.body ? JSON.parse(calls[0].body) : null;
  });

  expect(payload).toMatchObject({
    mcp_servers: ['docs-search'],
    mcp_tools: ['docs-search/search_docs'],
  });
});

test('agent 详情页应支持将 MCP 全部禁用保存为 null', async ({ page }) => {
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

  await page.addInitScript(mockAgentMcpPage);
  await page.goto('/agents/researcher?token=e2e-sensenova-claw-token');

  await page.getByRole('button', { name: 'mcp' }).click();
  await page.getByTestId('mcp-server-toggle-browser').click();
  await page.getByTestId('mcp-server-toggle-docs-search').click();
  await page.getByRole('button', { name: 'Save Preferences' }).click();

  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as Window & { __agentConfigCalls?: Array<{ body?: string }> }).__agentConfigCalls ?? [];
      return calls.length;
    });
  }).toBe(1);

  const payload = await page.evaluate(() => {
    const calls = (window as Window & { __agentConfigCalls?: Array<{ body?: string }> }).__agentConfigCalls ?? [];
    return calls[0]?.body ? JSON.parse(calls[0].body) : null;
  });

  expect(payload).toMatchObject({
    mcp_servers: null,
    mcp_tools: null,
  });
});
