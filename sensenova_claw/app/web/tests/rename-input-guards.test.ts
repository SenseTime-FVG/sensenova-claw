import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldSubmitInlineRename } from '../components/session/renameInputGuards.ts';

test('非 Enter 键不应提交重命名', () => {
  assert.equal(shouldSubmitInlineRename({ key: 'a' }), false);
});

test('普通 Enter 且非输入法状态时应提交重命名', () => {
  assert.equal(shouldSubmitInlineRename({ key: 'Enter' }), true);
});

test('React composition 状态下按 Enter 不应提交重命名', () => {
  assert.equal(shouldSubmitInlineRename({ key: 'Enter', isComposing: true }), false);
});

test('原生事件 composition 状态下按 Enter 不应提交重命名', () => {
  assert.equal(shouldSubmitInlineRename({ key: 'Enter', nativeIsComposing: true }), false);
});

test('输入法确认阶段 keyCode=229 时按 Enter 不应提交重命名', () => {
  assert.equal(shouldSubmitInlineRename({ key: 'Enter', keyCode: 229 }), false);
});
