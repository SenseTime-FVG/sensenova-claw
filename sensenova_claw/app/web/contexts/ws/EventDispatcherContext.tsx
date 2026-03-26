'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useWebSocket } from './WebSocketContext';
import { parseWsEvent, type WsInboundEvent } from '@/lib/wsEvents';

// ── 全局 agent 活动状态 ──

export interface GlobalAgentActivity {
  anyWorking: boolean;
  workingSessionIds: Set<string>;
  lastToolName: string;
}

// ── 订阅回调类型 ──

type EventHandler = (event: WsInboundEvent) => void;

// ── Context 类型 ──

export interface EventDispatcherContextValue {
  /** 订阅当前 session 的事件（已过滤） */
  subscribeCurrentSession: (handler: EventHandler) => () => void;
  /** 订阅全局事件（不受 session 过滤） */
  subscribeGlobal: (handler: EventHandler) => () => void;
  /** 订阅前端主动创建的 session_created 事件 */
  subscribeFrontendCreate: (handler: EventHandler) => () => void;
  /** 全局 agent 活动状态 */
  globalActivity: GlobalAgentActivity;
  /** 设置当前活跃 sessionId（由 SessionContext 调用） */
  setCurrentSessionId: (sid: string | null) => void;
  /** 标记即将发起前端 session 创建（由 SessionContext/MessageContext 调用） */
  markFrontendCreate: () => void;
}

const EventDispatcherCtx = createContext<EventDispatcherContextValue | null>(null);

// ── 事件分类 ──

/** 全局事件：始终分发，不受 session 过滤 */
const GLOBAL_EVENT_TYPES = new Set([
  'title_updated', 'session_list_changed', 'session_deleted',
  'notification', 'proactive_result', 'todolist_updated',
]);

/** 当前 session 事件：仅在 session_id 匹配时分发 */
const CURRENT_SESSION_EVENT_TYPES = new Set([
  'agent_thinking', 'llm_delta', 'llm_result',
  'tool_execution', 'tool_result',
  'tool_confirmation_requested', 'tool_confirmation_resolved',
  'user_question_asked', 'user_question_answered_event',
  'session_loaded',
  'turn_completed', 'turn_cancelled', 'error',
]);

/** 交互事件：始终分发到 currentSession（绕过 session 过滤），同时分发到 global
 *  原因：重构前这些事件被标记为 isGlobalInteractionEvent，不受 session 过滤。
 *  场景：用户确认工具执行、回答 agent 问题，可能跨 session 触发。 */
const INTERACTION_EVENT_TYPES = new Set([
  'tool_confirmation_requested', 'tool_confirmation_resolved',
  'user_question_asked', 'user_question_answered_event',
]);

// ── Provider ──

