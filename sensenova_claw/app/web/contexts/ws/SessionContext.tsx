'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useWebSocket } from './WebSocketContext';
import { useEventDispatcher } from './EventDispatcherContext';
import {
  type SessionItem,
  type TaskGroup,
  getAgentId,
  groupSessionsToTasks,
  makeId,
} from '@/lib/chatTypes';
import type { WsInboundEvent } from '@/lib/wsEvents';

// ── 类型 ──

export interface SessionContextValue {
  currentSessionId: string | null;
  sessions: SessionItem[];
  taskGroups: TaskGroup[];
  loadingSessions: boolean;

  switchSession: (sessionId: string) => Promise<void>;
  createSession: (agentId: string, taskId?: string) => void;
  startNewChat: () => void;
  deleteSession: (sessionId: string) => Promise<void>;
  resetIfNeeded: () => void;
  cleanupEmptySession: () => void;
  refreshTaskGroups: () => void;
  getCurrentSessionAgentId: () => string | null;

  /** 供 MessageContext 调用：session 创建后绑定 WS */
  bindSessionToCurrentSocket: (sid: string | null) => void;
  /** 供 MessageContext 读取当前 sessionId ref */
  sessionIdRef: React.RefObject<string | null>;
  /** 空会话 ref（供 MessageContext 在 session_created 时清除） */
  emptySessionIdRef: React.MutableRefObject<string | null>;
}

const SessionCtx = createContext<SessionContextValue | null>(null);

