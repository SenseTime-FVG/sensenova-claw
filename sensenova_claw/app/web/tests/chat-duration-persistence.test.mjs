import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('历史事件重建应恢复 assistant 耗时气泡，避免刷新后丢失', () => {
  const source = readSource('lib/chatTypes.ts');

  assert.match(source, /function getEventTimestampMs\(event: Record<string, unknown>\): number \{/);
  assert.match(source, /const rawDurationMs = payload\.duration_ms;/);
  assert.match(source, /const userTurnTimestampMs = new Map<string, number>\(\);/);
  assert.match(source, /lastUserTimestampMs = eventTimestampMs;/);
  assert.match(source, /timestamp: eventTimestampMs,\s*turnId,/s);
  assert.match(source, /const durationMs = resolvePersistedDurationMs\(payload, \{\s*turnId,\s*completedAtMs: eventTimestampMs,/s);
  assert.match(source, /rebuilt\[i\] = \{ \.\.\.message, durationMs \};/);
  assert.match(source, /timestamp: eventTimestampMs, durationMs/);
});
