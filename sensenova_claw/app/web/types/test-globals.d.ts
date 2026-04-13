declare global {
  interface Window {
    // Playwright 办公室场景测试会直接读取 Phaser 实例。
    __phaserGame?: any;
  }
}

export {};
