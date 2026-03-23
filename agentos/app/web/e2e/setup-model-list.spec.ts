import { expect, test } from '@playwright/test';

test('setup 页面选择 minimax 时应使用具体 provider 拉取动态模型列表', async ({ page }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method?.toUpperCase() ?? 'GET';

      if (url.includes('/api/config/llm-presets')) {
        return new Response(JSON.stringify({
          categories: [
            {
              key: 'openai_compatible',
              label: 'OpenAI 兼容',
              providers: [
                {
                  key: 'openai',
                  label: 'OpenAI',
                  base_url: 'https://api.openai.com/v1',
                  models: [],
                },
                {
                  key: 'minimax',
                  label: 'MiniMax',
                  base_url: 'https://api.minimax.chat/v1',
                  models: [
                    { key: 'abab6_5s_chat', model_id: 'abab6.5s-chat' },
                    { key: 'abab6_5g_chat', model_id: 'abab6.5g-chat' },
                  ],
                },
              ],
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/config/list-models') && method === 'POST') {
        const bodyText = typeof init?.body === 'string' ? init.body : '{}';
        const body = JSON.parse(bodyText);

        (window as typeof window & { __lastListModelsBody?: unknown }).__lastListModelsBody = body;

        const models = body.provider === 'minimax'
          ? [
              { id: 'MiniMax-M2.7-highspeed', owned_by: 'minimax' },
              { id: 'MiniMax-Text-01', owned_by: 'minimax' },
            ]
          : [
              { id: 'abab6.5s-chat', owned_by: 'preset-fallback' },
            ];

        return new Response(JSON.stringify({ success: true, models }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return nativeFetch(input, init);
    };
  });

  await page.goto('/setup');

  await page.getByRole('button', { name: 'OpenAI 兼容' }).click();
  await page.getByRole('button', { name: 'MiniMax' }).click();
  await expect(page.getByRole('heading', { name: '填写连接配置' })).toBeVisible();
  await page.getByPlaceholder('sk-...').fill('sk-minimax-test');
  await page.getByRole('button', { name: '下一步' }).click();

  await expect(page.getByText('MiniMax-M2.7-highspeed')).toBeVisible();
  await expect(page.getByText('MiniMax-Text-01')).toBeVisible();
  await expect(page.getByText('abab6.5s-chat')).not.toBeVisible();

  const requestBody = await page.evaluate(() => {
    return (window as typeof window & { __lastListModelsBody?: unknown }).__lastListModelsBody;
  });

  expect(requestBody).toMatchObject({
    provider: 'minimax',
    base_url: 'https://api.minimax.chat/v1',
    api_key: 'sk-minimax-test',
  });
});
