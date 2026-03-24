import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
}

test('settings 页面应支持读取并保存 miniapps ACP 配置', async ({ page }) => {
  const token = readCurrentToken();
  await page.context().addCookies([
    {
      name: 'sensenova_claw_token',
      value: token,
      domain: 'localhost',
      path: '/',
    },
  ]);

  await page.addInitScript((currentToken) => {
    document.cookie = `sensenova_claw_token=${currentToken}; path=/`;
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
    const installBodies: unknown[] = [];
    const wizardState = {
      platform: {
        id: 'windows',
        label: 'Windows',
        python: 'C:/Python/python.exe',
      },
      installers: {
        npm: { id: 'npm', label: 'npm', found: true, path: 'C:/Program Files/nodejs/npm.cmd', candidate: 'npm' },
        powershell: { id: 'powershell', label: 'PowerShell', found: true, path: 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', candidate: 'powershell' },
      },
      current_config: state.miniapps.acp,
      agents: [
        {
          id: 'gemini',
          name: 'Gemini CLI',
          summary: 'Gemini CLI 原生支持 ACP，需带上 --experimental-acp。',
          homepage: 'https://github.com/google-gemini/gemini-cli',
          platforms: ['linux', 'macos', 'windows'],
          supported_on_current_platform: true,
          mode: 'native',
          ready: true,
          configured: false,
          components: [
            { id: 'gemini', label: 'Gemini CLI', found: true, path: 'C:/Tools/gemini.cmd', candidate: 'gemini' },
          ],
          runtime: { id: 'gemini', label: 'Gemini CLI', found: true, path: 'C:/Tools/gemini.cmd', candidate: 'gemini' },
          missing_components: [],
          recommended_config: {
            enabled: true,
            command: 'C:/Tools/gemini.cmd',
            args: ['--experimental-acp'],
            env: { ACP_PROFILE: 'default' },
            startup_timeout_seconds: 20,
            request_timeout_seconds: 180,
            default_builder: 'acp',
          },
          install_steps: [
            {
              id: 'agent',
              label: '安装 Gemini CLI',
              installed: true,
              available: true,
              selected_recipe_id: 'npm',
              command_preview: 'npm install -g @google/gemini-cli',
              note: '官方 npm 包',
            },
          ],
          env_hints: [
            { key: 'GEMINI_API_KEY', description: '如果不使用交互登录，可在 env 中提供', required: false },
          ],
          notes: ['Gemini CLI 的 ACP 仍是 experimental 模式，推荐保留默认参数 --experimental-acp。'],
        },
        {
          id: 'codex',
          name: 'Codex CLI',
          summary: '通过 Zed 官方 codex-acp adapter 将 Codex CLI 接入 ACP。',
          homepage: 'https://github.com/zed-industries/codex-acp',
          platforms: ['linux', 'macos', 'windows'],
          supported_on_current_platform: true,
          mode: 'adapter',
          ready: false,
          configured: false,
          components: [
            { id: 'codex', label: 'Codex CLI', found: false, path: '', candidate: 'codex' },
            { id: 'codex-acp', label: 'codex-acp adapter', found: false, path: '', candidate: 'codex-acp' },
          ],
          runtime: { id: 'codex-acp', label: 'codex-acp adapter', found: false, path: '', candidate: 'codex-acp' },
          missing_components: ['Codex CLI', 'codex-acp adapter'],
          recommended_config: {
            enabled: true,
            command: 'codex-acp',
            args: [],
            env: { ACP_PROFILE: 'default' },
            startup_timeout_seconds: 20,
            request_timeout_seconds: 180,
            default_builder: 'acp',
          },
          install_steps: [
            {
              id: 'agent',
              label: '安装 Codex CLI',
              installed: false,
              available: true,
              selected_recipe_id: 'npm',
              command_preview: 'npm install -g @openai/codex',
              note: '官方 npm 包',
            },
            {
              id: 'adapter',
              label: '安装 codex-acp adapter',
              installed: false,
              available: true,
              selected_recipe_id: 'npm',
              command_preview: 'npm install -g @zed-industries/codex-acp',
              note: 'Zed 官方 adapter',
            },
          ],
          env_hints: [],
          notes: [],
        },
      ],
    };

    Object.assign(window, {
      __settingsAcpBodies: putBodies,
      __settingsAcpInstallBodies: installBodies,
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

      if (url.includes('/api/auth/verify-token')) {
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

      if (url.endsWith('/api/config/acp/wizard') && method === 'GET') {
        return new Response(JSON.stringify(wizardState), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/config/acp/wizard/install') && method === 'POST') {
        const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}');
        installBodies.push(body);
        wizardState.agents = wizardState.agents.map(agent => (
          agent.id === 'codex'
            ? {
                ...agent,
                ready: true,
                components: agent.components.map(component => ({ ...component, found: true, path: `C:/Tools/${component.candidate}.cmd` })),
                runtime: { ...agent.runtime, found: true, path: 'C:/Tools/codex-acp.cmd' },
                install_steps: agent.install_steps.map(step => ({ ...step, installed: true })),
              }
            : agent
        ));
        Object.assign(window, {
          __settingsAcpInstallBodies: installBodies,
        });
        return new Response(JSON.stringify({ ok: true, wizard: wizardState }), {
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
  }, token);

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

  await page.goto('about:blank');
  await page.goto('/acp');
  await expect(page).toHaveURL(/\/acp$/);

  await expect(page.getByRole('heading', { name: 'ACP Settings' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Tools' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Skills' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'ACP' })).toBeVisible();
  await expect(page.getByTestId('acp-wizard-platform')).toContainText('Windows');
  await expect(page.getByTestId('acp-wizard-card-gemini')).toContainText('Gemini CLI');
  await expect(page.getByTestId('acp-wizard-card-codex')).toContainText('缺少依赖');
  await expect(page.getByTestId('miniapps-default-builder-select')).toHaveValue('builtin');
  await expect(page.getByTestId('miniapps-acp-command-input')).toHaveValue('codex');
  await expect(page.getByTestId('miniapps-acp-enabled')).not.toBeChecked();
  await expect(page.getByTestId('miniapps-acp-startup-timeout-input')).toHaveValue('20');
  await expect(page.getByTestId('miniapps-acp-request-timeout-input')).toHaveValue('180');
  await expect(page.getByTestId('miniapps-acp-args-input')).toContainText('--stdio');
  await expect(page.getByTestId('miniapps-acp-env-input')).toContainText('ACP_PROFILE');

  await page.getByTestId('acp-wizard-apply-gemini').click();
  await expect(page.getByTestId('miniapps-default-builder-select')).toHaveValue('acp');
  await expect(page.getByTestId('miniapps-acp-enabled')).toBeChecked();
  await expect(page.getByTestId('miniapps-acp-command-input')).toHaveValue('C:/Tools/gemini.cmd');
  await expect(page.getByTestId('miniapps-acp-args-input')).toContainText('--experimental-acp');

  await page.getByTestId('acp-wizard-install-codex').click();
  await expect(page.getByText('Codex CLI 安装完成')).toBeVisible();
  await expect(page.getByTestId('acp-wizard-card-codex')).toContainText('可直接使用');

  await page.getByTestId('miniapps-acp-startup-timeout-input').fill('45');
  await page.getByTestId('miniapps-acp-request-timeout-input').fill('300');
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
        command: 'C:/Tools/gemini.cmd',
        args: ['--experimental-acp'],
        env: {
          ACP_PROFILE: 'team',
          OPENAI_BASE_URL: 'https://api.openai.com/v1',
        },
        startup_timeout_seconds: 45,
        request_timeout_seconds: 300,
      },
    },
  });

  const lastInstallBody = await page.evaluate(() => {
    const bodies = (window as typeof window & { __settingsAcpInstallBodies?: unknown[] }).__settingsAcpInstallBodies ?? [];
    return bodies[bodies.length - 1];
  });

  expect(lastInstallBody).toEqual({ agent_id: 'codex' });
});
