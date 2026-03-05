'use client';

import { useWebSocket } from '@/hooks/useWebSocket';

export function StatusBar() {
  const { isConnected } = useWebSocket();
  return (
    <footer className="statusbar">
      <span>{isConnected ? 'WebSocket 已连接' : 'WebSocket 未连接'}</span>
    </footer>
  );
}
