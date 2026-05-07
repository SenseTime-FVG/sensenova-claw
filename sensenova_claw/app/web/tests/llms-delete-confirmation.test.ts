import test from 'node:test';
import assert from 'node:assert/strict';

import { buildDeleteConfirmationConfig } from '../app/llms/deleteConfirmation.ts';

test('provider 删除文案包含关联 llm 数量，普通模式会落盘', () => {
  const config = buildDeleteConfirmationConfig('provider', 'deepseek', {
    relatedModelCount: 2,
    editingAll: false,
  });

  assert.equal(config.title, '确认删除 provider');
  assert.equal(config.confirmLabel, '删除 provider');
  assert.equal(config.persistToConfig, true);
  assert.match(config.description, /2 个 llm/);
});

test('llm 删除在全局编辑模式下只删除草稿，不落盘', () => {
  const config = buildDeleteConfirmationConfig('model', 'deepseek-chat', {
    editingAll: true,
  });

  assert.equal(config.title, '确认删除 llm');
  assert.equal(config.confirmLabel, '删除 llm');
  assert.equal(config.persistToConfig, false);
  assert.match(config.description, /deepseek-chat/);
});
