import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const componentPath = resolve(process.cwd(), 'components/dashboard/ProactiveAgentPanel.tsx');

test('Proactive 看板应使用统一滚动容器承载下一问推荐和主动产出', () => {
  const source = readFileSync(componentPath, 'utf8');

  const scrollIndex = source.indexOf('data-testid="proactive-panel-scroll"');
  const recommendationsIndex = source.indexOf('data-testid="next-question-recommendations"');
  const outputListIndex = source.indexOf('data-testid="proactive-panel-output-list"');

  assert.notEqual(scrollIndex, -1, '缺少统一滚动容器');
  assert.notEqual(recommendationsIndex, -1, '缺少下一问推荐区');
  assert.notEqual(outputListIndex, -1, '缺少主动产出列表区');
  assert.ok(scrollIndex < recommendationsIndex, '下一问推荐应位于统一滚动容器内');
  assert.ok(recommendationsIndex < outputListIndex, '主动产出列表应位于下一问推荐之后');
});
