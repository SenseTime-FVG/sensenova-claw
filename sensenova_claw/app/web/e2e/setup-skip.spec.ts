import { expect, test } from '@playwright/test';

test('setup 页面点击跳过后不应被立刻重定向回 setup', async ({ page }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const NativeWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/llm-presets')) {
        return new Response(JSON.stringify({ categories: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/')) {
        return new Response(JSON.stringify({}), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };

    function MockWebSocket(url: string | URL, protocols?: string | string[]) {
      const socket = {
        readyState: 1,
        send() {},
        close() {},
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent() { return true; },
        onopen: null,
        onclose: null,
        onerror: null,
        onmessage: null,
        url: String(url),
        protocol: '',
        extensions: '',
        bufferedAmount: 0,
        binaryType: 'blob' as BinaryType,
      };

      window.setTimeout(() => {
        (socket as any).onopen?.(new Event('open'));
      }, 0);

      return socket as unknown as WebSocket;
    }

    Object.assign(MockWebSocket, NativeWebSocket);
    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });

  await page.goto('/setup');
  await page.evaluate(() => {
    sessionStorage.setItem('auth_just_verified', '1');
  });
  await expect(page.getByRole('button', { name: '跳过，稍后配置' })).toBeVisible();
  await page.getByRole('button', { name: '跳过，稍后配置' }).click();

  await page.waitForURL('http://localhost:3000/', { timeout: 5000 });
  await page.waitForTimeout(1500);
  await expect(page).toHaveURL('http://localhost:3000/');
  await expect.poll(async () => {
    return page.evaluate(() => sessionStorage.getItem('llm_setup_skipped'));
  }).toBe('1');
});
