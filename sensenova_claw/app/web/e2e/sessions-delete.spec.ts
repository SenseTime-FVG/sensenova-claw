import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('sessions 页面应支持选择模式和批量删除', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const deleteCalls: Array<Record<string, unknown>> = [];
    const sessions = [
      {
        session_id: 'sess_active_001',
        created_at: 1710000000,
        last_active: 1710003600,
        status: 'active',
        meta: JSON.stringify({ title: 'Alpha Active', agent_id: 'helper' }),
      },
      {
        session_id: 'sess_closed_001',
        created_at: 1710007200,
        last_active: 1710010800,
        status: 'closed',
        meta: JSON.stringify({ title: 'Alpha Closed' }),
      },
      {
        session_id: 'sess_closed_002',
        created_at: 1710014400,
        last_active: 1710018000,
        status: 'closed',
        meta: JSON.stringify({ title: 'Beta Closed' }),
      },
    ];

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
        return new Response(JSON.stringify({
          sessions,
          page: Number(parsed.searchParams.get('page') ?? '1'),
          page_size: Number(parsed.searchParams.get('page_size') ?? '50'),
          total: sessions.length,
          total_pages: 1,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions/bulk-delete') && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}'));
        deleteCalls.push(body);

        let deletedIds: string[] = [];
        if (Array.isArray(body.session_ids)) {
          deletedIds = body.session_ids;
        } else if (body.filter?.search_term === 'Alpha' && body.filter?.status === 'closed') {
          deletedIds = ['sess_closed_001'];
        }

        for (const id of deletedIds) {
          const idx = sessions.findIndex((session) => session.session_id === id);
          if (idx >= 0) {
            sessions.splice(idx, 1);
          }
        }

        (window as typeof window & { __sessionBulkDeleteCalls?: Array<Record<string, unknown>> }).__sessionBulkDeleteCalls = deleteCalls;
        return new Response(JSON.stringify({
          status: 'deleted',
          deleted_count: deletedIds.length,
          deleted_session_ids: deletedIds,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/agents') && method === 'GET') {
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

  await expect(page.getByText('Alpha Active')).toBeVisible({ timeout: 10000 });
  await page.getByTestId('sessions-selection-toggle').click();
  await expect(page.getByTestId('sessions-bulk-bar')).toBeVisible();

  await page.getByTestId('sessions-select-page').click();
  await expect(page.getByTestId('sessions-selected-summary')).toContainText('已选中当前页面 3 个会话');
  await page.getByTestId('sessions-bulk-delete').click();
  await expect(page.getByTestId('session-bulk-delete-dialog')).toBeVisible();
  await page.getByTestId('session-bulk-delete-confirm').click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __sessionBulkDeleteCalls?: Array<Record<string, unknown>>;
    }).__sessionBulkDeleteCalls ?? []).length);
  }).toBe(1);

  await expect(page.getByText('Alpha Active')).not.toBeVisible();

  await page.fill('input[placeholder="Search session ID or title..."]', 'Alpha');
  await page.selectOption('select', 'closed');
  await page.getByTestId('sessions-selection-toggle').click();
  await page.getByTestId('sessions-select-filtered-all').click();
  await expect(page.getByTestId('sessions-selected-summary')).toContainText('已选中当前筛选的所有结果');
  await page.getByTestId('sessions-bulk-delete').click();
  await expect(page.getByTestId('session-bulk-delete-dialog')).toContainText('当前筛选条件');
  await page.getByTestId('session-bulk-delete-confirm').click();

  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & {
      __sessionBulkDeleteCalls?: Array<Record<string, unknown>>;
    }).__sessionBulkDeleteCalls ?? []).length);
  }).toBe(2);
});

test('sessions 页面删除含子会话的记录时应提供作用域选项', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const deleteCalls: string[] = [];
    const sessions = [
      {
        session_id: 'sess_parent_001',
        created_at: 1710000000,
        last_active: 1710003600,
        status: 'closed',
        meta: JSON.stringify({ title: 'Parent Session', agent_id: 'helper' }),
        has_children: true,
      },
      {
        session_id: 'sess_plain_001',
        created_at: 1710007200,
        last_active: 1710010800,
        status: 'closed',
        meta: JSON.stringify({ title: 'Plain Session' }),
        has_children: false,
      },
    ];

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
        return new Response(JSON.stringify({
          sessions,
          page: Number(parsed.searchParams.get('page') ?? '1'),
          page_size: Number(parsed.searchParams.get('page_size') ?? '50'),
          total: sessions.length,
          total_pages: 1,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/sessions/sess_parent_001') && method === 'DELETE') {
        deleteCalls.push(url);
        (window as typeof window & { __sessionDeleteCalls?: string[] }).__sessionDeleteCalls = deleteCalls;
        return new Response(JSON.stringify({
          status: 'deleted',
          session_id: 'sess_parent_001',
          scope: url.includes('scope=self_and_descendants') ? 'self_and_descendants' : 'self',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/agents') && method === 'GET') {
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

  await expect(page.getByText('Parent Session')).toBeVisible({ timeout: 10000 });
  await page.getByTestId('session-delete-button-sess_parent_001').click();
  await expect(page.getByTestId('session-delete-dialog')).toBeVisible();
  await expect(page.getByTestId('session-delete-dialog')).toContainText('存在子会话');
  await expect(page.getByTestId('session-delete-self-confirm')).toBeVisible();
  await expect(page.getByTestId('session-delete-descendants-confirm')).toBeVisible();

  await page.getByTestId('session-delete-self-confirm').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __sessionDeleteCalls?: string[] }).__sessionDeleteCalls ?? []).at(-1) ?? null);
  }).toContain('/api/sessions/sess_parent_001');
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __sessionDeleteCalls?: string[] }).__sessionDeleteCalls ?? []).at(-1) ?? null);
  }).not.toContain('scope=self_and_descendants');

  await page.getByTestId('session-delete-button-sess_parent_001').click();
  await page.getByTestId('session-delete-descendants-confirm').click();
  await expect.poll(async () => {
    return page.evaluate(() => ((window as typeof window & { __sessionDeleteCalls?: string[] }).__sessionDeleteCalls ?? []).at(-1) ?? null);
  }).toContain('scope=self_and_descendants');
});
