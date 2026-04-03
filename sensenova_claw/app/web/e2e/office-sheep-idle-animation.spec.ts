import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';

type OfficeIdleAgentGroup = {
  idleSprite: {
    visible: boolean;
    anims: {
      isPlaying: boolean;
      currentAnim?: { key?: string };
    };
  };
};

function readCurrentToken(): string {
  try {
    return fs.readFileSync(path.join(os.homedir(), '.sensenova-claw', 'token'), 'utf-8').trim();
  } catch {
    return 'test-token';
  }
}

test('office 页面中的待命小羊应播放多帧 idle 动画', async ({ page }) => {
  const token = readCurrentToken();
  await page.goto(`/office?token=${token}`);

  await page.waitForFunction(() => {
    const game = (window as typeof window & {
      __phaserGame?: {
        events?: { emit: (eventName: string, payload: unknown) => void };
        scene: { scenes: Array<{ agentSprites?: Map<string, unknown> }> };
      };
    }).__phaserGame;
    return Boolean(game?.scene?.scenes?.length);
  });

  await page.waitForFunction(() => {
    const game = (window as typeof window & {
      __phaserGame?: {
        anims?: { get: (key: string) => { frames?: unknown[] } | undefined };
      };
    }).__phaserGame;
    return (game?.anims?.get?.('star_idle')?.frames?.length ?? 0) > 0;
  });

  await page.evaluate(() => {
    const scene = (window as typeof window & {
      __phaserGame?: {
        scene?: {
          scenes?: Array<{
            handleAgentsUpdate?: (agents: Array<{ id: string; name: string }>) => void;
            handleStateChange?: (state: string, detail: string) => void;
          }>;
        };
      };
    }).__phaserGame?.scene?.scenes?.[0];
    scene?.handleAgentsUpdate?.([{ id: 'office-sheep-test', name: '像素小羊' }]);
    scene?.handleStateChange?.('idle', '');
  });

  const idleState = await page.evaluate(() => {
    const game = (window as typeof window & {
      __phaserGame: {
        anims: { get: (key: string) => { frames: unknown[] } | undefined };
        scene: {
          scenes: Array<{
            agentSprites?: Map<
              string,
              {
                idleSprite: {
                  visible: boolean;
                  anims: {
                    isPlaying: boolean;
                    currentAnim?: { key?: string };
                  };
                };
              }
            >;
          }>;
        };
      };
    }).__phaserGame;
    const idleAnim = game.anims.get('star_idle');
    const scene = game.scene.scenes[0];
    const agents = Array.from(
      (scene.agentSprites?.values?.() ?? []) as Iterable<OfficeIdleAgentGroup>
    );
    const visibleIdleAgents = agents.filter(agent => agent.idleSprite.visible);
    return {
      idleFrameCount: idleAnim?.frames.length ?? 0,
      idleAgentCount: visibleIdleAgents.length,
      allIdleAgentsPlaying: visibleIdleAgents.every(
        agent =>
          agent.idleSprite.anims.isPlaying &&
          agent.idleSprite.anims.currentAnim?.key === 'star_idle'
      ),
    };
  });

  expect(idleState.idleAgentCount).toBeGreaterThan(0);
  expect(idleState.idleFrameCount).toBeGreaterThan(1);
  expect(idleState.allIdleAgentsPlaying).toBe(true);
});
