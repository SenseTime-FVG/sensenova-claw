'use client';

import { useEffect, useRef } from 'react';
import { MessageBubble } from '@/components/chat/MessageBubble';
import type { Message } from '@/types/message';

export function MessageList({ messages }: { messages: Message[] }) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="messages" data-testid="message-list">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
