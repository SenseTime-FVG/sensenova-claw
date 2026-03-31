import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveSlashCommandSubmission } from '../components/chat/slashCommand.ts';

test('未知 slash 命令不应被当作已处理命令', () => {
  const result = resolveSlashCommandSubmission('/does-not-exist 帮我做个总结', ['brainstorming']);

  assert.deepEqual(result, {
    handled: false,
    skillName: null,
    args: '',
  });
});

test('已存在的 slash 命令应返回 skill 名称和参数', () => {
  const result = resolveSlashCommandSubmission('/brainstorming 帮我整理需求', ['brainstorming']);

  assert.deepEqual(result, {
    handled: true,
    skillName: 'brainstorming',
    args: '帮我整理需求',
  });
});
