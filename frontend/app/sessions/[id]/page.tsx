'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Bot, User, Wrench, Loader2, AlertCircle, Send } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

interface Message {
  role: string;
  content?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
}

interface ToolCall {
  id: string;
  type?: string;
  name?: string;
  arguments?: string;
  function?: { name: string; arguments: string };
}

interface SessionInfo {
  session_id: string;
  created_at: number;
  last_active: number;
  status: string;
  meta: string;
}

function parseTitle(meta: string): string {
  try {
    const obj = JSON.parse(meta);
    return obj.title || obj.name || 'Untitled';
  } catch {
    return 'Untitled';
  }
}

function formatTimestamp(ts: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString();
}

function formatArgs(args: unknown): string {
  if (!args) return '';
  if (typeof args === 'string') {
    try {
      return JSON.stringify(JSON.parse(args), null, 2);
    } catch {
      return args;
    }
  }
  if (typeof args === 'object') {
    return JSON.stringify(args, null, 2);
  }
  return String(args);
}

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === 'system') {
    return (
      <div className="flex justify-center my-4">
        <span className="text-[10px] bg-[#1e1e1e] text-[#858585] px-3 py-1 rounded-full border border-[#2d2d30]">
          System Prompt
        </span>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-3 max-w-4xl mx-auto flex-row-reverse my-4">
        <div className="w-8 h-8 rounded bg-[#3c3c3c] flex items-center justify-center shrink-0">
          <User size={18} className="text-[#cccccc]" />
        </div>
        <div className="flex-1 flex flex-col items-end">
          <div className="bg-[#0e639c] text-white text-sm p-3 rounded-lg max-w-[80%] whitespace-pre-wrap">
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'assistant') {
    const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
    return (
      <div className="flex gap-3 max-w-4xl mx-auto my-4">
        <div className="w-8 h-8 rounded bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0">
          <Bot size={18} className="text-white" />
        </div>
        <div className="flex-1 space-y-2">
          {msg.content && (
            <div className="text-sm text-[#cccccc] bg-[#252526] border border-[#2d2d30] p-4 rounded-lg whitespace-pre-wrap">
              {msg.content}
            </div>
          )}
          {hasToolCalls && (
            <div className="space-y-2">
              {msg.tool_calls!.map((tc) => {
                const tcName = tc.function?.name || tc.name || 'unknown';
                const tcArgs = tc.function?.arguments || tc.arguments || '';
                return (
                  <div key={tc.id} className="bg-[#1e1e1e] border border-[#2d2d30] rounded-lg overflow-hidden">
                    <div className="bg-[#2d2d30] px-3 py-1.5 flex items-center gap-2 text-xs">
                      <Wrench size={12} className="text-yellow-400" />
                      <span className="text-[#cccccc] font-mono">{tcName}</span>
                    </div>
                    <pre className="p-3 text-xs text-[#858585] font-mono overflow-auto max-h-40">
                      {formatArgs(tcArgs)}
                    </pre>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (msg.role === 'tool') {
    let displayContent = msg.content || '';
    if (displayContent.length > 500) {
      displayContent = displayContent.slice(0, 500) + '\n... (truncated)';
    }
    return (
      <div className="flex gap-3 max-w-4xl mx-auto my-2 pl-11">
        <div className="flex-1">
          <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded-lg overflow-hidden">
            <div className="bg-[#2d2d30] px-3 py-1.5 flex items-center gap-2 text-xs">
              <Wrench size={12} className="text-green-400" />
              <span className="text-[#858585]">Tool result</span>
              {msg.name && <span className="text-[#cccccc] font-mono">{msg.name}</span>}
            </div>
            <pre className="p-3 text-xs text-[#858585] font-mono overflow-auto max-h-40 whitespace-pre-wrap">
              {displayContent}
            </pre>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 max-w-4xl mx-auto my-4">
      <div className="w-8 h-8 rounded bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0">
        <Bot size={18} className="text-white animate-pulse" />
      </div>
      <div className="bg-[#252526] border border-[#2d2d30] p-3 rounded-lg flex items-center gap-1.5">
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
      </div>
    </div>
  );
}

export default function SessionDetailPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // WebSocket 连接
  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'agent_thinking':
            setIsTyping(true);
            break;
          case 'llm_result': {
            const content = String(data.payload?.content || '');
            if (content) {
              setMessages((prev) => [...prev, { role: 'assistant', content }]);
            }
            break;
          }
          case 'tool_execution': {
            const toolName = String(data.payload?.tool_name || '');
            const args = data.payload?.arguments || {};
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content: '',
                tool_calls: [{
                  id: data.payload?.tool_call_id || `tc_${Date.now()}`,
                  name: toolName,
                  arguments: JSON.stringify(args),
                }],
              },
            ]);
            break;
          }
          case 'tool_result': {
            const toolName = String(data.payload?.tool_name || '');
            const result = data.payload?.result;
            const resultStr = typeof result === 'string' ? result : JSON.stringify(result);
            setMessages((prev) => [
              ...prev,
              { role: 'tool', name: toolName, content: resultStr },
            ]);
            break;
          }
          case 'turn_completed': {
            const finalResponse = String(data.payload?.final_response || '');
            if (finalResponse) {
              setMessages((prev) => [...prev, { role: 'assistant', content: finalResponse }]);
            }
            setIsTyping(false);
            break;
          }
          case 'error': {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `错误: ${data.payload?.message || '未知错误'}` },
            ]);
            setIsTyping(false);
            break;
          }
        }
      } catch { /* ignore */ }
    };

    return () => { ws.close(); };
  }, []);

  // 加载历史消息
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [sessRes, msgRes] = await Promise.all([
          fetch(`${API_BASE}/api/sessions`),
          fetch(`${API_BASE}/api/sessions/${sessionId}/messages`),
        ]);
        const sessData = await sessRes.json();
        const msgData = await msgRes.json();

        const found = (sessData.sessions || []).find(
          (s: SessionInfo) => s.session_id === sessionId
        );
        setSessionInfo(found || null);
        setMessages(msgData.messages || []);
      } catch {
        setError('Failed to load session data');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [sessionId]);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = useCallback(() => {
    const content = inputValue.trim();
    if (!content || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [...prev, { role: 'user', content }]);
    wsRef.current.send(JSON.stringify({
      type: 'user_input',
      session_id: sessionId,
      payload: { content, attachments: [], context_files: [] },
      timestamp: Date.now() / 1000,
    }));
    setInputValue('');
    setIsTyping(true);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [inputValue, sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  };

  const title = sessionInfo ? parseTitle(sessionInfo.meta) : sessionId;
  const visibleMessages = messages.filter((m) => m.role !== 'system');

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4 shrink-0">
          <div className="flex items-center gap-3">
            <Link href="/sessions" className="p-1.5 hover:bg-[#2d2d30] rounded transition-colors">
              <ArrowLeft size={18} />
            </Link>
            <div className="flex-1 min-w-0">
              <h1 className="text-base font-semibold text-[#cccccc] truncate">{title}</h1>
              <div className="flex items-center gap-4 text-xs text-[#858585] mt-1">
                <span className="font-mono">{sessionId}</span>
                {sessionInfo && (
                  <>
                    <span>{formatTimestamp(sessionInfo.created_at)}</span>
                    <span className="flex items-center gap-1">
                      <span className={`w-1.5 h-1.5 rounded-full ${sessionInfo.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}`} />
                      {sessionInfo.status}
                    </span>
                  </>
                )}
                <span className="flex items-center gap-1">
                  <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-blue-500' : 'bg-red-500'}`} />
                  {wsConnected ? '已连接' : '未连接'}
                </span>
              </div>
            </div>
            <div className="text-xs text-[#858585]">
              {visibleMessages.length} messages
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-[#858585]">
              <AlertCircle size={32} />
              <p className="text-sm">{error}</p>
            </div>
          ) : visibleMessages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[#858585] text-sm">
              No messages in this session
            </div>
          ) : (
            <div className="space-y-1">
              {sessionInfo && (
                <div className="flex justify-center mb-6">
                  <span className="text-[10px] bg-[#1e1e1e] text-[#858585] px-3 py-1 rounded-full border border-[#2d2d30]">
                    会话开始：{formatTimestamp(sessionInfo.created_at)}
                  </span>
                </div>
              )}
              {visibleMessages.map((msg, idx) => (
                <MessageBubble key={idx} msg={msg} />
              ))}
              {isTyping && <TypingIndicator />}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-[#2d2d30] bg-[#1e1e1e] p-4 shrink-0">
          <div className="max-w-4xl mx-auto flex gap-3 items-end">
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder={wsConnected ? '输入消息... (Enter 发送, Shift+Enter 换行)' : '等待连接...'}
                disabled={!wsConnected || isTyping}
                rows={1}
                className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded-lg px-4 py-2.5 text-sm text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc] resize-none disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ minHeight: '40px', maxHeight: '120px' }}
              />
            </div>
            <button
              onClick={sendMessage}
              disabled={!inputValue.trim() || !wsConnected || isTyping}
              className="px-4 py-2.5 bg-[#0e639c] text-white rounded-lg hover:bg-[#1177bb] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
