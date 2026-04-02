import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('wsEvents 应覆盖 MessageContext 已消费的新增 turn 字段', () => {
  const source = readSource('lib/wsEvents.ts');

  assert.match(source, /export interface ToolExecutionEvent[\s\S]*turn_id\?: string;/);
  assert.match(source, /export interface TurnCancelledEvent[\s\S]*reason\?: string;/);
  assert.match(source, /export interface ErrorEvent[\s\S]*turn_id\?: string;/);
});

test('wsEvents 应覆盖当前后端 websocket 已下发的新增 payload 字段', () => {
  const source = readSource('lib/wsEvents.ts');

  assert.match(source, /export interface LlmResultEvent[\s\S]*tool_calls\?: unknown\[];/);
  assert.match(source, /export interface ToolConfirmationRequestedEvent[\s\S]*timeout_action\?: string;/);
  assert.match(source, /export interface ToolConfirmationRequestedEvent[\s\S]*requested_at_ms\?: number;/);
  assert.match(source, /export interface ToolConfirmationResolvedEvent[\s\S]*approved\?: boolean;/);
  assert.match(source, /export interface ToolConfirmationResolvedEvent[\s\S]*resolved_at_ms\?: number;/);
  assert.match(source, /export interface UserQuestionAnsweredEvent[\s\S]*cancelled\?: boolean;/);
  assert.match(source, /export interface ProactiveResultEvent[\s\S]*scratch_session_id\?: string;/);
  assert.match(source, /export interface TodolistUpdatedEvent[\s\S]*action\?: string;/);
});
