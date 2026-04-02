'use client';

import { useEffect, useLayoutEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useSession, useWebSocket } from '@/contexts/ws';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { getAgentId } from '@/lib/chatTypes';
import { useI18n } from '@/contexts/I18nContext';

// ── 类型 ──

interface SessionInfo {
  session_id: string;
  created_at: number;
  last_active: number;
  status: string;
  meta: string;
}

function parseTitle(meta: string, fallback: string): string {
  try {
    const m = JSON.parse(meta);
    return m.title || m.name || fallback;
  } catch {
    return fallback;
  }
}

function formatTimestamp(ts: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString('zh-CN');
}

// ── 页面组件 ──

export default function SessionDetailPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const { t } = useI18n();

  const { switchSession, sessions, currentSessionId } = useSession();
  const { wsConnected } = useWebSocket();
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [bindingSession, setBindingSession] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // URL param 驱动 session 切换
  useLayoutEffect(() => {
    let cancelled = false;
    if (sessionId) {
      setBindingSession(true);
      Promise.resolve(switchSession(sessionId)).finally(() => {
        if (!cancelled) {
          setBindingSession(false);
        }
      });
    }
    return () => {
      cancelled = true;
    };
  }, [sessionId, switchSession]);

  // 加载 session 元数据
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await authFetch(`${API_BASE}/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error('Session not found');
        const data = await res.json();
        setSessionInfo(data.session || data);
      } catch (e: any) {
        setError(e.message || t('chat.loadSessionFailed'));
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, t]);

  // 从 session 列表获取 agentId
  const activeSession = sessions.find(s => s.session_id === sessionId);
  const agentId = activeSession ? (getAgentId(activeSession.meta) || 'default') : 'default';

  if (loading || bindingSession) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-full">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center h-full gap-4">
          <p className="text-destructive">{error}</p>
          <Link href="/sessions" className="text-primary hover:underline">{t('chat.backToSessions')}</Link>
        </div>
      </DashboardLayout>
    );
  }

  const title = sessionInfo ? parseTitle(sessionInfo.meta, t('chat.untitledSession')) : t('chat.sessionDetail');

  return (
    <DashboardLayout>
      <div className="flex flex-col h-full">
        <span data-testid="current-session-id" className="sr-only">{currentSessionId || ''}</span>
        {/* ── Header ── */}
        <div className="sticky top-0 z-10 bg-background border-b px-4 py-3 flex items-center gap-3">
          <Link href="/sessions" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold truncate">{title}</h1>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-mono">{sessionId.slice(0, 8)}...</span>
              {sessionInfo?.created_at && (
                <span>{t('chat.createdAt', { time: formatTimestamp(sessionInfo.created_at) })}</span>
              )}
              <span className={`inline-flex items-center gap-1 ${wsConnected ? 'text-green-500' : 'text-red-400'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-400'}`} />
                {wsConnected ? t('chat.connected') : t('chat.disconnected')}
              </span>
            </div>
          </div>
        </div>

        {/* ── Chat Area (复用 ChatPanel) ── */}
        <div className="flex-1 overflow-hidden">
          <ChatPanel defaultAgentId={agentId} hideAgentSelector lockAgent />
        </div>
      </div>
    </DashboardLayout>
  );
}
