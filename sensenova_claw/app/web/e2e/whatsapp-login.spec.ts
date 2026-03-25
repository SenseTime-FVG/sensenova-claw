import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';

async function mockAuthenticatedWhatsAppBlocked(page: Page, context: BrowserContext) {
  await context.addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'test-token',
      domain: 'localhost',
      path: '/',
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    },
  ]);

  await page.route('**/api/auth/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/gateway/stats', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totalChannels: 1,
        activeChannels: 1,
        totalConnections: 0,
        totalSessions: 0,
      }),
    });
  });

  await page.route('**/api/gateway/channels', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'whatsapp',
          name: 'whatsapp',
          type: 'whatsapp',
          status: 'connected',
          config: {},
        },
      ]),
    });
  });

  await page.route('**/api/gateway/whatsapp/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        authorized: false,
        state: 'connecting',
        phone: null,
        lastQr: 'qr-text',
        lastQrDataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==',
        lastError: null,
      }),
    });
  });
}

async function mockAuthenticatedWhatsAppBlockedWithError(page: Page, context: BrowserContext) {
  await context.addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'test-token',
      domain: 'localhost',
      path: '/',
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    },
  ]);

  await page.route('**/api/auth/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/gateway/stats', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totalChannels: 1,
        activeChannels: 1,
        totalConnections: 0,
        totalSessions: 0,
      }),
    });
  });

  await page.route('**/api/gateway/channels', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'whatsapp',
          name: 'whatsapp',
          type: 'whatsapp',
          status: 'connected',
          config: {},
        },
      ]),
    });
  });

  await page.route('**/api/gateway/whatsapp/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        authorized: false,
        state: 'closed',
        phone: null,
        authDir: '/tmp/wa-auth',
        lastQr: 'qr-text',
        lastQrDataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==',
        lastError: 'WhatsApp reconnect exhausted after 3 attempts.',
        lastStatusCode: 408,
        lastEvent: 'error',
        debugMessage: 'opening handshake timed out',
      }),
    });
  });
}

async function mockAuthenticatedWhatsAppBlockedWithTransientRestart(page: Page, context: BrowserContext) {
  await context.addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'test-token',
      domain: 'localhost',
      path: '/',
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    },
  ]);

  await page.route('**/api/auth/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/gateway/stats', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totalChannels: 1,
        activeChannels: 1,
        totalConnections: 0,
        totalSessions: 0,
      }),
    });
  });

  await page.route('**/api/gateway/channels', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'whatsapp',
          name: 'whatsapp',
          type: 'whatsapp',
          status: 'connected',
          config: {},
        },
      ]),
    });
  });

  await page.route('**/api/gateway/whatsapp/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        authorized: false,
        state: 'restarting',
        phone: null,
        authDir: '/tmp/wa-auth',
        lastQr: 'qr-text',
        lastQrDataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==',
        lastError: 'WhatsApp asked for a restart after pairing (statusCode=515), recreating socket.',
        lastStatusCode: 515,
        lastEvent: 'close',
        debugMessage: 'restart required after pairing, recreating socket',
      }),
    });
  });
}

test('whatsapp 未授权时 gateway 页面显示红灯和授权按钮', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/gateway');

  await expect(page).toHaveURL(/\/gateway$/);
  await expect(page.getByText('unauthorized')).toBeVisible();
  await expect(page.getByRole('button', { name: '授权' })).toBeVisible();
});

test('点击 gateway 中的 whatsapp 授权按钮后进入独立登录页', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/gateway');
  await page.getByRole('button', { name: '授权' }).click();

  await expect(page).toHaveURL(/\/gateway\/whatsapp/);
  await expect(page.getByText('WhatsApp Login')).toBeVisible();
});

test('whatsapp 登录页显示 lastError 错误卡片和排查信息', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlockedWithError(page, context);

  await page.goto('/gateway/whatsapp');

  await expect(page.getByText('WhatsApp Login')).toBeVisible();
  await expect(page.getByText('最近错误')).toBeVisible();
  await expect(page.getByText('WhatsApp reconnect exhausted after 3 attempts.')).toBeVisible();
  await expect(page.getByText('状态码：408')).toBeVisible();
  await expect(page.getByText('调试信息：opening handshake timed out')).toBeVisible();
  await expect(page.getByText('请优先检查 sidecar 进程日志')).toBeVisible();
});

test('whatsapp 登录页在重启配对流程时不显示错误卡片', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlockedWithTransientRestart(page, context);

  await page.goto('/gateway/whatsapp');

  await expect(page.getByText('WhatsApp Login')).toBeVisible();
  await expect(page.getByText('使用手机 WhatsApp 扫描此二维码完成授权。')).toBeVisible();
  await expect(page.getByText('最近错误')).toHaveCount(0);
  await expect(page.getByText('Current State')).toBeVisible();
});

test('whatsapp 未授权时访问普通页面不会自动跳转', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/chat');

  await expect(page).toHaveURL(/\/chat/);
});

test('gateway 页面中 telegram 失败时显示红色状态', async ({ page, context }) => {
  await context.addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'test-token',
      domain: 'localhost',
      path: '/',
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    },
  ]);

  await page.route('**/api/auth/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/gateway/stats', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totalChannels: 1,
        activeChannels: 0,
        totalConnections: 0,
        totalSessions: 0,
      }),
    });
  });

  await page.route('**/api/gateway/channels', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'telegram',
          name: 'telegram',
          type: 'telegram',
          status: 'failed',
          config: {},
        },
      ]),
    });
  });

  await page.route('**/api/gateway/whatsapp/status', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false,
        authorized: false,
        state: 'not_initialized',
      }),
    });
  });

  await page.goto('/gateway');

  const failedBadge = page.getByText('failed').first();
  await expect(failedBadge).toBeVisible();
  await expect(failedBadge).toHaveClass(/bg-red-500/);
});
