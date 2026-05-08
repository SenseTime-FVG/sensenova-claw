import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isOpenAICodexOAuthSourceType,
  openAICodexOAuthSourceLabel,
  shouldShowProviderSecretFields,
} from '../app/llms/providerAuth.ts';

test('OpenAI-Codex-OAuth 使用新的 source_type 值和显示名', () => {
  assert.equal(isOpenAICodexOAuthSourceType('openai-codex-oauth'), true);
  assert.equal(isOpenAICodexOAuthSourceType('openai-codex'), false);
  assert.equal(openAICodexOAuthSourceLabel(), 'OpenAI-Codex-OAuth');
});

test('OpenAI-Codex-OAuth 不显示 API Key/Base URL/Max Retries 等 secret 字段', () => {
  assert.equal(shouldShowProviderSecretFields('openai-codex-oauth'), false);
  assert.equal(shouldShowProviderSecretFields('openai'), true);
  assert.equal(shouldShowProviderSecretFields('openai-compatible'), true);
});
