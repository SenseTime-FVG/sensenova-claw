import { expect, test } from '@playwright/test';

test('settings 页面应支持读取并保存 miniapps ACP 配置', async ({ page }) => {
  await page.context().addCookies([
    {
      name: 'sensenova_claw_token',
      value: 'e2e-sensenova-claw-token',
      url: 'http://127.0.0.1:3000',
    },
    {
      name: 'sensenova_claw_token',
      value: 'e2e-sensenova-claw-token',
      url: 'http://localhost:3000',
    },
  ]);

  await page.addInitScript(() => {
    document.cookie = 'sensenova_claw_token=e2e-sensenova-claw-token; path=/';
    localStorage.setItem('access_token', 'e2e-access-token');
    localStorage.setItem('refresh_token', 'e2e-refresh-token');

    const nativeFetch = window.fetch.bind(window);

    const state = {
      llm: {
        providers: {
          mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
          openai: {
            api_key: { configured: true, masked_value: 'sk-••••1234', source: 'config' },
            base_url: 'https://api.openai.com/v1',
            timeout: 60,
            max_retries: 3,
          },
        },
        models: {
          mock: { provider: 'mock', model_id: 'mock-agent-v1' },
          'gpt-4o-mini': {
            provider: 'openai',
            model_id: 'gpt-4o-mini',
            timeout: 60,
            max_output_tokens: 8192,
          },
        },
        default_model: 'gpt-4o-mini',
      },
      miniapps: {
        default_builder: 'builtin',
        acp: {
          enabled: false,
          command: 'codex',
          args: ['--stdio'],
          env: { ACP_PROFILE: 'default' },
          startup_timeout_seconds: 20,
          request_timeout_seconds: 180,
        },
      },
    };

    const putBodies: unknown[] = [];

    Object.assign(window, {
      __settingsAcpBodies: putBodies,
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/auth/me')) {
        return new Response(JSON.stringify({
          user_id: 'u_e2e',
          username: 'e2e',
          email: null,
          is_active: true,
          is_admin: true,
          created_at: Date.now() / 1000,
          last_login: Date.now() / 1000,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/auth/status')) {
        return new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/llm-status')) {
        return new Response(JSON.stringify({ configured: true, providers: ['openai'] }), {
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

      if (url.includes('/api/files/roots')) {
        return new Response(JSON.stringify({ roots: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/files?path=')) {
        return new Response(JSON.stringify({ items: [] }), {
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

      if (url.endsWith('/api/config/sections') && method === 'GET') {
        return new Response(JSON.stringify(state), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/config/sections') && method === 'PUT') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        putBodies.push(body);
        (window as typeof window & { __settingsAcpBodies: unknown[] }).__settingsAcpBodies = putBodies;
        return new Response(JSON.stringify({ status: 'saved' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/settings');
  await expect(page).toHaveURL(/\/acp$/);

  await expect(page.getByRole('heading', { name: 'ACP Settings' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Tools' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Skills' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'ACP' })).toBeVisible();
  await expect(page.getByTestId('miniapps-default-builder-select')).toHaveValue('builtin');
  await expect(page.getByTestId('miniapps-acp-command-input')).toHaveValue('codex');
  await expect(page.getByTestId('miniapps-acp-enabled')).not.toBeChecked();
  await expect(page.getByTestId('miniapps-acp-startup-timeout-input')).toHaveValue('20');
  await expect(page.getByTestId('miniapps-acp-request-timeout-input')).toHaveValue('180');
  await expect(page.getByTestId('miniapps-acp-args-input')).toContainText('--stdio');
  await expect(page.getByTestId('miniapps-acp-env-input')).toContainText('ACP_PROFILE');

  await page.getByTestId('miniapps-default-builder-select').selectOption('acp');
  await page.getByTestId('miniapps-acp-enabled').check();
  await page.getByTestId('miniapps-acp-command-input').fill('claude-code');
  await page.getByTestId('miniapps-acp-startup-timeout-input').fill('45');
  await page.getByTestId('miniapps-acp-request-timeout-input').fill('300');
  await page.getByTestId('miniapps-acp-args-input').fill('[\"--stdio\",\"--json\"]');
  await page.getByTestId('miniapps-acp-env-input').fill('{\n  \"ACP_PROFILE\": \"team\",\n  \"OPENAI_BASE_URL\": \"https://api.openai.com/v1\"\n}');
  await page.getByTestId('save-settings').click();

  await expect(page.getByText('已保存')).toBeVisible();

  const lastBody = await page.evaluate(() => {
    const bodies = (window as typeof window & { __settingsAcpBodies?: unknown[] }).__settingsAcpBodies ?? [];
    return bodies[bodies.length - 1];
  });

  expect(lastBody).toEqual({
    llm: {
      providers: {
        mock: { api_key: '', base_url: '', timeout: 60, max_retries: 1 },
        openai: {
          base_url: 'https://api.openai.com/v1',
          timeout: 60,
          max_retries: 3,
        },
      },
      models: {
        mock: { provider: 'mock', model_id: 'mock-agent-v1' },
        'gpt-4o-mini': {
          provider: 'openai',
          model_id: 'gpt-4o-mini',
          timeout: 60,
          max_output_tokens: 8192,
        },
      },
      default_model: 'gpt-4o-mini',
    },
    miniapps: {
      default_builder: 'acp',
      acp: {
        enabled: true,
        command: 'claude-code',
        args: ['--stdio', '--json'],
        env: {
          ACP_PROFILE: 'team',
          OPENAI_BASE_URL: 'https://api.openai.com/v1',
        },
        startup_timeout_seconds: 45,
        request_timeout_seconds: 300,
      },
    },
  });
});
