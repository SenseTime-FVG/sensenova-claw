import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';

type AgentSpriteGroup = {
  idleSprite: {
    visible: boolean;
    x: number;
    y: number;
    anims?: {
      isPlaying?: boolean;
      currentAnim?: { key?: string };
    };
  };
  workingSprite: {
    visible: boolean;
    x: number;
    y: number;
    anims?: {
      isPlaying?: boolean;
      currentAnim?: { key?: string };
    };
  };
  nameLabel: { visible: boolean };
};

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

async function mockOfficeShellApis(
  page: import('@playwright/test').Page,
  agents: Array<{ id: string; name: string }>,
  statuses: Record<string, { status: 'idle' | 'running' | 'error' }>,
) {
  await page.route('**/api/auth/verify-token', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/auth/status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: true }),
    });
  });

  await page.route('**/api/custom-pages', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/config/llm-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true }),
    });
  });

  await page.route('**/api/sessions', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });

  await page.route('**/api/todolist/**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/agents', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
    });
  });

  await page.route('**/api/office/agent-status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agents: statuses,
        updated_at: 1770000000,
      }),
    });
  });
}

test('单 agent 办公室只应显示当前 agent 的办公室视图', async ({ page }) => {
  const token = readCurrentToken();
  const agents = [
    { id: 'office-main', name: '办公主助手' },
    { id: 'ppt-agent', name: 'PPT 生成助手' },
    { id: 'data-analyst', name: '数据分析助手' },
  ];

  await mockOfficeShellApis(page, agents, {
    'office-main': { status: 'idle' },
    'ppt-agent': { status: 'idle' },
    'data-analyst': { status: 'idle' },
  });

  await page.goto(`/office/ppt-agent?token=${token}`);
  await page.waitForFunction(() => Boolean(window.__phaserGame?.scene?.scenes?.[0]));
  await page.waitForFunction(() => window.__phaserGame?.scene?.scenes?.[0]?.agentSprites?.size === 1);

  const state = await page.evaluate(() => {
    const scene = window.__phaserGame?.scene?.scenes?.[0];
    const rawEntries = Array.from(
      (scene?.agentSprites?.entries?.() ?? []) as Iterable<[string, AgentSpriteGroup]>
    );
    const entries = rawEntries.map(([id, group]) => ({
      id,
      idleVisible: group.idleSprite.visible,
      workVisible: group.workingSprite.visible,
      nameVisible: group.nameLabel.visible,
      idleX: group.idleSprite.x,
      idleY: group.idleSprite.y,
    }));
    const visible = entries.filter(entry => entry.idleVisible || entry.workVisible || entry.nameVisible);
    return {
      count: entries.length,
      visibleIds: visible.map(entry => entry.id),
      idleEntry: entries[0] ?? null,
    };
  });

  expect(state.count).toBe(1);
  expect(state.visibleIds).toEqual(['ppt-agent']);
  expect(state.idleEntry?.idleX).toBe(780);
  expect(state.idleEntry?.idleY).toBe(250);
  await expect(page.getByTestId('office-room-title')).toContainText('PPT 生成助手');
});

test('单 agent 办公室中运行中的羊应移动到电脑前', async ({ page }) => {
  const token = readCurrentToken();
  const agents = [
    { id: 'office-main', name: '办公主助手' },
    { id: 'ppt-agent', name: 'PPT 生成助手' },
  ];

  await mockOfficeShellApis(page, agents, {
    'office-main': { status: 'idle' },
    'ppt-agent': { status: 'running' },
  });

  await page.goto(`/office/ppt-agent?token=${token}`);
  await page.waitForFunction(() => Boolean(window.__phaserGame?.scene?.scenes?.[0]));
  await page.waitForFunction(() => window.__phaserGame?.scene?.scenes?.[0]?.agentSprites?.size === 1);

  const state = await page.evaluate(() => {
    const game = window.__phaserGame;
    const scene = window.__phaserGame?.scene?.scenes?.[0];
    const rawEntries = Array.from(
      (scene?.agentSprites?.entries?.() ?? []) as Iterable<[string, AgentSpriteGroup]>
    );
    const group = rawEntries[0]?.[1];
    const syncSprite = scene?.children?.list?.find?.(
      (obj: any) => obj?.type === 'Sprite' && obj?.x === 1157 && obj?.y === 592
    );
    return {
      count: rawEntries.length,
      idleVisible: group?.idleSprite.visible ?? false,
      workVisible: group?.workingSprite.visible ?? false,
      workX: group?.workingSprite.x ?? null,
      workY: group?.workingSprite.y ?? null,
      workAnimKey: group?.workingSprite.anims?.currentAnim?.key ?? null,
      workAnimPlaying: group?.workingSprite.anims?.isPlaying ?? false,
      idleFrameCount: game?.anims?.get?.('star_idle')?.frames?.length ?? 0,
      workFrameCount: game?.anims?.get?.('star_working_breath')?.frames?.length ?? 0,
      syncVisible: syncSprite?.visible ?? null,
    };
  });

  expect(state.count).toBe(1);
  expect(state.idleVisible).toBe(false);
  expect(state.workVisible).toBe(true);
  expect(state.workX).toBe(217);
  expect(state.workY).toBe(333);
  expect(state.workAnimKey).toBe('star_working_breath');
  expect(state.workAnimPlaying).toBe(true);
  expect(state.idleFrameCount).toBeGreaterThan(1);
  expect(state.workFrameCount).toBe(state.idleFrameCount);
  expect(state.syncVisible).toBe(false);
});
