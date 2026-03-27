'use client';

import { useRef, useEffect } from 'react';
import { MessageList } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { type ChatMessage } from '@/lib/chatTypes';

interface MessageAreaProps {
  messages: ChatMessage[];
  isTyping: boolean;
  currentSessionId: string | null;
  emptyState?: React.ReactNode;
}

export function MessageArea({ messages, isTyping, currentSessionId, emptyState }: MessageAreaProps) {
  const chatEndRef = useRef<HTMLDivElement>(null);
  const showEmptyState = messages.length === 0 && !isTyping;

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 min-h-0">
      {showEmptyState ? (
        emptyState
      ) : (
        <>
          <MessageList messages={messages} />
          {isTyping && <TypingIndicator />}
          <div ref={chatEndRef} />
        </>
      )}
    </div>
  );
}
