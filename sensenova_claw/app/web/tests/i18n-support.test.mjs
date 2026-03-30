import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const webRoot = process.cwd();

function readSource(relativePath) {
  return readFileSync(resolve(webRoot, relativePath), 'utf8');
}

test('根布局应将 I18nProvider 挂到用户偏好 Provider 内部', () => {
  const source = readSource('app/layout.tsx');

  const prefsIndex = source.indexOf('<UserPreferencesProvider>');
  const i18nIndex = source.indexOf('<I18nProvider>');
  const protectedRouteIndex = source.indexOf('<ProtectedRoute>');

  assert.notEqual(prefsIndex, -1, '缺少 UserPreferencesProvider');
  assert.notEqual(i18nIndex, -1, '缺少 I18nProvider');
  assert.notEqual(protectedRouteIndex, -1, '缺少 ProtectedRoute');
  assert.ok(prefsIndex < i18nIndex, 'I18nProvider 应位于用户偏好 Provider 内部');
  assert.ok(i18nIndex < protectedRouteIndex, 'I18nProvider 应包裹受保护页面');
});

test('用户偏好上下文应持久化 locale 并暴露 setLocale', () => {
  const source = readSource('contexts/UserPreferencesContext.tsx');

  assert.match(source, /locale:\s*Locale;/, '用户偏好中缺少 locale 字段');
  assert.match(source, /locale:\s*'zh-CN'/, '默认语言应落到 zh-CN');
  assert.match(source, /setLocale:\s*\(locale:\s*Locale\)\s*=>\s*void;/, 'Context value 应暴露 setLocale');
  assert.match(source, /const setLocale = useCallback\(\(locale: Locale\) => \{/, 'Provider 应实现 setLocale');
});

test('聊天与导航主链路应通过 i18n hook 读取文案', () => {
  const navSource = readSource('components/layout/DashboardNav.tsx');
  const dropdownSource = readSource('components/layout/UserDropdown.tsx');
  const chatInputSource = readSource('components/chat/ChatInput.tsx');
  const chatPageSource = readSource('app/chat/page.tsx');

  assert.match(navSource, /useI18n/, '顶部导航应接入 useI18n');
  assert.match(navSource, /labelKey:\s*'nav\.workspace'/, '主导航应声明可翻译文案 key');
  assert.match(navSource, /label:\s*t\(item\.labelKey\)/, '主导航应通过 key 读取翻译文案');
  assert.match(dropdownSource, /LOCALE_OPTIONS\.map/, '用户菜单应遍历可用语言列表');
  assert.match(dropdownSource, /data-testid=\{`locale-option-\$\{option\.value\}`\}/, '用户菜单应提供语言切换入口');
  assert.match(dropdownSource, /t\('preferences\.language'\)/, '语言选择器应使用翻译文案');
  assert.match(chatInputSource, /t\('chat\.connected'\)/, '聊天输入区连接状态应使用翻译文案');
  assert.match(chatPageSource, /t\('chat\.searchConversations'\)/, '聊天页搜索框应使用翻译文案');
});

test('会话时间标签应走 i18n 相对时间格式并兜底非法时间戳', () => {
  const source = readSource('lib/chatTypes.ts');

  assert.match(source, /typeof ts !== 'number' \|\| !Number\.isFinite\(ts\)/, '非法时间戳应直接兜底为空');
  assert.match(source, /return formatRelativeTime\(locale, ts\);/, '时间标签应统一走 i18n 格式化');
});
