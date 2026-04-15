'use client';

/**
 * ChatSessionContext — 组合层
 *
 * 保持 useChatSession() 接口不变，内部委托给 4 个拆分后的子 Context：
 * - WebSocketContext: WS 连接管理
 * - SessionContext: 会话列表 & 生命周期
 * - MessageContext: 消息状态 & 流式更新
 * - InteractionContext: 交互队列 & 问答确认
 *
 * 所有消费者无需修改 import。
 */

import React from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  WebSocketProvider,
  EventDispatcherProvider,
  SessionProvider,
  MessageProvider,
  InteractionProvider,
  useWebSocket,
  useSession,
  useMessages,
  useInteraction,
  useEventDispatcher,
} from '@/contexts/ws';
import type { GlobalAgentActivity, ProactiveResultItem, PrefillInputPayload, RecommendationSendMeta } from '@/contexts/ws';
import type { PendingInteraction, PendingQuestionInteraction } from '@/components/chat/QuestionDialog';
import type {
  ChatMessage,
  SessionItem,
  TaskGroup,
  StepItem,
  TaskProgressItem,
  ContextFileRef,
} from '@/lib/chatTypes';

// ── 导出类型（保持向后兼容） ──

export type { GlobalAgentActivity, ProactiveResultItem, RecommendationSendMeta, PrefillInputPayload };

export interface ChatSessionContextValue {
  // 连接
  wsConnected: boolean;

  // Session
  currentSessionId: string | null;
  switchSession: (sessionId: string) => void;
  createSession: (agentId: string, taskId?: string) => void;
  startNewChat: () => void;
  deleteSession: (sessionId: string) => Promise<void>;
  resetIfNeeded: () => void;
  cleanupEmptySession: () => void;

  // 消息
  messages: ChatMessage[];
  isTyping: boolean;
  turnActive: boolean;
  turnCancelling: boolean;
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
  currentSessionQuestionInteraction: PendingQuestionInteraction | null;
  interactionSubmitting: boolean;
  sendQuestionAnswer: (answer: string | string[] | null, cancelled: boolean) => void;
  sendCurrentSessionQuestionAnswer: (answer: string | string[] | null, cancelled: boolean) => void;
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

  // 通知面板
  resolveInteractionFromNotification?: (kind: 'question' | 'confirmation', interactionId: string) => void;

  // proactive 推送
  proactiveResults: ProactiveResultItem[];

  // 推荐卡片预填
  pendingPrefill: PrefillInputPayload | null;
  prefillInput: (value: string | PrefillInputPayload) => void;
  clearPendingPrefill: () => void;

  // 手动触发 WebSocket 重连
  reconnect: () => void;
}

// ── Provider 组合 ──

const BYPASS_PATHS = ['/login', '/setup'];

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const shouldActivate = !isLoading && isAuthenticated && !BYPASS_PATHS.includes(pathname || '');

  return (
    <WebSocketProvider enabled={shouldActivate}>
      <EventDispatcherProvider>
        <SessionProvider>
          <MessageProvider>
            <InteractionProvider>
              {children}
            </InteractionProvider>
          </MessageProvider>
        </SessionProvider>
      </EventDispatcherProvider>
    </WebSocketProvider>
  );
}

// ── 组合 Hook（保持向后兼容） ──

export function useChatSession(): ChatSessionContextValue {
  const ws = useWebSocket();
  const session = useSession();
  const msg = useMessages();
  const interaction = useInteraction();
  const dispatcher = useEventDispatcher();

  return {
    // 连接
    wsConnected: ws.wsConnected,
    wsSend: ws.wsSend,

    // Session
    currentSessionId: session.currentSessionId,
    switchSession: session.switchSession,
    createSession: session.createSession,
    startNewChat: session.startNewChat,
    deleteSession: session.deleteSession,
    resetIfNeeded: session.resetIfNeeded,
    cleanupEmptySession: session.cleanupEmptySession,
    sessions: session.sessions,
    taskGroups: session.taskGroups,
    refreshTaskGroups: session.refreshTaskGroups,
    loadingSessions: session.loadingSessions,

    // 消息
    messages: msg.messages,
    isTyping: msg.isTyping,
    turnActive: msg.turnActive,
    turnCancelling: msg.turnCancelling,
    sendMessage: msg.sendMessage,
    steps: msg.steps,
    taskProgress: msg.taskProgress,
    globalActivity: dispatcher.globalActivity,
    proactiveResults: msg.proactiveResults,
    handleSkillInvoke: msg.handleSkillInvoke,
    cancelTurn: msg.cancelTurn,

    // 交互
    activeInteraction: interaction.activeInteraction,
    currentSessionQuestionInteraction: interaction.currentSessionQuestionInteraction,
    interactionSubmitting: interaction.interactionSubmitting,
    sendQuestionAnswer: interaction.sendQuestionAnswer,
    sendCurrentSessionQuestionAnswer: interaction.sendCurrentSessionQuestionAnswer,
    submitQuestionResponse: interaction.submitQuestionResponse,
    sendConfirmationResponse: interaction.sendConfirmationResponse,
    handleInteractionTimeout: interaction.handleInteractionTimeout,
    resolveInteractionFromNotification: interaction.resolveInteractionFromNotification,

    // 推荐卡片预填
    pendingPrefill: msg.pendingPrefill,
    prefillInput: msg.prefillInput,
    clearPendingPrefill: msg.clearPendingPrefill,

    // 重连
    reconnect: ws.reconnect,
  };
}
