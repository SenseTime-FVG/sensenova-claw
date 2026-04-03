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

test('office 左侧应展示总入口和 agent 入口，并支持切换到单 agent 办公室', async ({ page }) => {
  const token = readCurrentToken();
  const agents = [
    { id: 'office-main', name: '办公主助手' },
    { id: 'ppt-agent', name: 'PPT 生成助手' },
    { id: 'data-analyst', name: '数据分析助手' },
  ];

  await page.route('**/api/agents', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
    });
  });

  await page.goto(`/office?token=${token}`);

  await expect(page.getByTestId('office-entry-global')).toBeVisible();
  await expect(page.getByTestId('office-entry-office-main')).toBeVisible();
  await expect(page.getByTestId('office-entry-ppt-agent')).toBeVisible();

  await expect(page.getByTestId('office-entry-global')).toHaveAttribute('aria-current', 'page');

  await page.getByTestId('office-entry-ppt-agent').click();
  await page.waitForURL('**/office/ppt-agent');

  await expect(page.getByTestId('office-entry-ppt-agent')).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('office-room-title')).toContainText('PPT 生成助手');
});
