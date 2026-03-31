'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useNotification } from '@/hooks/useNotification';
import { useWebSocket } from './WebSocketContext';
import { useSession } from './SessionContext';
import { useEventDispatcher } from './EventDispatcherContext';
import { extractThinkContentFromReasoningDetails } from '@/lib/assistantThink';
import type { WsInboundEvent } from '@/lib/wsEvents';
import {
  type ChatMessage,
  type StepItem,
  type TaskProgressItem,
  type ContextFileRef,
  makeId,
  formatArgs,
  truncateResult,
  rebuildMessagesFromEvents,
  rebuildStepsFromEvents,
  findLatestAssistantTurnMessage,
  upsertAssistantTurnMessage,
} from '@/lib/chatTypes';

/** 检查事件列表中 turn 是否仍在进行中（有 user_input 但无对应的终结事件） */
/** 检查事件列表中 turn 是否仍在进行中：
 *  有 user_input 开启了 turn，但尚未收到终结事件。
 *  兼容两种事件格式：
 *  - WS 推送: type 字段，下划线命名 (user_input, turn_completed, ...)
 *  - API 历史: event_type 字段，点分命名 (user.input, agent.step_completed, ...) */
function isTurnStillActive(events: Record<string, unknown>[]): boolean {
  let active = false;
  for (const e of events) {
    const type = (e.type || e.event_type || '') as string;
    if (type === 'user_input' || type === 'user.input') {
      active = true;
    } else if (
      type === 'turn_completed' || type === 'turn_cancelled' || type === 'error' ||
      type === 'agent.step_completed'
    ) {
      active = false;
    }
  }
  return active;
}

// ── proactive 推送 ──

export interface ProactiveResultItem {
  jobId: string;
  jobName: string;
  sessionId: string;
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

// ── Context 类型 ──

export interface RecommendationSendMeta {
  recommendationId: string;
  sourceSessionId: string;
}

export interface PrefillInputPayload {
  text: string;
  recommendation?: RecommendationSendMeta | null;
}

export interface MessageContextValue {
  messages: ChatMessage[];
  isTyping: boolean;
  /** 当前 turn 是否在进行中（从发送消息到 turn_completed/cancelled/error）。
   *  与 isTyping 的区别：isTyping 在 user_question_asked 时会变 false（允许显示输入 UI），
   *  但 turnActive 始终为 true 直到 turn 真正结束。用于控制输入框的 disabled 状态。 */
  turnActive: boolean;
  steps: StepItem[];
  taskProgress: TaskProgressItem[];
  proactiveResults: ProactiveResultItem[];

  // 推荐卡片预填输入
  pendingPrefill: PrefillInputPayload | null;
  prefillInput: (value: string | PrefillInputPayload) => void;
  clearPendingPrefill: () => void;

  sendMessage: (content: string, contextFiles?: ContextFileRef[], agentId?: string) => void;
  cancelTurn: () => void;
  handleSkillInvoke: (skillName: string, args: string) => void;
  setTyping: (typing: boolean) => void;

