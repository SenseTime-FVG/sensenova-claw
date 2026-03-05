'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useWebSocketContext } from '@/contexts/WebSocketContext';
import type { Message, ToolInfo } from '@/types/message';

interface SessionContextValue {
  sessionId: string | null;
  messages: Message[];
  isTyping: boolean;
  createSession: () => void;
  sendUserInput: (content: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function toMessage(role: Message['role'], content: string, toolInfo?: ToolInfo): Message {
  return {
    id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    role,
    content,
    timestamp: Date.now(),
    toolInfo,
  };
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { send, lastMessage } = useWebSocketContext();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [toolCallMap, setToolCallMap] = useState<Map<string, string>>(new Map()); // tool_call_id -> message_id

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
      case 'tool_execution': {
        const toolName = String(lastMessage.payload.tool_name || '');
        const toolCallId = String(lastMessage.payload.tool_call_id || '');
        const args = lastMessage.payload.arguments || {};

        const toolInfo: ToolInfo = {
          name: toolName,
          arguments: args,
          status: 'running',
        };

        const newMessage = toMessage('tool', `工具执行中: ${toolName}`, toolInfo);
        setMessages((prev) => [...prev, newMessage]);

        // 记录 tool_call_id 到 message_id 的映射
        setToolCallMap((prev) => new Map(prev).set(toolCallId, newMessage.id));
        break;
      }
      case 'tool_result': {
        const toolName = String(lastMessage.payload.tool_name || '');
        const toolCallId = String(lastMessage.payload.tool_call_id || '');
        const result = lastMessage.payload.result;
        const success = Boolean(lastMessage.payload.success);
        const error = String(lastMessage.payload.error || '');

        // 查找对应的 running 消息并替换
        const messageId = toolCallMap.get(toolCallId);
        if (messageId) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === messageId
                ? {
                    ...msg,
                    content: `工具完成: ${toolName}`,
                    toolInfo: {
                      name: toolName,
                      arguments: msg.toolInfo?.arguments || {},
                      result,
                      success,
                      error,
                      status: 'completed',
                    },
                  }
                : msg
            )
          );
        }
        break;
      }
      case 'turn_completed': {
        const finalResponse = String(lastMessage.payload.final_response || '');
        if (finalResponse) {
          setMessages((prev) => [...prev, toMessage('assistant', finalResponse)]);
        }
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
