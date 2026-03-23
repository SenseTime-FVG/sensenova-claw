import { expect, test } from '@playwright/test';

test('根路径应保留 token 查询参数重定向到 /chat', async ({ page }) => {
  await page.route('**/api/auth/verify-token', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.goto('/?token=test-token-123&from=root');

  await page.waitForURL('**/chat?token=test-token-123&from=root', { timeout: 3000 });
  await expect(page.getByText('验证中...')).toBeVisible();
});
