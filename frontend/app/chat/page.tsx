'use client';

import { useEffect, useRef, useState } from 'react';
import { Bot, User, Wrench, Send, Plus, RefreshCw, Loader2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { SlashCommandMenu, useSlashCommand } from '@/components/chat/SlashCommandMenu';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

interface ToolInfo {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  success?: boolean;
  error?: string;
  status: 'running' | 'completed';
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  timestamp: number;
  toolInfo?: ToolInfo;
}

interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

function makeId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function getTitle(meta: string) {
  try { return JSON.parse(meta).title || '未命名会话'; } catch { return '未命名会话'; }
}

function timeLabel(ts: number) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function truncateResult(result: unknown, max = 50000): unknown {
  if (!result) return result;
  const s = JSON.stringify(result);
  if (s.length <= max) return result;
  if (typeof result === 'object' && result !== null && 'content' in result) {
    return { ...(result as Record<string, unknown>), content: String((result as Record<string, unknown>).content).slice(0, max) + '\n... (截断)' };
  }
  return s.slice(0, max) + '... (截断)';
}

function formatArgs(args: unknown): string {
  if (!args) return '';
  if (typeof args === 'string') { try { return JSON.stringify(JSON.parse(args), null, 2); } catch { return args; } }
  if (typeof args === 'object') return JSON.stringify(args, null, 2);
  return String(args);
}

// ── Message Bubble ─────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const [showArgs, setShowArgs] = useState(false);
  const [showResult, setShowResult] = useState(false);

  if (msg.role === 'system') {
    return (
      <div className="flex justify-center my-3">
        <span className="text-[10px] bg-[#1e1e1e] text-[#858585] px-3 py-1 rounded-full border border-[#2d2d30]">{msg.content}</span>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-3 max-w-3xl mx-auto flex-row-reverse my-3">
        <div className="w-7 h-7 rounded bg-[#3c3c3c] flex items-center justify-center shrink-0">
          <User size={16} className="text-[#cccccc]" />
        </div>
        <div className="flex-1 flex flex-col items-end">
          <div className="bg-[#0e639c] text-white text-[13px] p-3 rounded-lg max-w-[80%] whitespace-pre-wrap leading-relaxed">{msg.content}</div>
        </div>
      </div>
    );
  }

  if (msg.role === 'tool' && msg.toolInfo) {
    const ti = msg.toolInfo;
    return (
      <div className="flex gap-3 max-w-3xl mx-auto my-2">
        <div className="w-7 h-7 shrink-0" />
        <div className="flex-1">
          <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded-lg overflow-hidden">
            <div className="bg-[#2d2d30] px-3 py-1.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <Wrench size={12} className={ti.status === 'completed' ? 'text-green-400' : 'text-yellow-400'} />
                <span className="text-[#cccccc] font-mono">{ti.name}</span>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded ${ti.status === 'running' ? 'bg-yellow-500/20 text-yellow-400' : ti.success !== false ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                {ti.status === 'running' ? '执行中...' : ti.success !== false ? '成功' : '失败'}
              </span>
            </div>
            <div className="px-3 py-2 space-y-1">
              <button onClick={() => setShowArgs(!showArgs)} className="text-[10px] text-[#858585] hover:text-[#cccccc] flex items-center gap-1">
                {showArgs ? '▼' : '▶'} 参数
              </button>
              {showArgs && (
                <pre className="text-[10px] text-[#858585] font-mono bg-black/20 p-2 rounded overflow-auto max-h-32">{formatArgs(ti.arguments)}</pre>
              )}
              {ti.status === 'completed' && (
                <>
                  <button onClick={() => setShowResult(!showResult)} className="text-[10px] text-[#858585] hover:text-[#cccccc] flex items-center gap-1">
                    {showResult ? '▼' : '▶'} 结果
                  </button>
                  {showResult && (
                    <pre className="text-[10px] text-[#858585] font-mono bg-black/20 p-2 rounded overflow-auto max-h-40 whitespace-pre-wrap">
                      {ti.error || formatArgs(ti.result)}
                    </pre>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex gap-3 max-w-3xl mx-auto my-3">
      <div className="w-7 h-7 rounded bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0">
        <Bot size={16} className="text-white" />
      </div>
      <div className="flex-1">
        <div className="text-[13px] text-[#cccccc] bg-[#252526] border border-[#2d2d30] p-3 rounded-lg whitespace-pre-wrap leading-relaxed">{msg.content}</div>
      </div>
    </div>
  );
}

// ── Typing indicator ───────────────────────────────────

function TypingDots() {
  return (
    <div className="flex gap-3 max-w-3xl mx-auto my-3">
      <div className="w-7 h-7 rounded bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0">
        <Bot size={16} className="text-white animate-pulse" />
      </div>
      <div className="bg-[#252526] border border-[#2d2d30] p-3 rounded-lg flex items-center gap-1.5">
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
        <div className="w-1.5 h-1.5 bg-[#858585] rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────

export default function ChatPage() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [wsConnected, setWsConnected] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toolCallMapRef = useRef<Map<string, string>>(new Map());
  const pendingInputRef = useRef<string | null>(null);

  // ── 斜杠命令 ──

  const handleSkillInvoke = async (skillName: string, args: string) => {
    if (!sessionId) return;
    await fetch(`${API_BASE}/api/sessions/${sessionId}/skill-invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_name: skillName, arguments: args }),
    });
    setInputValue('');
    setIsTyping(true);
  };

  const { showMenu, handleSelect: handleSlashSelect, handleSubmit: handleSlashSubmit } = useSlashCommand(
    inputValue, setInputValue, handleSkillInvoke,
  );

  // ── WebSocket ──

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWsMessage(data);
      } catch { /* ignore */ }
    };

    return () => { ws.close(); };
  }, []);

  const handleWsMessage = (data: Record<string, unknown>) => {
    const payload = (data.payload || {}) as Record<string, unknown>;
    switch (data.type) {
      case 'session_created': {
        const newSid = data.session_id as string;
        setSessionId(newSid);
        loadSessionList();
        if (pendingInputRef.current) {
          wsSend({ type: 'user_input', session_id: newSid, payload: { content: pendingInputRef.current, attachments: [], context_files: [] }, timestamp: Date.now() / 1000 });
          pendingInputRef.current = null;
        }
        break;
      }
      case 'agent_thinking':
        setIsTyping(true);
        break;
      case 'llm_result': {
        const content = String(payload.content || '');
        if (content) addMsg('assistant', content);
        break;
      }
      case 'tool_execution': {
        const toolName = String(payload.tool_name || '');
        const toolCallId = String(payload.tool_call_id || '');
        const ti: ToolInfo = { name: toolName, arguments: (payload.arguments || {}) as Record<string, unknown>, status: 'running' };
        const msg: ChatMessage = { id: makeId(), role: 'tool', content: `工具执行中: ${toolName}`, timestamp: Date.now(), toolInfo: ti };
        setMessages(prev => [...prev, msg]);
        toolCallMapRef.current.set(toolCallId, msg.id);
        break;
      }
      case 'tool_result': {
        const toolName = String(payload.tool_name || '');
        const toolCallId = String(payload.tool_call_id || '');
        const result = truncateResult(payload.result);
        const success = Boolean(payload.success);
        const error = String(payload.error || '');
        const mid = toolCallMapRef.current.get(toolCallId);
        if (mid) {
          setMessages(prev => prev.map(m => m.id === mid ? { ...m, content: `工具完成: ${toolName}`, toolInfo: { name: toolName, arguments: m.toolInfo?.arguments || {}, result, success, error, status: 'completed' } } : m));
        }
        break;
      }
      case 'turn_completed': {
        const final = String(payload.final_response || '');
        if (final) addMsg('assistant', final);
        setIsTyping(false);
        break;
      }
      case 'title_updated': {
        const sid = data.session_id as string;
        const title = (payload.title || '') as string;
        setSessions(prev => prev.map(s => {
          if (s.session_id !== sid) return s;
          try { const m = JSON.parse(s.meta); m.title = title; return { ...s, meta: JSON.stringify(m) }; } catch { return s; }
        }));
        break;
      }
      case 'error':
        addMsg('system', `错误: ${payload.message || '未知错误'}`);
        setIsTyping(false);
        break;
      case 'notification': {
        const text = String(payload.text || '');
        if (text) addMsg('system', text);
        break;
      }
    }
  };

  function addMsg(role: ChatMessage['role'], content: string) {
    setMessages(prev => [...prev, { id: makeId(), role, content, timestamp: Date.now() }]);
  }

  function wsSend(msg: Record<string, unknown>) {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(msg));
  }

  // ── Sessions ──

  const loadSessionList = async () => {
    setLoadingSessions(true);
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      const d = await res.json();
      setSessions(d.sessions || []);
    } catch { /* ignore */ }
    finally { setLoadingSessions(false); }
  };

  useEffect(() => { loadSessionList(); }, []);

  const switchSession = async (sid: string) => {
    setSessionId(sid);
    setMessages([]);
    setIsTyping(false);
    toolCallMapRef.current.clear();
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sid}/events`);
      const d = await res.json();
      const events = (d.events || []) as Record<string, unknown>[];
      const rebuilt: ChatMessage[] = [];
      const tMap = new Map<string, string>();
      for (const ev of events) {
        const p = JSON.parse(ev.payload_json as string);
        const et = ev.event_type as string;
        if (et === 'user.input') {
          rebuilt.push({ id: makeId(), role: 'user', content: p.content || '', timestamp: Date.now() });
        } else if (et === 'tool.call_requested') {
          const ti: ToolInfo = { name: p.tool_name || '', arguments: p.arguments || {}, status: 'running' };
          const m: ChatMessage = { id: makeId(), role: 'tool', content: `工具执行中: ${p.tool_name}`, timestamp: Date.now(), toolInfo: ti };
          rebuilt.push(m);
          tMap.set(p.tool_call_id, m.id);
        } else if (et === 'tool.call_result') {
          const mid = tMap.get(p.tool_call_id);
          if (mid) {
            const idx = rebuilt.findIndex(m => m.id === mid);
            if (idx !== -1) {
              rebuilt[idx] = { ...rebuilt[idx], content: `工具完成: ${p.tool_name}`, toolInfo: { name: p.tool_name || '', arguments: rebuilt[idx].toolInfo?.arguments || {}, result: truncateResult(p.result), success: p.success, error: p.error, status: 'completed' } };
            }
          }
        } else if (et === 'agent.step_completed') {
          const resp = p.final_response || '';
          if (resp) rebuilt.push({ id: makeId(), role: 'assistant', content: resp, timestamp: Date.now() });
        }
      }
      setMessages(rebuilt);
    } catch { /* ignore */ }
  };

  const startNewChat = () => {
    setSessionId(null);
    setMessages([]);
    setIsTyping(false);
    toolCallMapRef.current.clear();
    pendingInputRef.current = null;
  };

  // ── Send ──

  const sendMessage = () => {
    const content = inputValue.trim();
    if (!content || !wsConnected) return;
    // 斜杠命令拦截
    if (handleSlashSubmit(content)) {
      addMsg('user', content);
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }
    addMsg('user', content);
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (!sessionId) {
      pendingInputRef.current = content;
      wsSend({ type: 'create_session', payload: { meta: { title: content.slice(0, 20) || '新对话' } }, timestamp: Date.now() / 1000 });
    } else {
      wsSend({ type: 'user_input', session_id: sessionId, payload: { content, attachments: [], context_files: [] }, timestamp: Date.now() / 1000 });
    }
    setIsTyping(true);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  };

  // scroll
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isTyping]);

  return (
    <DashboardLayout>
      <div className="h-full flex">
        {/* Sidebar - Session list */}
        <div className="w-56 bg-[#111113] border-r border-[#2d2d30] flex flex-col shrink-0">
          <div className="p-3 border-b border-[#2d2d30] flex items-center justify-between">
            <span className="text-xs font-semibold text-[#cccccc]">会话历史</span>
            <div className="flex gap-1.5">
              <button onClick={startNewChat} className="p-1 rounded hover:bg-[#2d2d30] text-[#858585] hover:text-[#cccccc] transition-colors" title="新建会话">
                <Plus size={14} />
              </button>
              <button onClick={loadSessionList} disabled={loadingSessions} className="p-1 rounded hover:bg-[#2d2d30] text-[#858585] hover:text-[#cccccc] transition-colors disabled:opacity-50" title="刷新">
                <RefreshCw size={14} className={loadingSessions ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-auto p-2 space-y-1">
            {sessions.length === 0 && !loadingSessions && (
              <div className="text-center text-[#858585] text-[11px] py-6">暂无会话</div>
            )}
            {sessions.map(s => (
              <div
                key={s.session_id}
                onClick={() => switchSession(s.session_id)}
                className={`px-2.5 py-2 rounded cursor-pointer transition-colors text-[11px] border ${
                  s.session_id === sessionId
                    ? 'bg-[#2d2d30] border-[#007acc] text-[#cccccc]'
                    : 'border-transparent text-[#858585] hover:bg-[#2d2d30] hover:text-[#cccccc]'
                }`}
              >
                <div className="truncate">{getTitle(s.meta)}</div>
                <div className="text-[10px] text-[#585858] mt-0.5">{timeLabel(s.last_active)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-auto p-6">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-[#858585]">
                <Bot size={40} className="text-[#3c3c3c]" />
                <p className="text-sm">开始一段新对话</p>
                <p className="text-[11px]">在下方输入你的问题</p>
              </div>
            ) : (
              <>
                {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
                {isTyping && <TypingDots />}
                <div ref={chatEndRef} />
              </>
            )}
          </div>

          {/* Input area */}
          <div className="border-t border-[#2d2d30] bg-[#1e1e1e] p-4 shrink-0">
            <div className="max-w-3xl mx-auto flex gap-3 items-end">
              <div className="flex-1 relative">
                <SlashCommandMenu
                  inputValue={inputValue}
                  onSelect={handleSlashSelect}
                  visible={showMenu}
                />
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={handleInput}
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
            <div className="max-w-3xl mx-auto mt-2 flex items-center gap-3 text-[10px] text-[#585858]">
              <span className="flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                {wsConnected ? '已连接' : '未连接'}
              </span>
              {sessionId && <span className="font-mono">{sessionId}</span>}
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
