'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

// ── 类型 ──

export type WsEventData = Record<string, unknown>;
export type WsSubscriber = (data: WsEventData) => void;

export interface WebSocketContextValue {
  /** WebSocket 是否已连接 */
  wsConnected: boolean;
  /** 发送 JSON 消息到后端 */
  wsSend: (msg: Record<string, unknown>) => void;
  /** 订阅所有 WS 消息，返回取消订阅函数 */
  subscribe: (fn: WsSubscriber) => () => void;
  /** 手动触发 WebSocket 重连 */
  reconnect: () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

// ── 常量 ──

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || '/ws';
const WS_RECONNECT_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_ATTEMPTS = 50;
const COOKIE_NAME = 'sensenova_claw_token';

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// ── Provider ──

export function WebSocketProvider({
  children,
  enabled = true,
}: {
  children: React.ReactNode;
  /** 是否激活连接（未认证时传 false） */
  enabled?: boolean;
}) {
  const [wsConnected, setWsConnected] = useState(false);
  const [connectionNonce, setConnectionNonce] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const subscribersRef = useRef<Set<WsSubscriber>>(new Set());

  // 发送
  const wsSend = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  // 订阅
  const subscribe = useCallback((fn: WsSubscriber) => {
    subscribersRef.current.add(fn);
    return () => { subscribersRef.current.delete(fn); };
  }, []);

  // 连接管理
  useEffect(() => {
    if (!enabled) {
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
      const token = getCookie(COOKIE_NAME);
      const wsUrl = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled || wsRef.current !== ws) return;
        setWsConnected(true);
        reconnectAttemptsRef.current = 0;
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
        try {
          const data = JSON.parse(event.data) as WsEventData;
          subscribersRef.current.forEach((fn) => fn(data));
        } catch { /* 忽略非法 JSON */ }
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
  }, [enabled, connectionNonce]);

  // 手动重连
  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    shouldReconnectRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
    setConnectionNonce((prev) => prev + 1);
  }, []);

  const value: WebSocketContextValue = { wsConnected, wsSend, subscribe, reconnect };

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

// ── Hooks ──

export function useWebSocket(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocket must be used inside WebSocketProvider');
  return ctx;
}

/** 安全版本：在 Provider 外返回 null */
export function useOptionalWebSocket(): WebSocketContextValue | null {
  return useContext(WebSocketContext);
}
