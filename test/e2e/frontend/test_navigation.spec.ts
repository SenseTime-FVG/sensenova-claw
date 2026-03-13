import { test, expect } from '@playwright/test';

const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('导航', () => {
  for (const path of ['/chat', '/agents', '/skills', '/tools', '/workflows', '/sessions']) {
    test(`${path} 页面可访问`, async ({ page }) => {
      await page.goto(`${BASE}${path}`);
      await expect(page).not.toHaveTitle(/Error|500|404/);
    });
  }
});
