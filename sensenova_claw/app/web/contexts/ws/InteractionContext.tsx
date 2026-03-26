'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNotification } from '@/hooks/useNotification';
import { useWebSocket } from './WebSocketContext';
import { useEventDispatcher } from './EventDispatcherContext';
import type { PendingInteraction } from '@/components/chat/QuestionDialog';
import type { WsInboundEvent } from '@/lib/wsEvents';

// ── Context 类型 ──

export interface InteractionContextValue {
  activeInteraction: PendingInteraction | null;
  interactionSubmitting: boolean;
  sendQuestionAnswer: (answer: string | string[] | null, cancelled: boolean) => void;
  sendConfirmationResponse: (approved: boolean) => void;
  handleInteractionTimeout: () => void;
  /** 通知面板回答 ask_user 时同步解除阻塞 */
  resolveInteractionFromNotification?: (kind: 'question' | 'confirmation', interactionId: string) => void;
}

const InteractionCtx = createContext<InteractionContextValue | null>(null);

// ── Provider ──

export function InteractionProvider({ children }: { children: React.ReactNode }) {
  const { wsSend } = useWebSocket();
  const { subscribeCurrentSession } = useEventDispatcher();
  const { pushCard, resolveCard } = useNotification();

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

  // ── 监听当前 session 事件 ──

  useEffect(() => {
    return subscribeCurrentSession((event: WsInboundEvent) => {
      switch (event.type) {
        case 'tool_confirmation_requested': {
          const { tool_call_id: toolCallId, tool_name: toolName } = event.payload;
          const sourceSessionId = event.session_id || '';
          if (!toolCallId || !sourceSessionId) break;
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
          pushCard({
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
            resolveInteraction('question', questionId);
            resolveCard(`question_${questionId}`, 'answered');
          }
          break;
        }
        case 'turn_completed':
        case 'turn_cancelled':
        case 'error':
          clearInteractions();
          break;
      }
    });
  }, [subscribeCurrentSession, enqueueInteraction, resolveInteraction, clearInteractions, pushCard, resolveCard]);

  // ── 对外接口 ──

  const sendQuestionAnswer = useCallback((answer: string | string[] | null, cancelled: boolean) => {
    const interaction = activeInteractionRef.current;
    if (!interaction || interaction.kind !== 'question') return;
    if (!interaction.sourceSessionId) return;
    setInteractionSubmitting(true);
    wsSend({
      type: 'user_question_answered',
      session_id: interaction.sourceSessionId,
      payload: { question_id: interaction.interactionId, answer, cancelled },
      timestamp: Date.now() / 1000,
    });
    resolveCard(`question_${interaction.interactionId}`, cancelled ? 'cancel' : 'answered');
    resolveInteraction('question', interaction.interactionId);
  }, [wsSend, resolveCard, resolveInteraction]);

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
