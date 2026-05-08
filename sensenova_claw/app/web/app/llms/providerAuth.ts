export const OPENAI_CODEX_OAUTH_SOURCE_TYPE = 'openai-codex-oauth';

export function isOpenAICodexOAuthSourceType(sourceType: string | null | undefined): boolean {
  return sourceType === OPENAI_CODEX_OAUTH_SOURCE_TYPE;
}

export function shouldShowProviderSecretFields(sourceType: string | null | undefined): boolean {
  return !isOpenAICodexOAuthSourceType(sourceType);
}

export function openAICodexOAuthSourceLabel(): string {
  return 'OpenAI-Codex-OAuth';
}
