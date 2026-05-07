'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown } from 'lucide-react';
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
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef<boolean>(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const showEmptyState = messages.length === 0 && !isTyping;

  // 监听滚动：用户上滑时标记，不再自动滚动
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const isScrolledUp = distanceFromBottom > 50;
    userScrolledUpRef.current = isScrolledUp;
    setShowScrollButton(isScrolledUp);
  }, []);

  // 自动滚动到底部（仅在用户未上滑时）
  useEffect(() => {
    if (!userScrolledUpRef.current) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isTyping]);

  // 点击"回到底部"按钮
  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    userScrolledUpRef.current = false;
    setShowScrollButton(false);
  }, []);

  return (
    <div ref={containerRef} onScroll={handleScroll} className="relative flex-1 overflow-y-auto p-4 md:p-8 min-h-0">
      {showEmptyState ? (
        emptyState
      ) : (
        <>
          <MessageList messages={messages} />
          {isTyping && <TypingIndicator />}
          <div ref={chatEndRef} />
        </>
      )}
      {/* 回到底部悬浮按钮 */}
      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="sticky bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center justify-center w-9 h-9 rounded-full bg-background/80 border border-border shadow-md backdrop-blur-sm hover:bg-background transition-colors"
          aria-label="回到底部"
        >
          <ArrowDown size={16} className="text-muted-foreground" />
        </button>
      )}
    </div>
  );
}
