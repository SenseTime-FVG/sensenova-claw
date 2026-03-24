'use client';

import { useEffect, useState } from 'react';
import { useUIContext } from '@/contexts/UIContext';
import { useSessionContext } from '@/contexts/SessionContext';
import { useWebSocketContext } from '@/contexts/WebSocketContext';

interface Session {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

export function Sidebar() {
  const { sidebarView } = useUIContext();
  const { sessionId, switchSession, startNewChat } = useSessionContext();
  const { lastMessage } = useWebSocketContext();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasNewChat, setHasNewChat] = useState(false);

  useEffect(() => {
    if (sidebarView === 'history') {
      loadSessions();
    }
  }, [sidebarView]);

  // 监听标题更新事件
  useEffect(() => {
    if (lastMessage?.type === 'title_updated') {
      const updatedSessionId = lastMessage.session_id;
      const newTitle = lastMessage.payload.title;

      setSessions((prev) =>
        prev.map((session) => {
          if (session.session_id === updatedSessionId) {
            const meta = JSON.parse(session.meta);
            meta.title = newTitle;
            return { ...session, meta: JSON.stringify(meta) };
          }
          return session;
        })
      );
    }
  }, [lastMessage]);

  // 监听会话创建事件
  useEffect(() => {
    if (lastMessage?.type === 'session_created') {
      setHasNewChat(false);
      loadSessions();
    }
  }, [lastMessage]);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return '昨天';
    } else if (days < 7) {
      return `${days}天前`;
    } else {
      return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
    }
  };

  const getTitle = (metaStr: string) => {
    try {
      const meta = JSON.parse(metaStr);
      return meta.title || '未命名会话';
    } catch {
      return '未命名会话';
    }
  };

  const handleNewChat = () => {
    if (!hasNewChat) {
      setHasNewChat(true);
    }
    startNewChat();
  };

  if (sidebarView !== 'history') {
    return (
      <aside className="sidebar">
        <h3>文件浏览器</h3>
        <p>v0.1 暂提供占位文件树。</p>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h3>会话历史</h3>
        <div className="sidebar-actions">
          <button className="refresh-button" onClick={handleNewChat}>
            新建
          </button>
          <button className="refresh-button" onClick={loadSessions} disabled={loading}>
            {loading ? '加载中...' : '刷新'}
          </button>
        </div>
      </div>
      <div className="session-list">
        {hasNewChat && (
          <div
            className={`session-item ${!sessionId ? 'active' : ''}`}
            onClick={handleNewChat}
          >
            <div className="session-title">新对话</div>
            <div className="session-time">刚刚</div>
          </div>
        )}
        {sessions.length === 0 && !loading && !hasNewChat && (
          <div className="empty-state">暂无会话记录</div>
        )}
        {sessions.map((session) => (
          <div
            key={session.session_id}
            className={`session-item ${session.session_id === sessionId ? 'active' : ''}`}
            onClick={() => switchSession(session.session_id)}
          >
            <div className="session-title">{getTitle(session.meta)}</div>
            <div className="session-time">{formatTime(session.last_active)}</div>
          </div>
        ))}
      </div>
    </aside>
  );
}
