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

async function mockOfficeShellApis(page: import('@playwright/test').Page, agents: Array<{ id: string; name: string }>) {
  await page.route('**/api/auth/verify-token', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/custom-pages', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/config/llm-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true }),
    });
  });

  await page.route('**/api/sessions', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.route('**/api/todolist/**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/agents', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
    });
  });

  await page.route('**/api/office/agent-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agents: {
          'office-main': { status: 'idle' },
          'ppt-agent': { status: 'idle' },
          'data-analyst': { status: 'idle' },
        },
        updated_at: 1770000000,
      }),
    });
  });
}

test('office 左侧应展示总入口和 agent 入口，并支持切换到单 agent 办公室', async ({ page }) => {
  const token = readCurrentToken();
  const agents = [
    { id: 'office-main', name: '办公主助手' },
    { id: 'ppt-agent', name: 'PPT 生成助手' },
    { id: 'data-analyst', name: '数据分析助手' },
  ];

  await mockOfficeShellApis(page, agents);

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
