'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useWebSocketContext } from '@/contexts/WebSocketContext';
import type { Message } from '@/types/message';

interface SessionContextValue {
  sessionId: string | null;
  messages: Message[];
  isTyping: boolean;
  createSession: () => void;
  sendUserInput: (content: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function toMessage(role: Message['role'], content: string): Message {
  return {
    id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    role,
    content,
    timestamp: Date.now(),
  };
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { send, lastMessage } = useWebSocketContext();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case 'session_created': {
        if (lastMessage.session_id) {
          setSessionId(lastMessage.session_id);
        }
        break;
      }
      case 'agent_thinking': {
        setIsTyping(true);
        break;
      }
      case 'agent_response': {
        const content = String(lastMessage.payload.content || '');
        if (content) {
          setMessages((prev) => [...prev, toMessage('assistant', content)]);
        }
        if (lastMessage.payload.is_final === true) {
          setIsTyping(false);
        }
        break;
      }
      case 'tool_execution': {
        const toolName = String(lastMessage.payload.tool_name || '');
        setMessages((prev) => [...prev, toMessage('tool', `工具执行中: ${toolName}`)]);
        break;
      }
      case 'tool_result': {
        const toolName = String(lastMessage.payload.tool_name || '');
        const success = Boolean(lastMessage.payload.success);
        setMessages((prev) => [
          ...prev,
          toMessage('tool', `工具完成: ${toolName} (${success ? 'success' : 'failed'})`),
        ]);
        break;
      }
      case 'turn_completed': {
        setIsTyping(false);
        break;
      }
      case 'error': {
        const content = String(lastMessage.payload.message || '未知错误');
        setMessages((prev) => [...prev, toMessage('system', `错误: ${content}`)]);
        setIsTyping(false);
        break;
      }
      default:
        break;
    }
  }, [lastMessage]);

  const value = useMemo<SessionContextValue>(
    () => ({
      sessionId,
      messages,
      isTyping,
      createSession: () => {
        send({
          type: 'create_session',
          payload: { meta: { title: '新对话' } },
          timestamp: Date.now() / 1000,
        });
      },
      sendUserInput: (content: string) => {
        setMessages((prev) => [...prev, toMessage('user', content)]);
        send({
          type: 'user_input',
          session_id: sessionId,
          payload: { content, attachments: [], context_files: [] },
          timestamp: Date.now() / 1000,
        });
      },
    }),
    [messages, send, sessionId, isTyping],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessionContext(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSessionContext must be used inside SessionProvider');
  }
  return ctx;
}
