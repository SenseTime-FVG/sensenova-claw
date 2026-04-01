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

test('office 右下角小羊应播放待机动画', async ({ page }) => {
  const token = readCurrentToken();
  await page.goto(`/office?token=${token}`);

  await page.waitForFunction(() => Boolean(window.__phaserGame?.scene?.scenes?.[0]));
  await page.waitForFunction(() => {
    const game = window.__phaserGame;
    const scene = game?.scene?.scenes?.[0];
    const sprite = scene?.children?.list?.find?.(
      (obj: any) => obj?.type === 'Sprite' && obj?.x === 1157 && obj?.y === 592
    );
    const anim = game?.anims?.get?.('sync_sheep_idle');
    return Boolean(sprite && anim);
  });

  const state = await page.evaluate(() => {
    const game = window.__phaserGame;
    const scene = game?.scene?.scenes?.[0];
    const sprite = scene?.children?.list?.find?.(
      (obj: any) => obj?.type === 'Sprite' && obj?.x === 1157 && obj?.y === 592
    );
    const anim = game?.anims?.get?.('sync_sheep_idle');
    return {
      frameCount: anim?.frames?.length ?? 0,
      isPlaying: sprite?.anims?.isPlaying ?? false,
      currentAnim: sprite?.anims?.currentAnim?.key ?? null,
      texture: sprite?.texture?.key ?? null,
    };
  });

  expect(state.texture).toBeTruthy();
  expect(state.frameCount).toBeGreaterThan(1);
  expect(state.isPlaying).toBe(true);
  expect(state.currentAnim).toBe('sync_sheep_idle');
});
