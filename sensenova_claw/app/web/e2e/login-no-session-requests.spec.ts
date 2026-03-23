import { expect, test } from '@playwright/test';

test('/login 未认证时不应主动请求 sessions 或建立业务 websocket', async ({ page }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const fetchCalls: string[] = [];
    const wsCalls: string[] = [];
    const NativeWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      fetchCalls.push(url);
      (window as typeof window & { __fetchCalls?: string[] }).__fetchCalls = fetchCalls;

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };

    function MockWebSocket(url: string | URL, protocols?: string | string[]) {
      const urlString = String(url);
      wsCalls.push(urlString);
      (window as typeof window & { __wsCalls?: string[] }).__wsCalls = wsCalls;
      return new NativeWebSocket(url, protocols);
    }

    Object.assign(MockWebSocket, NativeWebSocket);
    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });

  await page.goto('about:blank');
  await page.goto('/login');
  await expect(page.getByText('请输入服务启动时生成的 Token')).toBeVisible({ timeout: 10000 });

  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as typeof window & { __fetchCalls?: string[] }).__fetchCalls ?? [];
      return calls.filter((url) => url.includes('/api/sessions')).length;
    });
  }).toBe(0);

  await expect.poll(async () => {
    return page.evaluate(() => {
      const calls = (window as typeof window & { __wsCalls?: string[] }).__wsCalls ?? [];
      return calls.filter((url) => url.includes('localhost:8000/ws')).length;
    });
  }).toBe(0);
});
