import { expect, test } from '@playwright/test';

function mockAuthAndWebSocket() {
  document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
  localStorage.setItem('access_token', 'e2e-access-token');
  localStorage.setItem('refresh_token', 'e2e-refresh-token');

  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
    const { pathname, searchParams } = new URL(url, window.location.origin);

    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

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
    if (pathname.endsWith('/api/skills/check-updates')) {
      return json({ updates: [] });
    }
    if (pathname.endsWith('/api/skills')) {
      return json([
        {
          id: 'skill-disabled-skill',
          name: 'disabled-skill',
          description: 'Disabled skill description',
          category: 'workspace',
          enabled: false,
          source: 'local',
          version: null,
          has_update: false,
          update_version: null,
          dependencies: null,
          all_deps_met: true,
        },
      ]);
    }
    if (pathname.endsWith('/api/skills/market/detail') && searchParams.get('source') === 'local') {
      return json({ detail: { error: '本地 Skill 未找到: disabled-skill', code: 'NETWORK_ERROR' } }, 502);
    }
    if (pathname.endsWith('/api/custom-pages')) {
      return json([]);
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

test('disabled skill 详情接口失败时不应让 /skills 页面崩溃', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });

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

  await page.addInitScript(mockAuthAndWebSocket);
  await page.goto('/skills?token=e2e-sensenova-claw-token');

  await expect(page.getByText('disabled-skill')).toBeVisible();
  await page.getByText('disabled-skill').click();
  await expect(page.getByText('加载失败')).toBeVisible();
  await expect(pageErrors).toEqual([]);
});
