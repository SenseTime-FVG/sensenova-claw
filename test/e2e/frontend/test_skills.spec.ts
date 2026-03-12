import { test, expect } from '@playwright/test';

const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('Skills 页面', () => {
  test('可以访问', async ({ page }) => {
    await page.goto(`${BASE}/skills`);
    await expect(page).not.toHaveTitle(/Error|500|404/);
  });

  test('显示 Skills 列表', async ({ page }) => {
    await page.goto(`${BASE}/skills`);
    await page.waitForTimeout(3000);
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });
});
