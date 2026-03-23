export interface AssistantDisplayContent {
  answerContent: string;
  thinkContent: string;
}

const THINK_TAG_RE = /<think>([\s\S]*?)<\/think>/gi;

export function extractThinkContentFromText(content: string): AssistantDisplayContent {
  if (!content) {
    return { answerContent: '', thinkContent: '' };
  }

  const thinkParts: string[] = [];
  const answerContent = content.replace(THINK_TAG_RE, (_match, thinkBody: string) => {
    const trimmed = thinkBody.trim();
    if (trimmed) {
      thinkParts.push(trimmed);
    }
    return '';
  }).trim();

  return {
    answerContent,
    thinkContent: thinkParts.join('\n\n').trim(),
  };
}

export function extractThinkContentFromReasoningDetails(reasoningDetails: unknown): string {
  if (!Array.isArray(reasoningDetails)) {
    return '';
  }

  return reasoningDetails
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return '';
      }
      const detail = item as Record<string, unknown>;
      if (detail.type !== 'thinking') {
        return '';
      }
      return String(detail.thinking || detail.text || '').trim();
    })
    .filter(Boolean)
    .join('\n\n')
    .trim();
}

export function resolveAssistantDisplayContent(content: string, thinkingContent?: string): AssistantDisplayContent {
  const parsed = extractThinkContentFromText(content);
  if (thinkingContent?.trim()) {
    return {
      answerContent: parsed.answerContent,
      thinkContent: thinkingContent.trim(),
    };
  }
  return parsed;
}
