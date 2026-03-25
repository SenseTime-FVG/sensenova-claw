'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Bell,
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
  Lightbulb,
  Info,
  Check,
  X,
  Trash2,
} from 'lucide-react';
import { useNotification } from '@/hooks/useNotification';
import { useChatSession } from '@/contexts/ChatSessionContext';
import type { NotificationCard, NotificationCardKind } from '@/components/notification/NotificationProvider';

// ── 卡片图标 & 配色 ──

const kindConfig: Record<NotificationCardKind, {
  icon: typeof Bell;
  color: string;
  bg: string;
  border: string;
}> = {
  task_completed: {
    icon: CheckCircle2,
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-900/30',
    border: 'border-emerald-200 dark:border-emerald-800',
  },
  user_question: {
    icon: HelpCircle,
    color: 'text-sky-600 dark:text-sky-400',
    bg: 'bg-sky-50 dark:bg-sky-900/30',
    border: 'border-sky-200 dark:border-sky-800',
  },
  tool_confirmation: {
    icon: ShieldAlert,
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/30',
    border: 'border-amber-200 dark:border-amber-800',
  },
  proactive: {
    icon: Lightbulb,
    color: 'text-violet-600 dark:text-violet-400',
    bg: 'bg-violet-50 dark:bg-violet-900/30',
    border: 'border-violet-200 dark:border-violet-800',
  },
  general: {
    icon: Info,
    color: 'text-neutral-600 dark:text-neutral-400',
    bg: 'bg-neutral-50 dark:bg-neutral-900/30',
    border: 'border-neutral-200 dark:border-neutral-700',
  },
};

function timeAgo(ms: number): string {
  const diff = Date.now() - ms;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return '刚刚';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  return `${Math.floor(hour / 24)} 天前`;
}

