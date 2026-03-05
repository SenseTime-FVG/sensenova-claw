'use client';

import { useWebSocketContext } from '@/contexts/WebSocketContext';

export function useWebSocket() {
  return useWebSocketContext();
}
