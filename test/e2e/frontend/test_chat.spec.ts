import { test, expect } from '@playwright/test';

const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('Chat 页面', () => {
  test('可以访问', async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await expect(page).not.toHaveTitle(/Error|500|404/);
  });

  test('包含输入框', async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    const input = page.locator('textarea, input[type="text"]');
    await expect(input.first()).toBeVisible({ timeout: 10000 });
  });
});
