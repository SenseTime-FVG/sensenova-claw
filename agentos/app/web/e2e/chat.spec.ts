import { expect, test } from '@playwright/test';

test('用户可以发送消息并收到响应', async ({ page }) => {
  await page.goto('/chat');

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

test('bash命令工具调用后应显示完整的assistant回复', async ({ page }) => {
  await page.goto('/chat');

  await expect(page.getByText('WebSocket 已连接')).toBeVisible({ timeout: 30000 });

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible();

  const question = '帮我把目录下所有的.py文件都存到一个txt文件中';
  await input.fill(question);
  await page.getByTestId('send-button').click();

  // 等待用户消息显示
  await expect(page.locator('.bubble.user').last()).toHaveText(question, { timeout: 10000 });

  // 等待工具执行消息（至少有一个）
  await expect(page.locator('.bubble.tool').first()).toBeVisible({ timeout: 60000 });

  // 等待最终的 assistant 回复
  const assistantBubbles = page.locator('.bubble.assistant');
  await expect(assistantBubbles.last()).toBeVisible({ timeout: 60000 });

  // 验证 assistant 回复包含实际内容（不只是工具状态）
  const lastAssistantText = await assistantBubbles.last().textContent();
  expect(lastAssistantText).toBeTruthy();
  expect(lastAssistantText!.length).toBeGreaterThan(50); // 应该有实质性内容

  // 验证回复中包含代码或方案相关的关键词
  expect(lastAssistantText).toMatch(/(python|bash|脚本|方案|代码)/i);

  // 验证不只是工具执行状态
  expect(lastAssistantText).not.toMatch(/^工具执行中/);
  expect(lastAssistantText).not.toMatch(/^工具完成/);

  // 打印实际内容用于调试
  console.log('Assistant 回复内容:', lastAssistantText);
});

test('工具消息应显示详细信息并支持展开/收起', async ({ page }) => {
  await page.goto('/chat');

  await expect(page.getByText('WebSocket 已连接')).toBeVisible({ timeout: 30000 });

  const input = page.getByTestId('chat-input');
  const question = '帮我搜索最新的AI新闻';
  await input.fill(question);
  await page.getByTestId('send-button').click();

  // 等待工具消息出现
  const toolBubble = page.locator('.bubble.tool').first();
  await expect(toolBubble).toBeVisible({ timeout: 60000 });

  // 验证工具信息区域存在
  await expect(toolBubble.locator('.tool-info')).toBeVisible();

  // 验证工具名称显示
  await expect(toolBubble.locator('.tool-name')).toBeVisible();

  // 验证状态显示
  await expect(toolBubble.locator('.tool-status')).toBeVisible();

  // 点击参数展开按钮
  const argsToggle = toolBubble.locator('.section-toggle').filter({ hasText: '参数' });
  if (await argsToggle.isVisible()) {
    await argsToggle.click();
    // 验证参数内容显示
    await expect(toolBubble.locator('.section-content').first()).toBeVisible();
  }

  // 等待工具完成
  await expect(toolBubble.locator('.tool-status.completed')).toBeVisible({ timeout: 60000 });

  // 点击结果展开按钮
  const resultToggle = toolBubble.locator('.section-toggle').filter({ hasText: '结果' });
  if (await resultToggle.isVisible()) {
    await resultToggle.click();
    // 验证结果内容显示
    await expect(toolBubble.locator('.section-content').last()).toBeVisible();
  }
});

