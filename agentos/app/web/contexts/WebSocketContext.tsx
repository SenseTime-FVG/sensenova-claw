'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { WsMessage } from '@/types/websocket';
import { useAuth } from './AuthContext';

interface WebSocketContextValue {
  isConnected: boolean;
  lastMessage: WsMessage | null;
  send: (message: Record<string, unknown>) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
const RECONNECT_INTERVAL = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;
const COOKIE_NAME = 'agentos_token';

/** 从 document.cookie 读取指定 cookie */
function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    shouldReconnectRef.current = true;

    const connect = () => {
      if (wsRef.current) {
        wsRef.current.close();
      }

      try {
        // 通过 query param 传递 token（WebSocket 不自动带跨端口 cookie）
        const token = getCookie(COOKIE_NAME);
        const wsUrl = token
          ? `${WS_URL}?token=${encodeURIComponent(token)}`
          : WS_URL;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('WebSocket connected');
          setIsConnected(true);
          reconnectAttemptsRef.current = 0;
        };

        ws.onclose = () => {
          console.log('WebSocket disconnected');
          setIsConnected(false);

          if (shouldReconnectRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttemptsRef.current += 1;
            console.log(`Attempting to reconnect (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})...`);
            reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_INTERVAL);
          } else if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            console.error('Max reconnection attempts reached. Please check if the backend is running.');
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setIsConnected(false);
        };

        ws.onmessage = (event) => {
          try {
            setLastMessage(JSON.parse(event.data));
          } catch {
            // 忽略非法消息
          }
        };
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        setIsConnected(false);
      }
    };

    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isAuthenticated]);

  const value = useMemo<WebSocketContextValue>(
    () => ({
      isConnected,
      lastMessage,
      send: (message) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify(message));
        }
      },
    }),
    [isConnected, lastMessage],
  );

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

export function useWebSocketContext(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error('useWebSocketContext must be used inside WebSocketProvider');
  }
  return ctx;
}
