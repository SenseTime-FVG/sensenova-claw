import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('Agent 配置页模型下拉应提供空值 默认 选项', () => {
  const source = readSource('app/agents/[id]/page.tsx');

  assert.match(source, /<option value="">默认<\/option>/);
});
