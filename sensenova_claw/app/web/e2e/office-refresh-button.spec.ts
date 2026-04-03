import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

test('office 右上角刷新按钮应重新拉取最新状态', async ({ page }) => {
  const token = readCurrentToken();
  let agentsRequestCount = 0;
  let shouldDelayNextAgentsRequest = false;
  const refreshRequestController: { release: (() => void) | null } = { release: null };

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

  await page.route('**/api/custom-pages', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/config/llm-status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true }),
    });
  });

  await page.route('**/api/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.route('**/api/todolist/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/agents', async (route) => {
    agentsRequestCount += 1;
    const requestIndex = agentsRequestCount;

    if (shouldDelayNextAgentsRequest) {
      shouldDelayNextAgentsRequest = false;
      await new Promise<void>((resolve) => {
        refreshRequestController.release = resolve;
      });
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: `agent-${requestIndex}`, name: `Agent ${requestIndex}` },
      ]),
    });
  });

  await page.addInitScript(() => {
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
      private listeners = new Map<string, Set<(event: Event) => void>>();

      constructor(_url: string) {
        window.setTimeout(() => {
          this.readyState = FakeWebSocket.OPEN;
          const event = new Event('open');
          this.onopen?.(event);
          this.dispatchEvent(event);
        }, 20);
      }

      send(_data: string) {}

      addEventListener(type: string, listener: (event: Event) => void) {
        const handlers = this.listeners.get(type) ?? new Set<(event: Event) => void>();
        handlers.add(listener);
        this.listeners.set(type, handlers);
      }

      removeEventListener(type: string, listener: (event: Event) => void) {
        this.listeners.get(type)?.delete(listener);
      }

      dispatchEvent(event: Event) {
        this.listeners.get(event.type)?.forEach((listener) => listener(event));
        return true;
      }

      close() {
        this.readyState = FakeWebSocket.CLOSED;
        const event = new CloseEvent('close');
        this.onclose?.(event);
        this.dispatchEvent(event);
      }
    }

    // @ts-expect-error 测试中用假 WebSocket 隔离后端依赖
    window.WebSocket = FakeWebSocket;
  });

  await page.goto(`/office?token=${token}`);
  await page.waitForTimeout(400);

  await expect.poll(() => agentsRequestCount).toBeGreaterThan(0);
  const initialRequestCount = agentsRequestCount;

  const refreshButton = page.getByRole('button', { name: '刷新办公室状态' });
  await expect(refreshButton).toBeVisible();

  shouldDelayNextAgentsRequest = true;
  const refreshClick = refreshButton.click({ force: true });
  await expect.poll(() => agentsRequestCount).toBe(initialRequestCount + 1);
  await expect
    .poll(async () => (await refreshButton.locator('svg').getAttribute('class')) || '')
    .toContain('animate-spin');

  refreshRequestController.release?.();
  await refreshClick;

  await expect(refreshButton).toBeEnabled();
});
