// 办公室 Phaser 场景：状态机、动画、气泡对话
import Phaser from 'phaser';
import { LAYOUT } from './layout';
import { STATES, BUBBLE_TEXTS, type OfficeStateName } from './types';

const BUBBLE_INTERVAL = 8000;
const CAT_BUBBLE_INTERVAL = 18000;

export class OfficeScene extends Phaser.Scene {
  private star!: Phaser.Physics.Arcade.Sprite;
  private sofa!: Phaser.GameObjects.Sprite;
  private serverroom!: Phaser.GameObjects.Sprite;
  private syncAnimSprite!: Phaser.GameObjects.Sprite;
  private starWorking!: Phaser.GameObjects.Sprite;
  private errorBug!: Phaser.GameObjects.Sprite;
  private errorBugDir = 1;
  private catSprite!: Phaser.GameObjects.Sprite;

  private currentState: OfficeStateName = 'idle';
  private bubble: Phaser.GameObjects.Container | null = null;
  private catBubble: Phaser.GameObjects.Container | null = null;
  private lastBubble = 0;
  private lastCatBubble = 0;

  constructor() {
    super({ key: 'OfficeScene' });
  }

  preload() {
    const base = '/office';
    // 背景
    this.load.image('office_bg', `${base}/office_bg_small.webp`);
    // 主角
    this.load.spritesheet('star_idle', `${base}/icon.png`, { frameWidth: 256, frameHeight: 256 });
    this.load.spritesheet('star_working', `${base}/icon.png`, { frameWidth: 256, frameHeight: 256 });
    // 家具
    this.load.image('sofa_idle', `${base}/sofa-idle-v3.png`);
    this.load.image('desk', `${base}/desk-v3.webp`);
    // 装饰动画
    this.load.spritesheet('plants', `${base}/plants-spritesheet.webp`, { frameWidth: 160, frameHeight: 160 });
    this.load.spritesheet('posters', `${base}/posters-spritesheet.webp`, { frameWidth: 160, frameHeight: 160 });
    this.load.spritesheet('coffee_machine', `${base}/coffee-machine-v3-grid.webp`, { frameWidth: 230, frameHeight: 230 });
    this.load.spritesheet('serverroom', `${base}/serverroom-spritesheet.webp`, { frameWidth: 180, frameHeight: 251 });
    this.load.spritesheet('error_bug', `${base}/error-bug-spritesheet-grid.webp`, { frameWidth: 180, frameHeight: 180 });
    this.load.spritesheet('cats', `${base}/cats-spritesheet.webp`, { frameWidth: 160, frameHeight: 160 });
    this.load.spritesheet('sync_anim', `${base}/sync-animation-v3-grid.webp`, { frameWidth: 256, frameHeight: 256 });
    this.load.spritesheet('flowers', `${base}/flowers-bloom-v2.webp`, { frameWidth: 65, frameHeight: 65 });
  }

