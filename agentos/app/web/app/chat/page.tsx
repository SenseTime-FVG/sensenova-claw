'use client';

import { useEffect, useRef, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Bot, User, Wrench, Send, Plus, RefreshCw, Loader2, ChevronDown, Check } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { SlashCommandMenu, useSlashCommand } from '@/components/chat/SlashCommandMenu';
import { authFetch, API_BASE } from '@/lib/authFetch';
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

interface AgentOption { id: string; name: string; description: string; }

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
        <span className="text-[10px] bg-muted/50 text-muted-foreground px-3 py-1 rounded-full border border-border">{msg.content}</span>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-4 max-w-4xl mx-auto flex-row-reverse my-6">
        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0 border-2 border-border shadow-md">
          <User size={20} className="text-secondary-foreground" />
        </div>
        <div className="flex-1 flex flex-col items-end pt-1">
          <div className="bg-primary text-primary-foreground text-base md:text-lg p-5 rounded-3xl rounded-tr-sm max-w-[85%] whitespace-pre-wrap leading-relaxed shadow-lg">{msg.content}</div>
        </div>
      </div>
    );
  }

  if (msg.role === 'tool' && msg.toolInfo) {
    const ti = msg.toolInfo;
    return (
      <div className="flex gap-3 max-w-3xl mx-auto my-2">
        <div className="w-8 h-8 shrink-0" />
        <div className="flex-1">
          <div className="bg-card border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="bg-muted px-4 py-2 flex items-center justify-between text-xs border-b">
              <div className="flex items-center gap-2">
                <Wrench size={14} className={ti.status === 'completed' ? 'text-green-500' : 'text-amber-500'} />
                <span className="text-foreground font-mono font-medium">{ti.name}</span>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${ti.status === 'running' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20' : ti.success !== false ? 'bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20'}`}>
                {ti.status === 'running' ? 'Executing...' : ti.success !== false ? 'Success' : 'Failed'}
              </span>
            </div>
            <div className="px-4 py-3 space-y-2">
              <button onClick={() => setShowArgs(!showArgs)} className="text-[11px] font-medium text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors">
                <ChevronDown size={14} className={`transition-transform duration-200 ${showArgs ? 'rotate-180' : ''}`} /> Payload
              </button>
              {showArgs && (
                <pre className="text-[11px] text-muted-foreground font-mono bg-muted/50 p-3 rounded-md overflow-auto border max-h-32">{formatArgs(ti.arguments)}</pre>
              )}
              {ti.status === 'completed' && (
                <>
                  <button onClick={() => setShowResult(!showResult)} className="text-[11px] font-medium text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors mt-2">
                    <ChevronDown size={14} className={`transition-transform duration-200 ${showResult ? 'rotate-180' : ''}`} /> Output
                  </button>
                  {showResult && (
                    <pre className="text-[11px] text-foreground font-mono bg-muted/50 p-3 rounded-md overflow-auto border max-h-40 whitespace-pre-wrap">
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
    <div className="flex gap-4 max-w-4xl mx-auto my-8 group">
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-lg mt-1 group-hover:scale-105 transition-transform">
        <Bot size={20} className="text-primary-foreground" />
      </div>
      <div className="flex-1">
        <div className="text-base md:text-lg text-foreground whitespace-pre-wrap leading-relaxed font-medium">{msg.content}</div>
      </div>
    </div>
  );
}

// ── Typing indicator ───────────────────────────────────

function TypingDots() {
  return (
    <div className="flex gap-4 max-w-4xl mx-auto my-6">
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-md">
        <Bot size={20} className="text-primary-foreground animate-pulse" />
      </div>
      <div className="flex items-center gap-2 pt-4">
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
      </div>
    </div>
  );
}

// ── Target Selector (Agent 选择器) ────────────

function TargetSelector({
  selectedAgent,
  onSelectAgent,
}: {
  selectedAgent: string;
  onSelectAgent: (id: string) => void;
}) {
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    authFetch(`${API_BASE}/api/agents`).then(r => r.json()).catch(() => []).then(a => setAgents(a));
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const currentLabel = agents.find(a => a.id === selectedAgent)?.name || selectedAgent || 'Default Agent';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary/50 border hover:bg-secondary transition-colors text-xs font-medium text-secondary-foreground"
      >
        <Bot size={14} className="text-primary" />
        <span className="max-w-[140px] truncate">{currentLabel}</span>
        <ChevronDown size={14} className="text-muted-foreground ml-1" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-72 bg-popover border rounded-xl shadow-lg z-50 overflow-hidden">
          <div className="flex border-b">
            <div className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-semibold text-foreground border-b-2 border-primary">
              <Bot size={14} /> Available Agents
            </div>
          </div>

          <div className="max-h-60 overflow-auto p-2">
            {agents.length === 0 ? (
              <div className="text-center text-muted-foreground text-xs py-6">No Agents Found</div>
            ) : agents.map(a => (
              <button
                key={a.id}
                onClick={() => { onSelectAgent(a.id); setOpen(false); }}
                className={`w-full text-left px-3 py-2.5 rounded-md text-sm hover:bg-muted transition-colors flex items-center gap-3 ${
                  selectedAgent === a.id ? 'bg-muted/80' : ''
                }`}
              >
                <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Bot size={14} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-foreground font-medium truncate">{a.name}</div>
                  {a.description && <div className="text-[11px] text-muted-foreground truncate mt-0.5">{a.description}</div>}
                </div>
                {selectedAgent === a.id && <Check size={16} className="text-primary shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page (inner, needs useSearchParams) ───────────

function ChatPageInner() {
  const searchParams = useSearchParams();
  const initialAgent = searchParams.get('agent') || 'default';

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [wsConnected, setWsConnected] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const [selectedAgent, setSelectedAgent] = useState(initialAgent);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toolCallMapRef = useRef<Map<string, string>>(new Map());
  const pendingInputRef = useRef<string | null>(null);

  const handleSelectAgent = (id: string) => {
    setSelectedAgent(id);
  };

  // ── 斜杠命令 ──

  const handleSkillInvoke = async (skillName: string, args: string) => {
    if (!sessionId) return;
    await authFetch(`${API_BASE}/api/sessions/${sessionId}/skill-invoke`, {
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
        const msg: ChatMessage = { id: makeId(), role: 'tool', content: `Executing tool: ${toolName}`, timestamp: Date.now(), toolInfo: ti };
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
          setMessages(prev => prev.map(m => m.id === mid ? { ...m, content: `Tool Finished: ${toolName}`, toolInfo: { name: toolName, arguments: m.toolInfo?.arguments || {}, result, success, error, status: 'completed' } } : m));
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
        addMsg('system', `Error: ${payload.message || 'Unknown Error'}`);
        setIsTyping(false);
        break;
      case 'notification': {
        const text = String(payload.text || '');
        if (text) addMsg('system', text);
        break;
      }
    }
  };

  // 用 ref 保持 handleWsMessage 始终指向最新版本，避免 stale closure
  const handleWsMessageRef = useRef(handleWsMessage);
  handleWsMessageRef.current = handleWsMessage;

  useEffect(() => {
    // 从 cookie 读取 token（Jupyter-lab 风格认证）
    const cookieMatch = document.cookie.match(/(?:^|; )agentos_token=([^;]*)/);
    const token = cookieMatch ? decodeURIComponent(cookieMatch[1]) : null;
    const wsUrl = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;

    let ws: WebSocket | null = null;
    let cancelled = false;

    // 延迟连接，避免 React Strict Mode 双重执行时第一个连接被立即关闭
    const timer = setTimeout(() => {
      if (cancelled) return;
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => setWsConnected(false);
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          handleWsMessageRef.current(JSON.parse(event.data));
        } catch { /* ignore */ }
      };
    }, 50);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (ws) ws.close();
    };
  }, []);

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
      const res = await authFetch(`${API_BASE}/api/sessions`);
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
      const res = await authFetch(`${API_BASE}/api/sessions/${sid}/events`);
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
          const m: ChatMessage = { id: makeId(), role: 'tool', content: `Executing tool: ${p.tool_name}`, timestamp: Date.now(), toolInfo: ti };
          rebuilt.push(m);
          tMap.set(p.tool_call_id, m.id);
        } else if (et === 'tool.call_result') {
          const mid = tMap.get(p.tool_call_id);
          if (mid) {
            const idx = rebuilt.findIndex(m => m.id === mid);
            if (idx !== -1) {
              rebuilt[idx] = { ...rebuilt[idx], content: `Tool Finished: ${p.tool_name}`, toolInfo: { name: p.tool_name || '', arguments: rebuilt[idx].toolInfo?.arguments || {}, result: truncateResult(p.result), success: p.success, error: p.error, status: 'completed' } };
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

    // Agent 模式
    addMsg('user', content);
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (!sessionId) {
      pendingInputRef.current = content;
      const meta: Record<string, string> = { title: content.slice(0, 20) || '新对话' };
      const agentId = selectedAgent || 'default';
      wsSend({
        type: 'create_session',
        payload: { agent_id: agentId, meta },
        timestamp: Date.now() / 1000,
      });
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

  const targetLabel = selectedAgent !== 'default'
    ? `Agent: ${selectedAgent}`
    : null;

  return (
    <DashboardLayout>
      <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
        {/* Sidebar - Session list */}
        <div className="w-72 bg-muted/20 border-r flex flex-col shrink-0 h-full">
          <div className="p-6 border-b bg-card flex items-center justify-between">
            <span className="text-base font-black uppercase tracking-widest text-foreground/80">History</span>
            <div className="flex gap-2">
              <button onClick={startNewChat} className="p-2 rounded-xl hover:bg-primary/10 text-primary transition-all active:scale-90" title="New Chat">
                <Plus size={20} />
              </button>
              <button onClick={loadSessionList} disabled={loadingSessions} className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all disabled:opacity-50" title="Refresh">
                <RefreshCw size={20} className={loadingSessions ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-2 no-scrollbar">
            {sessions.length === 0 && !loadingSessions && (
              <div className="text-center text-muted-foreground text-sm py-20 flex flex-col items-center gap-4 opacity-30">
                <Bot size={48} />
                <p className="font-bold uppercase tracking-widest">No active logs</p>
              </div>
            )}
            {sessions.map(s => (
              <div
                key={s.session_id}
                onClick={() => switchSession(s.session_id)}
                className={`px-4 py-4 rounded-2xl cursor-pointer transition-all border text-sm shadow-sm group ${
                  s.session_id === sessionId
                    ? 'bg-primary border-primary text-primary-foreground shadow-lg shadow-primary/20'
                    : 'bg-card border-border/60 text-foreground hover:border-primary/40 hover:bg-muted/30'
                }`}
              >
                <div className="font-bold truncate text-base">{getTitle(s.meta)}</div>
                <div className={`text-xs mt-2 uppercase font-black tracking-tighter opacity-60 ${s.session_id === sessionId ? 'text-primary-foreground' : 'text-muted-foreground'}`}>{timeLabel(s.last_active)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col min-w-0 bg-background h-full">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 md:p-8">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-5 text-muted-foreground max-w-md mx-auto text-center">
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-2 shadow-sm">
                  <Bot size={32} />
                </div>
                <h3 className="text-xl font-semibold text-foreground">How can I help you today?</h3>
                {targetLabel && (
                  <span className="text-xs px-3 py-1.5 rounded-full border border-primary/20 text-primary bg-primary/10 font-medium">
                    {targetLabel}
                  </span>
                )}
                <p className="text-sm">Type a message below to start a new conversation with AgentOS.</p>
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
          <div className="border-t bg-card/50 backdrop-blur-sm p-4 shrink-0 shadow-[0_-4px_16px_rgba(0,0,0,0.02)]">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-3 mb-3 pl-1">
                <TargetSelector
                  selectedAgent={selectedAgent}
                  onSelectAgent={handleSelectAgent}
                />
                <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground bg-muted/50 px-2 py-1 rounded-full border">
                  <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
                  {wsConnected ? 'Connected' : 'Offline'}
                </span>
                {sessionId && <span className="font-mono text-xs text-muted-foreground px-2">ID: {sessionId.slice(0, 8)}...</span>}
              </div>
              
              <div className="flex items-end gap-3 bg-background border border-border/80 rounded-[2rem] shadow-xl focus-within:ring-4 focus-within:ring-primary/10 focus-within:border-primary transition-all p-3 relative">
                <div className="flex-1">
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
                    placeholder={
                      wsConnected
                        ? 'Message AgentOS... (Enter to send, Shift+Enter for new line)'
                        : 'Waiting for connection...'
                    }
                    disabled={!wsConnected || isTyping}
                    rows={1}
                    className="w-full bg-transparent border-none px-5 py-4 text-lg text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed leading-relaxed"
                    style={{ minHeight: '56px', maxHeight: '300px' }}
                  />
                </div>
                <button
                  onClick={sendMessage}
                  disabled={!inputValue.trim() || !wsConnected || isTyping}
                  className="w-14 h-14 mb-1 mr-1 rounded-2xl bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center shrink-0 transition-all active:scale-90 disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed shadow-lg shadow-primary/20"
                >
                  <Send size={24} className="ml-1" />
                </button>
              </div>
              <div className="text-center mt-3 text-[10px] text-muted-foreground/70">
                 AgentOS can make mistakes. Consider verifying important information.
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}

// ── Export with Suspense boundary for useSearchParams ───

export default function ChatPage() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
          <Loader2 className="animate-spin text-muted-foreground" size={32} />
        </div>
      </DashboardLayout>
    }>
      <ChatPageInner />
    </Suspense>
  );
}
