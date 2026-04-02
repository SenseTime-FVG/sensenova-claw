import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

test('单 agent 办公室只应显示当前 agent 的办公室视图', async ({ page }) => {
  const token = readCurrentToken();
  const agents = [
    { id: 'office-main', name: '办公主助手' },
    { id: 'ppt-agent', name: 'PPT 生成助手' },
    { id: 'data-analyst', name: '数据分析助手' },
  ];

  await page.route('**/api/agents', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
    });
  });

  await page.goto(`/office/ppt-agent?token=${token}`);
  await page.waitForFunction(() => Boolean(window.__phaserGame?.scene?.scenes?.[0]));

  const state = await page.evaluate(() => {
    const scene = window.__phaserGame?.scene?.scenes?.[0];
    const entries = Array.from(scene?.agentSprites?.entries?.() ?? []).map(([id, group]) => ({
      id,
      idleVisible: group.idleSprite.visible,
      workVisible: group.workingSprite.visible,
      nameVisible: group.nameLabel.visible,
    }));
    const visible = entries.filter(entry => entry.idleVisible || entry.workVisible || entry.nameVisible);
    return {
      count: entries.length,
      visibleIds: visible.map(entry => entry.id),
    };
  });

  expect(state.count).toBe(1);
  expect(state.visibleIds).toEqual([]);
  await expect(page.getByTestId('office-room-title')).toContainText('PPT 生成助手');
});
