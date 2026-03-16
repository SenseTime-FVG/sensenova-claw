'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useWebSocketContext } from '@/contexts/WebSocketContext';
import type { Message, ToolInfo } from '@/types/message';
import { authFetch } from '@/lib/authFetch';

interface SessionContextValue {
  sessionId: string | null;
  messages: Message[];
  isTyping: boolean;
  createSession: () => void;
  sendUserInput: (content: string) => void;
  switchSession: (sessionId: string) => void;
  startNewChat: () => void;
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

function truncateToolResult(result: any, maxLength = 50000): any {
  if (!result) return result;

  const resultStr = JSON.stringify(result);
  if (resultStr.length <= maxLength) return result;

  // 如果是对象且有 content 字段（如 fetch_url），截断 content
  if (typeof result === 'object' && result.content) {
    return {
      ...result,
      content: result.content.slice(0, maxLength) + `\n\n... (截断，原始长度: ${result.content.length} 字符)`,
    };
  }

  // 其他情况直接截断字符串
  return resultStr.slice(0, maxLength) + '... (截断)';
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { send, lastMessage } = useWebSocketContext();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const toolCallMapRef = useRef<Map<string, string>>(new Map()); // tool_call_id -> message_id
  const [pendingUserInput, setPendingUserInput] = useState<string | null>(null);

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case 'session_created': {
        if (lastMessage.session_id) {
          setSessionId(lastMessage.session_id);

          // 如果有待发送的用户输入，现在发送
          if (pendingUserInput) {
            send({
              type: 'user_input',
              session_id: lastMessage.session_id,
              payload: { content: pendingUserInput, attachments: [], context_files: [] },
              timestamp: Date.now() / 1000,
            });
            setPendingUserInput(null);
          }
        }
        break;
      }
      case 'agent_thinking': {
        setIsTyping(true);
        break;
      }
      case 'llm_result': {
        const content = String(lastMessage.payload.content || '');
        if (content) {
          setMessages((prev) => [...prev, toMessage('assistant', content)]);
        }
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
        toolCallMapRef.current.set(toolCallId, newMessage.id);
        break;
      }
      case 'tool_result': {
        const toolName = String(lastMessage.payload.tool_name || '');
        const toolCallId = String(lastMessage.payload.tool_call_id || '');
        const result = truncateToolResult(lastMessage.payload.result);
        const success = Boolean(lastMessage.payload.success);
        const error = String(lastMessage.payload.error || '');

        console.log('[tool_result]', { toolCallId, toolName, success, messageId: toolCallMapRef.current.get(toolCallId) });

        // 查找对应的 running 消息并替换
        const messageId = toolCallMapRef.current.get(toolCallId);
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
        } else {
          console.warn(`Tool call ID not found in map: ${toolCallId}`, toolCallMapRef.current);
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
      case 'notification': {
        const text = String(lastMessage.payload.text || '');
        if (text) {
          setMessages((prev) => [...prev, toMessage('system', `📢 ${text}`)]);
        }
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

        // 如果没有 sessionId，先创建会话
        if (!sessionId) {
          setPendingUserInput(content);
          send({
            type: 'create_session',
            payload: { meta: { title: content.slice(0, 20) || '新对话' } },
            timestamp: Date.now() / 1000,
          });
          return;
        }

        send({
          type: 'user_input',
          session_id: sessionId,
          payload: { content, attachments: [], context_files: [] },
          timestamp: Date.now() / 1000,
        });
      },
      switchSession: (newSessionId: string) => {
        setSessionId(newSessionId);
        setMessages([]);
        toolCallMapRef.current.clear();
        setIsTyping(false);
        setPendingUserInput(null);

        // 从 events 重建完整历史
        authFetch(`http://localhost:8000/api/sessions/${newSessionId}/events`)
          .then((res) => res.json())
          .then((data) => {
            const events = data.events || [];
            const historyMessages: Message[] = [];
            const toolMap = new Map<string, string>();

            events.forEach((event: any) => {
              const payload = JSON.parse(event.payload_json);

              if (event.event_type === 'user.input') {
                historyMessages.push(toMessage('user', payload.content || ''));
              } else if (event.event_type === 'tool.call_requested') {
                const toolInfo: ToolInfo = {
                  name: payload.tool_name || '',
                  arguments: payload.arguments || {},
                  status: 'running',
                };
                const msg = toMessage('tool', `工具执行中: ${payload.tool_name}`, toolInfo);
                historyMessages.push(msg);
                toolMap.set(payload.tool_call_id, msg.id);
              } else if (event.event_type === 'tool.call_result') {
                const msgId = toolMap.get(payload.tool_call_id);
                if (msgId) {
                  const msgIndex = historyMessages.findIndex((m) => m.id === msgId);
                  if (msgIndex !== -1) {
                    historyMessages[msgIndex] = {
                      ...historyMessages[msgIndex],
                      content: `工具完成: ${payload.tool_name}`,
                      toolInfo: {
                        name: payload.tool_name || '',
                        arguments: historyMessages[msgIndex].toolInfo?.arguments || {},
                        result: payload.result,
                        success: payload.success !== false,
                        error: payload.error,
                        status: 'completed',
                      },
                    };
                  }
                }
              } else if (event.event_type === 'agent.step_completed') {
                const finalResponse = payload.result?.content || payload.final_response;
                if (finalResponse) {
                  historyMessages.push(toMessage('assistant', finalResponse));
                }
              }
            });

            setMessages(historyMessages);
          })
          .catch((error) => {
            console.error('Failed to load session history:', error);
          });
      },
      startNewChat: () => {
        setSessionId(null);
        setMessages([]);
        toolCallMapRef.current.clear();
        setIsTyping(false);
        setPendingUserInput(null);
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