  /** 供 InteractionContext 更新消息列表（如 ask_user 状态） */
  updateMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
}

const MessageCtx = createContext<MessageContextValue | null>(null);

// ── Provider ──

export function MessageProvider({ children }: { children: React.ReactNode }) {
  const { wsSend } = useWebSocket();
  const {
    sessionIdRef,
    emptySessionIdRef,
    startNewChat,
    getCurrentSessionAgentId,
    refreshTaskGroups,
    bindSessionToCurrentSocket,
  } = useSession();
  const { subscribeCurrentSession, subscribeGlobal, subscribeFrontendCreate, markFrontendCreate } = useEventDispatcher();
  const { pushNotification, pushCard } = useNotification();

  // 消息状态
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  // turnActive: 从发送消息起为 true，仅在 turn_completed/turn_cancelled/error 时才变 false
  const [turnActive, setTurnActive] = useState(false);

  // 步骤/进度
  const [rightSteps, setRightSteps] = useState<StepItem[]>([]);
  const [rightTaskProgress, setRightTaskProgress] = useState<TaskProgressItem[]>([]);
  const toolStepMapRef = useRef<Map<string, number>>(new Map());

  // proactive 推送
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

  // Turn 追踪
  const toolCallMapRef = useRef<Map<string, string>>(new Map());
  const cancelledTurnIdsRef = useRef<Set<string>>(new Set());
  const lastStreamingTurnIdRef = useRef<string | null>(null);
  const pendingInputRef = useRef<{ content: string; contextFiles?: string[] } | null>(null);
  const pendingSessionBootstrapIdRef = useRef<string | null>(null);

  // ── helpers ──

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
          role: 'assistant' as const,
          content,
          timestamp: Date.now(),
          turnId,
          thinkingContent,
          thinkingState,
        },
      ];
    });
  }

  const resetTurnTracking = useCallback(() => {
    cancelledTurnIdsRef.current.clear();
    lastStreamingTurnIdRef.current = null;
  }, []);

  // 监听 session 切换 — 重建消息和步骤
  const { currentSessionId } = useSession();
  const currentSessionIdRef = useRef<string | null>(null);
  currentSessionIdRef.current = currentSessionId;
  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      setIsTyping(false);
      setTurnActive(false);
      resetTurnTracking();
      toolCallMapRef.current.clear();
      setRightSteps([]);
      setRightTaskProgress([]);
      toolStepMapRef.current.clear();
      pendingInputRef.current = null;
      pendingSessionBootstrapIdRef.current = null;
      return;
    }
    let cancelled = false;
    const isPendingSessionBootstrap = pendingSessionBootstrapIdRef.current === currentSessionId;
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/api/sessions/${currentSessionId}/events`);
        const d = await res.json();
        const events = (d.events || []) as Record<string, unknown>[];
        if (cancelled) return;
        resetTurnTracking();
        toolCallMapRef.current.clear();
        setMessages(rebuildMessagesFromEvents(events));
        const { steps, taskProgress, toolStepMap } = rebuildStepsFromEvents(events);
        setRightSteps(steps);
        setRightTaskProgress(taskProgress);
        toolStepMapRef.current = toolStepMap;
        if (!isPendingSessionBootstrap) {
          const stillActive = isTurnStillActive(events);
          setIsTyping(stillActive);
          setTurnActive(stillActive);
        }
        pendingSessionBootstrapIdRef.current = null;
      } catch {
        if (cancelled) return;
        setRightSteps([]);
        setRightTaskProgress([]);
        toolStepMapRef.current.clear();
      }
    })();
    return () => { cancelled = true; };
  }, [currentSessionId, resetTurnTracking]);

  // ── 当前 session 事件处理 ──

  useEffect(() => {
    return subscribeCurrentSession((event: WsInboundEvent) => {
      switch (event.type) {
        case 'session_loaded': {
          const events = Array.isArray(event.payload.events) ? event.payload.events : [];
          resetTurnTracking();
          setMessages(rebuildMessagesFromEvents(events));
          const stillActive = isTurnStillActive(events);
          setIsTyping(stillActive);
          setTurnActive(stillActive);
          pendingSessionBootstrapIdRef.current = null;
          break;
        }
        case 'agent_thinking':
          setIsTyping(true);
          break;
        case 'llm_delta': {
          const { turn_id: turnId, content_delta: contentDelta, reasoning_delta: reasoningDelta, content_snapshot: contentSnapshot } = event.payload;
          if (turnId && cancelledTurnIdsRef.current.has(turnId)) break;
          if (contentDelta || reasoningDelta || contentSnapshot) {
            if (turnId) lastStreamingTurnIdRef.current = turnId;
            setIsTyping(true);
            setMessages((prev) => {
              if (turnId) {
                const existing = findLatestAssistantTurnMessage(prev, turnId);
                return upsertAssistantTurnMessage(prev, turnId, {
                  content: contentSnapshot || ((existing?.content || '') + (contentDelta || '')),
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
                  content: contentSnapshot || contentDelta || '',
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
          const content = event.payload.content || '';
          const turnId = event.payload.turn_id;
          if (turnId && cancelledTurnIdsRef.current.has(turnId)) break;
          const thinkingContent = extractThinkContentFromReasoningDetails(event.payload.reasoning_details);
          if (content || thinkingContent) {
            if (turnId) lastStreamingTurnIdRef.current = turnId;
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
          const { tool_name: toolName, tool_call_id: toolCallId } = event.payload;
          const ti = { name: toolName, arguments: (event.payload.arguments || {}) as Record<string, unknown>, status: 'running' as const };
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
          const { tool_name: toolName, tool_call_id: toolCallId } = event.payload;
          const result = truncateResult(event.payload.result);
          const success = Boolean(event.payload.success);
          const error = event.payload.error || '';
          const mid = toolCallMapRef.current.get(toolCallId);
          if (mid) {
            setMessages(prev => prev.map(m => m.id === mid ? { ...m, content: `Tool Finished: ${toolName}`, toolInfo: { name: toolName, arguments: m.toolInfo?.arguments || {}, result, success, error, status: 'completed' } } : m));
          } else {
            const fallbackContent = typeof result === 'string' ? result : formatArgs(result);
            setMessages(prev => [...prev, { id: makeId(), role: 'tool', name: toolName, content: fallbackContent, timestamp: Date.now() }]);
          }
          const stepIdx = toolStepMapRef.current.get(toolCallId);
          if (stepIdx !== undefined) {
            setRightSteps(prev => prev.map((s, i) => i === stepIdx ? { ...s, status: 'done' as const } : s));
          }
          setRightTaskProgress(prev => {
            const idx = prev.findIndex(t => t.task === toolName && t.status === 'running');
            if (idx === -1) return prev;
            return prev.map((t, i) => i === idx ? { ...t, step: 1, status: 'completed' as const } : t);
          });
          break;
        }
        case 'turn_completed': {
          if (event.payload.source === 'recommendation') {
            break;
          }
          const final = event.payload.final_response || '';
          const completedTurnId = event.payload.turn_id || null;
          if (completedTurnId) {
            cancelledTurnIdsRef.current.delete(completedTurnId);
            if (lastStreamingTurnIdRef.current === completedTurnId) lastStreamingTurnIdRef.current = null;
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
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant') {
                const existing = prev[i];
                // 如果 llm_result 已经设置了相同内容，保持不变
                if (existing.content === final || !final) {
                  return prev;
                }
                // 内容不同时才更新（不创建新消息）
                const next = [...prev]; next[i] = { ...next[i], content: final }; return next;
              }
            }
            if (final) return [...prev, { id: makeId(), role: 'assistant', content: final, timestamp: Date.now() }];
            return prev;
          });
          setIsTyping(false);
          setTurnActive(false);
          pendingSessionBootstrapIdRef.current = null;
          break;
        }
        case 'turn_cancelled': {
          const cancelledTurnId = event.payload.turn_id || null;
          if (cancelledTurnId) {
            cancelledTurnIdsRef.current.add(cancelledTurnId);
            if (lastStreamingTurnIdRef.current === cancelledTurnId) lastStreamingTurnIdRef.current = null;
          }
          setIsTyping(false);
          setTurnActive(false);
          pendingSessionBootstrapIdRef.current = null;
          break;
        }
        case 'error':
          addMsg('system', event.payload.user_message || event.payload.message || event.payload.error_type || 'Unknown Error');
          setIsTyping(false);
          setTurnActive(false);
          pendingSessionBootstrapIdRef.current = null;
          break;
        // 交互事件的 typing 状态（仅当前 session，重构前在单体 handler 中 isCurrentSession 守卫内处理）
        case 'tool_confirmation_requested':
          if (!event.session_id || event.session_id === currentSessionIdRef.current) setIsTyping(true);
          break;
        case 'user_question_asked':
          if (!event.session_id || event.session_id === currentSessionIdRef.current) setIsTyping(false);
          break;
        case 'user_question_answered_event':
          if (!event.session_id || event.session_id === currentSessionIdRef.current) setIsTyping(false);
          break;
      }
    });
  }, [subscribeCurrentSession, resetTurnTracking]);

  // ── 全局事件处理（跨会话通知） ──

  useEffect(() => {
    return subscribeGlobal((event: WsInboundEvent) => {
      switch (event.type) {
        case 'turn_completed': {
          // 跨会话 turn_completed → 推送通知卡片
          const completedSessionId = event.session_id || '';
          const final = event.payload.final_response || '';
          pushCard({
            kind: 'task_completed',
            title: '任务完成',
            body: final ? (final.length > 100 ? final.slice(0, 100) + '...' : final) : '一个任务已完成',
            level: 'success',
            source: 'agent',
            sessionId: completedSessionId,
            actions: [{ label: '查看会话 →', value: 'view_session' }],
          });
          break;
        }
        case 'notification': {
          const title = event.payload.title || 'Notification';
          const body = event.payload.body || event.payload.text || '';
          const metadata = event.payload.metadata || {};
          if (body) {
            pushNotification({
              title,
              body,
              level: (event.payload.level || 'info') as 'info' | 'warning' | 'error' | 'success',
              source: event.payload.source || 'system',
              createdAtMs: event.payload.created_at_ms || Date.now(),
            }, {
              toast: metadata.show_toast !== false,
              browser: metadata.show_browser === true,
            });
            const notifSessionId = event.session_id;
            pushCard({
              kind: 'general',
              title,
              body,
              level: (event.payload.level || 'info') as 'info' | 'warning' | 'error' | 'success',
              source: event.payload.source || 'system',
              sessionId: notifSessionId,
              actions: notifSessionId ? [{ label: '查看会话 →', value: 'view_session' }] : undefined,
            });
          }
          if (body && Boolean(metadata.append_to_chat)) {
            const targetSessionId = event.session_id || null;
            if (!targetSessionId || targetSessionId === sessionIdRef.current) {
              addMsg('system', body);
            }
          }
          break;
        }
        case 'proactive_result': {
          const { job_id: jobId, job_name: jobName, result: resultText } = event.payload;
          const resultSessionId = event.payload.session_id || event.session_id || '';
          const sourceSessionId = event.payload.source_session_id ? String(event.payload.source_session_id) : undefined;
          const recommendationType = event.payload.recommendation_type ? String(event.payload.recommendation_type) : undefined;
          const items = Array.isArray(event.payload.items) ? event.payload.items : undefined;

          const newItem: ProactiveResultItem = {
            jobId, jobName, result: resultText,
            sessionId: resultSessionId,
            receivedAt: Date.now(),
            sourceSessionId,
            recommendationType,
            items,
          };

          if (resultText) {
            setProactiveResults(prev => {
              const deduped = prev.filter(r => !(r.jobId === jobId && r.sessionId === resultSessionId));
              return [newItem, ...deduped].slice(0, 50);
            });
            refreshTaskGroups();
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
          break;
        }
      }
    });
  }, [subscribeGlobal, pushCard, pushNotification, refreshTaskGroups, sessionIdRef]);

  // ── 前端创建 session 事件处理（pendingInput） ──

  useEffect(() => {
    return subscribeFrontendCreate((event: WsInboundEvent) => {
      if (event.type === 'session_created') {
        const newSid = event.session_id;
        if (!newSid) return;
        if (pendingInputRef.current) {
          const { content, contextFiles } = pendingInputRef.current;
          pendingSessionBootstrapIdRef.current = newSid;
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
      }
    });
  }, [subscribeFrontendCreate, wsSend, emptySessionIdRef]);

  // ── 对外接口 ──

  const sendMessage = useCallback((content: string, contextFiles?: ContextFileRef[], agentId?: string) => {
    if (!content.trim()) return;

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

    if (!sessionIdRef.current) {
      pendingInputRef.current = { content, contextFiles: filePaths };
      markFrontendCreate();
      const meta: Record<string, string> = { title: content.slice(0, 20) || '新对话' };
      const requestId = makeId();
      wsSend({
        type: 'create_session',
        payload: { agent_id: targetAgentId, meta, request_id: requestId },
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
    setTurnActive(true);
  }, [getCurrentSessionAgentId, resetTurnTracking, startNewChat, wsSend, sessionIdRef, emptySessionIdRef, markFrontendCreate]);

  const handleSkillInvoke = useCallback(async (skillName: string, args: string) => {
    if (!sessionIdRef.current) {
      pushNotification({
        title: '命令执行失败',
        body: '请先发送一条普通消息创建会话，再执行 / 命令',
        level: 'error',
        source: 'skill',
      });
      return;
    }
    try {
      const resp = await authFetch(`${API_BASE}/api/sessions/${sessionIdRef.current}/skill-invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: skillName, arguments: args }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        pushNotification({
          title: '命令执行失败',
          body: errData.detail || `未知错误 (${resp.status})`,
          level: 'error',
          source: 'skill',
        });
        return;
      }
      setIsTyping(true);
      setTurnActive(true);
    } catch (err) {
      pushNotification({
        title: '命令执行失败',
        body: '网络错误，请稍后重试',
        level: 'error',
        source: 'skill',
      });
    }
  }, [sessionIdRef, pushNotification]);

  const cancelTurn = useCallback(() => {
    if (!sessionIdRef.current && !pendingInputRef.current) return;
    addMsg('system', '用户中止');
    if (!sessionIdRef.current) {
      pendingInputRef.current = null;
      pendingSessionBootstrapIdRef.current = null;
      setIsTyping(false);
      return;
    }
    if (lastStreamingTurnIdRef.current) {
      cancelledTurnIdsRef.current.add(lastStreamingTurnIdRef.current);
    }
    wsSend({
      type: 'cancel_turn',
      session_id: sessionIdRef.current,
      timestamp: Date.now() / 1000,
    });
    setIsTyping(false);
  }, [wsSend, sessionIdRef]);

  const updateMessages = useCallback((updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setMessages(updater);
  }, []);

  const value: MessageContextValue = {
    messages,
    isTyping,
    turnActive,
    steps: rightSteps,
    taskProgress: rightTaskProgress,
    proactiveResults,
    pendingPrefill,
    prefillInput,
    clearPendingPrefill,
    sendMessage,
    cancelTurn,
    handleSkillInvoke,
    setTyping: setIsTyping,
    updateMessages,
  };

  return <MessageCtx.Provider value={value}>{children}</MessageCtx.Provider>;
}

// ── Hooks ──

export function useMessages(): MessageContextValue {
  const ctx = useContext(MessageCtx);
  if (!ctx) throw new Error('useMessages must be used inside MessageProvider');
  return ctx;
}
