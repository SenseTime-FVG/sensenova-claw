export type Locale = 'zh-CN' | 'en-US';

export interface LocaleOption {
  value: Locale;
  label: string;
}

type MessageValue = string | { [key: string]: MessageValue };

const messages: Record<Locale, MessageValue> = {
  'zh-CN': {
    common: {
      agent: 'Agent',
      settings: '设置',
      logout: '登出',
      searchPlaceholder: '搜索...',
      brandTagline: 'AI Agent 工作平台',
    },
    nav: {
      workspace: '工作台',
      ppt: 'PPT',
      chat: '消息',
      office: '办公室',
      features: '功能',
      admin: '管理',
      feature: {
        research: '深度研究',
        automation: '自动化',
        create: '+ 创建',
      },
      adminItems: {
        agents: 'Agents',
        sessions: 'Sessions',
        llms: 'LLMs',
        gateway: 'Gateway',
        tools: 'Tools',
        skills: 'Skills',
        acp: 'ACP',
      },
    },
    preferences: {
      accent: '主题色',
      appearance: '外观',
      fontSize: '字号',
      panelRadius: '圆角',
      language: '语言',
      appearanceModes: {
        light: '浅色',
        dark: '深色',
        system: '系统',
      },
      fontSizes: {
        compact: '紧凑',
        standard: '标准',
        comfortable: '舒适',
      },
      radiusModes: {
        rounded: '圆润',
        sharp: '方正',
      },
      colors: {
        teal: '青绿',
        indigo: '靛蓝',
        amber: '琥珀',
        rose: '玫瑰',
        violet: '紫罗兰',
        slate: '石板蓝',
      },
      locales: {
        'zh-CN': '简体中文',
        'en-US': 'English',
      },
    },
    chat: {
      searchConversations: '搜索对话',
      noConversation: '暂无对话',
      startConversationWith: '开始与 {agent} 的对话',
      selectConversation: '选择一个对话开始聊天',
      sessionId: 'Session ID',
      newChat: '新建',
      agentCount: '{count} Agents',
      teamSessionsCount: '{count} 个团队会话',
      untitledSession: '未命名会话',
      inputPlaceholder: '输入消息… 拖拽文件插入 @引用 (Enter 发送)',
      waitingConnection: '等待连接...',
      connected: 'WebSocket 已连接',
      disconnected: '未连接',
      reconnect: '重连 WebSocket',
      stopGeneration: '停止生成',
      sendMessage: '发送消息',
      addFileReference: '添加文件引用',
      chooseFile: '选择文件',
      chooseFolder: '选择文件夹',
      disclaimer: 'Sensenova-Claw 可能会出错。重要信息请自行核验。',
      availableAgents: '可用 Agents',
      noAgentsFound: '未找到 Agent',
      defaultAgent: '默认 Agent',
      emptyTitle: 'How can I help you today?',
      emptyDescription: '在下方输入消息，开始与 Sensenova-Claw 的新对话。',
      chooseAgentSession: '选择一个 Agent 后开始聊天',
    },
    time: {
      justNow: '刚刚',
      minutesAgo: '{count}分钟前',
      hoursAgo: '{count}小时前',
      daysAgo: '{count}天前',
    },
  },
  'en-US': {
    common: {
      agent: 'Agent',
      settings: 'Settings',
      logout: 'Log out',
      searchPlaceholder: 'Search...',
      brandTagline: 'AI Agent Workspace',
    },
    nav: {
      workspace: 'Workspace',
      ppt: 'PPT',
      chat: 'Chat',
      office: 'Office',
      features: 'Features',
      admin: 'Admin',
      feature: {
        research: 'Research',
        automation: 'Automation',
        create: '+ Create',
      },
      adminItems: {
        agents: 'Agents',
        sessions: 'Sessions',
        llms: 'LLMs',
        gateway: 'Gateway',
        tools: 'Tools',
        skills: 'Skills',
        acp: 'ACP',
      },
    },
    preferences: {
      accent: 'Accent',
      appearance: 'Appearance',
      fontSize: 'Font size',
      panelRadius: 'Corner radius',
      language: 'Language',
      appearanceModes: {
        light: 'Light',
        dark: 'Dark',
        system: 'System',
      },
      fontSizes: {
        compact: 'Compact',
        standard: 'Standard',
        comfortable: 'Comfortable',
      },
      radiusModes: {
        rounded: 'Rounded',
        sharp: 'Sharp',
      },
      colors: {
        teal: 'Teal',
        indigo: 'Indigo',
        amber: 'Amber',
        rose: 'Rose',
        violet: 'Violet',
        slate: 'Slate',
      },
      locales: {
        'zh-CN': '简体中文',
        'en-US': 'English',
      },
    },
    chat: {
      searchConversations: 'Search conversations',
      noConversation: 'No conversations yet',
      startConversationWith: 'Start chatting with {agent}',
      selectConversation: 'Select a conversation to start chatting',
      sessionId: 'Session ID',
      newChat: 'New',
      agentCount: '{count} agents',
      teamSessionsCount: '{count} team sessions',
      untitledSession: 'Untitled session',
      inputPlaceholder: 'Type a message... Drag files to insert @references (Enter to send)',
      waitingConnection: 'Waiting for connection...',
      connected: 'WebSocket connected',
      disconnected: 'Disconnected',
      reconnect: 'Reconnect WebSocket',
      stopGeneration: 'Stop generation',
      sendMessage: 'Send message',
      addFileReference: 'Add file reference',
      chooseFile: 'Choose files',
      chooseFolder: 'Choose folder',
      disclaimer: 'Sensenova-Claw can make mistakes. Consider verifying important information.',
      availableAgents: 'Available agents',
      noAgentsFound: 'No agents found',
      defaultAgent: 'Default agent',
      emptyTitle: 'How can I help you today?',
      emptyDescription: 'Type a message below to start a new conversation with Sensenova-Claw.',
      chooseAgentSession: 'Choose a conversation to start chatting',
    },
    time: {
      justNow: 'just now',
      minutesAgo: '{count}m ago',
      hoursAgo: '{count}h ago',
      daysAgo: '{count}d ago',
    },
  },
};