export function EventDispatcherProvider({ children }: { children: React.ReactNode }) {
  const { subscribe } = useWebSocket();

  // 订阅者集合
  const currentSessionSubs = useRef<Set<EventHandler>>(new Set());
  const globalSubs = useRef<Set<EventHandler>>(new Set());
  const frontendCreateSubs = useRef<Set<EventHandler>>(new Set());

  // 当前 session（ref 保证回调内读到最新值）
  const currentSessionIdRef = useRef<string | null>(null);
  // 前端主动创建标记
  const pendingFrontendCreateRef = useRef(false);

  // 全局活动追踪
  const [globalWorkingSessions, setGlobalWorkingSessions] = useState<Set<string>>(new Set());
  const [globalLastToolName, setGlobalLastToolName] = useState('');

  // ── 订阅 API ──

  const subscribeCurrentSession = useCallback((handler: EventHandler) => {
    currentSessionSubs.current.add(handler);
    return () => { currentSessionSubs.current.delete(handler); };
  }, []);

  const subscribeGlobal = useCallback((handler: EventHandler) => {
    globalSubs.current.add(handler);
    return () => { globalSubs.current.delete(handler); };
  }, []);

  const subscribeFrontendCreate = useCallback((handler: EventHandler) => {
    frontendCreateSubs.current.add(handler);
    return () => { frontendCreateSubs.current.delete(handler); };
  }, []);

  const setCurrentSessionId = useCallback((sid: string | null) => {
    currentSessionIdRef.current = sid;
  }, []);

  const markFrontendCreate = useCallback(() => {
    pendingFrontendCreateRef.current = true;
  }, []);

  // ── 核心：监听 raw WS 并分发 ──

  useEffect(() => {
    return subscribe((raw) => {
      const event = parseWsEvent(raw);
      if (!event) return;

      const eventSessionId = event.session_id ?? null;
      const eventType = event.type;
      const currentSid = currentSessionIdRef.current;

      // 1. 全局活动追踪（在分发之前，对所有 session 生效）
      if (eventSessionId) {
        if (eventType === 'agent_thinking') {
          setGlobalWorkingSessions(prev => prev.has(eventSessionId) ? prev : new Set(prev).add(eventSessionId));
        } else if (eventType === 'turn_completed' || eventType === 'turn_cancelled' || eventType === 'error') {
          setGlobalWorkingSessions(prev => { if (!prev.has(eventSessionId)) return prev; const next = new Set(prev); next.delete(eventSessionId); return next; });
        } else if (eventType === 'tool_execution') {
          setGlobalLastToolName((event.payload as { tool_name?: string }).tool_name || '');
        }
      }

      // 2. session_created 特殊处理
      if (eventType === 'session_created') {
        if (pendingFrontendCreateRef.current) {
          pendingFrontendCreateRef.current = false;
          frontendCreateSubs.current.forEach((fn) => { try { fn(event); } catch (e) { console.error('[EventDispatcher] handler error:', e); } });
        }
        // session_created 也作为全局事件分发（用于刷新列表）
        globalSubs.current.forEach((fn) => { try { fn(event); } catch (e) { console.error('[EventDispatcher] handler error:', e); } });
        return;
      }

      // 3. 全局事件
      if (GLOBAL_EVENT_TYPES.has(eventType)) {
        globalSubs.current.forEach((fn) => { try { fn(event); } catch (e) { console.error('[EventDispatcher] handler error:', e); } });
      }

      // 4. 当前 session 事件
      if (CURRENT_SESSION_EVENT_TYPES.has(eventType)) {
        const isCurrentSession = !eventSessionId || eventSessionId === currentSid;
        const isInteraction = INTERACTION_EVENT_TYPES.has(eventType);
        // 普通事件：严格 session 匹配；交互事件：始终分发到 currentSession
        if (isCurrentSession || isInteraction) {
          currentSessionSubs.current.forEach((fn) => { try { fn(event); } catch (e) { console.error('[EventDispatcher] handler error:', e); } });
        }
        // turn_completed / error：非当前 session 时分发到 global（跨会话通知）
        if ((eventType === 'turn_completed' || eventType === 'error') && !isCurrentSession) {
          globalSubs.current.forEach((fn) => { try { fn(event); } catch (e) { console.error('[EventDispatcher] handler error:', e); } });
        }
      }
    });
  }, [subscribe]);

  // ── value ──

  const globalActivity = useMemo<GlobalAgentActivity>(() => ({
    anyWorking: globalWorkingSessions.size > 0,
    workingSessionIds: globalWorkingSessions,
    lastToolName: globalLastToolName,
  }), [globalWorkingSessions, globalLastToolName]);

  const value = useMemo<EventDispatcherContextValue>(() => ({
    subscribeCurrentSession,
    subscribeGlobal,
    subscribeFrontendCreate,
    globalActivity,
    setCurrentSessionId,
    markFrontendCreate,
  }), [subscribeCurrentSession, subscribeGlobal, subscribeFrontendCreate,
       globalActivity, setCurrentSessionId, markFrontendCreate]);

  return <EventDispatcherCtx.Provider value={value}>{children}</EventDispatcherCtx.Provider>;
}

// ── Hooks ──

export function useEventDispatcher(): EventDispatcherContextValue {
  const ctx = useContext(EventDispatcherCtx);
  if (!ctx) throw new Error('useEventDispatcher must be used inside EventDispatcherProvider');
  return ctx;
}
