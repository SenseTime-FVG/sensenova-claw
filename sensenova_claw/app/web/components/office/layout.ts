// 办公室布局配置：坐标、层级、资源路径

export const LAYOUT = {
  game: { width: 1280, height: 720 },

  areas: {
    door:        { x: 640, y: 550 },
    writing:     { x: 320, y: 360 },
    researching: { x: 320, y: 360 },
    error:       { x: 1066, y: 180 },
    breakroom:   { x: 640, y: 360 },
  },

  furniture: {
    sofa: { x: 670, y: 144, origin: { x: 0, y: 0 }, depth: 10 },
    desk: { x: 218, y: 417, origin: { x: 0.5, y: 0.5 }, depth: 1000 },
    flower: { x: 310, y: 390, origin: { x: 0.5, y: 0.5 }, depth: 1100, scale: 0.8 },
    starWorking: { x: 217, y: 333, origin: { x: 0.5, y: 0.5 }, depth: 900, scale: 1.0 },
    plants: [
      { x: 565, y: 178, depth: 5 },
      { x: 230, y: 185, depth: 5 },
      { x: 977, y: 496, depth: 5 },
    ],
    poster: { x: 252, y: 66, depth: 4 },
    coffeeMachine: { x: 659, y: 397, origin: { x: 0.5, y: 0.5 }, depth: 99 },
    serverroom: { x: 1021, y: 142, origin: { x: 0.5, y: 0.5 }, depth: 2 },
    errorBug: {
      x: 1007, y: 221, origin: { x: 0.5, y: 0.5 }, depth: 50, scale: 0.9,
      pingPong: { leftX: 1007, rightX: 1111, speed: 0.6 },
    },
    syncAnim: { x: 1157, y: 592, origin: { x: 0.5, y: 0.5 }, depth: 40 },
    cat: { x: 94, y: 557, origin: { x: 0.5, y: 0.5 }, depth: 2000 },
  },

  // agent 角色可用的位置槽位
  agentSlots: {
    idle: [
      { x: 780, y: 250, depth: 15 },    // 沙发区位置1
      { x: 830, y: 270, depth: 14 },    // 沙发区位置2
      { x: 730, y: 270, depth: 14 },    // 沙发区位置3
      { x: 500, y: 420, depth: 15 },    // 休息区位置4
      { x: 850, y: 450, depth: 15 },    // 休息区位置5
    ],
    working: [
      { x: 217, y: 333, depth: 900 },   // 工位1（原 starWorking 位置）
      { x: 317, y: 333, depth: 900 },   // 工位2
      { x: 417, y: 333, depth: 900 },   // 工位3
      { x: 517, y: 400, depth: 900 },   // 工位4
      { x: 617, y: 400, depth: 900 },   // 工位5
    ],
  },

  plaque: { x: 640, y: 720 - 36, width: 420, height: 44 },
  totalAssets: 15,
} as const;
