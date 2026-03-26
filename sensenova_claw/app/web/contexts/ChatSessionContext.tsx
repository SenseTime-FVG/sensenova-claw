'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
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
  getAgentId,
  truncateResult,
  rebuildMessagesFromEvents,
  rebuildStepsFromEvents,
  groupSessionsToTasks,
  findLatestAssistantTurnMessage,
  upsertAssistantTurnMessage,
  attachAskUserToLatestToolMessage,
  updateAskUserToolState,
} from '@/lib/chatTypes';
import { extractThinkContentFromReasoningDetails } from '@/lib/assistantThink';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
const WS_RECONNECT_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;
const BYPASS_PATHS = ['/login', '/setup'];
const MAX_PROACTIVE_RESULTS = 50;

// ── Context 值类型 ──

/** 全局 agent 工作状态（跨会话） */
export interface GlobalAgentActivity {
  /** 是否有任意 agent 正在工作 */
  anyWorking: boolean;
  /** 正在工作的 session id 集合 */
  workingSessionIds: Set<string>;
  /** 最近一个正在执行的工具名（跨会话） */
  lastToolName: string;
}

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
  sendMessage: (
    content: string,
    contextFiles?: ContextFileRef[],
    agentId?: string,
    recommendation?: RecommendationSendMeta | null,
  ) => void;

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
  submitQuestionResponse: (params: {
    questionId: string;
    sourceSessionId: string;
    answer: string | string[] | null;
    cancelled: boolean;
  }) => void;
  sendConfirmationResponse: (approved: boolean) => void;
  handleInteractionTimeout: () => void;

  // 斜杠命令
  handleSkillInvoke: (skillName: string, args: string) => void;

  // 停止当前轮次
  cancelTurn: () => void;

  // 全局 agent 活动状态
  globalActivity: GlobalAgentActivity;

  // 底层发送
  wsSend: (msg: Record<string, unknown>) => void;

  // 通知面板回答 ask_user 时同步解除阻塞
  resolveInteractionFromNotification?: (kind: 'question' | 'confirmation', interactionId: string) => void;

  // 实时 proactive 推送结果
  proactiveResults: ProactiveResultItem[];

  // 推荐卡片预填输入
  pendingPrefill: PrefillInputPayload | null;
  prefillInput: (value: string | PrefillInputPayload) => void;
  clearPendingPrefill: () => void;
}

export interface RecommendationSendMeta {
  recommendationId: string;
  sourceSessionId: string;
}

export interface PrefillInputPayload {
  text: string;
  recommendation?: RecommendationSendMeta | null;
}

/** 实时接收到的 proactive 推送结果 */
export interface ProactiveResultItem {
  jobId: string;
  jobName: string;
  sessionId: string;
  scratchSessionId?: string;
  result: string;
  receivedAt: number;
  sourceSessionId?: string;
  recommendationType?: string;
  items?: Array<{
    id: string;
    title: string;
    prompt: string;
    category?: string;
  }>;
}

interface PendingRecommendationApiItem {
  job_id?: string;
  job_name?: string;
  session_id?: string;
  source_session_id?: string;
  recommendation_type?: string;
  received_at_ms?: number;
  result?: string;
  items?: Array<{
    id?: string;
    title?: string;
    prompt?: string;
    category?: string;
  }>;
}

function proactiveResultKey(item: ProactiveResultItem): string {
  return [
    item.jobId,
    item.sessionId,
    item.sourceSessionId || '',
    item.recommendationType || '',
  ].join('::');
}

function mergeProactiveResults(
  existing: ProactiveResultItem[],
  incoming: ProactiveResultItem[],
): ProactiveResultItem[] {
  const merged = new Map<string, ProactiveResultItem>();

  for (const item of [...existing, ...incoming]) {
    const key = proactiveResultKey(item);
    const prev = merged.get(key);
    if (!prev || item.receivedAt >= prev.receivedAt) {
      merged.set(key, item);
    }
  }

  return Array.from(merged.values())
    .sort((a, b) => b.receivedAt - a.receivedAt)
    .slice(0, MAX_PROACTIVE_RESULTS);
}

