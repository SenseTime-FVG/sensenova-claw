'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNotification } from '@/hooks/useNotification';
import { useWebSocket } from './WebSocketContext';
import { useEventDispatcher } from './EventDispatcherContext';
import { useSession } from './SessionContext';
import { useMessages } from './MessageContext';
import { attachAskUserToLatestToolMessage, updateAskUserToolState } from '@/lib/chatTypes';
import type { PendingInteraction } from '@/components/chat/QuestionDialog';
import type { WsInboundEvent } from '@/lib/wsEvents';

// ── Context 类型 ──

export interface InteractionContextValue {
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
  /** 通知面板回答 ask_user 时同步解除阻塞 */
  resolveInteractionFromNotification?: (kind: 'question' | 'confirmation', interactionId: string) => void;
}

const InteractionCtx = createContext<InteractionContextValue | null>(null);

// ── Provider ──

export function InteractionProvider({ children }: { children: React.ReactNode }) {
  const { wsSend } = useWebSocket();
  const { subscribeCurrentSession, subscribeGlobal } = useEventDispatcher();
  const { pushCard, pushToast, resolveCard, markCardPending } = useNotification();
  const { currentSessionId } = useSession();
  const { updateMessages } = useMessages();
  const currentSessionIdRef = useRef<string | null>(null);
  currentSessionIdRef.current = currentSessionId;

  const [activeInteraction, setActiveInteraction] = useState<PendingInteraction | null>(null);
  const [interactionSubmitting, setInteractionSubmitting] = useState(false);

  const interactionQueueRef = useRef<PendingInteraction[]>([]);
  const activeInteractionRef = useRef<PendingInteraction | null>(null);

  // ── 队列管理 ──

  const interactionKey = (interaction: PendingInteraction) =>
    `${interaction.kind}:${interaction.interactionId}`;

  const enqueueInteraction = useCallback((interaction: PendingInteraction) => {
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
  }, []);

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

  const clearInteractions = useCallback(() => {
    interactionQueueRef.current = [];
    activeInteractionRef.current = null;
    setActiveInteraction(null);
    setInteractionSubmitting(false);
  }, []);

  const clearInteractionsForSession = useCallback((sourceSessionId: string) => {
    if (!sourceSessionId) return;

    const active = activeInteractionRef.current;
    const queue = interactionQueueRef.current;
    const filteredQueue = queue.filter((item) => item.sourceSessionId !== sourceSessionId);

    if (active?.sourceSessionId === sourceSessionId) {
      interactionQueueRef.current = filteredQueue;
      const next = filteredQueue[0] ?? null;
      if (next) {
        interactionQueueRef.current = filteredQueue.slice(1);
      }
      activeInteractionRef.current = next;
      setActiveInteraction(next);
      setInteractionSubmitting(false);
      return;
    }

    if (filteredQueue.length !== queue.length) {
      interactionQueueRef.current = filteredQueue;
    }
  }, []);

  // ── 监听当前 session 事件 ──

  useEffect(() => {
    return subscribeCurrentSession((event: WsInboundEvent) => {
      switch (event.type) {
        case 'tool_confirmation_requested': {
          const { tool_call_id: toolCallId, tool_name: toolName } = event.payload;
          const sourceSessionId = event.session_id || '';
          if (!toolCallId || !sourceSessionId) break;
          const isThisSession = sourceSessionId === currentSessionIdRef.current;
          if (isThisSession) {
            enqueueInteraction({
              kind: 'confirmation',
              interactionId: toolCallId,
              sourceSessionId,
              timeout: event.payload.timeout || 300,
              createdAt: Date.now(),
              toolName: toolName || '',
              riskLevel: event.payload.risk_level || 'medium',
              arguments: (event.payload.arguments || {}) as Record<string, unknown>,
            });
          }
          const cardId = pushCard({
            id: `confirm_${toolCallId}`,
            kind: 'tool_confirmation',
            title: '需要授权',
            body: `工具 "${toolName}" 需要你的确认才能执行`,
            level: 'warning',
            source: 'tool',
            sessionId: sourceSessionId,
            interactionId: toolCallId,
            actions: [
              { label: '批准', value: 'approve' },
              { label: '拒绝', value: 'deny' },
            ],
          });
          // 当前 session 也需要 toast 弹窗（聊天区域没有内嵌的确认 UI）
          pushToast({
            kind: 'tool_confirmation',
            title: '需要授权',
            body: `工具 "${toolName}" 需要你的确认才能执行`,
            level: 'warning',
            actions: [
              { label: '批准', value: 'approve' },
              { label: '拒绝', value: 'deny' },
            ],
            cardId,
            sessionId: sourceSessionId,
            eventKey: `confirm_${toolCallId}`,
            onAction: (actionValue) => {
              wsSend({
                type: 'tool_confirmation_response',
                session_id: sourceSessionId,
                payload: { tool_call_id: toolCallId, approved: actionValue === 'approve' },
                timestamp: Date.now() / 1000,
              });
              markCardPending(cardId, actionValue);
            },
          });
          break;
        }
        case 'tool_confirmation_resolved': {
          const { tool_call_id: toolCallId, status } = event.payload;
          if (!toolCallId) break;
          resolveCard(`confirm_${toolCallId}`, status === 'approved' ? 'approve' : 'deny');
          break;
        }
        case 'user_question_asked': {
          const sourceSessionId = event.session_id || '';
          const { question_id: questionId, question, source_agent_id, source_agent_name, options, multi_select: multiSelect, timeout } = event.payload;
          if (!questionId || !sourceSessionId) break;
          const sourceAgentId = (source_agent_id || 'default').trim() || 'default';
          const sourceAgentName = (source_agent_name || sourceAgentId).trim() || sourceAgentId;
          const rawOptions = Array.isArray(options) ? options : null;
          // 重构前行为：enqueueInteraction 仅当前 session，pushCard 始终执行
          const isThisSession2 = sourceSessionId === currentSessionIdRef.current;
          if (isThisSession2) {
            updateMessages((prev) => attachAskUserToLatestToolMessage(prev, {
              questionId,
              sourceSessionId,
              sourceAgentId,
              sourceAgentName,
              question: question || '',
              options: rawOptions,
              multiSelect: Boolean(multiSelect),
              pending: false,
              resolved: false,
            }));
            enqueueInteraction({
              kind: 'question',
              interactionId: questionId,
              sourceSessionId,
              timeout: timeout || 300,
              createdAt: Date.now(),
              sourceAgentId,
              sourceAgentName,
              question: question || '',
              options: rawOptions,
              multiSelect: Boolean(multiSelect),
            });
          }
          const questionCardActions = rawOptions
            ? rawOptions.map((o) => ({ label: o, value: o }))
            : undefined;
          pushCard({
            id: `question_${questionId}`,
            kind: 'user_question',
            title: `${sourceAgentName} 需要你的回复`,
            body: question || '请做出选择',
            level: 'info',
            source: sourceAgentName,
            sessionId: sourceSessionId,
            interactionId: questionId,
            actions: questionCardActions,
            questionData: {
              question: question || '',
              options: rawOptions || null,
              multiSelect: Boolean(multiSelect),
              interactionId: questionId,
              sessionId: sourceSessionId,
            },
            allowsInput: !questionCardActions || questionCardActions.length === 0,
            inputPlaceholder: '请输入回复',
          });
          break;
        }
        case 'user_question_answered_event': {
          const questionId = event.payload.question_id || '';
          if (questionId) {
            updateMessages((prev) => updateAskUserToolState(prev, questionId, {
              pending: false,
              resolved: true,
            }));
            setInteractionSubmitting(false);
            resolveInteraction('question', questionId);
            resolveCard(`question_${questionId}`, 'answered');
          }
          break;
        }
        case 'turn_completed':
        case 'turn_cancelled':
        case 'error': {
          const sourceSessionId = event.session_id || '';
          if (sourceSessionId) {
            clearInteractionsForSession(sourceSessionId);
          } else {
            clearInteractions();
          }
          break;
        }
      }
    });
  }, [
    subscribeCurrentSession,
    enqueueInteraction,
    resolveInteraction,
    clearInteractions,
    clearInteractionsForSession,
    pushCard,
    resolveCard,
    updateMessages,
  ]);

  // ── 跨 session 交互弹窗 ──
  // 当交互事件来自非当前 session 时，通过 pushToast 弹出可操作的悬浮提示
  useEffect(() => {
    return subscribeGlobal((event: WsInboundEvent) => {
      switch (event.type) {
        case 'tool_confirmation_requested': {
          const { tool_call_id: toolCallId, tool_name: toolName } = event.payload;
          const sourceSessionId = event.session_id || '';
          if (!toolCallId || !sourceSessionId) break;
          // 仅为跨 session 事件创建弹窗（当前 session 已有内联对话框）
          if (sourceSessionId === currentSessionIdRef.current) break;
          const cardId = `confirm_${toolCallId}`;
          pushToast({
            kind: 'tool_confirmation',
            title: '工具授权请求',
            body: `工具 "${toolName || '工具'}" 需要你的确认才能执行`,
            level: 'warning',
            actions: [
              { label: '批准', value: 'approve' },
              { label: '拒绝', value: 'deny' },
            ],
            cardId,
            sessionId: sourceSessionId,
            eventKey: `confirm_${toolCallId}`,
            onAction: (actionValue) => {
              wsSend({
                type: 'tool_confirmation_response',
                session_id: sourceSessionId,
                payload: { tool_call_id: toolCallId, approved: actionValue === 'approve' },
                timestamp: Date.now() / 1000,
              });
              markCardPending(cardId, actionValue);
            },
          });
          break;
        }
        case 'user_question_asked': {
          const { question_id: questionId, question, source_agent_id, source_agent_name, options, multi_select: multiSelect } = event.payload;
          const sourceSessionId = event.session_id || '';
          if (!questionId || !sourceSessionId) break;
          // 仅为跨 session 事件创建弹窗（当前 session 已有内联对话框）
          if (sourceSessionId === currentSessionIdRef.current) break;
          const sourceAgentId = (source_agent_id || 'default').trim() || 'default';
          const sourceAgentName = (source_agent_name || sourceAgentId).trim() || sourceAgentId;
          const rawOptions = Array.isArray(options) ? options : null;
          const cardId = `question_${questionId}`;
          const questionData = {
            question: question || '',
            options: rawOptions || null,
            multiSelect: Boolean(multiSelect),
            interactionId: questionId,
            sessionId: sourceSessionId,
          };
          const questionCardActions = rawOptions
            ? rawOptions.map((o: string) => ({ label: o, value: o }))
            : undefined;
          pushToast({
            kind: 'user_question',
            title: `${sourceAgentName} 需要你的回复`,
            body: question || '请做出选择',
            level: 'info',
            actions: questionCardActions,
            allowsInput: !questionCardActions || questionCardActions.length === 0,
            inputPlaceholder: '请输入回复',
            questionData,
            cardId,
            sessionId: sourceSessionId,
            eventKey: `question_${questionId}`,
            onAction: (actionValue, inputValue) => {
              wsSend({
                type: 'user_question_answered',
                session_id: sourceSessionId,
                payload: { question_id: questionId, answer: inputValue || actionValue, cancelled: false },
                timestamp: Date.now() / 1000,
              });
              markCardPending(cardId, actionValue);
            },
          });
          break;
        }
      }
    });
  }, [subscribeGlobal, pushToast, wsSend, markCardPending]);

  // ── 对外接口 ──

  const submitQuestionResponse = useCallback((params: {
    questionId: string;
    sourceSessionId: string;
    answer: string | string[] | null;
    cancelled: boolean;
  }) => {
    const { questionId, sourceSessionId, answer, cancelled } = params;
    if (!sourceSessionId) return;
    setInteractionSubmitting(true);
    updateMessages((prev) => updateAskUserToolState(prev, questionId, {
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
  }, [markCardPending, wsSend, resolveInteraction, updateMessages]);

  const sendQuestionAnswer = useCallback((answer: string | string[] | null, cancelled: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'question') return;
    submitQuestionResponse({
      questionId: interaction.interactionId,
      sourceSessionId: interaction.sourceSessionId,
      answer,
      cancelled,
    });
  }, [submitQuestionResponse]);

  const sendConfirmationResponse = useCallback((approved: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'confirmation') return;
    if (!interaction.sourceSessionId) return;
    setInteractionSubmitting(true);
    wsSend({
      type: 'tool_confirmation_response',
      session_id: interaction.sourceSessionId,
      payload: { tool_call_id: interaction.interactionId, approved },
      timestamp: Date.now() / 1000,
    });
  }, [wsSend]);

  const handleInteractionTimeout = useCallback(() => {
    const interaction = activeInteractionRef.current;
    if (!interaction) return;
    if (interaction.kind === 'confirmation') return;
    resolveInteraction('question', interaction.interactionId);
  }, [resolveInteraction]);

  const value: InteractionContextValue = {
    activeInteraction,
    interactionSubmitting,
    sendQuestionAnswer,
    submitQuestionResponse,
    sendConfirmationResponse,
    handleInteractionTimeout,
    resolveInteractionFromNotification: resolveInteraction,
  };

  return <InteractionCtx.Provider value={value}>{children}</InteractionCtx.Provider>;
}

// ── Hooks ──

export function useInteraction(): InteractionContextValue {
  const ctx = useContext(InteractionCtx);
  if (!ctx) throw new Error('useInteraction must be used inside InteractionProvider');
  return ctx;
}