  create() {
    // 背景
    this.add.image(640, 360, 'office_bg');

    // 沙发
    const sf = LAYOUT.furniture.sofa;
    this.sofa = this.add.sprite(sf.x, sf.y, 'sofa_idle')
      .setOrigin(sf.origin.x, sf.origin.y).setDepth(sf.depth);

    // 主角 idle 精灵（沙发上休息）
    this.anims.create({
      key: 'star_idle',
      frames: this.anims.generateFrameNumbers('star_idle', { start: 0, end: 0 }),
      frameRate: 1, repeat: -1,
    });
    // 放在沙发座面上
    this.star = this.physics.add.sprite(780, 250, 'star_idle')
      .setOrigin(0.5).setScale(0.35).setAlpha(0.9).setDepth(15);
    this.star.play('star_idle');

    // 工作动画精灵（桌前，初始隐藏）
    this.anims.create({
      key: 'star_working',
      frames: this.anims.generateFrameNumbers('star_working', { start: 0, end: 0 }),
      frameRate: 1, repeat: -1,
    });
    const sw = LAYOUT.furniture.starWorking;
    this.starWorking = this.add.sprite(sw.x, sw.y, 'star_working', 0)
      .setOrigin(sw.origin.x, sw.origin.y).setScale(sw.scale).setDepth(sw.depth).setVisible(false);

    // 办公桌
    const dk = LAYOUT.furniture.desk;
    this.add.image(dk.x, dk.y, 'desk').setOrigin(dk.origin.x, dk.origin.y).setDepth(dk.depth);

    // 花盆
    const fl = LAYOUT.furniture.flower;
    const flowerFrame = Math.floor(Math.random() * 16);
    this.add.sprite(fl.x, fl.y, 'flowers', flowerFrame)
      .setOrigin(fl.origin.x, fl.origin.y).setScale(fl.scale).setDepth(fl.depth);

    // 植物
    for (const p of LAYOUT.furniture.plants) {
      this.add.sprite(p.x, p.y, 'plants', Math.floor(Math.random() * 16))
        .setOrigin(0.5).setDepth(p.depth);
    }

    // 海报
    const ps = LAYOUT.furniture.poster;
    this.add.sprite(ps.x, ps.y, 'posters', Math.floor(Math.random() * 32))
      .setOrigin(0.5).setDepth(ps.depth);

    // 咖啡机
    this.anims.create({
      key: 'coffee_machine',
      frames: this.anims.generateFrameNumbers('coffee_machine', { start: 0, end: 95 }),
      frameRate: 12.5, repeat: -1,
    });
    const cm = LAYOUT.furniture.coffeeMachine;
    this.add.sprite(cm.x, cm.y, 'coffee_machine')
      .setOrigin(cm.origin.x, cm.origin.y).setDepth(cm.depth).play('coffee_machine');

    // 服务器区
    this.anims.create({
      key: 'serverroom_on',
      frames: this.anims.generateFrameNumbers('serverroom', { start: 0, end: 39 }),
      frameRate: 6, repeat: -1,
    });
    const sr = LAYOUT.furniture.serverroom;
    this.serverroom = this.add.sprite(sr.x, sr.y, 'serverroom', 0)
      .setOrigin(sr.origin.x, sr.origin.y).setDepth(sr.depth);

    // Bug 精灵
    this.anims.create({
      key: 'error_bug',
      frames: this.anims.generateFrameNumbers('error_bug', { start: 0, end: 95 }),
      frameRate: 12, repeat: -1,
    });
    const eb = LAYOUT.furniture.errorBug;
    this.errorBug = this.add.sprite(eb.x, eb.y, 'error_bug', 0)
      .setOrigin(eb.origin.x, eb.origin.y).setDepth(eb.depth).setScale(eb.scale).setVisible(false);
    this.errorBug.play('error_bug');

    // 同步动画
    this.anims.create({
      key: 'sync_anim',
      frames: this.anims.generateFrameNumbers('sync_anim', { start: 1, end: 48 }),
      frameRate: 12, repeat: -1,
    });
    const sa = LAYOUT.furniture.syncAnim;
    this.syncAnimSprite = this.add.sprite(sa.x, sa.y, 'sync_anim', 0)
      .setOrigin(sa.origin.x, sa.origin.y).setDepth(sa.depth);

    // 小猫（可点击切换）
    const ct = LAYOUT.furniture.cat;
    this.catSprite = this.add.sprite(ct.x, ct.y, 'cats', Math.floor(Math.random() * 16))
      .setOrigin(ct.origin.x, ct.origin.y).setDepth(ct.depth);
    this.catSprite.setInteractive({ useHandCursor: true });
    this.catSprite.on('pointerdown', () => {
      this.catSprite.setFrame(Math.floor(Math.random() * 16));
    });

    // 牌匾
    const pl = LAYOUT.plaque;
    const plaqueBg = this.add.rectangle(pl.x, pl.y, pl.width, pl.height, 0x5d4037);
    plaqueBg.setStrokeStyle(3, 0x3e2723).setDepth(3000);
    this.add.text(pl.x, pl.y, 'Sensenova-Claw 的像素办公室', {
      fontFamily: 'monospace', fontSize: '18px', color: '#ffd700',
      stroke: '#000', strokeThickness: 2,
    }).setOrigin(0.5).setDepth(3001);

    // 监听外部状态变更
    this.game.events.on('setState', (state: OfficeStateName, detail: string) => {
      this.handleStateChange(state, detail);
    });
  }

