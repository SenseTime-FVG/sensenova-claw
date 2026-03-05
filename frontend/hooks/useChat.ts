'use client';

import { useSessionContext } from '@/contexts/SessionContext';

export function useChat() {
  const { messages, isTyping, sendUserInput } = useSessionContext();
  return { messages, isTyping, sendUserInput };
}
