'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useNotification } from '@/hooks/useNotification';
import { useAuth } from '@/contexts/AuthContext';
import type { PendingInteraction } from '@/components/chat/QuestionDialog';
import {
  type ChatMessage,
  type SessionItem,
  type TaskGroup,
  type StepItem,
  type TaskProgressItem,
  type ContextFileRef,
  makeId,
  formatArgs,
  truncateResult,
  rebuildMessagesFromEvents,
  rebuildStepsFromEvents,
  groupSessionsToTasks,
} from '@/lib/chatTypes';
import { extractThinkContentFromReasoningDetails } from '@/lib/assistantThink';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
const WS_RECONNECT_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;
const BYPASS_PATHS = ['/login', '/setup'];

// ── Context 值类型 ──

export interface ChatSessionContextValue {
  // 连接
  wsConnected: boolean;

  // Session
  currentSessionId: string | null;
  switchSession: (sessionId: string) => void;
  createSession: (agentId: string, taskId?: string) => void;
  startNewChat: () => void;
  /** 删除会话 */
  deleteSession: (sessionId: string) => Promise<void>;
  /** 页面挂载时调用：如果是通过 switchSession 跳转过来的则保留会话，否则重置 */
  resetIfNeeded: () => void;
  /** 清理当前空会话（新建后未发消息） */
  cleanupEmptySession: () => void;

  // 消息
  messages: ChatMessage[];
  isTyping: boolean;
  sendMessage: (content: string, contextFiles?: ContextFileRef[], agentId?: string) => void;

  // 任务列表
  sessions: SessionItem[];
  taskGroups: TaskGroup[];
  refreshTaskGroups: () => void;
  loadingSessions: boolean;

  // 执行步骤
  steps: StepItem[];
  taskProgress: TaskProgressItem[];

  // 交互对话框
  activeInteraction: PendingInteraction | null;
  interactionSubmitting: boolean;
  sendQuestionAnswer: (answer: string | string[] | null, cancelled: boolean) => void;
  sendConfirmationResponse: (approved: boolean) => void;
  handleInteractionTimeout: () => void;

  // 斜杠命令
  handleSkillInvoke: (skillName: string, args: string) => void;

  // 底层发送
  wsSend: (msg: Record<string, unknown>) => void;
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

// ── Provider ──

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const { pushNotification } = useNotification();
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();

  // Session 状态
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [activeInteraction, setActiveInteraction] = useState<PendingInteraction | null>(null);
  const [interactionSubmitting, setInteractionSubmitting] = useState(false);

  // 右侧面板
  const [rightSteps, setRightSteps] = useState<StepItem[]>([]);
  const [rightTaskProgress, setRightTaskProgress] = useState<TaskProgressItem[]>([]);
  const toolStepMapRef = useRef<Map<string, number>>(new Map());

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const sessionIdRef = useRef<string | null>(null);
  const toolCallMapRef = useRef<Map<string, string>>(new Map());
  const pendingInputRef = useRef<{ content: string; contextFiles?: string[] } | null>(null);
  const interactionQueueRef = useRef<PendingInteraction[]>([]);
  const activeInteractionRef = useRef<PendingInteraction | null>(null);
  const pendingCreateMeta = useRef<Record<string, string> | null>(null);
  // 追踪新建但未发消息的空会话，切换离开时自动删除
  const emptySessionIdRef = useRef<string | null>(null);
  const skipNextResetRef = useRef(false);
  const shouldActivate = !isLoading && isAuthenticated && !BYPASS_PATHS.includes(pathname || '');

  // ── helpers ──

  const wsSend = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  function addMsg(role: ChatMessage['role'], content: string) {
    setMessages(prev => [...prev, { id: makeId(), role, content, timestamp: Date.now() }]);
  }