  update(time: number) {
    // 服务器灯光：工作时亮，空闲时灭
    if (this.currentState === 'idle') {
      if (this.serverroom.anims.isPlaying) {
        this.serverroom.anims.stop();
        this.serverroom.setFrame(0);
      }
    } else {
      if (!this.serverroom.anims.isPlaying) {
        this.serverroom.play('serverroom_on');
      }
    }

    // Bug 弹跳
    if (this.currentState === 'error') {
      this.errorBug.setVisible(true);
      const pp = LAYOUT.furniture.errorBug.pingPong;
      this.errorBug.x += pp.speed * this.errorBugDir;
      if (this.errorBug.x >= pp.rightX) this.errorBugDir = -1;
      if (this.errorBug.x <= pp.leftX) this.errorBugDir = 1;
    } else {
      this.errorBug.setVisible(false);
    }

    // 同步动画
    if (this.currentState === 'syncing') {
      if (!this.syncAnimSprite.anims.isPlaying) this.syncAnimSprite.play('sync_anim');
    } else {
      if (this.syncAnimSprite.anims.isPlaying) this.syncAnimSprite.anims.stop();
      this.syncAnimSprite.setFrame(0);
    }

    // 气泡
    if (time - this.lastBubble > BUBBLE_INTERVAL) {
      this.showBubble();
      this.lastBubble = time;
    }
    if (time - this.lastCatBubble > CAT_BUBBLE_INTERVAL) {
      this.showCatBubble();
      this.lastCatBubble = time;
    }
  }

  private handleStateChange(nextState: OfficeStateName, _detail: string) {
    if (nextState === this.currentState) return;
    this.currentState = nextState;

    if (nextState === 'idle') {
      // 回沙发休息 — 角色显示在沙发上
      this.star.setPosition(780, 250);
      this.star.setVisible(true);
      this.star.play('star_idle');
      this.starWorking.setVisible(false);
      this.starWorking.anims.stop();
    } else if (['writing', 'researching', 'executing'].includes(nextState)) {
      // 桌前工作
      this.star.setVisible(false);
      this.starWorking.setVisible(true);
      this.starWorking.play('star_working');
    } else {
      // syncing / error：隐藏主角，由对应特效展示
      this.star.setVisible(false);
      this.starWorking.setVisible(false);
      this.starWorking.anims.stop();
    }
  }

  private showBubble() {
    if (this.currentState === 'idle') return;
    if (this.bubble) { this.bubble.destroy(); this.bubble = null; }

    const texts = BUBBLE_TEXTS[this.currentState] || BUBBLE_TEXTS.idle;
    const text = texts[Math.floor(Math.random() * texts.length)];

    let anchorX: number, anchorY: number;
    if (this.currentState === 'syncing') {
      anchorX = this.syncAnimSprite.x; anchorY = this.syncAnimSprite.y;
    } else if (this.currentState === 'error') {
      anchorX = this.errorBug.x; anchorY = this.errorBug.y;
    } else {
      anchorX = this.starWorking.x; anchorY = this.starWorking.y;
    }

    const bubbleY = anchorY - 70;
    const bg = this.add.rectangle(anchorX, bubbleY, text.length * 10 + 20, 28, 0xffffff, 0.95);
    bg.setStrokeStyle(2, 0x000000);
    const txt = this.add.text(anchorX, bubbleY, text, {
      fontFamily: 'monospace', fontSize: '12px', color: '#000', align: 'center',
    }).setOrigin(0.5);
    this.bubble = this.add.container(0, 0, [bg, txt]).setDepth(1200);
    this.time.delayedCall(3000, () => {
      if (this.bubble) { this.bubble.destroy(); this.bubble = null; }
    });
  }

  private showCatBubble() {
    if (this.catBubble) { this.catBubble.destroy(); this.catBubble = null; }
    const texts = BUBBLE_TEXTS.cat;
    const text = texts[Math.floor(Math.random() * texts.length)];
    const anchorX = this.catSprite.x;
    const anchorY = this.catSprite.y - 60;
    const bg = this.add.rectangle(anchorX, anchorY, text.length * 10 + 20, 24, 0xfffbeb, 0.95);
    bg.setStrokeStyle(2, 0xd4a574);
    const txt = this.add.text(anchorX, anchorY, text, {
      fontFamily: 'monospace', fontSize: '11px', color: '#8b6914', align: 'center',
    }).setOrigin(0.5);
    this.catBubble = this.add.container(0, 0, [bg, txt]).setDepth(2100);
    this.time.delayedCall(4000, () => {
      if (this.catBubble) { this.catBubble.destroy(); this.catBubble = null; }
    });
  }
}

/** 创建 Phaser 游戏实例，挂载到指定 DOM 元素 */
export function createOfficeGame(parent: HTMLDivElement): Phaser.Game {
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    width: LAYOUT.game.width,
    height: LAYOUT.game.height,
    parent,
    pixelArt: true,
    physics: { default: 'arcade', arcade: { gravity: { x: 0, y: 0 }, debug: false } },
    scene: [OfficeScene],
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
  // 调试用
  (window as unknown as Record<string, unknown>).__phaserGame = game;
  return game;
}
