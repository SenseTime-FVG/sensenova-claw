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
      <div className="flex justify-center my-8">
        <span className="text-xs bg-muted text-muted-foreground px-4 py-1.5 rounded-full border border-border">
          System Prompt
        </span>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-4 max-w-5xl mx-auto flex-row-reverse my-6">
        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0 border border-border shadow-sm">
          <User size={20} className="text-secondary-foreground" />
        </div>
        <div className="flex-1 flex flex-col items-end">
          <div className="bg-primary text-primary-foreground text-base p-4 rounded-2xl rounded-tr-none shadow-sm max-w-[85%] whitespace-pre-wrap leading-relaxed">
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'assistant') {
    const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
    return (
      <div className="flex gap-4 max-w-5xl mx-auto my-6">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center shrink-0 border border-primary/20 shadow-md">
          <Bot size={22} className="text-primary-foreground" />
        </div>
        <div className="flex-1 space-y-4">
          {msg.content && (
            <div className="text-base text-foreground bg-card border border-border p-5 rounded-2xl rounded-tl-none shadow-sm whitespace-pre-wrap leading-relaxed">
              {msg.content}
            </div>
          )}
          {hasToolCalls && (
            <div className="space-y-3">
              {msg.tool_calls!.map((tc) => {
                const tcName = tc.function?.name || tc.name || 'unknown';
                const tcArgs = tc.function?.arguments || tc.arguments || '';
                return (
                  <div key={tc.id} className="bg-muted/50 border border-border rounded-xl overflow-hidden shadow-sm">
                    <div className="bg-muted px-4 py-2 flex items-center gap-2 text-sm font-medium border-b border-border">
                      <Wrench size={14} className="text-yellow-500" />
                      <span className="text-foreground font-mono">{tcName}</span>
                    </div>
                    <pre className="p-4 text-xs text-muted-foreground font-mono overflow-auto max-h-60 bg-background/50">
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
    if (displayContent.length > 1000) {
      displayContent = displayContent.slice(0, 1000) + '\n... (truncated)';
    }
    return (
      <div className="flex gap-4 max-w-5xl mx-auto my-4 pl-14">
        <div className="flex-1">
          <div className="bg-muted/30 border border-border rounded-xl overflow-hidden shadow-sm">
            <div className="bg-muted px-4 py-2 flex items-center gap-2 text-xs font-medium border-b border-border">
              <Wrench size={14} className="text-green-500" />
              <span className="text-muted-foreground uppercase tracking-wider">Tool result</span>
              {msg.name && <span className="text-foreground font-mono ml-auto">{msg.name}</span>}
            </div>
            <pre className="p-4 text-xs text-muted-foreground font-mono overflow-auto max-h-60 whitespace-pre-wrap bg-background/30">
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
    <div className="flex gap-4 max-w-5xl mx-auto my-6">
      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center shrink-0 border border-primary/20 shadow-md">
        <Bot size={22} className="text-primary-foreground animate-pulse" />
      </div>
      <div className="bg-card border border-border p-4 rounded-2xl rounded-tl-none flex items-center gap-2 shadow-sm">
        <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
        <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
        <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
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
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  };

  const title = sessionInfo ? parseTitle(sessionInfo.meta) : sessionId;
  const visibleMessages = messages.filter((m) => m.role !== 'system');

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col bg-background">
        {/* Header */}
        <div className="bg-card/50 backdrop-blur-sm border-b border-border p-5 shrink-0 z-10 sticky top-0 shadow-sm">
          <div className="flex items-center gap-4">
            <Link href="/sessions" className="p-2 hover:bg-muted rounded-full transition-all border border-transparent hover:border-border shadow-sm">
              <ArrowLeft size={20} />
            </Link>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold text-foreground truncate tracking-tight">{title}</h1>
              <div className="flex items-center gap-5 text-sm text-muted-foreground mt-1.5 overflow-x-auto no-scrollbar pb-1">
                <span className="font-mono bg-muted px-2 py-0.5 rounded text-[11px] border border-border/50">{sessionId}</span>
                {sessionInfo && (
                  <>
                    <span className="shrink-0">{formatTimestamp(sessionInfo.created_at)}</span>
                    <span className="flex items-center gap-1.5 shrink-0">
                      <span className={`w-2 h-2 rounded-full shadow-[0_0_8px_rgba(34,197,94,0.4)] ${sessionInfo.status === 'active' ? 'bg-green-500' : 'bg-muted-foreground/50'}`} />
                      <span className="capitalize">{sessionInfo.status}</span>
                    </span>
                  </>
                )}
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className={`w-2 h-2 rounded-full shadow-[0_0_8px_rgba(59,130,246,0.4)] ${wsConnected ? 'bg-blue-500 border border-blue-400/50' : 'bg-destructive/70 border border-destructive/50'}`} />
                  {wsConnected ? 'WebSocket Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
            <div className="text-sm font-medium text-muted-foreground bg-muted/50 px-3 py-1.5 rounded-full border border-border">
              {visibleMessages.length} Messages
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto p-8 space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <Loader2 className="animate-spin text-primary" size={40} />
              <p className="text-sm text-muted-foreground font-medium">Loading session history...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
              <div className="p-4 bg-destructive/10 rounded-full">
                <AlertCircle size={40} className="text-destructive" />
              </div>
              <p className="text-base font-medium">{error}</p>
            </div>
          ) : visibleMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4">
              <div className="p-5 bg-muted rounded-full">
                <Bot size={48} className="opacity-30" />
              </div>
              <p className="text-base font-medium">No messages in this session. Start by typing below!</p>
            </div>
          ) : (
            <div className="pb-8">
              {sessionInfo && (
                <div className="flex justify-center mb-10">
                  <span className="text-xs bg-muted/80 backdrop-blur-sm text-muted-foreground px-4 py-2 rounded-full border border-border shadow-sm font-medium">
                    Session started on {formatTimestamp(sessionInfo.created_at)}
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
        <div className="border-t border-border bg-card/80 backdrop-blur-md p-6 shrink-0 shadow-[0_-4px_12px_rgba(0,0,0,0.03)] dark:shadow-[0_-4px_12px_rgba(0,0,0,0.2)]">
          <div className="max-w-5xl mx-auto">
            <div className="flex gap-4 items-end bg-background/50 border border-border rounded-2xl p-2 pr-3 focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/5 transition-all shadow-sm">
              <div className="flex-1 relative">
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={handleTextareaInput}
                  onKeyDown={handleKeyDown}
                  placeholder={wsConnected ? 'Type a message... (Enter to send, Shift+Enter for newline)' : 'Waiting for connection...'}
                  disabled={!wsConnected || isTyping}
                  rows={1}
                  className="w-full bg-transparent border-none focus:ring-0 px-4 py-3 text-base text-foreground placeholder:text-muted-foreground/60 resize-none disabled:opacity-50 disabled:cursor-not-allowed selection:bg-primary/20"
                  style={{ minHeight: '48px', maxHeight: '160px' }}
                />
              </div>
              <button
                onClick={sendMessage}
                disabled={!inputValue.trim() || !wsConnected || isTyping}
                className="p-3 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center shadow-lg active:scale-95 shrink-0"
              >
                <Send size={20} />
              </button>
            </div>
            <div className="mt-3 text-center">
              <p className="text-[11px] text-muted-foreground/60 font-medium">
                {isTyping ? 'Assistant is producing a response...' : wsConnected ? 'Press Enter to send' : 'Disconnected from WebSocket'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
