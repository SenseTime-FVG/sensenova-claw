import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('sessions 页面应按页请求并支持上一页下一页切换', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const requestUrls: string[] = [];
    const sessionPages: Record<string, Array<Record<string, unknown>>> = {
      '1': [
        {
          session_id: 'sess_page_001',
          created_at: 1710000000,
          last_active: 1710003600,
          status: 'active',
          meta: JSON.stringify({ title: 'Page One Session A', agent_id: 'helper' }),
        },
        {
          session_id: 'sess_page_002',
          created_at: 1710007200,
          last_active: 1710010800,
          status: 'closed',
          meta: JSON.stringify({ title: 'Page One Session B' }),
        },
      ],
      '2': [
        {
          session_id: 'sess_page_003',
          created_at: 1710014400,
          last_active: 1710018000,
          status: 'closed',
          meta: JSON.stringify({ title: 'Page Two Session A' }),
        },
      ],
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';
      const parsed = new URL(url, window.location.origin);

      if (parsed.pathname.includes('/api/auth/status') || parsed.pathname.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (parsed.pathname.endsWith('/api/sessions') && method === 'GET') {
        requestUrls.push(parsed.toString());
        (window as typeof window & { __sessionPaginationRequests?: string[] }).__sessionPaginationRequests = requestUrls;
        const currentPage = parsed.searchParams.get('page') ?? '';
        const currentPageSize = parsed.searchParams.get('page_size') ?? '';
        const sessions = sessionPages[currentPage] ?? [];
        return new Response(JSON.stringify({
          sessions,
          page: Number(currentPage || '1'),
          page_size: Number(currentPageSize || '50'),
          total: 3,
          active_total: 1,
          total_pages: 2,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (parsed.pathname.includes('/api/agents') && method === 'GET') {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto(`/sessions?token=${encodeURIComponent(token)}`);

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __sessionPaginationRequests?: string[];
    }).__sessionPaginationRequests ?? []).at(0) ?? null);
  }).toContain('/api/sessions?page=1&page_size=50');

  await expect(page.getByText('Page One Session A')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('sessions-pagination-summary')).toContainText('第 1 / 2 页');
  await expect(page.getByTestId('sessions-active-total')).toHaveText('1');
  await expect(page.getByText('Active on current filter')).toBeVisible();

  await page.getByTestId('sessions-pagination-next').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __sessionPaginationRequests?: string[];
    }).__sessionPaginationRequests ?? []).at(-1) ?? null);
  }).toContain('/api/sessions?page=2&page_size=50');
  await expect(page.getByText('Page Two Session A')).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('Page One Session A')).not.toBeVisible();

  await page.getByTestId('sessions-pagination-prev').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __sessionPaginationRequests?: string[];
    }).__sessionPaginationRequests ?? []).at(-1) ?? null);
  }).toContain('/api/sessions?page=1&page_size=50');
  await expect(page.getByText('Page One Session A')).toBeVisible({ timeout: 10000 });
});
