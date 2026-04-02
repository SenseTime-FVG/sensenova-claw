import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('skills 市场请求应携带认证 cookie，避免 browse/search 401', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  let browseHeaders: Record<string, string> | null = null;
  let marketSearchHeaders: Record<string, string> | null = null;
  let unifiedSearchHeaders: Record<string, string> | null = null;

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method().toUpperCase();

    if (pathname.endsWith('/api/auth/status')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
      });
      return;
    }

    if (pathname.endsWith('/api/config/llm-status')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ configured: true }),
      });
      return;
    }

    if (pathname.endsWith('/api/custom-pages')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ pages: [] }),
      });
      return;
    }

    if (pathname.endsWith('/api/sessions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ sessions: [] }),
      });
      return;
    }

    if (/\/api\/todolist\/[^/]+$/.test(pathname)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ date: '2026-03-25', items: [] }),
      });
      return;
    }

    if (pathname.endsWith('/api/skills') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (pathname.endsWith('/api/skills/market/browse')) {
      browseHeaders = await route.request().allHeaders();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'clawhub-starter',
            name: 'ClawHub Starter',
            description: '用于验证 browse 请求认证头。',
            author: 'ClawHub',
            version: '1.0.0',
            downloads: 42,
            source: 'clawhub',
          }],
          total: 1,
        }),
      });
      return;
    }

    if (pathname.endsWith('/api/skills/market/search')) {
      marketSearchHeaders = await route.request().allHeaders();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'clawhub-search',
            name: 'ClawHub Search Result',
            description: '用于验证 market search 请求认证头。',
            author: 'ClawHub',
            version: '1.1.0',
            downloads: 7,
            source: 'clawhub',
          }],
          total: 1,
        }),
      });
      return;
    }

    if (pathname.endsWith('/api/skills/search')) {
      unifiedSearchHeaders = await route.request().allHeaders();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          local_results: [],
          remote_results: [{
            id: 'clawhub-python',
            name: 'Python Market Skill',
            description: '用于验证 unified search 请求认证头。',
            author: 'ClawHub',
            version: '2.0.0',
            downloads: 12,
            source: 'clawhub',
            category: 'clawhub',
          }],
        }),
      });
      return;
    }

    await route.continue();
  });

  await page.goto('/skills');
  await expect(page.getByRole('heading', { name: 'Skills Engine' })).toBeVisible();

  await page.getByRole('button', { name: 'ClawHub' }).click();
  await expect(page.getByText('ClawHub Starter')).toBeVisible();

  await expect.poll(() => browseHeaders).not.toBeNull();
  expect((browseHeaders as any)?.authorization).toBe(`Bearer ${token}`);
  expect((browseHeaders as any)?.cookie).toContain(`sensenova_claw_token=${token}`);

  await page.getByPlaceholder('Search ClawHub market...').fill('starter');
  await page.getByRole('button', { name: 'Search Market' }).click();
  await expect(page.getByText('ClawHub Search Result')).toBeVisible();

  await expect.poll(() => marketSearchHeaders).not.toBeNull();
  expect((marketSearchHeaders as any)?.authorization).toBe(`Bearer ${token}`);
  expect((marketSearchHeaders as any)?.cookie).toContain(`sensenova_claw_token=${token}`);

  await page.getByPlaceholder("Search skills (e.g. 'web search', 'python')...").fill('python');
  await page.getByRole('button', { name: /^Search$/ }).click();
  await expect(page.getByText('Python Market Skill')).toBeVisible();

  await expect.poll(() => unifiedSearchHeaders).not.toBeNull();
  expect((unifiedSearchHeaders as any)?.authorization).toBe(`Bearer ${token}`);
  expect((unifiedSearchHeaders as any)?.cookie).toContain(`sensenova_claw_token=${token}`);
});
