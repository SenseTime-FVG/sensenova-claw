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

test('office 桌面花瓶贴图应按完整帧尺寸切分', async ({ page }) => {
  const token = readCurrentToken();

  const fulfillJson = (body: unknown) => ({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

  await page.route('**/api/auth/verify-token', async (route) => {
    await route.fulfill(fulfillJson({ authenticated: true }));
  });

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill(fulfillJson({ authenticated: true }));
  });

  await page.route('**/api/custom-pages', async (route) => {
    await route.fulfill(fulfillJson([]));
  });

  await page.route('**/api/config/llm-status', async (route) => {
    await route.fulfill(fulfillJson({ configured: true }));
  });

  await page.route('**/api/sessions', async (route) => {
    await route.fulfill(fulfillJson({ sessions: [] }));
  });

  await page.route('**/api/todolist/**', async (route) => {
    await route.fulfill(fulfillJson({ items: [] }));
  });

  await page.route('**/api/agents', async (route) => {
    await route.fulfill(fulfillJson([{ id: 'office-main', name: '办公主助手' }]));
  });

  await page.route('**/api/office/agent-status', async (route) => {
    await route.fulfill(fulfillJson({
      statuses: {
        'office-main': { status: 'idle' },
      },
    }));
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

      constructor(_url: string) {
        window.setTimeout(() => {
          this.readyState = FakeWebSocket.OPEN;
          this.onopen?.(new Event('open'));
        }, 20);
      }

      send(_data: string) {}
      addEventListener(_type: string, _listener: (event: Event) => void) {}
      removeEventListener(_type: string, _listener: (event: Event) => void) {}
      close() {
        this.readyState = FakeWebSocket.CLOSED;
      }
    }

    // @ts-expect-error 测试中用假 WebSocket 隔离后端依赖
    window.WebSocket = FakeWebSocket;
  });

  await page.goto(`/office?token=${token}`);

  await page.waitForFunction(() => Boolean(window.__phaserGame?.scene?.scenes?.[0]));
  await page.waitForFunction(() => {
    const scene = window.__phaserGame?.scene?.scenes?.[0];
    return Boolean(
      scene?.children?.list?.find?.(
        (obj: any) => obj?.type === 'Sprite' && obj?.texture?.key === 'flowers'
      )
    );
  });

  const flowerTexture = await page.evaluate(() => {
    const scene = window.__phaserGame?.scene?.scenes?.[0];
    const flowerSprite = scene?.children?.list?.find?.(
      (obj: any) => obj?.type === 'Sprite' && obj?.texture?.key === 'flowers'
    );

    return {
      frameWidth: flowerSprite?.frame?.width ?? null,
      frameHeight: flowerSprite?.frame?.height ?? null,
      cutWidth: flowerSprite?.frame?.cutWidth ?? null,
      cutHeight: flowerSprite?.frame?.cutHeight ?? null,
      displayWidth: flowerSprite?.displayWidth ?? null,
      displayHeight: flowerSprite?.displayHeight ?? null,
    };
  });

  expect(flowerTexture.frameWidth).toBe(128);
  expect(flowerTexture.frameHeight).toBe(128);
  expect(flowerTexture.cutWidth).toBe(128);
  expect(flowerTexture.cutHeight).toBe(128);
  expect(flowerTexture.displayWidth).toBeCloseTo(102.4, 1);
  expect(flowerTexture.displayHeight).toBeCloseTo(102.4, 1);
});
