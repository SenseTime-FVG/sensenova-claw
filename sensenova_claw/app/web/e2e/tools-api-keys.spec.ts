import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('tools 页面应展示详细的搜索工具 token 获取步骤', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([{
    name: 'sensenova_claw_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    const toolList = [
      {
        id: 'tool-serper_search',
        name: 'serper_search',
        description: 'Google search via Serper API',
        category: 'builtin',
        riskLevel: 'low',
        enabled: true,
        parameters: {},
        requiresApiKey: true,
        apiKeyConfigured: false,
      },
      {
        id: 'tool-brave_search',
        name: 'brave_search',
        description: 'Web search via Brave Search API',
        category: 'builtin',
        riskLevel: 'low',
        enabled: true,
        parameters: {},
        requiresApiKey: true,
        apiKeyConfigured: false,
      },
    ];

    const apiKeys = {
      serper_search: {
        configured: false,
        masked_key: null,
        docs_url: 'https://serper.dev/',
        description: 'Google search via Serper API',
        setup_guide: [
          '1. 打开 https://serper.dev/ ，点击 Sign up / Get started，使用邮箱或 Google 账号完成注册并登录。',
          '2. 登录后进入 Dashboard，在页面中找到 API Key 区域；Serper 会在控制台里直接展示可复制的 key。',
          '3. 点击复制按钮获取 API Key。Serper 官方提供免费试用额度，通常可以先不绑信用卡就完成测试。',
          '4. 把复制出的 API Key 粘贴到这里，点击 Validate 验证；验证通过后，再保存到当前工具配置中。',
        ],
        example_format: '<serper-api-key>',
      },
      brave_search: {
        configured: false,
        masked_key: null,
        docs_url: 'https://api-dashboard.search.brave.com/app/documentation/web-search/get-started',
        description: 'Web search via Brave Search API',
        setup_guide: [
          '1. 打开 Brave Search API 文档页 https://api-dashboard.search.brave.com/app/documentation/web-search/get-started ，点击 Log in 注册或登录控制台。',
          '2. 登录后进入 dashboard，在 Subscriptions 中选择并订阅一个 Web Search plan；没有订阅时不会生成可用 token。',
          '3. 打开订阅后的应用或凭据页面，复制请求头里要用的 X-Subscription-Token。',
          '4. 把这个 token 粘贴到这里，点击 Validate 验证；验证通过后保存即可。',
        ],
        example_format: '<brave-x-subscription-token>',
      },
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/status') || url.includes('/api/auth/verify-token')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/custom-pages')) {
        return new Response(JSON.stringify({ pages: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/cron/runs')) {
        return new Response(JSON.stringify({ runs: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/sessions')) {
        return new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/tools') && method === 'GET') {
        return new Response(JSON.stringify(toolList), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/tools/api-keys') && method === 'GET') {
        return new Response(JSON.stringify(apiKeys), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/notifications/config')) {
        return new Response(JSON.stringify({
          enabled: true,
          channels: ['browser', 'session'],
          native: { enabled: false },
          browser: { enabled: true },
          electron: { enabled: false },
          session: { enabled: true },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('about:blank');
  await page.goto('/tools');

  await expect(page.getByRole('heading', { name: 'Tools Workspace' })).toBeVisible();
  await page.getByRole('tab', { name: 'API Keys' }).click();

  const tabsList = page.locator('[data-slot="tabs-list"]').first();
  const tabsListBox = await tabsList.boundingBox();
  const serperCardBox = await page.getByTestId('api-key-card-serper_search').boundingBox();
  expect(tabsListBox).not.toBeNull();
  expect(serperCardBox).not.toBeNull();
  expect(serperCardBox!.y).toBeGreaterThan(tabsListBox!.y + 20);
  expect(Math.abs(serperCardBox!.x - tabsListBox!.x)).toBeLessThan(80);

  const serperGuide = page.getByTestId('setup-guide-serper_search');
  await expect(page.getByTestId('api-key-card-serper_search')).toBeVisible();
  await serperGuide.locator('summary').click();
  await expect(serperGuide).toContainText('Dashboard');
  await expect(serperGuide).toContainText('免费试用额度');
  await expect(serperGuide).toContainText('https://serper.dev/');

  const braveGuide = page.getByTestId('setup-guide-brave_search');
  await expect(page.getByTestId('api-key-card-brave_search')).toBeVisible();
  await braveGuide.locator('summary').click();
  await expect(braveGuide).toContainText('Subscriptions');
  await expect(braveGuide).toContainText('X-Subscription-Token');
  await expect(braveGuide).toContainText('Web Search plan');
});
