'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { WsMessage } from '@/types/websocket';

interface WebSocketContextValue {
  isConnected: boolean;
  lastMessage: WsMessage | null;
  send: (message: Record<string, unknown>) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);
    ws.onmessage = (event) => {
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {
        // 忽略非法消息
      }
    };

    return () => {
      ws.close();
    };
  }, []);

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
