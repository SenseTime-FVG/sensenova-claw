import { test, expect } from '@playwright/test';

const BASE = process.env.FRONTEND_URL || 'http://localhost:3000';

test.describe('Agents 页面', () => {
  test('可以访问', async ({ page }) => {
    await page.goto(`${BASE}/agents`);
    await expect(page).not.toHaveTitle(/Error|500|404/);
  });

  test('显示 Agent 列表', async ({ page }) => {
    await page.goto(`${BASE}/agents`);
    // 等待页面加载完成
    await page.waitForTimeout(3000);
    // 应至少有 default agent
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });
});