export const LOCALE_OPTIONS: LocaleOption[] = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en-US', label: 'English' },
];

export function resolveLocale(value?: string | null): Locale {
  if (!value) return 'zh-CN';
  const normalized = value.toLowerCase();
  if (normalized.startsWith('en')) return 'en-US';
  return 'zh-CN';
}

export function detectLocale(): Locale {
  if (typeof document !== 'undefined') {
    return resolveLocale(document.documentElement.lang);
  }
  if (typeof navigator !== 'undefined') {
    return resolveLocale(navigator.language);
  }
  return 'zh-CN';
}

function getMessage(locale: Locale, key: string): string | null {
  const parts = key.split('.');
  let current: MessageValue | undefined = messages[locale];
  for (const part of parts) {
    if (!current || typeof current === 'string' || !(part in current)) {
      return null;
    }
    current = current[part];
  }
  return typeof current === 'string' ? current : null;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = vars[key];
    return value === undefined ? `{${key}}` : String(value);
  });
}

export function translate(
  locale: Locale,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const template = getMessage(locale, key) ?? getMessage('zh-CN', key) ?? key;
  return interpolate(template, vars);
}

export function formatRelativeTime(locale: Locale, ts: number): string {
  if (!Number.isFinite(ts) || ts <= 0) return '';
  const diff = Date.now() / 1000 - ts;
  const resolvedLocale = resolveLocale(locale);
  if (diff < 60) return translate(resolvedLocale, 'time.justNow');
  if (diff < 3600) return translate(resolvedLocale, 'time.minutesAgo', { count: Math.floor(diff / 60) });
  if (diff < 86400) return translate(resolvedLocale, 'time.hoursAgo', { count: Math.floor(diff / 3600) });
  return translate(resolvedLocale, 'time.daysAgo', { count: Math.floor(diff / 86400) });
}
