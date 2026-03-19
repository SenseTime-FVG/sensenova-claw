import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';

async function mockAuthenticatedWhatsAppBlocked(page: Page, context: BrowserContext) {
  await context.addCookies([
    {
      name: 'agentos_token',
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

test('whatsapp 未授权时访问 gateway 会自动跳转到独立登录页并显示二维码', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/gateway');

  await expect(page).toHaveURL(/\/gateway\/whatsapp/);
  await expect(page.getByText('WhatsApp Login')).toBeVisible();
  await expect(page.locator('img[alt="WhatsApp QR"]')).toBeVisible();
  await expect(page.getByText('未授权')).toBeVisible();
});

test('whatsapp 未授权时访问 sessions/whatsapp 页面会自动跳转到独立登录页', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/sessions/whatsapp_demo');

  await expect(page).toHaveURL(/\/gateway\/whatsapp/);
  await expect(page.getByText('WhatsApp Login')).toBeVisible();
});

test('whatsapp 未授权时访问非 gateway 页面不会自动跳转', async ({ page, context }) => {
  await mockAuthenticatedWhatsAppBlocked(page, context);

  await page.goto('/chat');

  await expect(page).toHaveURL(/\/chat/);
});