function NotificationCardItem({
  card,
  onResolve,
  onDismiss,
  onNavigate,
}: {
  card: NotificationCard;
  onResolve: (id: string, action?: string) => void;
  onDismiss: (id: string) => void;
  onNavigate: (sessionId: string) => void;
}) {
  const config = kindConfig[card.kind] || kindConfig.general;
  const Icon = config.icon;

  return (
    <div
      className={`group relative rounded-xl border px-3 py-2.5 transition-all ${
        card.resolved
          ? 'border-neutral-100 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-900/50 opacity-60'
          : card.read
            ? `${config.border} ${config.bg}/50`
            : `${config.border} ${config.bg}`
      }`}
    >
      <div className="flex items-start gap-2.5">
        {/* 图标 */}
        <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${config.bg} ${config.color}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>

        {/* 内容 */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1">
            <span className="text-xs font-semibold text-foreground leading-tight">{card.title}</span>
            {!card.read && !card.resolved && (
              <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-500" />
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground leading-relaxed line-clamp-2">{card.body}</p>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">{timeAgo(card.createdAtMs)}</span>
            {card.source && (
              <span className="text-[10px] text-muted-foreground">· {card.source}</span>
            )}
          </div>

          {/* 操作按钮 */}
          {!card.resolved && card.actions && card.actions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {card.actions.map((action) => (
                <button
                  key={action.value}
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onResolve(card.id, action.value); }}
                  className={`rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors ${
                    action.value === 'approve' || action.value === 'accept'
                      ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/50'
                      : action.value === 'deny' || action.value === 'reject'
                        ? 'border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/50'
                        : 'border-neutral-200 dark:border-neutral-700 bg-background text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

          {/* 已处理状态 */}
          {card.resolved && card.resolvedAction && (
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <Check className="h-3 w-3" />
              <span>
                {card.resolvedAction === 'approve' ? '已批准' :
                 card.resolvedAction === 'deny' ? '已拒绝' :
                 `已处理: ${card.resolvedAction}`}
              </span>
            </div>
          )}

          {/* 跳转到会话 */}
          {card.sessionId && !card.resolved && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onNavigate(card.sessionId!); }}
              className="mt-1.5 text-[10px] font-medium text-violet-600 hover:text-violet-700 transition-colors"
            >
              查看会话 →
            </button>
          )}
        </div>

        {/* 关闭按钮 */}
        <button
          type="button"
          onClick={() => onDismiss(card.id)}
          className="shrink-0 rounded-md p-0.5 text-muted-foreground/50 opacity-0 transition-all hover:bg-muted hover:text-muted-foreground group-hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

export function NotificationDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const {
    cards,
    unreadCount,
    markAllRead,
    resolveCard,
    dismissCard,
    clearAllCards,
    setOnActionToastAction,
  } = useNotification();
  const { switchSession, wsSend } = useChatSession();

  // 点击外部关闭
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const handleOpen = () => {
    setOpen(!open);
    if (!open) markAllRead();
  };

  const handleNavigate = async (sessionId: string) => {
    setOpen(false);
    await switchSession(sessionId);
    router.push('/');
  };

  // 处理卡片操作：根据类型发送 WebSocket 响应
  const handleResolve = useCallback((cardId: string, action?: string) => {
    const card = cards.find(c => c.id === cardId);
    if (!card || card.resolved) return;

    if (card.kind === 'tool_confirmation' && card.interactionId && card.sessionId) {
      // 发送工具确认响应
      wsSend({
        type: 'tool_confirmation_response',
        session_id: card.sessionId,
        payload: {
          tool_call_id: card.interactionId,
          approved: action === 'approve',
        },
        timestamp: Date.now() / 1000,
      });
    } else if (card.kind === 'user_question' && card.interactionId && card.sessionId) {
      // 发送问题回答
      wsSend({
        type: 'user_question_answered',
        session_id: card.sessionId,
        payload: {
          question_id: card.interactionId,
          answer: action || '',
          cancelled: false,
        },
        timestamp: Date.now() / 1000,
      });
    } else if (action === 'view_session' && card.sessionId) {
      // 导航到对应会话
      handleNavigate(card.sessionId);
    }

    resolveCard(cardId, action);
  }, [cards, wsSend, resolveCard]);

  // 注册操作弹窗的回调，使弹窗按钮也能发送 WebSocket 响应
  useEffect(() => {
    setOnActionToastAction((cardId: string, actionValue: string) => {
      handleResolve(cardId, actionValue);
    });
    return () => setOnActionToastAction(null);
  }, [handleResolve, setOnActionToastAction]);

  // 按类型分组
  const pendingCards = cards.filter(c => !c.resolved);
  const resolvedCards = cards.filter(c => c.resolved);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleOpen}
        className="relative p-1.5 rounded-lg hover:bg-muted transition-colors"
        title={`${unreadCount} 条未读通知`}
      >
        <Bell className="w-5 h-5 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center px-0.5">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 rounded-2xl border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] shadow-[0_20px_60px_rgba(15,23,42,0.12)] dark:shadow-[0_20px_60px_rgba(0,0,0,0.3)] backdrop-blur-2xl z-[100]">
          {/* 头部 */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-foreground">通知中心</span>
              {pendingCards.length > 0 && (
                <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-700 dark:text-violet-400">
                  {pendingCards.length} 待处理
                </span>
              )}
            </div>
            {cards.length > 0 && (
              <button
                type="button"
                onClick={clearAllCards}
                className="flex items-center gap-1 text-[11px] text-neutral-400 transition-colors hover:text-neutral-600"
              >
                <Trash2 className="h-3 w-3" />
                清空
              </button>
            )}
          </div>

          {/* 卡片列表 */}
          <div className="max-h-[420px] overflow-y-auto p-3 space-y-2 hide-scrollbar">
            {cards.length === 0 ? (
              <div className="flex h-24 items-center justify-center">
                <span className="text-xs text-muted-foreground">暂无通知</span>
              </div>
            ) : (
              <>
                {pendingCards.map(card => (
                  <NotificationCardItem
                    key={card.id}
                    card={card}
                    onResolve={handleResolve}
                    onDismiss={dismissCard}
                    onNavigate={handleNavigate}
                  />
                ))}
                {resolvedCards.length > 0 && pendingCards.length > 0 && (
                  <div className="my-2 border-t border-border" />
                )}
                {resolvedCards.map(card => (
                  <NotificationCardItem
                    key={card.id}
                    card={card}
                    onResolve={handleResolve}
                    onDismiss={dismissCard}
                    onNavigate={handleNavigate}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