  function upsertAssistantMessage(message: {
    turnId?: string;
    content: string;
    thinkingContent?: string;
    thinkingState?: 'streaming' | 'collapsed';
  }) {
    const { turnId, content, thinkingContent, thinkingState } = message;
    setMessages((prev) => {
      if (turnId) {
        const existingIndex = prev.findIndex((item) => item.role === 'assistant' && item.turnId === turnId);
        if (existingIndex !== -1) {
          // 检查该 assistant 消息之后是否已经插入了 tool 消息
          // 如果有，说明这是新一轮 LLM 调用的结果，应创建新消息而不是覆盖
          const hasToolAfter = prev.slice(existingIndex + 1).some((m) => m.role === 'tool');
          if (hasToolAfter) {
            // 新一轮 LLM 思考，追加新的 assistant 消息
            return [
              ...prev,
              {
                id: makeId(),
                role: 'assistant' as const,
                content,
                timestamp: Date.now(),
                turnId: `${turnId}_${Date.now()}`,
                thinkingContent,
                thinkingState,
              },
            ];
          }
          // 同一轮 LLM 调用的流式更新，原地更新
          const next = [...prev];
          next[existingIndex] = {
            ...next[existingIndex],
            content,
            thinkingContent,
            thinkingState,
          };
          return next;
        }
      }
      return [
        ...prev,
        {
          id: makeId(),
          role: 'assistant',
          content,
          timestamp: Date.now(),
          turnId,
          thinkingContent,
          thinkingState,
        },
      ];
    });
  }

  const bindSessionToCurrentSocket = useCallback((sid: string | null) => {
    if (!sid) return;
    wsSend({ type: 'load_session', payload: { session_id: sid }, timestamp: Date.now() / 1000 });
  }, [wsSend]);

  // ── Session 管理 ──

  const loadSessionList = useCallback(async () => {
    if (!shouldActivate) {
      setSessions([]);
      return;
    }
    setLoadingSessions(true);
    try {
      const res = await authFetch(`${API_BASE}/api/sessions`);
      const d = await res.json();
      setSessions(d.sessions || []);
    } catch {
      // 允许失败
    } finally {
      setLoadingSessions(false);
    }
  }, [shouldActivate]);

  const reloadSessionHistory = useCallback(async (sid: string, shouldBind = true) => {
    if (!shouldActivate) return;
    setSessionId(sid);
    setMessages([]);
    setIsTyping(false);
    toolCallMapRef.current.clear();

    if (shouldBind) {
      bindSessionToCurrentSocket(sid);
    }

    try {
      const res = await authFetch(`${API_BASE}/api/sessions/${sid}/events`);
      const d = await res.json();
      const events = (d.events || []) as Record<string, unknown>[];
      setMessages(rebuildMessagesFromEvents(events));

      const { steps, taskProgress, toolStepMap } = rebuildStepsFromEvents(events);
      setRightSteps(steps);
      setRightTaskProgress(taskProgress);
      toolStepMapRef.current = toolStepMap;
    } catch {
      setRightSteps([]);
      setRightTaskProgress([]);
      toolStepMapRef.current.clear();
    }
  }, [bindSessionToCurrentSocket, shouldActivate]);

  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  // ── Interaction 队列 ──

  const interactionKey = (interaction: PendingInteraction) =>
    `${interaction.kind}:${interaction.interactionId}`;

  const enqueueInteraction = (interaction: PendingInteraction) => {
    const active = activeInteractionRef.current;
    const queue = interactionQueueRef.current;
    const nextKey = interactionKey(interaction);
    const exists = (active && interactionKey(active) === nextKey)
      || queue.some((item) => interactionKey(item) === nextKey);
    if (exists) return;
    if (!active) {
      activeInteractionRef.current = interaction;
      setActiveInteraction(interaction);
      return;
    }
    interactionQueueRef.current = [...queue, interaction];
  };

  const resolveInteraction = (kind: PendingInteraction['kind'], interactionId: string) => {
    const active = activeInteractionRef.current;
    const queue = interactionQueueRef.current;
    if (active && active.kind === kind && active.interactionId === interactionId) {
      if (queue.length > 0) {
        const [next, ...rest] = queue;
        interactionQueueRef.current = rest;
        activeInteractionRef.current = next;
        setActiveInteraction(next);
      } else {
        activeInteractionRef.current = null;
        setActiveInteraction(null);
      }
      setInteractionSubmitting(false);
      return;
    }
    const filtered = queue.filter((item) => !(item.kind === kind && item.interactionId === interactionId));
    if (filtered.length !== queue.length) {
      interactionQueueRef.current = filtered;
    }
  };