function consumeRecommendationFromResults(
  results: ProactiveResultItem[],
  recommendationId: string,
  sourceSessionId: string,
): ProactiveResultItem[] {
  return results
    .flatMap((result) => {
      if (result.recommendationType !== 'turn_end') {
        return [result];
      }

      const resultSourceSessionId = result.sourceSessionId || result.sessionId;
      if (resultSourceSessionId !== sourceSessionId || !Array.isArray(result.items)) {
        return [result];
      }

      const remainingItems = result.items.filter((item) => item.id !== recommendationId);
      if (remainingItems.length === 0) {
        return [];
      }

      return [{ ...result, items: remainingItems }];
    })
    .slice(0, MAX_PROACTIVE_RESULTS);
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

// ── Provider ──

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const { pushNotification, pushCard, resolveCard, markCardPending } = useNotification();
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

  // 全局 agent 活动追踪（跨会话）
  const [globalWorkingSessions, setGlobalWorkingSessions] = useState<Set<string>>(new Set());
  const [globalLastToolName, setGlobalLastToolName] = useState('');

  // 实时 proactive 推送结果（最多保留 50 条，去重）
  const [proactiveResults, setProactiveResults] = useState<ProactiveResultItem[]>([]);

  // 推荐卡片预填输入
  const [pendingPrefill, setPendingPrefill] = useState<PrefillInputPayload | null>(null);

  const prefillInput = useCallback((value: string | PrefillInputPayload) => {
    if (typeof value === 'string') {
      setPendingPrefill({ text: value, recommendation: null });
      return;
    }
    setPendingPrefill({
      text: value.text,
      recommendation: value.recommendation || null,
    });
  }, []);

  const clearPendingPrefill = useCallback(() => {
    setPendingPrefill(null);
  }, []);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const sessionIdRef = useRef<string | null>(null);
  const toolCallMapRef = useRef<Map<string, string>>(new Map());
  const cancelledTurnIdsRef = useRef<Set<string>>(new Set());
  const lastStreamingTurnIdRef = useRef<string | null>(null);
  const pendingInputRef = useRef<{
    content: string;
    contextFiles?: string[];
    meta?: Record<string, unknown>;
  } | null>(null);
  const interactionQueueRef = useRef<PendingInteraction[]>([]);
  const activeInteractionRef = useRef<PendingInteraction | null>(null);
  const pendingCreateMeta = useRef<Record<string, string> | null>(null);
  // 关联 create_session 请求与 session_created 响应，防止快速切换时乱序覆盖
  const pendingCreateIdRef = useRef<string | null>(null);
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
        return upsertAssistantTurnMessage(prev, turnId, {
          content,
          thinkingContent,
          thinkingState,
        });
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

  const resetTurnTracking = useCallback(() => {
    cancelledTurnIdsRef.current.clear();
    lastStreamingTurnIdRef.current = null;
  }, []);

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

  const loadPendingRecommendations = useCallback(async () => {
    if (!shouldActivate) {
      return;
    }
    try {
      const res = await authFetch(`${API_BASE}/api/proactive/recommendations?limit=3`);
      if (!res.ok) {
        return;
      }
      const data = await res.json() as { recommendations?: PendingRecommendationApiItem[] };
      const restored = Array.isArray(data.recommendations)
        ? data.recommendations.map((item): ProactiveResultItem => ({
            jobId: String(item.job_id || ''),
            jobName: String(item.job_name || ''),
            sessionId: String(item.session_id || item.source_session_id || ''),
            result: String(item.result || ''),
            receivedAt: Number(item.received_at_ms || Date.now()),
            sourceSessionId: item.source_session_id ? String(item.source_session_id) : undefined,
            recommendationType: item.recommendation_type ? String(item.recommendation_type) : undefined,
            items: Array.isArray(item.items)
              ? item.items.map((rec) => ({
                  id: String(rec.id || ''),
                  title: String(rec.title || ''),
                  prompt: String(rec.prompt || ''),
                  category: rec.category ? String(rec.category) : undefined,
                }))
              : undefined,
          }))
        : [];

      setProactiveResults((prev) => mergeProactiveResults(prev, restored));
    } catch {
      // 允许失败
    }
  }, [shouldActivate]);

  const reloadSessionHistory = useCallback(async (sid: string, shouldBind = true) => {
    if (!shouldActivate) return;
    setSessionId(sid);
    sessionIdRef.current = sid;
    setMessages([]);
    setIsTyping(false);
    resetTurnTracking();
    toolCallMapRef.current.clear();

    if (shouldBind) {
      bindSessionToCurrentSocket(sid);
    }

    try {
      const res = await authFetch(`${API_BASE}/api/sessions/${sid}/events`);
      const d = await res.json();
      // 竞态保护：异步请求返回时，用户可能已切换到其他 session，丢弃过时结果
      if (sessionIdRef.current !== sid) return;
      const events = (d.events || []) as Record<string, unknown>[];
      setMessages(rebuildMessagesFromEvents(events));

      const { steps, taskProgress, toolStepMap } = rebuildStepsFromEvents(events);
      setRightSteps(steps);
      setRightTaskProgress(taskProgress);
      toolStepMapRef.current = toolStepMap;
    } catch {
      if (sessionIdRef.current !== sid) return;
      setRightSteps([]);
      setRightTaskProgress([]);
      toolStepMapRef.current.clear();
    }
  }, [bindSessionToCurrentSocket, resetTurnTracking, shouldActivate]);

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

  // useCallback 包裹：通过 ref 操作队列，state setter 稳定，无外部依赖
  const resolveInteraction = useCallback((kind: PendingInteraction['kind'], interactionId: string) => {
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
  }, []);

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
      || eventType === 'tool_confirmation_resolved'
      || eventType === 'user_question_asked'
      || eventType === 'user_question_answered_event'
      || eventType === 'proactive_result';

    // ── 全局 agent 活动追踪（在 session 过滤之前处理，跨会话） ──
    if (incomingSessionId) {
      if (eventType === 'agent_thinking') {
        setGlobalWorkingSessions(prev => {
          const next = new Set(prev);
          next.add(incomingSessionId);
          return next;
        });
      } else if (eventType === 'turn_completed' || eventType === 'turn_cancelled' || eventType === 'error') {
        setGlobalWorkingSessions(prev => {
          const next = new Set(prev);
          next.delete(incomingSessionId);
          return next;
        });
      } else if (eventType === 'tool_execution') {
        setGlobalLastToolName(String(payload.tool_name || ''));
      }
    }

    if (incomingSessionId && sessionIdRef.current && incomingSessionId !== sessionIdRef.current && !isGlobalInteractionEvent) {
      return;
    }

    switch (eventType) {
      case 'session_created': {
        const newSid = data.session_id as string;
        const requestId = typeof payload.request_id === 'string' ? payload.request_id : null;
        // 归属校验：如果存在 pendingCreateId 且响应中携带 request_id，
        // 只接受与最近一次创建请求匹配的 session_created
        if (pendingCreateIdRef.current && requestId && requestId !== pendingCreateIdRef.current) {
          // 不匹配的 session_created（来自旧请求），忽略并清理远端空 session
          authFetch(`${API_BASE}/api/sessions/${newSid}`, { method: 'DELETE' }).catch(() => {});
          break;
        }
        pendingCreateIdRef.current = null;
        setSessionId(newSid);
        sessionIdRef.current = newSid;
        loadSessionList();
        if (pendingInputRef.current) {
          const { content, contextFiles, meta } = pendingInputRef.current;
          wsSend({
            type: 'user_input',
            session_id: newSid,
            payload: {
              content,
              attachments: [],
              context_files: contextFiles || [],
              ...(meta ? { meta } : {}),
            },
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
        // 竞态保护：忽略非当前 session 的 session_loaded 响应（快速切换时可能乱序到达）
        if (sid && sid === sessionIdRef.current) {
          resetTurnTracking();
          setSessionId(sid);
          setMessages(rebuildMessagesFromEvents(events));
          setIsTyping(false);
        }
        break;
      }
      case 'agent_thinking':
        setIsTyping(true);
        break;
      // 流式 LLM 输出：通过 upsertAssistantTurnMessage 追加内容到最后一条同 turnId 消息。
      // 同一 turn 中工具调用前后会产生多条 assistant 消息，各自独立持有 thinkingContent。
      case 'llm_delta': {
        const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : undefined;
        if (turnId && cancelledTurnIdsRef.current.has(turnId)) {
          break;
        }
        const contentDelta = String(payload.content_delta || '');
        const reasoningDelta = String(payload.reasoning_delta || '');
        const contentSnapshot = String(payload.content_snapshot || '');

        if (contentDelta || reasoningDelta || contentSnapshot) {
          if (turnId) {
            lastStreamingTurnIdRef.current = turnId;
          }
          setIsTyping(true);
          setMessages((prev) => {
            if (turnId) {
              const existing = findLatestAssistantTurnMessage(prev, turnId);
              return upsertAssistantTurnMessage(prev, turnId, {
                content: contentSnapshot || ((existing?.content || '') + contentDelta),
                thinkingContent: reasoningDelta
                  ? (existing?.thinkingContent || '') + reasoningDelta
                  : existing?.thinkingContent,
                thinkingState: reasoningDelta ? 'streaming' as const : existing?.thinkingState,
              });
            }
            return [
              ...prev,
              {
                id: makeId(),
                role: 'assistant' as const,
                content: contentSnapshot || contentDelta,
                timestamp: Date.now(),
                turnId,
                thinkingContent: reasoningDelta || undefined,
                thinkingState: reasoningDelta ? 'streaming' as const : undefined,
              },
            ];
          });
        }
        break;
      }
      case 'llm_result': {
        const content = String(payload.content || '');
        const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : undefined;
        if (turnId && cancelledTurnIdsRef.current.has(turnId)) {
          break;
        }
        const thinkingContent = extractThinkContentFromReasoningDetails(payload.reasoning_details);
        if (content || thinkingContent) {
          if (turnId) {
            lastStreamingTurnIdRef.current = turnId;
          }
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
        if (payload.source === 'recommendation') {
          break;
        }
        const final = String(payload.final_response || '');
        const completedTurnId = typeof payload.turn_id === 'string' ? payload.turn_id : null;
        if (completedTurnId) {
          cancelledTurnIdsRef.current.delete(completedTurnId);
          if (lastStreamingTurnIdRef.current === completedTurnId) {
            lastStreamingTurnIdRef.current = null;
          }
        }
        setMessages((prev) => {
          if (completedTurnId) {
            // 只更新最后一条同 turnId 的 assistant 消息，保留早期消息的 thinking 不变。
            // 注意：不设置 thinkingState，思考过程默认展开显示。
            return upsertAssistantTurnMessage(prev, completedTurnId, {
              content: final,
              keepExistingContentWhenEmpty: true,
            });
          }
          // 从后往前找最后一条 assistant 消息
          for (let i = prev.length - 1; i >= 0; i--) {
            if (prev[i].role === 'assistant') {
              const existing = prev[i];
              // 如果 llm_result 已经设置了相同内容，保持不变
              if (existing.content === final || !final) {
                return prev;
              }
              // 内容不同时才更新（不创建新消息）
              const next = [...prev];
              next[i] = { ...next[i], content: final };
              return next;
            }
          }
          // 没找到 assistant 消息且有内容，追加一条
          if (final) {
            return [...prev, { id: makeId(), role: 'assistant', content: final, timestamp: Date.now() }];
          }
          return prev;
        });
        setIsTyping(false);
        clearInteractions();
        // 推送任务完成通知卡片
        const completedSessionId = incomingSessionId || '';
        if (completedSessionId) {
          pushCard({
            kind: 'task_completed',
            title: '任务完成',
            body: final ? (final.length > 100 ? final.slice(0, 100) + '...' : final) : '一个任务已完成',
            level: 'success',
            source: 'agent',
            sessionId: completedSessionId,
            actions: [{ label: '查看会话 →', value: 'view_session' }],
          });
        }
        break;
      }
      case 'turn_cancelled': {
        const cancelledTurnId = typeof payload.turn_id === 'string' ? payload.turn_id : null;
        if (cancelledTurnId) {
          cancelledTurnIdsRef.current.add(cancelledTurnId);
          if (lastStreamingTurnIdRef.current === cancelledTurnId) {
            lastStreamingTurnIdRef.current = null;
          }
        }
        setIsTyping(false);
        clearInteractions();
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
        addMsg('system', String(payload.user_message || payload.message || payload.error_type || 'Unknown Error'));
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
          // 同时推送到通知中心卡片
          const notifSessionId = typeof data.session_id === 'string' ? data.session_id : undefined;
          pushCard({
            kind: 'general',
            title,
            body,
            level: String(payload.level || 'info') as 'info' | 'warning' | 'error' | 'success',
            source: String(payload.source || 'system'),
            sessionId: notifSessionId,
            actions: notifSessionId ? [{ label: '查看会话 →', value: 'view_session' }] : undefined,
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
        const isCurrentSession = sourceSessionId === sessionIdRef.current;
        if (isCurrentSession) {
          setIsTyping(true);
          enqueueInteraction({
            kind: 'confirmation',
            interactionId: toolCallId,
            sourceSessionId,
            timeout: Number(payload.timeout || 300),
            createdAt: Date.now(),
            toolName: String(payload.tool_name || ''),
            riskLevel: String(payload.risk_level || 'medium'),
            arguments: (typeof payload.arguments === 'object' && payload.arguments !== null
              ? payload.arguments : {}) as Record<string, unknown>,
          });
        }
        pushCard({
          id: `confirm_${toolCallId}`,
          kind: 'tool_confirmation',
          title: '需要授权',
          body: `工具 "${payload.tool_name}" 需要你的确认才能执行`,
          level: 'warning',
          source: 'tool',
          sessionId: sourceSessionId,
          interactionId: toolCallId,
          actions: [
            { label: '批准', value: 'approve' },
            { label: '拒绝', value: 'deny' },
          ],
        });
        break;
      }
      case 'tool_confirmation_resolved': {
        const toolCallId = String(payload.tool_call_id || '');
        const status = String(payload.status || '');
        if (!toolCallId) break;
        resolveCard(`confirm_${toolCallId}`, status === 'approved' ? 'approve' : 'deny');
        break;
      }
      case 'user_question_asked': {
        const questionId = String(payload.question_id || '');
        const sourceSessionId = incomingSessionId || '';
        if (!questionId || !sourceSessionId) break;
        const sourceAgentId = String(payload.source_agent_id || 'default').trim() || 'default';
        const sourceAgentName = String(payload.source_agent_name || sourceAgentId).trim() || sourceAgentId;
        const isCurrentSession = sourceSessionId === sessionIdRef.current;
        const rawOptions = Array.isArray(payload.options)
          ? payload.options.map((o: unknown) => String(o))
          : null;
        if (isCurrentSession) {
          setIsTyping(false);
          setMessages((prev) => attachAskUserToLatestToolMessage(prev, {
            questionId,
            sourceSessionId,
            sourceAgentId,
            sourceAgentName,
            question: String(payload.question || ''),
            options: rawOptions,
            multiSelect: Boolean(payload.multi_select),
            pending: false,
            resolved: false,
          }));
          enqueueInteraction({
            kind: 'question',
            interactionId: questionId,
            sourceSessionId,
            timeout: Number(payload.timeout || 300),
            createdAt: Date.now(),
            sourceAgentId,
            sourceAgentName,
            question: String(payload.question || ''),
            options: rawOptions,
            multiSelect: Boolean(payload.multi_select),
          });
        }
        const questionCardActions = rawOptions
          ? rawOptions.map((o) => ({ label: o, value: o }))
          : undefined;
        pushCard({
          id: `question_${questionId}`,
          kind: 'user_question',
          title: `${sourceAgentName} 需要你的回复`,
          body: String(payload.question || '请做出选择'),
          level: 'info',
          source: sourceAgentName,
          sessionId: sourceSessionId,
          interactionId: questionId,
          actions: questionCardActions,
          questionData: {
            question: String(payload.question || ''),
            options: rawOptions || null,
            multiSelect: Boolean(payload.multi_select),
            interactionId: questionId,
            sessionId: sourceSessionId,
          },
          allowsInput: !questionCardActions || questionCardActions.length === 0,
          inputPlaceholder: '请输入回复',
        });
        break;
      }
      case 'user_question_answered_event': {
        const questionId = String(payload.question_id || '');
        if (questionId) {
          setMessages((prev) => updateAskUserToolState(prev, questionId, {
            pending: false,
            resolved: true,
          }));
          resolveInteraction('question', questionId);
          resolveCard(`question_${questionId}`, 'answered');
        }
        break;
      }
      case 'proactive_result': {
        const jobId = String(payload.job_id || '');
        const jobName = String(payload.job_name || '');
        const resultText = String(payload.result || '');
        const resultSessionId = String(payload.session_id || incomingSessionId || '');
        const sourceSessionId = payload.source_session_id ? String(payload.source_session_id) : undefined;
        const scratchSessionId = payload.scratch_session_id ? String(payload.scratch_session_id) : undefined;
        const recommendationType = payload.recommendation_type ? String(payload.recommendation_type) : undefined;
        const items = Array.isArray(payload.items) ? payload.items : undefined;
        const rawTimestamp = typeof data.timestamp === 'number' ? data.timestamp : Date.now();
        const receivedAt = rawTimestamp < 1e12 ? rawTimestamp * 1000 : rawTimestamp;

        const newItem: ProactiveResultItem = {
          jobId, jobName, result: resultText,
          sessionId: resultSessionId,
          scratchSessionId,
          receivedAt,
          sourceSessionId,
          recommendationType,
          items,
        };

        if (resultText || items) {
          setProactiveResults(prev => mergeProactiveResults(prev, [newItem]));
          loadSessionList();
          // 推荐类型只走看板 RecommendationCard，不推送通知/卡片
          if (resultText && !recommendationType) {
            pushNotification({
              title: `[主动推送] ${jobName || 'Proactive Agent'}`,
              body: resultText.slice(0, 200),
              level: 'info',
              source: 'proactive',
              createdAtMs: Date.now(),
            }, { toast: true, browser: false });
            pushCard({
              kind: 'general',
              title: `主动推送 — ${jobName || 'Proactive Agent'}`,
              body: resultText.slice(0, 300),
              level: 'info',
              source: 'proactive',
              sessionId: resultSessionId || undefined,
              actions: resultSessionId ? [{ label: '查看会话 →', value: 'view_session' }] : undefined,
            });
          }
        }
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
      const cookieMatch = document.cookie.match(/(?:^|; )sensenova_claw_token=([^;]*)/);
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

  useEffect(() => {
    if (!shouldActivate) return;
    void loadPendingRecommendations();
  }, [loadPendingRecommendations, shouldActivate]);

  // ── 对外接口 ──

  const doCleanupEmptySession = useCallback((excludeSid?: string) => {
    const emptyId = emptySessionIdRef.current;
    if (emptyId && emptyId !== excludeSid) {
      emptySessionIdRef.current = null;
      setSessions(prev => prev.filter(s => s.session_id !== emptyId));
      authFetch(`${API_BASE}/api/sessions/${emptyId}`, { method: 'DELETE' }).catch(() => {});
    }
  }, []);

  const switchedSessionRef = useRef(false);
  const getCurrentSessionAgentId = useCallback(() => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return null;
    const activeSession = sessions.find((item) => item.session_id === activeSessionId);
    if (!activeSession) return null;
    return getAgentId(activeSession.meta);
  }, [sessions]);

  const switchSession = useCallback(async (sid: string) => {
    switchedSessionRef.current = true;
    clearPendingPrefill();
    doCleanupEmptySession(sid);
    await reloadSessionHistory(sid);
  }, [clearPendingPrefill, reloadSessionHistory, doCleanupEmptySession]);

  const createSession = useCallback((agentId: string, taskId?: string) => {
    const meta: Record<string, string> = { title: '新对话' };
    if (taskId) meta.task_id = taskId;
    pendingCreateMeta.current = meta;
    const requestId = makeId();
    pendingCreateIdRef.current = requestId;
    wsSend({
      type: 'create_session',
      payload: { agent_id: agentId || 'default', meta, request_id: requestId },
      timestamp: Date.now() / 1000,
    });
  }, [wsSend]);

  const startNewChat = useCallback(() => {
    doCleanupEmptySession();
    setSessionId(null);
    sessionIdRef.current = null;
    setMessages([]);
    setIsTyping(false);
    clearPendingPrefill();
    resetTurnTracking();
    toolCallMapRef.current.clear();
    pendingInputRef.current = null;
    setRightSteps([]);
    setRightTaskProgress([]);
    toolStepMapRef.current.clear();
  }, [clearPendingPrefill, doCleanupEmptySession, resetTurnTracking]);

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
    // 如果是通过 switchSession 跳转过来的，保留会话不重置
    if (switchedSessionRef.current) {
      switchedSessionRef.current = false;
      return;
    }
    startNewChat();
  }, [startNewChat]);

  const submitQuestionResponse = useCallback((params: {
    questionId: string;
    sourceSessionId: string;
    answer: string | string[] | null;
    cancelled: boolean;
  }) => {
    const { questionId, sourceSessionId, answer, cancelled } = params;
    if (!sourceSessionId) {
      addMsg('system', 'Question source session not found, cannot submit answer.');
      return;
    }
    setInteractionSubmitting(true);
    setMessages((prev) => updateAskUserToolState(prev, questionId, {
      pending: true,
      resolved: false,
    }));
    wsSend({
      type: 'user_question_answered',
      session_id: sourceSessionId,
      payload: { question_id: questionId, answer, cancelled },
      timestamp: Date.now() / 1000,
    });
    markCardPending(`question_${questionId}`, cancelled ? 'cancel' : 'answered');
    resolveInteraction('question', questionId);
  }, [markCardPending, wsSend]);

  const sendMessage = useCallback((
    content: string,
    contextFiles?: ContextFileRef[],
    agentId?: string,
    recommendation?: RecommendationSendMeta | null,
  ) => {
    if (!content.trim() || !wsConnected) return;

    const interaction = activeInteractionRef.current;
    if (interaction?.kind === 'question') {
      submitQuestionResponse({
        questionId: interaction.interactionId,
        sourceSessionId: interaction.sourceSessionId,
        answer: content.trim(),
        cancelled: false,
      });
      return;
    }

    // 防止在 session 创建中重复发送：如果已有 pending input 且正在等待 session_created，忽略
    if (pendingInputRef.current && !sessionIdRef.current) return;

    const targetAgentId = agentId || 'default';
    const currentSessionAgentId = getCurrentSessionAgentId();
    if (sessionIdRef.current && currentSessionAgentId && currentSessionAgentId !== targetAgentId) {
      startNewChat();
    }

    emptySessionIdRef.current = null;
    resetTurnTracking();
    addMsg('user', content);

    const filePaths = contextFiles?.map(f => f.path) || [];
    const recommendationMeta = recommendation
      && sessionIdRef.current
      && recommendation.sourceSessionId === sessionIdRef.current
      ? {
          recommendation_id: recommendation.recommendationId,
          recommendation_source_session_id: recommendation.sourceSessionId,
        }
      : undefined;

    if (!sessionIdRef.current) {
      pendingInputRef.current = {
        content,
        contextFiles: filePaths,
        ...(recommendationMeta ? { meta: recommendationMeta } : {}),
      };
      const meta: Record<string, string> = { title: content.slice(0, 20) || '新对话' };
      const requestId = makeId();
      pendingCreateIdRef.current = requestId;
      wsSend({
        type: 'create_session',
        payload: { agent_id: targetAgentId, meta, request_id: requestId },
        timestamp: Date.now() / 1000,
      });
    } else {
      wsSend({
        type: 'user_input',
        session_id: sessionIdRef.current,
        payload: {
          content,
          attachments: [],
          context_files: filePaths,
          ...(recommendationMeta ? { meta: recommendationMeta } : {}),
        },
        timestamp: Date.now() / 1000,
      });
    }
    if (recommendationMeta) {
      setProactiveResults((prev) => consumeRecommendationFromResults(
        prev,
        recommendationMeta.recommendation_id,
        recommendationMeta.recommendation_source_session_id,
      ));
    }
    setIsTyping(true);
  }, [getCurrentSessionAgentId, resetTurnTracking, startNewChat, submitQuestionResponse, wsConnected, wsSend]);

  const sendQuestionAnswerFn = useCallback((answer: string | string[] | null, cancelled: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'question') return;
    submitQuestionResponse({
      questionId: interaction.interactionId,
      sourceSessionId: interaction.sourceSessionId,
      answer,
      cancelled,
    });
  }, [submitQuestionResponse]);

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
    // 不在本地立即 resolve，等待服务端 tool_confirmation_resolved 事件关闭 UI
  }, [wsSend]);

  const handleInteractionTimeoutFn = useCallback(() => {
    const interaction = activeInteractionRef.current;
    if (!interaction) return;
    if (interaction.kind === 'confirmation') {
      if (interaction.timeoutAction !== 'block') {
        addMsg('system', '工具审批等待已到期，正在等待服务端确认最终处理结果。');
      }
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

  const cancelTurn = useCallback(() => {
    if (!sessionIdRef.current) return;
    if (lastStreamingTurnIdRef.current) {
      cancelledTurnIdsRef.current.add(lastStreamingTurnIdRef.current);
    }
    wsSend({
      type: 'cancel_turn',
      session_id: sessionIdRef.current,
      timestamp: Date.now() / 1000,
    });
    setIsTyping(false);
  }, [wsSend]);

  // 计算任务分组
  const taskGroups = useMemo(() => groupSessionsToTasks(sessions), [sessions]);

  const globalActivity = useMemo<GlobalAgentActivity>(() => ({
    anyWorking: globalWorkingSessions.size > 0,
    workingSessionIds: globalWorkingSessions,
    lastToolName: globalLastToolName,
  }), [globalWorkingSessions, globalLastToolName]);

  const value: ChatSessionContextValue = useMemo(() => ({
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
    submitQuestionResponse,
    sendConfirmationResponse: sendConfirmationResponseFn,
    handleInteractionTimeout: handleInteractionTimeoutFn,
    handleSkillInvoke,
    cancelTurn,
    globalActivity,
    wsSend,
    resolveInteractionFromNotification: resolveInteraction,
    proactiveResults,
    pendingPrefill,
    prefillInput,
    clearPendingPrefill,
  }), [
    wsConnected, sessionId, switchSession, createSession, deleteSession,
    startNewChat, resetIfNeeded, doCleanupEmptySession, messages, isTyping,
    sendMessage, sessions, taskGroups, loadSessionList, loadingSessions,
    rightSteps, rightTaskProgress, activeInteraction, interactionSubmitting,
    sendQuestionAnswerFn, sendConfirmationResponseFn, handleInteractionTimeoutFn,
    handleSkillInvoke, cancelTurn, globalActivity, wsSend, resolveInteraction,
    proactiveResults, pendingPrefill, prefillInput, clearPendingPrefill,
  ]);

  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>;
}

export function useChatSession(): ChatSessionContextValue {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error('useChatSession must be used inside ChatSessionProvider');
  }
  return ctx;
}
