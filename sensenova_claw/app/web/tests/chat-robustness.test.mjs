import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('ChatPanel 应在切换会话时清理内联预览状态', () => {
  const source = readSource('components/chat/ChatPanel.tsx');

  assert.match(
    source,
    /useEffect\(\(\) => \{\s*setSlidePreviewDir\(null\);\s*setFilePreview\(null\);\s*\}, \[currentSessionId\]\);/s,
  );
});

test('MessageArea 应在空消息时稳定展示 empty state', () => {
  const source = readSource('components/chat/MessageArea.tsx');

  assert.match(source, /const showEmptyState = messages\.length === 0 && !isTyping;/);
  assert.ok(!source.includes('messages.length === 0 && !currentSessionId'));
});

test('WebSocketContext 手动重连应强制重跑连接 effect', () => {
  const source = readSource('contexts/ws/WebSocketContext.tsx');

  assert.match(source, /const \[connectionNonce, setConnectionNonce\] = useState\(0\);/);
  assert.match(source, /setConnectionNonce\(\(prev\) => prev \+ 1\);/);
  assert.match(source, /\}, \[enabled, connectionNonce\]\);/);
});

test('WebSocketContext 默认应优先走同源 /ws 代理', () => {
  const source = readSource('contexts/ws/WebSocketContext.tsx');

  assert.match(source, /const WS_URL = process\.env\.NEXT_PUBLIC_WS_URL \|\| '\/ws';/);
  assert.doesNotMatch(source, /ws:\/\/localhost:8000\/ws/);
});

test('Next.js rewrites 应代理 /ws 到后端', () => {
  const source = readSource('next.config.mjs');

  assert.match(source, /source: '\/ws'/);
  assert.match(source, /destination: `\$\{API_URL\}\/ws`/);
});

test('前端 node 测试脚本应指向实际存在的测试文件集合', () => {
  const pkg = JSON.parse(readSource('package.json'));

  assert.equal(pkg.scripts['test:icon-route'], 'node --test tests/*.test.mjs');
});

test('聊天泡泡旧的全局 bubble 样式不应再给整行容器叠加背景', () => {
  const source = readSource('app/globals.css');

  assert.match(source, /\.bubble \{\s*min-width: 0;\s*\}/s);
  assert.match(source, /\.bubble\.user \{[\s\S]*background: transparent;[\s\S]*padding: 0;[\s\S]*border-radius: 0;/s);
  assert.match(source, /\.bubble\.assistant \{[\s\S]*background: transparent;[\s\S]*padding: 0;[\s\S]*border-radius: 0;/s);
  assert.match(source, /\.bubble\.tool \{[\s\S]*background: transparent;[\s\S]*padding: 0;[\s\S]*border-radius: 0;/s);
  assert.match(source, /\.bubble\.system \{[\s\S]*background: transparent;[\s\S]*padding: 0;[\s\S]*border-radius: 0;/s);
});

test('新建会话首条消息 bootstrap 期间不应被 session 历史加载提前清掉 isTyping', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(source, /const pendingSessionBootstrapIdRef = useRef<string \| null>\(null\);/);
  assert.match(source, /const isPendingSessionBootstrap = pendingSessionBootstrapIdRef\.current === currentSessionId;/);
  assert.match(source, /if \(!isPendingSessionBootstrap\) \{\s*const stillActive = isTurnStillActive\(events\);\s*setIsTyping\(stillActive\);\s*setTurnActive\(stillActive\);\s*\}/s);
  assert.match(source, /pendingSessionBootstrapIdRef\.current = newSid;/);
});

test('手动停止当前轮次时应追加 用户中止 系统消息', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(source, /addMsg\('system', '用户中止'\);/);
});

test('首条消息尚未创建会话时点击停止应同步清掉 turnActive', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(
    source,
    /if \(!sessionIdRef\.current\) \{\s*pendingInputRef\.current = null;\s*pendingSessionBootstrapIdRef\.current = null;\s*setIsTyping\(false\);\s*setTurnActive\(false\);\s*return;\s*\}/s,
  );
});

test('等待模型响应期间应继续显示停止按钮但允许编辑输入框', () => {
  const chatInputSource = readSource('components/chat/ChatInput.tsx');
  const chatPanelSource = readSource('components/chat/ChatPanel.tsx');
  const chatPageSource = readSource('app/chat/page.tsx');

  assert.match(chatInputSource, /showStopButton\?: boolean;/);
  assert.match(chatInputSource, /if \(!content \|\| !wsConnected \|\| disabled \|\| isSubmitting \|\| showStopButton\) return;/);
  assert.match(chatInputSource, /disabled=\{!wsConnected \|\| disabled\}/);
  assert.match(chatInputSource, /\{showStopButton && onStop \? \(/);

  assert.match(chatPanelSource, /disabled=\{activeInteraction\?\.kind === 'confirmation'\}/);
  assert.match(chatPanelSource, /showStopButton=\{turnActive && !isCurrentSessionQuestionInteraction\}/);

  assert.match(chatPageSource, /disabled=\{activeInteraction\?\.kind === 'confirmation'\}/);
  assert.match(chatPageSource, /showStopButton=\{turnActive && !isCurrentSessionQuestionInteraction\}/);
});

test('历史恢复判断 turnActive 时应把 error.raised 视为终结事件', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(source, /type === 'error' \|\|\s*type === 'error\.raised'/s);
});

test('从历史事件重建消息时应在 error.raised 后收敛仍为 running 的工具状态', () => {
  const source = readSource('lib/chatTypes.ts');

  assert.match(source, /eventType === 'error\.raised'/);
  assert.match(source, /toolInfo:\s*\{[\s\S]*status:\s*'completed'[\s\S]*success:\s*false/s);
});
