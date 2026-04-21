import test from 'node:test';
import assert from 'node:assert/strict';

import { getExistingModelValidationError, getNewModelValidationError } from '../app/llms/newModelValidation.ts';

test('空 llm 名称返回必填错误', () => {
  assert.equal(getNewModelValidationError('   ', ['t1']), 'LLM 名称不能为空');
});

test('重复 llm 名称返回已存在错误', () => {
  assert.equal(getNewModelValidationError('t1', ['t1', 't2']), 'LLM 名称已存在: t1');
});

test('新 llm 名称通过校验时返回空字符串', () => {
  assert.equal(getNewModelValidationError('t3', ['t1', 't2']), '');
});

test('编辑已有 llm 时保留原名不报错', () => {
  assert.equal(getExistingModelValidationError('t1', 't1', ['t1', 't2']), '');
});

test('编辑已有 llm 时改成重复名返回已存在错误', () => {
  assert.equal(getExistingModelValidationError('t2', 't1', ['t1', 't2']), 'LLM 名称已存在: t1');
});
