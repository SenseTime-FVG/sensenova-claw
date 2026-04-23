import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getExistingProviderValidationError,
  getNewProviderValidationError,
} from '../app/llms/providerValidation.ts';

test('空 provider 名称返回必填错误', () => {
  assert.equal(getNewProviderValidationError('   ', ['ttt']), 'Provider 名称不能为空');
});

test('重复 provider 名称返回已存在错误', () => {
  assert.equal(getNewProviderValidationError('ttt', ['ttt', 'deepseek']), 'Provider 名称已存在: ttt');
});

test('新增 provider 名称按小写去重', () => {
  assert.equal(getNewProviderValidationError('TTT', ['ttt']), 'Provider 名称已存在: ttt');
});

test('编辑 provider 时保留原名不报错', () => {
  assert.equal(getExistingProviderValidationError('ttt', 'ttt', ['ttt', 'deepseek']), '');
});

test('编辑 provider 时改成重复名返回已存在错误', () => {
  assert.equal(
    getExistingProviderValidationError('deepseek', 'TTT', ['ttt', 'deepseek']),
    'Provider 名称已存在: ttt',
  );
});
