import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  const customPages = [
    {
      id: 'page-issue217',
      slug: 'issue217-test',
      name: 'issue217-test',
      icon: 'Sparkles',
      type: 'miniapp',
      agent_id: 'default',
      create_dedicated_agent: false,
      description: '用于验证删除功能',
      system_prompt: '',
      templates: [],
      workspace_root: 'default/miniapps/issue217-test',
      app_dir: 'default/miniapps/issue217-test/app',
      entry_file_path: 'default/miniapps/issue217-test/app/index.html',
      server_entry_file_path: 'default/miniapps/issue217-test/server.py',
      bridge_script_path: 'default/miniapps/issue217-test/app/sensenova-claw-bridge.js',
      preview_mode: 'server',
      builder_type: 'builtin',
      build_status: 'ready',
    },
  ];
  let lastDeleteWorkspace: string | null = null;
  await page.exposeFunction('__readLastDeleteWorkspace', () => lastDeleteWorkspace);

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/verify-token', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/custom-pages', async (route) => {
    if (customPages.length === 0) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ pages: customPages.map(({ id, slug, name, icon }) => ({ id, slug, name, icon })) }),
    });
  });

  await page.route('**/api/custom-pages/issue217-test*', async (route) => {
    const method = route.request().method().toUpperCase();
    const url = new URL(route.request().url());
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(customPages[0]),
      });
      return;
    }
    if (method === 'DELETE') {
      customPages.splice(0, customPages.length);
      lastDeleteWorkspace = url.searchParams.get('delete_workspace');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/sessions**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.route('**/api/cron/jobs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/todolist/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });
});

test('right-click custom feature opens delete dialog and built-ins stay undeletable', async ({ page }) => {
  await page.goto('/agents?token=test-token');
  await page.getByRole('button', { name: /功能/i }).click();

  await expect(page.getByRole('link', { name: 'issue217-test' })).toBeVisible();
  await page.getByRole('link', { name: 'issue217-test' }).click({ button: 'right' });

  await expect(page.getByTestId('feature-context-menu')).toBeVisible();
  await expect(page.getByTestId('feature-context-menu-delete')).toBeVisible();

  await page.getByTestId('feature-context-menu-delete').click();

  await expect(page.getByTestId('feature-delete-dialog')).toBeVisible();
  await expect(page.getByTestId('feature-delete-workspace-toggle')).toBeVisible();

  await page.getByRole('button', { name: /功能/i }).click();
  await page.getByRole('link', { name: '深度研究' }).click({ button: 'right' });
  await expect(page.getByTestId('feature-context-menu')).not.toBeVisible();
});

test('feature detail page delete redirects and removes nav item immediately', async ({ page }) => {
  await page.goto('/features/issue217-test?token=test-token');

  await expect(page.getByTestId('feature-delete-button')).toBeVisible();
  await page.getByTestId('feature-delete-button').click();

  await expect(page.getByTestId('feature-delete-dialog')).toBeVisible();
  await page.getByTestId('feature-delete-workspace-toggle').click();
  await page.getByTestId('feature-delete-confirm').click();

  await expect.poll(async () => page.evaluate(() => (window as typeof window & { __readLastDeleteWorkspace: () => Promise<string | null> }).__readLastDeleteWorkspace())).toBe('true');
  await page.waitForURL('**/create-feature', { timeout: 1000 });
  await page.getByRole('button', { name: /功能/i }).click();
  await expect(page.getByTestId('feature-nav-item-issue217-test')).not.toBeVisible();
});