  const clearInteractions = () => {
    interactionQueueRef.current = [];
    activeInteractionRef.current = null;
    setActiveInteraction(null);
    setInteractionSubmitting(false);
  };

  // ── WebSocket 消息处理 ──

  const handleWsMessage = (data: Record<string, unknown>) => {
    const payload = (data.payload || {}) as Record<string, unknown>;
    const eventType = String(data.type || '');
    const incomingSessionId = typeof data.session_id === 'string' ? data.session_id : null;
    const isGlobalInteractionEvent = eventType === 'tool_confirmation_requested'
      || eventType === 'user_question_asked'
      || eventType === 'user_question_answered_event';
    if (incomingSessionId && sessionIdRef.current && incomingSessionId !== sessionIdRef.current && !isGlobalInteractionEvent) {
      return;
    }

    switch (eventType) {
      case 'session_created': {
        const newSid = data.session_id as string;
        setSessionId(newSid);
        loadSessionList();
        if (pendingInputRef.current) {
          const { content, contextFiles } = pendingInputRef.current;
          wsSend({
            type: 'user_input',
            session_id: newSid,
            payload: { content, attachments: [], context_files: contextFiles || [] },
            timestamp: Date.now() / 1000,
          });
          pendingInputRef.current = null;
          emptySessionIdRef.current = null;
        } else {
          emptySessionIdRef.current = newSid;
        }
        break;
      }
      case 'session_loaded': {
        const sid = typeof data.session_id === 'string' ? data.session_id : null;
        const events = Array.isArray(payload.events) ? payload.events as Record<string, unknown>[] : [];
        if (sid) {
          setSessionId(sid);
          setMessages(rebuildMessagesFromEvents(events));
          setIsTyping(false);
        }
        break;
      }
      case 'agent_thinking':
        setIsTyping(true);
        break;
      case 'llm_result': {
        const content = String(payload.content || '');
        const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : undefined;
        const thinkingContent = extractThinkContentFromReasoningDetails(payload.reasoning_details);
        const hasToolCalls = Array.isArray(payload.tool_calls) && payload.tool_calls.length > 0;
        // 有内容、有思考过程、或有工具调用时，都创建 assistant 消息
        // 确保工具调用前的思考过程不会丢失
        if (content || thinkingContent || hasToolCalls) {
          upsertAssistantMessage({
            turnId,
            content,
            thinkingContent,
            thinkingState: thinkingContent ? 'streaming' : undefined,
          });
        }
        break;
      }
      case 'tool_execution': {
        const toolName = String(payload.tool_name || '');
        const toolCallId = String(payload.tool_call_id || '');
        const ti = { name: toolName, arguments: (payload.arguments || {}) as Record<string, unknown>, status: 'running' as const };
        const msg: ChatMessage = { id: makeId(), role: 'tool', content: `Executing tool: ${toolName}`, timestamp: Date.now(), toolInfo: ti };
        setMessages(prev => [...prev, msg]);
        toolCallMapRef.current.set(toolCallId, msg.id);
        setRightSteps(prev => {
          const idx = prev.length;
          toolStepMapRef.current.set(toolCallId, idx);
          return [...prev, { label: `执行 ${toolName}`, status: 'running' as const }];
        });
        setRightTaskProgress(prev => [...prev, { task: toolName, step: 0, total: 1, status: 'running' as const }]);
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
        } else {
          const fallbackContent = typeof result === 'string'
            ? result
            : formatArgs(result);
          setMessages(prev => [...prev, {
            id: makeId(),
            role: 'tool',
            name: toolName,
            content: fallbackContent,
            timestamp: Date.now(),
          }]);
        }
        const stepIdx = toolStepMapRef.current.get(toolCallId);
        if (stepIdx !== undefined) {
          setRightSteps(prev => prev.map((s, i) => i === stepIdx ? { ...s, status: 'done' as const } : s));
        }
        setRightTaskProgress(prev => {
          const tName = String(payload.tool_name || '');
          const idx = prev.findIndex(t => t.task === tName && t.status === 'running');
          if (idx === -1) return prev;
          return prev.map((t, i) => i === idx ? { ...t, step: 1, status: 'completed' as const } : t);
        });
        break;
      }
      case 'turn_completed': {
        const final = String(payload.final_response || '');
        if (final) {
          // 更新最后一条 assistant 消息的内容（不创建新消息）
          setMessages((prev) => {
            // 从后往前找最后一条 assistant 消息
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant') {
                const next = [...prev];
                next[i] = { ...next[i], content: final, thinkingState: 'collapsed' };
                return next;
              }
            }
            // 没找到 assistant 消息（理论上不会发生），追加一条
            return [...prev, { id: makeId(), role: 'assistant', content: final, timestamp: Date.now() }];
          });
        }
        setIsTyping(false);
        clearInteractions();
        break;
      }
      case 'turn_cancelled':
        setIsTyping(false);
        clearInteractions();
        break;
      case 'title_updated': {
        const sid = data.session_id as string;
        const title = (payload.title || '') as string;
        setSessions(prev => prev.map(s => {
          if (s.session_id !== sid) return s;
          try { const m = JSON.parse(s.meta); m.title = title; return { ...s, meta: JSON.stringify(m) }; } catch { return s; }
        }));
        break;
      }
      case 'session_list_changed': {
        // 后端通知有新 session（如 send_message 创建），刷新列表
        loadSessionList();
        break;
      }
      case 'session_deleted': {
        const deletedSid = String(payload.session_id || '');
        if (deletedSid) {
          setSessions(prev => prev.filter(s => s.session_id !== deletedSid));
          if (sessionIdRef.current === deletedSid) {
            startNewChat();
          }
        }
        break;
      }
      case 'error':
        addMsg('system', `Error: ${payload.message || payload.error_type || 'Unknown Error'}`);
        setIsTyping(false);
        clearInteractions();
        break;
      case 'notification': {
        const title = String(payload.title || 'Notification');
        const body = String(payload.body || payload.text || '');
        const metadata = (payload.metadata || {}) as Record<string, unknown>;
        if (body) {
          pushNotification({
            title,
            body,
            level: String(payload.level || 'info') as 'info' | 'warning' | 'error' | 'success',
            source: String(payload.source || 'system'),
            createdAtMs: Number(payload.created_at_ms || Date.now()),
          }, {
            toast: metadata.show_toast !== false,
            browser: metadata.show_browser === true,
          });
        }
        const targetSessionId = typeof data.session_id === 'string' ? data.session_id : null;
        if (body && Boolean(metadata.append_to_chat) && (!targetSessionId || targetSessionId === sessionIdRef.current)) {
          addMsg('system', body);
        }
        break;
      }
      case 'tool_confirmation_requested': {
        const toolCallId = String(payload.tool_call_id || '');
        const sourceSessionId = incomingSessionId || '';
        if (!toolCallId || !sourceSessionId) break;
        enqueueInteraction({
          kind: 'confirmation',
          interactionId: toolCallId,
          sourceSessionId,
          timeout: Number(payload.timeout || 300),
          createdAt: Date.now(),
          toolName: String(payload.tool_name || ''),
          riskLevel: String(payload.risk_level || 'high'),
          arguments: (payload.arguments || {}) as Record<string, unknown>,
        });
        setIsTyping(true);
        break;
      }
      case 'user_question_asked': {
        const questionId = String(payload.question_id || '');
        const sourceSessionId = incomingSessionId || '';
        if (!questionId || !sourceSessionId) break;
        const sourceAgentId = String(payload.source_agent_id || 'default').trim() || 'default';
        const sourceAgentName = String(payload.source_agent_name || sourceAgentId).trim() || sourceAgentId;
        enqueueInteraction({
          kind: 'question',
          interactionId: questionId,
          sourceSessionId,
          sourceAgentId,
          sourceAgentName,
          question: String(payload.question || ''),
          options: Array.isArray(payload.options) ? payload.options.map(String) : null,
          multiSelect: Boolean(payload.multi_select),
          timeout: Number(payload.timeout || 300),
          createdAt: Date.now(),
        });
        setIsTyping(true);
        break;
      }
      case 'user_question_answered_event': {
        const questionId = String(payload.question_id || '');
        if (questionId) resolveInteraction('question', questionId);
        break;
      }
    }
  };

  const handleWsMessageRef = useRef(handleWsMessage);
  handleWsMessageRef.current = handleWsMessage;

  // ── WebSocket 连接 ──

  useEffect(() => {
    if (!shouldActivate) {
      setWsConnected(false);
      return;
    }
    let cancelled = false;

    const scheduleReconnect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      if (reconnectAttemptsRef.current >= WS_MAX_RECONNECT_ATTEMPTS) return;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectAttemptsRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL_MS);
    };

    const connect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      const cookieMatch = document.cookie.match(/(?:^|; )agentos_token=([^;]*)/);
      const token = cookieMatch ? decodeURIComponent(cookieMatch[1]) : null;
      const wsUrl = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled || wsRef.current !== ws) return;
        setWsConnected(true);
        reconnectAttemptsRef.current = 0;
        loadSessionList();
        bindSessionToCurrentSocket(sessionIdRef.current);
      };
      ws.onclose = () => {
        if (wsRef.current !== ws && wsRef.current !== null) return;
        if (wsRef.current === ws) wsRef.current = null;
        setWsConnected(false);
        scheduleReconnect();
      };
      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        setWsConnected(false);
        if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
      ws.onmessage = (event) => {
        try { handleWsMessageRef.current(JSON.parse(event.data)); } catch { /* ignore */ }
      };
    };

    shouldReconnectRef.current = true;
    const timer = setTimeout(connect, 50);

    return () => {
      cancelled = true;
      shouldReconnectRef.current = false;
      clearTimeout(timer);
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        const activeSocket = wsRef.current;
        wsRef.current = null;
        activeSocket.close();
      }
    };
  }, [bindSessionToCurrentSocket, loadSessionList, shouldActivate]);

  // 初始加载 session 列表
  useEffect(() => {
    if (!shouldActivate) return;
    loadSessionList();
  }, [loadSessionList, shouldActivate]);

  // ── 对外接口 ──

  const doCleanupEmptySession = useCallback((excludeSid?: string) => {
    const emptyId = emptySessionIdRef.current;
    if (emptyId && emptyId !== excludeSid) {
      emptySessionIdRef.current = null;
      setSessions(prev => prev.filter(s => s.session_id !== emptyId));
      authFetch(`${API_BASE}/api/sessions/${emptyId}`, { method: 'DELETE' }).catch(() => {});
    }
  }, []);

  const switchSession = useCallback(async (sid: string) => {
    doCleanupEmptySession(sid);
    await reloadSessionHistory(sid);
  }, [reloadSessionHistory, doCleanupEmptySession]);

  const createSession = useCallback((agentId: string, taskId?: string) => {
    const meta: Record<string, string> = { title: '新对话' };
    if (taskId) meta.task_id = taskId;
    pendingCreateMeta.current = meta;
    wsSend({
      type: 'create_session',
      payload: { agent_id: agentId || 'default', meta },
      timestamp: Date.now() / 1000,
    });
  }, [wsSend]);

  const startNewChat = useCallback(() => {
    doCleanupEmptySession();
    setSessionId(null);
    sessionIdRef.current = null;
    setMessages([]);
    setIsTyping(false);
    toolCallMapRef.current.clear();
    pendingInputRef.current = null;
    setRightSteps([]);
    setRightTaskProgress([]);
    toolStepMapRef.current.clear();
  }, [doCleanupEmptySession]);

  const deleteSession = useCallback(async (sid: string) => {
    try {
      const res = await authFetch(`${API_BASE}/api/sessions/${sid}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('delete failed');
    } catch {
      // 忽略网络错误，继续清理本地状态
    }
    setSessions(prev => prev.filter(s => s.session_id !== sid));
    if (sessionIdRef.current === sid) {
      startNewChat();
    }
  }, [startNewChat]);

  const resetIfNeeded = useCallback(() => {
    startNewChat();
  }, [startNewChat]);

  const sendMessage = useCallback((content: string, contextFiles?: ContextFileRef[], agentId?: string) => {
    if (!content.trim() || !wsConnected) return;

    emptySessionIdRef.current = null;
    addMsg('user', content);

    const filePaths = contextFiles?.map(f => f.path) || [];

    if (!sessionIdRef.current) {
      pendingInputRef.current = { content, contextFiles: filePaths };
      const meta: Record<string, string> = { title: content.slice(0, 20) || '新对话' };
      wsSend({
        type: 'create_session',
        payload: { agent_id: agentId || 'default', meta },
        timestamp: Date.now() / 1000,
      });
    } else {
      wsSend({
        type: 'user_input',
        session_id: sessionIdRef.current,
        payload: { content, attachments: [], context_files: filePaths },
        timestamp: Date.now() / 1000,
      });
    }
    setIsTyping(true);
  }, [wsConnected, wsSend]);

  const sendQuestionAnswerFn = useCallback((answer: string | string[] | null, cancelled: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'question') return;
    if (!interaction.sourceSessionId) {
      addMsg('system', 'Question source session not found, cannot submit answer.');
      return;
    }
    setInteractionSubmitting(true);
    wsSend({
      type: 'user_question_answered',
      session_id: interaction.sourceSessionId,
      payload: { question_id: interaction.interactionId, answer, cancelled },
      timestamp: Date.now() / 1000,
    });
    resolveInteraction('question', interaction.interactionId);
  }, [wsSend]);

  const sendConfirmationResponseFn = useCallback((approved: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'confirmation') return;
    if (!interaction.sourceSessionId) {
      addMsg('system', 'Confirmation source session not found, cannot submit result.');
      return;
    }
    setInteractionSubmitting(true);
    wsSend({
      type: 'tool_confirmation_response',
      session_id: interaction.sourceSessionId,
      payload: { tool_call_id: interaction.interactionId, approved },
      timestamp: Date.now() / 1000,
    });
    resolveInteraction('confirmation', interaction.interactionId);
  }, [wsSend]);

  const handleInteractionTimeoutFn = useCallback(() => {
    const interaction = activeInteractionRef.current;
    if (!interaction) return;
    if (interaction.kind === 'confirmation') {
      addMsg('system', '工具审批已超时，系统将按后端策略拒绝。');
      resolveInteraction('confirmation', interaction.interactionId);
      return;
    }
    addMsg('system', '问题已超时，已取消等待。');
    resolveInteraction('question', interaction.interactionId);
  }, []);

  const handleSkillInvoke = useCallback(async (skillName: string, args: string) => {
    if (!sessionIdRef.current) return;
    await authFetch(`${API_BASE}/api/sessions/${sessionIdRef.current}/skill-invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_name: skillName, arguments: args }),
    });
    setIsTyping(true);
  }, []);

  // 计算任务分组
  const taskGroups = groupSessionsToTasks(sessions);

  const value: ChatSessionContextValue = {
    wsConnected,
    currentSessionId: sessionId,
    switchSession,
    createSession,
    deleteSession,
    startNewChat,
    resetIfNeeded,
    cleanupEmptySession: doCleanupEmptySession,
    messages,
    isTyping,
    sendMessage,
    sessions,
    taskGroups,
    refreshTaskGroups: loadSessionList,
    loadingSessions,
    steps: rightSteps,
    taskProgress: rightTaskProgress,
    activeInteraction,
    interactionSubmitting,
    sendQuestionAnswer: sendQuestionAnswerFn,
    sendConfirmationResponse: sendConfirmationResponseFn,
    handleInteractionTimeout: handleInteractionTimeoutFn,
    handleSkillInvoke,
    wsSend,
  };

  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>;
}

export function useChatSession(): ChatSessionContextValue {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error('useChatSession must be used inside ChatSessionProvider');
  }
  return ctx;
}
