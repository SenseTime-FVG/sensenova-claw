// 办公室状态类型定义

export type OfficeStateName = 'idle' | 'writing' | 'researching' | 'executing' | 'syncing' | 'error';

export interface OfficeState {
  state: OfficeStateName;
  detail: string;
}

export interface OfficeStateInfo {
  name: string;
  area: string;
}

export const STATES: Record<OfficeStateName, OfficeStateInfo> = {
  idle:        { name: '待命', area: 'breakroom' },
  writing:     { name: '整理文档', area: 'writing' },
  researching: { name: '搜索信息', area: 'researching' },
  executing:   { name: '执行任务', area: 'writing' },
  syncing:     { name: '同步备份', area: 'writing' },
  error:       { name: '出错了', area: 'error' },
};

export const BUBBLE_TEXTS: Record<OfficeStateName | 'cat', string[]> = {
  idle: [
    '待命中：耳朵竖起来了',
    '我在这儿，随时可以开工',
    '先把桌面收拾干净再说',
    '呼——给大脑放个风',
    '今天也要优雅地高效',
    '等待，是为了更准确的一击',
    '咖啡还热，灵感也还在',
  ],
  writing: [
    '进入专注模式：勿扰',
    '先把关键路径跑通',
    '我来把复杂变简单',
    '今天的进度，明天的底气',
    '稳住，我们能赢',
  ],
  researching: [
    '我在挖证据链',
    '让我把信息熬成结论',
    '找到了：关键在这里',
    '先定位，再优化',
    '别急，先画因果图',
  ],
  executing: [
    '执行中：不要眨眼',
    '把任务切成小块逐个击破',
    '开始跑 pipeline',
    '一键推进：走你',
    '让结果自己说话',
  ],
  syncing: [
    '同步中：把今天锁进云里',
    '备份不是仪式，是安全感',
    '把变更交给时间戳',
    '云端对齐：咔哒',
  ],
  error: [
    '警报响了：先别慌',
    '我闻到 bug 的味道了',
    '先复现，再谈修复',
    '错误不是敌人，是线索',
    '先止血，再手术',
  ],
  cat: [
    '喵~',
    '咕噜咕噜…',
    '尾巴摇一摇',
    '晒太阳最开心',
    '我是这个办公室的吉祥物',
  ],
};
