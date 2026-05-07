import { expect, test } from '@playwright/test';

test('token 验证请求失败时不应永久卡在验证中', async ({ page }) => {
  await page.route('**/api/auth/verify-token', async (route) => {
    await route.abort('failed');
  });

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: false }),
    });
  });

  await page.goto('/?token=test-token-123');

  await expect(page.getByText('请输入服务启动时生成的 Token')).toBeVisible({ timeout: 5000 });
  await expect(page.getByText('验证中...')).not.toBeVisible();
});
