import { test, expect } from '@playwright/test';

const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('Workflows 页面', () => {
  test('可以访问', async ({ page }) => {
    await page.goto(`${BASE}/workflows`);
    await expect(page).not.toHaveTitle(/Error|500|404/);
  });
});
