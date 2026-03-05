import { expect, test } from '@playwright/test';

test('用户可以发送消息并收到响应', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('WebSocket 已连接')).toBeVisible({ timeout: 30000 });

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible();

  const question = '帮我搜索英超联赛最近3年的冠亚军分别是什么球队';
  await input.fill(question);
  await page.getByTestId('send-button').click();

  await expect(page.locator('.bubble.user').last()).toHaveText(question, { timeout: 30000 });

  const responseBubble = page.locator('.bubble.assistant, .bubble.tool, .bubble.system');
  await expect(responseBubble.first()).toBeVisible({ timeout: 60000 });
  await expect(responseBubble.first()).not.toHaveText(/^$/, { timeout: 60000 });
});
