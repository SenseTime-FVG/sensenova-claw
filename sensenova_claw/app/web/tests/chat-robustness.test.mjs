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
  assert.match(source, /if \(!isPendingSessionBootstrap\) \{\s*setIsTyping\(false\);\s*\}/s);
  assert.match(source, /pendingSessionBootstrapIdRef\.current = newSid;/);
});

test('手动停止当前轮次时应追加 用户中止 系统消息', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(source, /addMsg\('system', '用户中止'\);/);
});
