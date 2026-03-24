'use client';

import { useEffect } from 'react';
import { InputArea } from '@/components/chat/InputArea';
import { MessageList } from '@/components/chat/MessageList';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
import { useChat } from '@/hooks/useChat';
import { useSession } from '@/hooks/useSession';

export function ChatContainer() {
  const { messages, isTyping, sendUserInput } = useChat();
  const { sessionId } = useSession();

  return (
    <main className="chat-container">
      <MessageList messages={messages} />
      {isTyping ? <TypingIndicator /> : null}
      <InputArea onSubmit={sendUserInput} />
    </main>
  );
}
