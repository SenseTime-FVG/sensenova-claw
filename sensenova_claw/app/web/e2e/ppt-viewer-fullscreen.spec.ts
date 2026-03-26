import { expect, test } from '@playwright/test';

type MockWindow = Window & {
  __mockWs?: {
    emit: (data: unknown) => void;
  };
  WebSocket: typeof globalThis.WebSocket;
};

function mockAuthAndWebSocket() {
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

    constructor(url: string) {
      if (url.includes('/ws')) {
        (window as unknown as MockWindow).__mockWs = this;
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

    emit(data: unknown) {
      const event = { data: JSON.stringify(data) } as MessageEvent;
      this.onmessage?.(event);
      (this.listeners.message || []).forEach((listener) => listener(event));
    }
  }

  (window as unknown as MockWindow).WebSocket = MockWebSocket as unknown as typeof globalThis.WebSocket;
}

test.describe('ppt viewer fullscreen', () => {
  test.beforeEach(async ({ page }) => {
    const now = Date.now() / 1000;

    await page.context().addCookies([
      {
        name: 'sensenova_claw_token',
        value: 'e2e-sensenova-claw-token',
        domain: '127.0.0.1',
        path: '/',
      },
      {
        name: 'sensenova_claw_token',
        value: 'e2e-sensenova-claw-token',
        domain: 'localhost',
        path: '/',
      },
    ]);

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'u_ppt',
          username: 'ppt-e2e',
          email: null,
          is_active: true,
          is_admin: true,
          created_at: now,
          last_login: now,
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
            description: '用于预览 PPT 的默认智能体',
            status: 'active',
            model: 'mock-model',
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
              session_id: 'sess_ppt_preview',
              created_at: now,
              last_active: now,
              status: 'active',
              meta: JSON.stringify({
                title: 'PPT 预览会话',
                agent_id: 'default',
              }),
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

    await page.route('**/api/files/workdir-list?*', async (route) => {
      const url = new URL(route.request().url());
      const dir = url.searchParams.get('dir');

      if (dir === 'default/demo_ppt') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            dir,
            slides: [
              { name: 'page_01.html', path: 'default/demo_ppt/page_01.html' },
              { name: 'page_02.html', path: 'default/demo_ppt/page_02.html' },
            ],
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ dir, slides: [] }),
      });
    });

    await page.route('**/api/files/workdir/default/demo_ppt/page_*.html', async (route) => {
      const slideName = route.request().url().includes('page_02.html') ? 'Slide 2' : 'Slide 1';
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: `<!doctype html><html><body style="margin:0;display:flex;align-items:center;justify-content:center;width:1280px;height:720px;background:#0f172a;color:#e2e8f0;font:700 64px sans-serif;">${slideName}</body></html>`,
      });
    });

    await page.addInitScript(mockAuthAndWebSocket);
  });

  test('fullscreen preview still exposes exit and close actions', async ({ page }) => {
    await page.goto('/chat');
    await page.waitForFunction(() => Boolean((window as unknown as MockWindow).__mockWs));
    await page.getByText('PPT 预览会话').last().click();
    await expect(page.getByText('Session:')).toBeVisible();

    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('sensenova-claw:open-slide-preview', {
        detail: {
          dir: 'default/demo_ppt',
          isAbsolute: true,
        },
      }));
    });

    const viewer = page.getByTestId('slide-viewer');
    const fullscreenToggle = page.getByTestId('slide-fullscreen-toggle');

    await expect(viewer).toHaveAttribute('data-fullscreen', 'false');
    await expect(fullscreenToggle).toHaveAttribute('aria-label', '放大预览');

    await fullscreenToggle.click();

    await expect(viewer).toHaveAttribute('data-fullscreen', 'true');
    await expect(page.getByRole('button', { name: '退出放大' })).toBeVisible();
    await expect(page.getByRole('button', { name: '关闭预览' })).toBeVisible();

    await page.getByRole('button', { name: '退出放大' }).click();

    await expect(viewer).toHaveAttribute('data-fullscreen', 'false');
    await expect(fullscreenToggle).toHaveAttribute('aria-label', '放大预览');
  });
});
