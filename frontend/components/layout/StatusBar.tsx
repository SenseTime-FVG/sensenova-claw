'use client';

import { useWebSocket } from '@/hooks/useWebSocket';
import { useSession } from '@/hooks/useSession';

export function StatusBar() {
  const { isConnected } = useWebSocket();
  const { sessionId, isTyping } = useSession();

  return (
    <footer className="statusbar">
      <div className="statusbar-left">
        <span className={isConnected ? 'status-connected' : 'status-disconnected'}>
          {isConnected ? '● 已连接' : '○ 未连接'}
        </span>
        {isTyping && (
          <span className="typing-status">
            ⚡ Agent 思考中...
          </span>
        )}
      </div>
      <div className="statusbar-right">
        {sessionId && (
          <span className="session-info">
            会话: {sessionId}
          </span>
        )}
      </div>
    </footer>
  );
}