// ── Provider ──

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { wsSend } = useWebSocket();
  const { subscribeGlobal, subscribeFrontendCreate, setCurrentSessionId, markFrontendCreate } = useEventDispatcher();

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const switchedSessionRef = useRef(false);
  const emptySessionIdRef = useRef<string | null>(null);
  // 关联 create_session 请求与 session_created 响应，防止快速切换时乱序覆盖
  const pendingCreateIdRef = useRef<string | null>(null);

  // 同步 ref + 通知 EventDispatcher
  useEffect(() => {
    sessionIdRef.current = sessionId;
    setCurrentSessionId(sessionId);
  }, [sessionId, setCurrentSessionId]);

  // ── Session 列表加载 ──

  const loadSessionList = useCallback(async () => {
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
  }, []);

  // ── WS 绑定 ──

  const bindSessionToCurrentSocket = useCallback((sid: string | null) => {
    if (!sid) return;
    wsSend({ type: 'load_session', payload: { session_id: sid }, timestamp: Date.now() / 1000 });
  }, [wsSend]);

  // ── 历史重建 ──

  const reloadSessionHistory = useCallback(async (sid: string) => {
    setSessionId(sid);
    bindSessionToCurrentSocket(sid);
  }, [bindSessionToCurrentSocket]);

  // ── 空会话清理 ──

  const doCleanupEmptySession = useCallback((excludeSid?: string) => {
    const emptyId = emptySessionIdRef.current;
    if (emptyId && emptyId !== excludeSid) {
      emptySessionIdRef.current = null;
      setSessions(prev => prev.filter(s => s.session_id !== emptyId));
      authFetch(`${API_BASE}/api/sessions/${emptyId}`, { method: 'DELETE' }).catch(() => {});
    }
  }, []);

  // ── 对外接口 ──

  const getCurrentSessionAgentId = useCallback(() => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return null;
    const activeSession = sessions.find((item) => item.session_id === activeSessionId);
    if (!activeSession) return null;
    return getAgentId(activeSession.meta);
  }, [sessions]);

  const switchSession = useCallback(async (sid: string) => {
    switchedSessionRef.current = true;
    doCleanupEmptySession(sid);
    await reloadSessionHistory(sid);
  }, [reloadSessionHistory, doCleanupEmptySession]);

  const createSession = useCallback((agentId: string, taskId?: string) => {
    const meta: Record<string, string> = { title: '新对话' };
    if (taskId) meta.task_id = taskId;
    const requestId = makeId();
    pendingCreateIdRef.current = requestId;
    markFrontendCreate();
    wsSend({
      type: 'create_session',
      payload: { agent_id: agentId || 'default', meta, request_id: requestId },
      timestamp: Date.now() / 1000,
    });
  }, [wsSend, markFrontendCreate]);

  const startNewChat = useCallback(() => {
    doCleanupEmptySession();
    setSessionId(null);
    sessionIdRef.current = null;
  }, [doCleanupEmptySession]);

  const deleteSession = useCallback(async (sid: string) => {
    try {
      const res = await authFetch(`${API_BASE}/api/sessions/${sid}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('delete failed');
    } catch {
      // 忽略网络错误
    }
    setSessions(prev => prev.filter(s => s.session_id !== sid));
    if (sessionIdRef.current === sid) {
      startNewChat();
    }
  }, [startNewChat]);

  const resetIfNeeded = useCallback(() => {
    if (switchedSessionRef.current) {
      switchedSessionRef.current = false;
      return;
    }
    startNewChat();
  }, [startNewChat]);

  // ── 监听全局事件 ──

  useEffect(() => {
    return subscribeGlobal((event: WsInboundEvent) => {
      switch (event.type) {
        case 'session_created':
          // 后台 agent 创建的 session，仅刷新列表
          loadSessionList();
          break;
        case 'title_updated': {
          const sid = event.session_id;
          const title = event.payload.title || '';
          setSessions(prev => prev.map(s => {
            if (s.session_id !== sid) return s;
            try { const m = JSON.parse(s.meta); m.title = title; return { ...s, meta: JSON.stringify(m) }; } catch { return s; }
          }));
          break;
        }
        case 'session_list_changed':
          loadSessionList();
          break;
        case 'session_deleted': {
          const deletedSid = event.payload.session_id || '';
          if (deletedSid) {
            setSessions(prev => prev.filter(s => s.session_id !== deletedSid));
            if (sessionIdRef.current === deletedSid) {
              startNewChat();
            }
          }
          break;
        }
      }
    });
  }, [subscribeGlobal, loadSessionList, startNewChat]);

  // ── 监听前端主动创建的 session ──

  useEffect(() => {
    return subscribeFrontendCreate((event: WsInboundEvent) => {
      if (event.type === 'session_created') {
        const newSid = event.session_id;
        if (!newSid) return;
        const requestId = typeof event.payload.request_id === 'string' ? event.payload.request_id : null;
        // 归属校验：如果存在 pendingCreateId 且响应中携带 request_id，
        // 只接受与最近一次创建请求匹配的 session_created
        if (pendingCreateIdRef.current && requestId && requestId !== pendingCreateIdRef.current) {
          authFetch(`${API_BASE}/api/sessions/${newSid}`, { method: 'DELETE' }).catch(() => {});
          return;
        }
        pendingCreateIdRef.current = null;
        setSessionId(newSid);
        loadSessionList();
      }
    });
  }, [subscribeFrontendCreate, loadSessionList]);

  // 连接成功后加载列表
  const { wsConnected } = useWebSocket();
  useEffect(() => {
    if (wsConnected) loadSessionList();
  }, [wsConnected, loadSessionList]);

  // ── value ──

  const taskGroups = useMemo(() => groupSessionsToTasks(sessions), [sessions]);

  const value: SessionContextValue = {
    currentSessionId: sessionId,
    sessions,
    taskGroups,
    loadingSessions,
    switchSession,
    createSession,
    startNewChat,
    deleteSession,
    resetIfNeeded,
    cleanupEmptySession: doCleanupEmptySession,
    refreshTaskGroups: loadSessionList,
    getCurrentSessionAgentId,
    bindSessionToCurrentSocket,
    sessionIdRef,
    emptySessionIdRef,
  };

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

// ── Hooks ──

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error('useSession must be used inside SessionProvider');
  return ctx;
}
